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
