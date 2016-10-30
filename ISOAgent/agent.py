import logging
import sys
import requests

from volttron.platform.vip.agent import Agent, PubSub, Core
from volttron.platform.agent import utils

utils.setup_logging()
_log = logging.getLogger(__name__)

import requests

INTERVAL=300

class ISOAgent(Agent):
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

    @Core.periodic(INTERVAL)
    def query_isone(self):
        a = self._config['LMP']
        req = requests.get(
            self._config['baseurl']+a,
            headers={"Accept":"application/json"},
            auth=(
                self._config['username'],
                self._config['password']))
        _log.debug("Fetching {}, got {}".format(a, req.status_code))
        _log.debug(pprint.pformat(req.json())

            
def main(argv=sys.argv):
    '''Main method called by the platform.'''
    utils.vip_main(ISOAgent)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
