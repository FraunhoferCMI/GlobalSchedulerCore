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
from datetime import timedelta, datetime
import pytz
import os
from volttron.platform.messaging.health import STATUS_GOOD
from volttron.platform.vip.agent import Agent, PubSub, Core, RPC, compat
from volttron.platform.agent import utils
from volttron.platform.agent.utils import jsonapi
from volttron.platform.messaging import topics
from volttron.platform.messaging import headers as headers_mod
import xml.etree.ElementTree as ET
from gs_identities import *
from gs_utilities import get_schedule, ForecastObject, Forecast
import csv
import pandas
from volttron.platform.messaging import headers as header_mod


utils.setup_logging()
_log = logging.getLogger(__name__)

__version__="0.1"

MINUTES_PER_YR = 365 * MINUTES_PER_DAY  # valid for our database files - assume no leap years

READ_BACK_MSGS = False


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
            "solar_forecast_topic": "devices/cpr/forecast/all",
            "demand_forecast_topic": "devices/flame/forecast/all",
            "demand_report_topic": "devices/flame/load_report/all",
            "loadshift_report_topic": "devices/flame/loadshift_forecast",
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
        self.ghi_series      = None
        self.demand_series   = None
        self.solar_forecast  = None
        self.demand_forecast = None

        # indicates that load_irradiance (called onstart) is incomplete, so don't start publishing forecast
        # data yet.
        self.initialization_complete = 0
        self.last_query              = None
        self.sim_time_corr = timedelta(seconds=0)
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

        if READ_BACK_MSGS == True: # subscribe to any topics of interest for read back / testing
            self.vip.pubsub.subscribe(peer='pubsub', prefix=self._config["loadshift_report_topic"], callback=self.read_msgs)  # +'/all'
            self.vip.pubsub.subscribe(peer='pubsub', prefix=self._config["solar_forecast_topic"], callback=self.read_msgs)  # +'/all'


        ### Get gs_start_time
        try:
            v1 = self.vip.rpc.call("executiveagent-1.0_1", "get_gs_start_time").get(timeout=5)
            self.gs_start_time       = datetime.strptime(v1,"%Y-%m-%dT%H:%M:%S") #.replace()  # was .%f
        except:
            _log.info("Forecast - gs_start_time not found.  Using current time as gs_start_time")
            self.gs_start_time = utils.get_aware_utc_now().replace(microsecond=0)
            self.gs_start_time = self.gs_start_time.replace(tzinfo=None)
            _log.info("GS STart time is "+str(self.gs_start_time))

        #self.gs_start_time = self.gs_start_time.replace(tzinfo=pytz.UTC)

        #### Initialize data input files
        # get solar forecast data
        self.ghi_series = self.load_forecast_file()
        _log.info("Loaded irradiance file")
        # initialize a ForecastObject for publishing data to the VOLTTRON message bus
        self.solar_forecast = ForecastObject(SSA_PTS_PER_SCHEDULE, "NegPct", "float")

        # get demand forecast data
        self.demand_series = self.load_forecast_file(forecast_file = DEMAND_FORECAST_FILE,
                                                     csv_time_resolution_min = DEMAND_FORECAST_FILE_TIME_RESOLUTION_MIN)
        self.demand_forecast = ForecastObject(SSA_PTS_PER_SCHEDULE, "kW", "float")

        # indicates that forecast data is ready to be published
        self.initialization_complete = 1





    ##############################################################################
    def load_forecast_file(self,
                           forecast_file = PV_FORECAST_FILE,
                           csv_time_resolution_min = PV_FORECAST_FILE_TIME_RESOLUTION_MIN):
        """
        Load a csv file of forecast values.
        The csv file is interpreted as follows:
        (1) each row is an forecast value, starting from jan 1st
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


        # Get irradiance data from csv file and populate in ghi_array
        self.volttron_root = os.getcwd()
        self.volttron_root = self.volttron_root + "/../../../../gs_cfg/"
        csv_name           = (self.volttron_root + forecast_file)
        _log.info(csv_name)

        forecast_array = []

        try:
            with open(csv_name, 'rb') as csvfile:
                csv_data = csv.reader(csvfile)

                for row in csv_data:
                    #_log.info("val = "+str(row[0]))
                    forecast_array.append(float(row[0]))
        except IOError as e:
            _log.info("forecast database " + csv_name + " not found")


        # Now construct a full year's worth of irradiance data.
        # It re-indexes the irradiance file such that start day / start hour is
        # set to the ACTUAL time at which the GS Executive started.
        pts_per_day = int((MINUTES_PER_DAY) / csv_time_resolution_min)
        start_ind = int((SIM_START_DAY - 1) * pts_per_day+SIM_START_HR*MINUTES_PER_HR/csv_time_resolution_min)

        _log.info("start index is: "+str(start_ind)+"; SIM_START_DAY is "+str(SIM_START_DAY))

        # now set up a panda.Series with indices = timestamp starting from GS start time,
        # time step from csv_time_resolution_min; and with values = ghi_array, starting from the index corresponding
        # to start day / start time
        forecast_timestamps = [self.gs_start_time + timedelta(minutes=t) for t in range(0, MINUTES_PER_YR, csv_time_resolution_min)]
        forecast_array_reindexed = []
        forecast_array_reindexed.extend(forecast_array[start_ind:])
        forecast_array_reindexed.extend(forecast_array[:start_ind])
        forecast_series_init = pandas.Series(data=forecast_array_reindexed, index=forecast_timestamps)

        # next resample to the time resolution of the GS optimizer.
        if csv_time_resolution_min != SSA_SCHEDULE_RESOLUTION: # need to resample!!
            sample_pd_str = str(SSA_SCHEDULE_RESOLUTION)+"min"
            forecast_series = forecast_series_init.resample(sample_pd_str).mean()
            if csv_time_resolution_min > SSA_SCHEDULE_RESOLUTION: # interpolate if upsampling is necessary
                forecast_series = forecast_series.interpolate(method='linear')
        else: # resampling is unnecessary
            forecast_series = forecast_series_init

        _log.info(str(forecast_series.head(48)))

        return forecast_series

    ##############################################################################
    @RPC.export
    def get_sim_time_corr(self):
        return self.sim_time_corr.seconds


    ##############################################################################
    def get_timestamps(self,
                       sim_time_corr = timedelta(0)):

        gs_aware = self.gs_start_time.replace(tzinfo=pytz.UTC)
        next_forecast_start_time = datetime.strptime(get_schedule(gs_aware,
                                                                  sim_time_corr = sim_time_corr),
                                                     "%Y-%m-%dT%H:%M:%S.%f")
        # Need to convert panda series to flat list of timestamps and irradiance data
        # that will comprise the next forecast:
        next_forecast_timestamps = [next_forecast_start_time +
                                    timedelta(minutes=t) for t in range(0,
                                                                        SSA_SCHEDULE_DURATION*MINUTES_PER_HR,
                                                                        SSA_SCHEDULE_RESOLUTION)]

        return next_forecast_timestamps


    ##############################################################################
    def parse_load_report(self):
        """
        Retrieves a load report in units of "kW"
            - start time of the forecast is defined by calling get_schedule()
            - Forecast duration is defined by SSA_SCHEDULE_DURATION
            - Forecast time step is defined by SSA_SCHEDULE_RESOLUTION
        """
        next_forecast_timestamps = self.get_timestamps(self.sim_time_corr)
        next_forecast            = self.demand_series.get(next_forecast_timestamps)
        self.load_report = next_forecast[0]


        #TimeStamp = utils.get_aware_utc_now()  # datetime.now()
        #TimeStamp_str = TimeStamp.strftime("%Y-%m-%dT%H:%M:%S.%f")

        # 2. build a device-compatible msg:
        msg =[{'load': self.load_report}, {'load': {"units": 'kW',
                                                   "tz": "UTC",
                                                   "data_type": "float"}}]

        now = utils.get_aware_utc_now().isoformat() #datetime.strftime(utils.get_aware_utc_now(), "%Y-%m-%dT%H:%M:%S.f")

        # python code to get this is
        # from datetime import datetime
        # from volttron.platform.messaging import headers as header_mod
        header = {header_mod.DATE: datetime.utcnow().isoformat() + 'Z'}
        #"Date": "2015-11-17T21:24:10.189393Z"

        return msg, header

    ##############################################################################
    def parse_demand_query(self):
        """
        Retrieves a demand forecast in units of "kW"
            - start time of the forecast is defined by calling get_schedule()
            - Forecast duration is defined by SSA_SCHEDULE_DURATION
            - Forecast time step is defined by SSA_SCHEDULE_RESOLUTION
        """
        next_forecast_timestamps = self.get_timestamps(self.sim_time_corr)
        next_forecast            = self.demand_series.get(next_forecast_timestamps)

        # Convert irradiance to a percentage
        self.demand_forecast.forecast_values["Forecast"] = [v for v in next_forecast]
        self.demand_forecast.forecast_values["Time"]     = [datetime.strftime(ts, "%Y-%m-%dT%H:%M:%S") for ts in next_forecast_timestamps]
        _log.info("Demand forecast is:"+str(self.demand_forecast.forecast_values["Forecast"]))
        _log.info("timestamps are:"+str(self.demand_forecast.forecast_values["Time"]))

        # for publication to IEB:
        return self.demand_forecast.forecast_obj


    ##############################################################################
    def parse_solar_query(self):
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

        next_forecast_timestamps = self.get_timestamps(sim_time_corr = self.sim_time_corr)
        next_forecast            = self.ghi_series.get(next_forecast_timestamps)

        # Convert irradiance to a percentage
        self.solar_forecast.forecast_values["Forecast"] = [100 * v / 1000 for v in next_forecast]
        self.solar_forecast.forecast_values["Time"]     = [datetime.strftime(ts, "%Y-%m-%dT%H:%M:%S") for ts in next_forecast_timestamps]  # was .%f
        _log.info("Solar forecast is:"+str(self.solar_forecast.forecast_values["Forecast"]))
        _log.info("timestamps are:"+str(self.solar_forecast.forecast_values["Time"]))

        # for publication to IEB:
        return self.solar_forecast.forecast_obj


    ##############################################################################
    @Core.periodic(period = DEMAND_FORECAST_QUERY_INTERVAL)
    def query_demand_forecast(self):
        """
        called at interval defined in DEMAND_FORECAST_QUERY_INTERVAL (gs_identities)
        publishes demand forecast corresponding to the next planned optimizer pass
        """
        if USE_DEMAND_SIM == 1:
            if self.initialization_complete == 1:
                _log.info("querying for demand forecast from database")
                message = self.parse_demand_query()
                self.vip.pubsub.publish(
                    peer="pubsub",
                    topic=self._config['demand_forecast_topic'],
                    headers={},
                    message=message)

                self.vip.pubsub.publish(
                    peer="pubsub",
                    topic=self._config['demand_forecast_topic'],
                    headers={},
                    message=[{"comm_status": 1}, {"comm_status": {'type': 'int', 'units': 'none'} }])
            else:
                _log.info("initialization incomplete!!")


    ##############################################################################
    @Core.periodic(period = LOADSHIFT_QUERY_INTERVAL)
    def query_loadshift_forecast(self):
        """
        called at interval defined in LOADSHIFT_QUERY_INTERVAL (gs_identities)
        publishes loadshift forecast corresponding to the next planned optimizer pass
        """
        if USE_DEMAND_SIM == 1:
            if self.initialization_complete == 1:
                _log.info("querying for load shift forecast from database")

                # # before refactor
                # load_shift_forecast = ForecastObject(SSA_PTS_PER_SCHEDULE, "kW", "float", nForecasts=10)
                # load_shift_forecast.forecast_values["Time"] = self.demand_forecast.forecast_values["Time"][:]
                # load_shift_forecast.forecast_values["Forecast"] = [[v*ii for v in self.demand_forecast.forecast_values["Forecast"]] for ii in range(0,10)]
                # message = load_shift_forecast.forecast_obj

                # Cam refactor
                forecast = self.format_forecast()
                # forecast = [[v*ii for v in self.demand_forecast.forecast_values["Forecast"]] for ii in range(0,10)]
                time = self.demand_forecast.forecast_values["Time"][:]
                units = "kW"
                datatype = "float"
                loadShiftForecast = Forecast(forecast,
                                             time,
                                             units,
                                             datatype)
                message = loadShiftForecast.forecast_obj
                self.vip.pubsub.publish(
                        peer="pubsub",
                        topic=self._config['loadshift_report_topic']+'/all',
                        headers={},
                        message=message)

                #for ii in range(0,10):
                #    self.vip.pubsub.publish(
                #        peer="pubsub",
                #        topic=self._config['test_report_topic']+"/option"+str(ii)+'/all',
                #        headers={},
                #        message=message)

                message = [{"nOptions": 10}, {"nOptions": {'type': 'int', 'units': 'none'}}]

                self.vip.pubsub.publish(
                    peer="pubsub",
                    topic=self._config['loadshift_report_topic']+'/all',
                    headers={},
                    message=message)


        else:
            _log.info("initialization incomplete!!")



    def format_forecast(self):
        raw_forecast = self.demand_forecast.forecast_values["Forecast"]
        formatted_forecast = []
        for ii in range(0,10):
            vals = []
            for v in raw_forecast:
                val = v * ii
                vals.append(val)
            formatted_forecast.append(vals)

        return formatted_forecast

    ##############################################################################
    @Core.periodic(period = DEMAND_REPORT_SCHEDULE)
    def query_load_report(self):
        """
        called at interval defined in DEMAND_REPORT_SCHEDULE  (gs_identities)
        publishes load report on current rt load
        """
        if USE_DEMAND_SIM == 1:
            if self.initialization_complete == 1:
                _log.info("querying for load report from database")
                message, header = self.parse_load_report()
                self.vip.pubsub.publish(
                    peer="pubsub",
                    topic=self._config['demand_report_topic'],
                    headers=header,
                    message=message)

                self.vip.pubsub.publish(
                    peer="pubsub",
                    topic=self._config['demand_report_topic'],
                    headers=header,
                    message=[{"comm_status": 1}, {"comm_status": {'type': 'int', 'units': 'none'} }])

            else:
                _log.info("initialization incomplete!!")



    ##############################################################################
    @Core.periodic(period = CPR_QUERY_INTERVAL)
    def query_solar_forecast(self):
        """
        called at interval defined in CPR_QUERY_INTERVAL (gs_identities)
        publishes solar forecast corresponding to the next planned optimizer pass
        """
        if USE_SOLAR_SIM == 1:
            if self.initialization_complete == 1:
                _log.info("querying for production forecast from database")
                message = self.parse_solar_query()
                self.vip.pubsub.publish(
                    peer="pubsub",
                    topic=self._config['solar_forecast_topic'],
                    headers={},
                    message=message)
            else:
                _log.info("initialization incomplete!!")


    ##############################################################################
    def read_msgs(self, peer, sender, bus, topic, headers, message):
        """
        for testing purposes -
        parses message on IEB published to the specified path and prints.
        To enable, set READ_BACK_MSGS to True
        """
        _log.info("Topic found - "+str(topic))
        if sender == 'pubsub.compat':
            message = compat.unpack_legacy_message(headers, message)
        _log.info("Msg: "+str(message)+"\n")

        try:
            #_log.info(str(message[0]["Forecast"][2][0:5]))
            df = pandas.DataFrame(data=message[0]["Forecast"]).transpose()
            df.index = pandas.Series(message[0]["Time"])
            print(df)
        except:
            try:
                df = pandas.DataFrame(data=message[0]["Forecast"])
                df.index = pandas.Series(message[0]["Time"])
                print(df)
            except:
                pass


def main(argv=sys.argv):
    '''Main method called by the platform.'''
    utils.vip_main(CPRAgent)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
