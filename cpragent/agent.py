import logging
import sys
import requests
from requests.auth import HTTPBasicAuth
import datetime
from datetime import timedelta
import pytz
from xml.dom import minidom
import time 
import xml.etree.ElementTree as ET

from volttron.platform.vip.agent import Agent, PubSub, Core
from volttron.platform.agent import utils
from volttron.platform.agent.utils import jsonapi
from volttron.platform.messaging import topics
from volttron.platform.messaging import headers as headers_mod

utils.setup_logging()
_log = logging.getLogger(__name__)

__version__="0.1"

_log.info("Agent Code begins here")

def CPRPub(config_path,**kwargs):
    conf = utils.load_config(config_path)
    test = utils.load_config(config_path)
    query_interval = conf.get("interval")
    userName = conf.get("userName")
    password = conf.get("password")    
    querystring = conf.get("querystring")
    url = conf.get("url")
    url2 = conf.get("url2")
    payload = conf.get("payload")
    headers = conf.get("headers")
    topic = conf.get("topic")
    horizon = conf.get("horizon")
    _log.info("Config variables-query_interval {}".format(query_interval))
    _log.info("Config variables-userName {}".format(userName))
    _log.info("Config variables-password {}".format(password))
    _log.info("Config variables-querystring {}".format(querystring))
    _log.info("Config variables-url {}".format(url))
    _log.info("Config variables-url2 {}".format(url2))
    _log.info("Config variables-payload {}".format(payload))
    _log.info("Config variables-headers {}".format(headers))
    _log.info("Config variables-topic {}".format(topic))
    _log.info("Config variables-horizon {}".format(horizon))
    _log.info("STEP 1")
      
    def get_date():
	    dt_strt = datetime.datetime.isoformat(datetime.datetime.now(tz=pytz.timezone('America/New_York')).replace(microsecond=0,second=0,minute=0)+ timedelta(hours=1))
            dt_end  = datetime.datetime.isoformat(datetime.datetime.now(tz=pytz.timezone('America/New_York')).replace(microsecond=0,second=0,minute=0)+timedelta(hours=6))
            
	    return dt_strt, dt_end 
	
    class CPRAgent(Agent):
	_log.info("Entering Agent class - STEP 2")
	def __init__(self,config_path,**kwargs):
            super(CPRAgent,self).__init__(**kwargs)
            self.initialization_complete = 0
            self.cnt=0
            _log.info("Initializing - STEP 3")


            self.start_date = datetime.datetime(year=2018, month=3, day=27, hour=0).replace(tzinfo=pytz.UTC)
            self.end_date   = datetime.datetime(year=2018, month=3, day=27, hour=4).replace(tzinfo=pytz.UTC)

	    self.default_config = {
            "interval": 60,
            #"userName":"",
            #"password": "",
            #"querystring":"" ,
            #"url": "https://service.solaranywhere.com/api/v2/Simulation",
            #"url2": "https://service.solaranywhere.com/api/v2/SimulationResult/"
            "payload":"""<CreateSimulationRequest xmlns="http://service.solaranywhere.com/api/v2">
 <EnergySites>
  <EnergySite Name="SHINES-Shirley, MA" Description="Shirley site in MA, higher resolution">
   <Location Latitude="42.5604788" Longitude="-71.6331026" />
    <PvSystems>
     <PvSystem Albedo_Percent="17" GeneralDerate_Percent="85.00">
      <Inverters>
       <Inverter Count="2" MaxPowerOutputAC_kW="500.00000" EfficiencyRating_Percent="98.000000" />
      </Inverters>
      <PvArrays>
       <PvArray>
        <PvModules>
         <PvModule Count="3222" NameplateDCRating_kW="0.310000" PtcRating_kW="0.284800" PowerTemperatureCoefficient_PercentPerDegreeC="0.43" NominalOperatingCellTemperature_DegreesC="45" />
        </PvModules>
        <ArrayConfiguration Azimuth_Degrees="232" Tilt_Degrees="20.000" Tracking="Fixed" TrackingRotationLimit_Degrees="90" />  #removed ModuleRowCount and RelativeRowSpacing and next 2 sections SolarObstructions and Monthly shadings
         </PvArray>
        </PvArrays>
       </PvSystem>
     </PvSystems>
    </EnergySite>
  </EnergySites>
 <SimulationOptions
 PowerModel="CprPVForm"
 ShadingModel="ShadeSimulator" OutputFields="StartTime,EndTime,PowerAC_kW,GlobalHorizontalIrradiance_WattsPerMeterSquared,AmbientTemperature_DegreesC">
 <WeatherDataOptions
WeatherDataSource="SolarAnywhere3_2"
WeatherDataPreference = "Auto"
PerformTimeShifting = "true"
StartTime="{0}"
EndTime="{1}"
SpatialResolution_Degrees="0.01"
TimeResolution_Minutes="60"/>
 </SimulationOptions>
</CreateSimulationRequest>""", 
            "headers": {'content-type': "text/xml; charset=utf-8",
                        'content-length': "length",},
		#"topic": "devices/cpr",
	   
            }
 
            self.payload_base = self.default_config["payload"]          

            self.init_config = self.default_config.copy()
            self.init_config["payload"] = self.init_config["payload"].format(datetime.datetime.isoformat(self.start_date), datetime.datetime.isoformat(self.end_date))
            #format(get_date()[0],get_date()[1])

            _log.info("init config is "+self.init_config["payload"])
            self.vip.config.set_default("conf", self.init_config) #self.default_config)
            _log.info("set default for conf")
            self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="conf")
            _log.info("subscribed to config store")

        def configure(self,config_name, action, contents):
           _log.info("configuring method - STEP 4")
           
           conf.update(contents)
           
           _log.info("conf {}".format(conf))
           _log.info("CONF")

           # make sure config variables are valid
           try:
               pass
           except ValueError as e:
               _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
           self.initialization_complete = 1           

        def parse_query(self,query):
            """ Function to parse XML response from API"""
            _log.info("Parse query - STEP 5")
            xmldoc = minidom.parseString(query)
            SimPd = xmldoc.getElementsByTagName('SimulationPeriod')
            results ={"results":[[sim.attributes['StartTime'].value,float(sim.attributes['PowerAC_kW'].value)] 
			for sim in SimPd],
                    "Units":"kWh",
                    "tz": "UTC-5",
                    "data_type":"float"
                }
            return results

        #@Core.periodic(period = 2)   
        #def test_msg(self):
         #   _log.info("cnt = "+str(self.cnt))
          #  self.cnt+=1
        

        @Core.periodic(period = query_interval)  
                  
        def query_cpr(self):
            status_pending = 1
            time_request = 0
            time_now = 0


            self.start_date = self.start_date+timedelta(seconds=3600)
            self.end_date   = self.end_date+timedelta(seconds=3600)
            _log.info("start date = "+str(self.start_date)+"; end date is "+str(self.end_date))

            if self.initialization_complete == 1:     # queries server only after config steps are completed

                    cur_payload = self.payload_base
                    _log.info("cur payload is {}".format(cur_payload))

                    cur_payload = cur_payload.format(datetime.datetime.isoformat(self.start_date), datetime.datetime.isoformat(self.end_date))
                    _log.info("new payload is {}".format(cur_payload))


                    _log.info("SEE ME 1")
                    response = requests.post(conf['url'],
		                         auth = HTTPBasicAuth(conf['userName'],conf['password']),
		                         data= cur_payload, #self.default_config['payload'],
		                         headers=self.default_config['headers'],
		                         params=conf['querystring'])
                    _log.info("Request Status Code{}".format(response.status_code))

		    _log.info("GET Request to get sim results - delay required upto 5 mins")
		    root = ET.fromstring(response.content)
		    publicId = root.attrib.get("SimulationId")
		    _log.info("PublicId {}".format(publicId))
                    time_request = time.time()
                    _log.info("SEE ME 2 - time request{}".format(time_request))
		    time.sleep(2)


                    while (status_pending == 1): #(time_now - time_request <= query_interval):
                        if status_pending == 1:
                            _log.info("SEE ME 3")                      
                            time_now = time.time()
                            _log.info("time_now {}".format(time_now))
                            data = requests.get(url2 + publicId, auth = HTTPBasicAuth(userName,password))
                            root1 = ET.fromstring(data.content)
                            status = root1.attrib.get("Status")
                            _log.info("Get Request Status {}".format(status))
                            if status == "Pending":
                                status_pending = 1
                                time.sleep(2)
                                _log.info("SEE ME 4")
                                time_now = time.time()
                            
                            else:
                                status_pending = 0
                                _log.info("SEE ME 5")
                                parsed_response = self.parse_query(data.content)
		                _log.info("Parsed Response {}".format(parsed_response))
		                self.vip.pubsub.publish(
		                peer="pubsub",
		                    topic=conf['topic'],
		                    headers={},
		                    message=parsed_response)
                        
                                                       

    CPRAgent.__name__="CPRPub"
    return CPRAgent(config_path,**kwargs)


def main(argv=sys.argv):
    '''Main method called by platform'''
    _log.info("Main method - STEP 8")
    utils.vip_main(CPRPub)


    
if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
