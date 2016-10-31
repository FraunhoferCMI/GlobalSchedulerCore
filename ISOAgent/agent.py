import logging
import sys
import requests

from volttron.platform.vip.agent import Agent, PubSub, Core
from volttron.platform.agent import utils

utils.setup_logging()
_log = logging.getLogger(__name__)

import requests

INTERVAL=300
def ISOpub(config_path, **kwargs):
    conf = utils.load_config(config_path)
    query_interval = conf.get("interval",300)
    
    class ISOAgent(Agent):
        #
        def __init__(self, config_path, **kwargs):
            super(TestAgent, self).__init__(**kwargs)
            
            self.default_config = {
                "interval":600,
                "username": "ocschwar@mit.edu",
                "password":"VolttronShines",
                "baseurl":"https://webservices.iso-ne.com/api/v1.1/"
                "LMP":"/fiveminutelmp/current/location/4332"
            }
            
            self.vip.config.set_default("config", self.default_config)
            self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")
            
        def configure(self,config_name, action, contents):
            self._config = self.default_config.copy()
            self._config.update(contents)
            
            # make sure config variables are valid
            try:
                pass
            except ValueError as e:
                _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
                
        @Core.periodic(period = query_interval)
        def query_isone(self):
            a = self._config['LMP']
            req = requests.get(
                self._config['baseurl']+a,
                headers={"Accept":"application/json"},
                auth=(
                    self._config['username'],
                    self._config['password']))            
            _log.debug("Fetching {}, got {}".format(a, req.status_code))
            if req.status_code == 200:
                self.publish_json(self, topic, {}, req.json())
            _log.debug(pprint.pformat(req.json()))
    #
    ISOAgent.__name__ = "ISOPub"
    return ISOAgent(**kwargs)
            
def main(argv=sys.argv):
    '''Main method called by the platform.'''
    utils.vip_main(ISOPub)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
