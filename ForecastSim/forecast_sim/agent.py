# Copyright (c) 2017, The Fraunhofer Center for Sustainable Energy
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in
#    the documentation and/or other materials provided with the
#    distribution.
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# This material was prepared as an account of work sponsored by an agency
# of the United States Government.  Neither the United States Government
# nor any agency thereof, nor Fraunhofer, nor any of their employees,
# makes any warranty, express or implied, or assumes any legal liability
# or responsibility for the accuracy, completeness, or usefulness of any
# information, apparatus, product, or process disclosed, or represents
# that its use would not infringe privately owned rights.
#
# Reference herein to any specific commercial product, process, or service
# by trade name, trademark, manufacturer, or otherwise does not necessarily
# constitute or imply its endorsement, recommendation, or favoring by the
# United States Government or any agency thereof, or Fraunhofer.  The
# views and opinions of authors expressed herein do not necessarily state
# or reflect those of the United States Government or any agency thereof.
from __future__ import absolute_import


import logging
import sys
import requests
import pprint,pickle
from datetime import timedelta
import pytz
import datetime
import os
from volttron.platform.messaging.health import STATUS_GOOD
from volttron.platform.vip.agent import Agent, PubSub, Core, RPC
from volttron.platform.agent import utils
from volttron.platform.agent.utils import jsonapi
from volttron.platform.messaging import topics
from volttron.platform.messaging import headers as headers_mod
import xml.etree.ElementTree as ET
from gs_identities import (SSA_SCHEDULE_RESOLUTION, SSA_SCHEDULE_DURATION, SSA_PTS_PER_SCHEDULE, CPR_QUERY_INTERVAL,
                           USE_VOLTTRON, SIM_START_DAY, SIM_START_HR, SIM_SCENARIO, PV_FORECAST_FILE,
                           PV_FORECAST_FILE_TIME_RESOLUTION_MIN, SIM_HRS_PER_HR)
from gs_utilities import get_schedule, ForecastObject
import csv
import pandas


_PROD = [0,0,0,0,0,0,68,294,499,666,751,791,787,685,540,
        717,699,600,580,366,112,0,0,0]
PROD = [ p* 1500000.0 / max(_PROD) for p in _PROD ]

utils.setup_logging()
_log = logging.getLogger(__name__)

__version__="0.1"

# constants
MINUTES_PER_HR = 60
MINUTES_PER_DAY = 24 * MINUTES_PER_HR
MINUTES_PER_YR = 365 * MINUTES_PER_DAY


