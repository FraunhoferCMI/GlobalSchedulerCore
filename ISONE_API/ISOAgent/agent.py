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
import pprint
import datetime, isodate, pytz
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
                "da_topic": "datalogger/isone/da_lmp/4332",

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
            today = datetime.datetime.now()
            nowstr = isodate.datetime_isoformat(today)
            tz = pytz.timezone("UTC")
            for day in [
                    today,
                    today + datetime.timedelta(days=1)]:
                req = requests.get(
                    datetime.datetime.strftime(day,path),
                    headers={"Accept":"application/json"},
                    auth=(
                        self._config['username'],
                        self._config['password']))
                _log.debug("Fetching {}, got {}".format(day, req.status_code))
                if req.status_code == 200:
                    Rl = req.json()["HourlyLmps"]
                    # this is to address how empty lists are served as the blank string
                    if Rl:
                        Rl = Rl['HourlyLmp']
                        _log.warning("GOt data for {}".format(day))
                    else:
                        _log.warning("NO data for {}".format(day))
                        continue
                    message = {
                        #d.astimezone(pytz.timezone("UTC")).isoformat(
                        #for R in Rl:
                        "LMP": {
                            "Readings":
                            [  [
                                isodate.parse_datetime(
                                R["BeginDate"]).astimezone(tz).isoformat()
                                ,R["LmpTotal"]]
                               for R in Rl
                               if R["BeginDate"] > nowstr
                            ],
                            "Units":"Dollar",
                            "tz":"UTC",
                            "data_type":"float"}}
                    self.vip.pubsub.publish(
                        peer="pubsub",
                        topic=self._config['da_topic'],
                        headers={},
                        message=message)
                    _log.debug(pprint.pformat(req.json()))

        @Core.periodic(period = query_interval)
        def query_isone(self):
            self.get_future()
            tz = pytz.timezone("UTC")
            a = self._config['LMP']
            req = requests.get(
                self._config['baseurl']+a,
                headers={"Accept":"application/json"},
                auth=(
                    self._config['username'],
                    self._config['password']))            
            _log.debug("Fetching {}, got {}".format(a, req.status_code))
            if req.status_code == 200:
                _log.warning("GOT RT PRICE")
                R = req.json()["FiveMinLmp"][0]
                _log.warning(R["BeginDate"])
                DT = isodate.parse_datetime(
                    R["BeginDate"]).astimezone(tz)
                DT -= datetime.timedelta(seconds=DT.second)
                message = {
                    "LMP":{
                        "Readings":
                           [
                               DT.isoformat(),                               
                               R["LmpTotal"]],
                        "Units":"Dollar",
                        "tz":"UTC",#America/New_York",
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
