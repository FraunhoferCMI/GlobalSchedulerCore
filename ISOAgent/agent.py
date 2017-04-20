import logging
import sys
import requests
import pprint
import datetime, isodate
from volttron.platform.vip.agent import Agent, PubSub, Core
from volttron.platform.agent import utils
from volttron.platform.agent.utils import jsonapi
from volttron.platform.messaging import topics
from volttron.platform.messaging import headers as headers_mod


utils.setup_logging()
_log = logging.getLogger(__name__)

__version__="0.1"


def ISOPub(config_path, **kwargs):
    conf = utils.load_config(config_path)
    query_interval = conf.get("interval",300)
    topic = conf.get("topic","/isone/lmp/4332")
    class ISOAgent(Agent):
        #
        """

TODO: 

Multiple REST calls, with a transform for each of them. 


Example datum: 
2016-11-01 18:13:34,293 (ISOAgentagent-0.1 2737) ISOAgent.agent ERROR: Fetching /fiveminutelmp/current/location/4332, got 200
2016-11-01 18:13:34,293 (ISOAgentagent-0.1 2737) ISOAgent.agent ERROR: {u'FiveMinLmp': [{u'BeginDate': u'2016-11-01T14:10:02.000-04:00',
                  u'CongestionComponent': 0.07,
                  u'EnergyComponent': 17,
                  u'LmpTotal': 16.88,
                  u'Location': {u'$': u'LD.AYER    69',
                                u'@LocId': u'4332',
                                u'@LocType': u'NETWORK NODE'},
                  u'LossComponent': -0.19}]}

        """
        
        def __init__(self, config_path, **kwargs):
            super(ISOAgent, self).__init__(**kwargs)
            
            self.default_config = {
                "interval":290,
                "username": "ocschwar@mit.edu",
                "password":"VolttronShines",
                "baseurl":"https://webservices.iso-ne.com/api/v1.1/",
                "LMP":"/fiveminutelmp/current/location/4332",
                "DA" : "/hourlylmp/da/final/day/%Y%m%d/location/4332",
                "topic": "datalogger/isone/lmp/4332",

            }
            self._config = self.default_config.copy()
            
            self.vip.config.set_default("config", self.default_config)
            self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")
            
        def configure(self,config_name, action, contents):
            self._config.update(contents)
            
            # make sure config variables are valid
            try:
                pass
            except ValueError as e:
                _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))

        def get_future(self):
            path = self._config["baseurl"] + self._config["DA"]
            day = datetime.datetime.now()
            nowstr = isodate.datetime_isoformat(day)
            req = requests.get(
                datetime.datetime.strftime(day,path),
                headers={"Accept":"application/json"},
                auth=(
                    self._config['username'],
                    self._config['password']))
            _log.debug("Fetching {}, got {}".format(a, req.status_code))
            if req.status_code == 200:
                Rl = req.json()["HourlyLmps"]['HourlyLmp']
                message = {
                    "LMP": {
                        "Readings":
                        [  [R["BeginDate"],R["LmpTotal"]]
                           for R in Rl
                           if R["BeginDate"] > nowstr
                        ],
                        "Units":"Dollar",
                        "tz":"America/NewYork",
                        "data_type":"float"}}
                self.vip.pubsub.publish(
                    peer="pubsub",
                    topic=self._config['topic'],
                    headers={},
                    message=message)
                #self.publish_json(self, topic, {}, req.json())
            _log.debug(pprint.pformat(req.json()))

        @Core.periodic(period = query_interval)
        def query_isone(self):
            self.get_future()
            a = self._config['LMP']
            req = requests.get(
                self._config['baseurl']+a,
                headers={"Accept":"application/json"},
                auth=(
                    self._config['username'],
                    self._config['password']))            
            _log.debug("Fetching {}, got {}".format(a, req.status_code))
            if req.status_code == 200:
                R = req.json()["FiveMinLmp"][0]
                message = {
                    "LMP":{
                        "Readings":
                           [  R["BeginDate"],R["LmpTotal"]],
                        "Units":"Dollar",
                        "tz":"America/NewYork",
                        "data_type":"float"}}
                self.vip.pubsub.publish(
                    peer="pubsub",
                    topic=self._config['topic'],
                    headers={},
                    message=message)
                #self.publish_json(self, topic, {}, req.json())
            _log.debug(pprint.pformat(req.json()))
    #
    ISOAgent.__name__ = "ISOPub"
    return ISOAgent(config_path,**kwargs)
            
def main(argv=sys.argv):
    '''Main method called by the platform.'''
    utils.vip_main(ISOPub)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
