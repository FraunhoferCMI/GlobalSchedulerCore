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
from requests.auth import HTTPBasicAuth
import datetime
from datetime import timedelta
import pytz
from xml.dom import minidom

from volttron.platform.vip.agent import Agent, PubSub, Core
from volttron.platform.agent import utils
from volttron.platform.agent.utils import jsonapi
from volttron.platform.messaging import topics
from volttron.platform.messaging import headers as headers_mod

utils.setup_logging()
_log = logging.getLogger(__name__)

__version__="0.2"


def ForecastPub(config_path,**kwargs):
    query_interval = 300
    
    def get_date():
	    dt_strt = datetime.datetime.now(tz=pytz.timezone('America/New_York')).replace(microsecond=0).isoformat()
            dt_end  = datetime.datetime.isoformat(datetime.datetime.now(tz=pytz.timezone('America/New_York')).replace(microsecond=0)+timedelta(days=1))
            
	    return dt_strt, dt_end 
	
    class ForecastAgent(Agent):
	
	def __init__(self,config_path,**kwargs):
            super(ForecastAgent,self).__init__(**kwargs)
        # self.config = utils.load_config(config_path)
        # _log.info("loaded config from config file")
        # self.query_interval = self.config.get("interval")
        # self.topic = self.config.get("topic")

	    self.default_config = {
            "interval": 300,
            "userName":"schoudhary@cse.fraunhofer.org",
            "password": "Shines2017",
            "querystring": {"key":"FRHR3MXX7"},
            "url": "https://service.solaranywhere.com/api/v1/BulkSimulate",
            "payload":"""<BulkSimulationRequest xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns="http://service.solaranywhere.com/api/v1">
                            <EnergySiteIds>
                                <EnergySiteId>saUCvatIj0S6A5nirHoQIQ</EnergySiteId>
                            </EnergySiteIds>
                            <SimulationOptions PVSimulationModel="PVFORM" ShadingModel="ShadeSimulator">
                                <WeatherDataOptions WeatherDataSource="SolarAnywhere3_2" StartTime="{0}" EndTime="{1}"/>
                             <IntermediateResults>
                                <IntermediateResult>PowerAC</IntermediateResult>
                                </IntermediateResults>
                            </SimulationOptions>
                        </BulkSimulationRequest>""".format(get_date()[0],get_date()[1]),
            "headers": {'content-type': "text/xml; charset=utf-8",
                        'content-length': "length",},
		"topic": "devices/cpr",
	   
            }

            
            self._config = self.default_config.copy()
            _log.info("loaded default config values")

           # self.vip.config.set_default("config",self.default_config)
           # self.vip.config.subscribe(self.configure,actions=["NEW","UPDATE"],pattern="config")


        def parse_query(self,query):
            """ Function to parse XML response from API"""
            xmldoc = minidom.parseString(query)
            SimPd = xmldoc.getElementsByTagName('q1:SimulationPeriod')
            results ={"results":[[sim.attributes['StartTime'].value,float(sim.attributes['Power_kW'].value)] 
			for sim in SimPd],
                    "Units":"kWh",
                    "tz": "UTC-5",
                    "data_type":"float"
                }
            return results

        @Core.periodic(period = query_interval)
        def query_cpr(self):
            response = requests.post(self._config['url'],
                                 auth = HTTPBasicAuth(self._config['userName'],self._config['password']),
                                 data=self.default_config['payload'],
                                 headers=self._config['headers'],
                                 params=self._config['querystring'])


            _log.info("Status Code{0}".format(response.status_code))

            parsed_response = self.parse_query(response.text)
            self.vip.pubsub.publish(
            peer="pubsub",
            topic=self._config['topic'],
            headers={},
            message=parsed_response)

    ForecastAgent.__name__="ForecastPub"
    return ForecastAgent(config_path,**kwargs)


def main(argv=sys.argv):
    '''Main method called by platform'''
    utils.vip_main(ForecastPub)


    
if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