class CPRAgent(Agent):
    """
    Retrieves solar forecast data from a csv file.
    csv file is a list of one year's worth of irradiance values (W/m2), with time step defined by csv_time_resolution_min
    Reindexes the file to make user-specified start-date and start time === the time when the GS Executive started
    Resamples data file to match desired forecast resolution


    periodically publishes forecasts.
    - Forecast duration is defined by SSA_SCHEDULE_DURATION
    - Forecast time step is defined by SSA_SCHEDULE_RESOLUTION
    - Publication interval is defined by CPR_QUERY_INTERVAL
    - Published in units of "Pct" (Irradiance / 1000)

    """

    ##############################################################################
    def __init__(self, config_path, **kwargs):
        super(CPRAgent, self).__init__(**kwargs)
        self.volttron_root = os.getcwd()
        self.volttron_root = self.volttron_root+"/../../../../"
        self.default_config = {
            "topic": "devices/cpr/forecast/all",
            "DEFAULT_HEARTBEAT_PERIOD": 5,
            "DEFAULT_MESSAGE": 'FORECAST_SIM_Message',
            "DEFAULT_AGENTID": "FORECAST_SIM",
            "interval":"PT60M",
        }
        self._config = self.default_config.copy()
        self._agent_id = self._config.get("DEFAULT_AGENTID")
        self._message = self._config.get("DEFAULT_MESSAGE")
        self._heartbeat_period = self._config.get('DEFAULT_HEARTBEAT_PERIOD')

        self.vip.config.set_default("config", self.default_config)
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

        # this is the data structure that will hold ghi data & time stamps, populated in load_irradiance()
        self.ghi_series = None

        # indicates that load_irradiance (called onstart) is incomplete, so don't start publishing forecast
        # data yet.
        self.initialization_complete = 0
        self.last_query = None
        self.sim_time_corr = timedelta(seconds=0)
        #self.gs_start_time_exact = None
        self.gs_start_time = None

    ##############################################################################
    def configure(self,config_name, action, contents):
        self._config.update(contents)
        # make sure config variables are valid
        try:
            pass
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))


    ##############################################################################
    @Core.receiver('onstart')
    def onstart(self, sender, **kwargs):
        if self._heartbeat_period != 0:
            self.vip.heartbeat.start_with_period(self._heartbeat_period)
            self.vip.health.set_status(STATUS_GOOD, self._message)
        self.load_irradiance()



    ##############################################################################
    def load_irradiance(self):
        """
        Load a csv file of irradiance values.
        The csv file is interpreted as follows:
        (1) each row is an irradiance point, starting from jan 1st
        (2) the time step between rows is defined by csv_time_resolution_min
        (3) the file is assumed to comprise exactly a single year of data

        Use user-defined offsets set in gs_identities (SIM_START_DAY, SIM_START_HR) to figure out where to start
        Synchronize this start time to the time when the GS executive started.

        these configuration parameters are set within gs_identities.py:
        SIM_START_DAY
        SIM_START_HR
        PV_FORECAST_FILE - name of an appropriately formatted irradiance csv
        PV_FORECAST_RILE_TIME_RESOLUTION_MIN - time resolution, in minutes, of data in the csv irradiance file
        """


        # fixme - rename
        pv_forecast_file = PV_FORECAST_FILE
        csv_time_resolution_min = PV_FORECAST_FILE_TIME_RESOLUTION_MIN

        # Get irradiance data from csv file and populate in ghi_array
        self.volttron_root = os.getcwd()
        self.volttron_root = self.volttron_root + "/../../../../gs_cfg/"
        csv_name           = (self.volttron_root + pv_forecast_file)
        _log.info(csv_name)

        ghi_array = []

        try:
            with open(csv_name, 'rb') as csvfile:
                csv_data = csv.reader(csvfile)

                for row in csv_data:
                    ghi_array.append(float(row[0]))
        except IOError as e:
            _log.info("forecast database " + csv_name + " not found")


        # Now construct a full year's worth of irradiance data.
        # It re-indexes the irradiance file such that start day / start hour is
        # set to the ACTUAL time at which the GS Executive started.
        pts_per_day = int((MINUTES_PER_DAY) / csv_time_resolution_min)
        start_ind = int((SIM_START_DAY - 1) * pts_per_day+SIM_START_HR*MINUTES_PER_HR/csv_time_resolution_min)

        try:
            #v1, v2 = self.vip.rpc.call("executiveagent-1.0_1", "get_gs_start_time").get(timeout=5)
            #self.gs_start_time       = datetime.datetime.strptime(v1,"%Y-%m-%dT%H:%M:%S.%f") #.replace()
            #self.gs_start_time_exact = datetime.datetime.strptime(v2,"%Y-%m-%dT%H:%M:%S.%f") #.replace()
            v1 = self.vip.rpc.call("executiveagent-1.0_1", "get_gs_start_time").get(timeout=5)
            self.gs_start_time       = datetime.datetime.strptime(v1,"%Y-%m-%dT%H:%M:%S.%f") #.replace()
        except:
            _log.info("Forecast - gs_start_time not found.  Using current time as gs_start_time")
            #self.gs_start_time_exact = utils.get_aware_utc_now() #.replace(second=0, microsecond=0)
            #self.gs_start_time       =  datetime.datetime.strptime(get_schedule(self.gs_start_time_exact),
            #                                                            "%Y-%m-%dT%H:%M:%S.%f")
            self.gs_start_time = utils.get_aware_utc_now().replace(microsecond=0)


        _log.info("start index is: "+str(start_ind)+"; SIM_START_DAY is "+str(SIM_START_DAY))

        # now set up a panda.Series with indices = timestamp starting from GS start time,
        # time step from csv_time_resolution_min; and with values = ghi_array, starting from the index corresponding
        # to start day / start time
        ghi_timestamps = [self.gs_start_time + timedelta(minutes=t) for t in range(0, MINUTES_PER_YR, csv_time_resolution_min)]
        ghi_array_reindexed = []
        ghi_array_reindexed.extend(ghi_array[start_ind:])
        ghi_array_reindexed.extend(ghi_array[:start_ind])
        ghi_series_init = pandas.Series(data=ghi_array_reindexed, index=ghi_timestamps)

        # next resample to the time resolution of the GS optimizer.
        if csv_time_resolution_min != SSA_SCHEDULE_RESOLUTION: # need to resample!!
            sample_pd_str = str(SSA_SCHEDULE_RESOLUTION)+"min"
            self.ghi_series = ghi_series_init.resample(sample_pd_str).mean()
            if csv_time_resolution_min > SSA_SCHEDULE_RESOLUTION: # interpolate if upsampling is necessary
                self.ghi_series = self.ghi_series.interpolate(method='linear')
        else: # resampling is unnecessary
            self.ghi_series = ghi_series_init

        _log.info(str(self.ghi_series.head(48)))
        _log.info("Loaded irradiance file")

        # indicates that forecast data is ready to be published
        self.initialization_complete = 1

        # initialize a ForecastObject for publishing data to the VOLTTRON message bus
        self.solar_forecast = ForecastObject(SSA_PTS_PER_SCHEDULE, "NegPct", "float")


    ##############################################################################
    @RPC.export
    def get_sim_time_corr(self):
        return self.sim_time_corr.seconds

    ##############################################################################
    def parse_query(self):
        """
        Retrieves a solar forecast in units of "Pct"
            - start time of the forecast is defined by calling get_schedule()
            - Forecast duration is defined by SSA_SCHEDULE_DURATION
            - Forecast time step is defined by SSA_SCHEDULE_RESOLUTION
        """

        # get the start time of the forecast

        # to do so: (1) check if we went to sleep since the last forecast retrieved.  If so, use a correction to
        # make it look like no time has elapsed; (2) if accelerated time is being used, translate actual elapsed time
        # into accelerated time

        now = utils.get_aware_utc_now()
        gs_aware = self.gs_start_time.replace(tzinfo=pytz.UTC)

        if self.last_query != None:
            delta = now - self.last_query
            expected_delta = timedelta(seconds=CPR_QUERY_INTERVAL)
            if delta > expected_delta*2:
                # maybe we went to sleep?
                _log.info("Expected Delta = "+str(expected_delta))
                _log.info("Delta = "+str(delta))
                self.sim_time_corr += delta-expected_delta
                _log.info("CPR: Found a time correction!!!!")
                _log.info("Cur time: "+now.strftime("%Y-%m-%dT%H:%M:%S")+"; prev time= "+ self.last_query.strftime("%Y-%m-%dT%H:%M:%S"))

        self.last_query = now
        _log.info("ForecastSim time correction: "+str(self.sim_time_corr))
        next_forecast_start_time = datetime.datetime.strptime(get_schedule(gs_aware,
                                                                           sim_time_corr = self.sim_time_corr),
                                                              "%Y-%m-%dT%H:%M:%S.%f")

        # Need to convert panda series to flat list of timestamps and irradiance data
        # that will comprise the next forecast:
        next_forecast_timestamps = [next_forecast_start_time +
                                    timedelta(minutes=t) for t in range(0,
                                                                        SSA_SCHEDULE_DURATION*MINUTES_PER_HR,
                                                                        SSA_SCHEDULE_RESOLUTION)]
        next_forecast = self.ghi_series.get(next_forecast_timestamps)


        # Convert irradiance to a percentage
        self.solar_forecast.forecast_values["Forecast"] = [100 * v / 1000 for v in next_forecast]
        self.solar_forecast.forecast_values["Time"]     = [datetime.datetime.strftime(ts, "%Y-%m-%dT%H:%M:%S") for ts in next_forecast_timestamps]
        _log.info("forecast is:"+str(self.solar_forecast.forecast_values["Forecast"]))
        _log.info("timestamps are:"+str(self.solar_forecast.forecast_values["Time"]))

        # for publication to IEB:
        return self.solar_forecast.forecast_obj

    ##############################################################################
    @Core.periodic(period = CPR_QUERY_INTERVAL)
    def query_cpr(self):
        """
        called at interval defined in CPR_QUERY_INTERVAL (gs_identities)
        publishes forecast corresponding to the next planned optimizer pass
        """
        if self.initialization_complete == 1:
            _log.info("querying for production forecast from database")
            message = self.parse_query()
            self.vip.pubsub.publish(
                peer="pubsub",
                topic=self._config['topic'],
                headers={},
                message=message)
        else:
            _log.info("initialization incomplete!!")
            
def main(argv=sys.argv):
    '''Main method called by the platform.'''
    utils.vip_main(CPRAgent)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
