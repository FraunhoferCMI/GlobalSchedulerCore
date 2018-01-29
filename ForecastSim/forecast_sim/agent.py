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
import datetime
import os
from volttron.platform.messaging.health import STATUS_GOOD
from volttron.platform.vip.agent import Agent, PubSub, Core, RPC
from volttron.platform.agent import utils
from volttron.platform.agent.utils import jsonapi
from volttron.platform.messaging import topics
from volttron.platform.messaging import headers as headers_mod
import xml.etree.ElementTree as ET
from gs_identities import (SSA_SCHEDULE_RESOLUTION, SSA_SCHEDULE_DURATION, CPR_QUERY_INTERVAL)
import csv
import pandas


#_PROD = [4,0,0,0,0,0,0,0,0,68,294,499,666,751,791,787,685,540,
#        717,699,600,580,366,112]
_PROD = [0,0,0,0,0,0,68,294,499,666,751,791,787,685,540,
        717,699,600,580,366,112,0,0,0]
PROD = [ p* 1500000.0 / max(_PROD) for p in _PROD ]

utils.setup_logging()
_log = logging.getLogger(__name__)

__version__="0.1"

SAMPLE = """
<SimulationResponse xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" EnergySiteId="EHmMWnHp-EqzKJx3McTWWg" RequestURL="/SolarAnywhereToolkit/Services/Services.svc/v1/Simulate?EnergySiteId=EHmMWnHp-EqzKJx3McTWWg&amp;StartTime=2011-01-01T09%%3a00%%3a00-08%%3a00&amp;EndTime=2011-01-01T11%%3a00%%3a00-08%%3a00&amp;AmbientTemperature&amp;WindSpeed&amp;key=****EY" Status="Success" xmlns="v3">
  <SimulationPeriods>
%s  
</SimulationPeriods>
</SimulationResponse>
"""
PERIOD = """
    <SimulationPeriod StartTime="%(start)s" EndTime="%(end)s" Energy_kWh="%(prod)s" ObservationTypes="AD" AmbientTemperature_DegreesC="0" WindSpeed_MetersPerSecond="3" />
"""
# constants
MINUTES_PER_HR = 60
MINUTES_PER_DAY = 24 * MINUTES_PER_HR
MINUTES_PER_YR = 365 * MINUTES_PER_DAY


