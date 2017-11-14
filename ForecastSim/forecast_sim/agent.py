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

import logging
import sys
import requests
import pprint,pickle
import datetime
import os
from volttron.platform.vip.agent import Agent, PubSub, Core
from volttron.platform.agent import utils
from volttron.platform.agent.utils import jsonapi
from volttron.platform.messaging import topics
from volttron.platform.messaging import headers as headers_mod
import xml.etree.ElementTree as ET

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
def CPRPub(config_path, **kwargs):
    conf = utils.load_config(config_path)
    query_interval = conf.get("interval",10)
    topic = conf.get("topic","/cpr/forecast")
    class CPRAgent(Agent):
        #
        """
        Retrieve locall production forecast for the site, 
        using the XML-based REST interface.

        At the moment, it will just retrieve a straw sample
        from the global variables
TODO: 

        """
        
        def __init__(self, config_path, **kwargs):
            super(CPRAgent, self).__init__(**kwargs)
            self.volttron_root = os.getcwd()
            self.volttron_root = self.volttron_root+"/../../../../"
            self.default_config = {
                "interval":1200,
                "username": "shines",
                "password":"VolttronShines",
                "baseurl":"",
                "topic": "datalogger/cpr/forecast",
                "horizon":24,
                "ghi":self.volttron_root+"gs_cfg/cpr_ghi.pkl",
                # straw suggestion as this is the only option available.
                "interval":"PT60M",
            }
            self._config = self.default_config.copy()
            
            self.vip.config.set_default("config", self.default_config)
            self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")
            self.GHI = None
            self.load_irradiance()
            _log.warning("loaded GHI on init")
	    _log.info("Interval is: "+self._config["interval"]+"topic is "+self._config["topic"])    
        def configure(self,config_name, action, contents):
            self._config.update(contents)
            self.load_irradiance()
            # make sure config variables are valid
            try:
                pass
            except ValueError as e:
                _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))

        def load_irradiance(self):
            self.GHI = pickle.load(open(self._config["ghi"])).sort_index().to_period("H")
            self.GHI *= 1500000 / max(self.GHI.ghi)
            _log.warning("Loaded irradiance file")
            
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
            root = ET.fromstring(query)
	    ret =  [ 
                {
		    "Forecast": [100*float(v)/1000 for v in _PROD], #[
                        #float(child.attrib["Energy_kWh"])
                        #for child in root[0] ],
		    "Time": [
			child.attrib["StartTime"] for child in root[0] ]},
		{ "Forecast":{
                    "units":"Pct",#"W",
                    "type":"float"}, 
                  "Time":{
		    "units":"UTC",
                    "type":"str"}}

                #{
		#    "Forecast": [
                #        [ child.attrib["StartTime"],
                #          float(child.attrib["Energy_kWh"])]
                #        for child in root[0] ]},
		#{ "Forecast":{
                #    "units":"W",
                #    "tz":"UTC",
                #    "type":"float"}}
                      
            #ret =  {
                
            #    "CPR" :{
            #        "Readings":[ 
            #             [ child.attrib["StartTime"],
            #               float(child.attrib["Energy_kWh"])]
            #             for child in root[0] ],
            #        "Units":"KWH",
            #        "tz":"UTC",
            #        "data_type":"float"
            #    }		
            ]
            return ret
            
        @Core.periodic(period = query_interval)
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
            _log.info("querying for production forecast from CPR")
            message = self.parse_query(self.generate_sample())
            self.vip.pubsub.publish(
                peer="pubsub",
                topic=self._config['topic'],
                headers={},
                message=message)
    CPRAgent.__name__ = "CPRPub"
    return CPRAgent(config_path,**kwargs)
            
def main(argv=sys.argv):
    '''Main method called by the platform.'''
    utils.vip_main(CPRPub)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
