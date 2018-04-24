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
from  xml.etree.ElementTree import tostring

from volttron.platform.vip.agent import Agent, PubSub, Core
from volttron.platform.agent import utils
from volttron.platform.agent.utils import jsonapi
from volttron.platform.messaging import topics
from volttron.platform.messaging import headers as headers_mod

from .CPRinteraction import create_xml_query, parse_query

utils.setup_logging()
_log = logging.getLogger(__name__)

__version__="0.1"

_log.info("Agent Code begins here")

def CPRPub(config_path,**kwargs):
    conf = utils.load_config(config_path)
    test = utils.load_config(config_path)
    query_interval = conf.get("interval")
    receive_interval = 5
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

            _log.info("Initializing - STEP 3")
            self.initialization_complete = False
            self.process_times = []
	    self.default_config = {
            "interval": 60,
            "headers": {'content-type': "text/xml; charset=utf-8",
                    'content-length': "length",},

            }

            _log.info("set default for conf")
            self.init_config = self.default_config.copy()

            self.vip.config.set_default("conf", self.init_config) #self.default_config)

            _log.info("subscribe to config store")
            self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="conf")

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
           self.initialization_complete = True
           self.status_pending = False


        @Core.periodic(period = query_interval)
        def request_cpr_model(self):

            if self.initialization_complete == True:     # queries server only after config steps are completed

                _log.info("Attempting to make a model request")
                if self.status_pending is not True:

                    _log.info("Creating cpr request")
                    self.start_date, self.end_date = get_date()
                    _log.debug("start date = "+str(self.start_date)+"; end date is "+str(self.end_date))
                    cur_payload = create_xml_query(self.start_date, self.end_date)
                    _log.debug("current payload:\n"+ minidom.parseString(cur_payload).toprettyxml())

                    _log.info("Making model request:\n{}".format(cur_payload))
                    response = requests.post(conf['url'],
                                             auth = HTTPBasicAuth(conf['userName'], conf['password']),
                                             data= cur_payload,
                                             headers=self.default_config['headers'],
                                             params=conf['querystring'])

                    _log.info("Request Status Code: {}".format(response.status_code))
                    if response.status_code == 200:
                        self.status_pending = True
                        self.simulationId = ET.fromstring(response.content).attrib.get("SimulationId")
                        self.start_time = time.time()
                else:
                    _log.info("Another model has been requested and is pending")


        @Core.periodic(period = receive_interval)
        def receive_cpr_model(self):

            if (self.initialization_complete == True) and (self.status_pending == True):

                url2 =  "https://service.solaranywhere.com/api/v2/SimulationResult/" + self.simulationId
                data = requests.get(url2,
                                    auth = HTTPBasicAuth(conf['userName'], conf['password'])
                                    )
                status = ET.fromstring(data.content).attrib.get('Status')

                if status == 'Done':
                    parsed_response = parse_query(data.content)

                    _log.info("Model received, Parsed Response Sending: {}".format(parsed_response))
                    self.vip.pubsub.publish(
                        peer="pubsub",
                        topic=conf['topic'],
                        headers={},
                        message=parsed_response)

                    self.status_pending = False # allow new model requests to be made

                    # receive_interval optimization
                    request_process_time = round(time.time() - self.start_time, 2)
                    _log.info("Request process time was: {}".format(request_process_time))
                    self.process_times.append(request_process_time)
                    receive_interval = sum(self.process_times)/len(self.process_times)


                elif status == 'Pending':
                    _log.info("model still pending, waiting...")


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