class CPRAgent(Agent):
    #
    """
    Retrieve locall production forecast for the site,
    using the XML-based REST interface.

    At the moment, it will just retrieve a straw sample
    from the global variables
    TODO:

    """

    ##############################################################################
    def __init__(self, config_path, **kwargs):
        super(CPRAgent, self).__init__(**kwargs)
        self.volttron_root = os.getcwd()
        self.volttron_root = self.volttron_root+"/../../../../"
        self.default_config = {
            "interval":1200,
            "username": "shines",
            "password":"VolttronShines",
            "baseurl":"",
            "topic": "devices/cpr/forecast/all",
            "horizon":24,
            "ghi":self.volttron_root+"gs_cfg/cpr_ghi.pkl",
            "DEFAULT_HEARTBEAT_PERIOD": 5,
            "DEFAULT_MESSAGE": 'FORECAST_SIM_Message',
            "DEFAULT_AGENTID": "FORECAST_SIM",
            # straw suggestion as this is the only option available.
            "interval":"PT60M",
        }
        self._config = self.default_config.copy()
        self._agent_id = self._config.get("DEFAULT_AGENTID")
        self._message = self._config.get("DEFAULT_MESSAGE")
        self._heartbeat_period = self._config.get('DEFAULT_HEARTBEAT_PERIOD')

        self.vip.config.set_default("config", self.default_config)
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")
        self.GHI = None
        _log.warning("loaded GHI on init")
        _log.info("Interval is: "+self._config["interval"]+"topic is "+self._config["topic"])

    ##############################################################################
    def configure(self,config_name, action, contents):
        self._config.update(contents)
        #self.load_irradiance()
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
        Load a csv file with an offset, in minutes
        Use user-defined offset to figure out where to start
        Synchronize this start time to the first optimizer run time.
        :return:
        """

        # before stopping, I would like to get this cleaned with respect to all of the parameters
        # i.e., GS_TIME_RESOLUTION, etc


        # User configured
        sim_start_day = 2  # day 106
        sim_start_hr  = 0

        csv_time_resolution_min = 60
        self.volttron_root = os.getcwd()
        self.volttron_root = self.volttron_root + "/../../../../gs_cfg/"
        csv_name = (self.volttron_root + "SAM_PVPwr_nyc.csv")
        _log.info(csv_name)

        gs_start_time = datetime.datetime.strptime( self.vip.rpc.call("executiveagent-1.0_1",
                                                                      "get_gs_start_time").get(timeout=5),
                                                    "%Y-%m-%dT%H:%M:%S.%f")


        t_array = []
        ghi_array = []

        try:
            with open(csv_name, 'rb') as csvfile:
                csv_data = csv.reader(csvfile)

                for row in csv_data:
                    t_array.append(int(row[0]))
                    ghi_array.append(float(row[1]))
        except IOError as e:
            _log.info("forecast database " + csv_name + " not found")


        # the following constructs a full year's worth of irradiance data.
        # It re-indexes the irradiance file such that start day / start hour is
        # set to the ACTUAL time at which the GS Executive started.
        # GS
        pts_per_day = int((MINUTES_PER_DAY) / csv_time_resolution_min)
        start_ind = int((sim_start_day - 1) * pts_per_day+sim_start_hr*MINUTES_PER_HR/csv_time_resolution_min)
        _log.info("start index is: "+str(start_ind)+"; sim_start_day is "+str(sim_start_day))

        ghi_timestamps = [gs_start_time + timedelta(minutes=t) for t in range(0, MINUTES_PER_YR, csv_time_resolution_min)]
        ghi_array_reindexed = []
        ghi_array_reindexed.extend(ghi_array[start_ind:])
        ghi_array_reindexed.extend(ghi_array[:start_ind])
        ghi_series_init = pandas.Series(data=ghi_array_reindexed, index=ghi_timestamps)

        #next_forecast_start_ind = ghi_timestamps.index(get_schedule())
        #next_forecast_end_ind   = next_forecast_start_ind + pts_per_day
        #next_forecast_ghi       = ghi_array_reindexed[next_forecast_start_ind:next_forecast_end_ind]
        #next_forecast_t         = ghi_timestamps[next_forecast_start_ind:next_forecast_end_ind]
        #for (t, g) in zip(next_forecast_t, next_forecast_ghi):  # zip(t_array,ghi_array):
        #    _log.info(str(t) + ": " + str(g))


        # resample to the time resolution of the GS optimizer
        if csv_time_resolution_min != SSA_SCHEDULE_RESOLUTION: # need to resample!!
            sample_pd_str = str(SSA_SCHEDULE_RESOLUTION)+"min"
            self.ghi_series = ghi_series_init.resample(sample_pd_str).mean()
            if csv_time_resolution_min > SSA_SCHEDULE_RESOLUTION: # interpolate if upsampling is necessary
                self.ghi_series = self.ghi_series.interpolate(method='linear')
        else:
            self.ghi_series = ghi_series_init

        _log.info(str(self.ghi_series.head(48)))

        _log.info("Loaded irradiance file")

    def generate_sample(self,
                        start=None, horizon=24):
        periods = []

        start = (datetime.datetime.combine(
            datetime.date.today(),
            datetime.time(datetime.datetime.now().hour)) +
                 datetime.timedelta(minutes=60))
        _log.warning("START " + start.isoformat())
        for i in range(horizon):
            end = start + datetime.timedelta(minutes=60)
            periods.append(
                PERIOD% {
                    "start":start,
                    "prod": (
                        PROD[start.hour]
                        if self.GHI is None else
                        self.GHI[start.replace(year=self.GHI.index[0].year):].ghi[0]
                    ),
                    "end":end
                    })
            start=end
        return SAMPLE%''.join(periods)

    def parse_query(self,query):
        """
        """
        # FIXME - units - kWh or W?

        # the following is what is used to retrieve data for a specific time in the future...
        # need to fix up all time deltas, etc.
        next_forecast_start_time = datetime.datetime.strptime(self.vip.rpc.call("executiveagent-1.0_1",
                                                                                "get_schedule").get(timeout=5),
                                                              "%Y-%m-%dT%H:%M:%S.%f")

        # generate the list of timestamps that will comprise the next forecast:
        next_forecast_timestamps = [next_forecast_start_time +
                                    timedelta(minutes=t) for t in range(0,
                                                                        SSA_SCHEDULE_DURATION*MINUTES_PER_HR,
                                                                        SSA_SCHEDULE_RESOLUTION)]
        next_forecast = self.ghi_series.get(next_forecast_timestamps)

        #_log.info(resample_ghi.head(48))

        next_forecast_list = [100 * v / 1000 for v in next_forecast]
        next_timestamps_list = [datetime.datetime.strftime(ts, "%Y-%m-%dT%H:%M:%S") for ts in next_forecast_timestamps]
        _log.info("forecast is:"+str(next_forecast_list))
        _log.info("timestamps are:"+str(next_timestamps_list))

        #for pts in forecast_pts:
        #    _log.info(str(pts))

        if (0):
            root = ET.fromstring(query)
            ret =  [ {"Forecast": [100*float(v)/1000 for v in _PROD], #[float(child.attrib["Energy_kWh"]) for child in root[0] ],
                      "Time": [child.attrib["StartTime"] for child in root[0] ]},
                     { "Forecast":{"units":"Pct", #"W",
                                   "type":"float"},
                       "Time":{"units":"UTC",
                               "type":"str"}}
            ]
        else:
            ret = [ {"Forecast": next_forecast_list,
                      "Time": next_timestamps_list},
                     { "Forecast":{"units":"Pct", #"W",
                                   "type":"float"},
                       "Time":{"units":"UTC",
                               "type":"str"}}]

        return ret

    @Core.periodic(period = CPR_QUERY_INTERVAL)
    def query_cpr(self):
        """
        Awaiting account setup:

        a = self._config['LMP']
        req = requests.get(
            self._config['baseurl']+a,
            headers={"Accept":"application/json"},
            auth=(
                self._config['username'],
                self._config['password']))
        _log.debug("Fetching {}, got {}".format(a, req.status_code))

        if req.status_code == 200:
        """
        _log.info("querying for production forecast from database")
        message = self.parse_query(self.generate_sample())
        self.vip.pubsub.publish(
            peer="pubsub",
            topic=self._config['topic'],
            headers={},
            message=message)
            
def main(argv=sys.argv):
    '''Main method called by the platform.'''
    utils.vip_main(CPRAgent)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
