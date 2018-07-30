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

from gs_utilities import Forecast

from CPRinteraction import create_xml_query, parse_query, get_date

utils.setup_logging()
_log = logging.getLogger(__name__)

__version__="0.1"

_log.info("Agent Code begins here")
query_interval = 60
receive_interval = 5


class CPRPub(Agent):
    _log.info("Entering Agent class - STEP 2")
    def __init__(self,config_path,**kwargs):
        super(CPRPub,self).__init__(**kwargs)

        self._conf = utils.load_config(config_path)
        self._conf['topic'] = "".join(["devices/cpr",
                                       str(self._conf['sim_interval']),
                                       "m"])
        query_interval = self._conf.get("query_interval")
        receive_interval = self._conf.get("receive_interval")

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

        self.vip.config.set_default("conf", self.init_config)

        _log.info("subscribe to config store")
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="conf")

    def configure(self,config_name, action, contents):
       _log.info("configuring method - STEP 4")

       self._conf.update(contents)

       _log.info("conf {}".format(self._conf))
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
            if self.status_pending is False:
                _log.info("Make a model request")
                _log.info("Creating cpr request")
                self.start_date, self.end_date = get_date()
                _log.debug("start date = "+str(self.start_date)+"; end date is "+str(self.end_date))
                cur_payload = create_xml_query(start=self.start_date,
                                               end=self.end_date,
                                               TimeResolution_Minutes=self._conf['sim_interval'])
                _log.debug("current payload:\n"+ minidom.parseString(cur_payload).toprettyxml())

                _log.info("Making model request:\n{}".format(cur_payload))
                response = requests.post(self._conf['url'],
                                         auth = HTTPBasicAuth(self._conf['userName'], self._conf['password']),
                                         data= cur_payload,
                                         headers=self.default_config['headers'],
                                         params=self._conf['querystring'])

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
            auth = HTTPBasicAuth(self._conf['userName'],
                                 self._conf['password'])
            data = requests.get(url2, auth = auth)
            status = ET.fromstring(data.content).attrib.get('Status')

            if status == 'Done':
                parsed_response = parse_query(data.content)
                _log.info("Model received, Parsed Response Sending: {}".format(parsed_response))
                cprModel = Forecast(**parsed_response)

                message = cprModel.forecast_obj
                self.vip.pubsub.publish(
                    peer="pubsub",
                    topic=self._conf['topic'],
                    headers={},
                    message=message)

                self.status_pending = False # allow new model requests to be made

                # receive_interval optimization
                request_process_time = round(time.time() - self.start_time, 2)
                _log.info("Request process time was: {}".format(request_process_time))
                self.process_times.append(request_process_time)
                receive_interval = sum(self.process_times)/len(self.process_times)


            elif status == 'Pending':
                _log.info("model still pending, waiting...")


def main(argv=sys.argv):
    '''Main method called by platform'''
    _log.info("Main method")
    utils.vip_main(CPRPub)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
