# Copyright © 2017, The Fraunhofer Center for Sustainable Energy
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

from __future__ import absolute_import

from datetime import datetime
import logging
import sys
import os
import csv
import json
import gevent
#import DERDevice
from volttron.platform.messaging.health import STATUS_GOOD
from volttron.platform.vip.agent import Agent, Core, PubSub, compat, RPC
from volttron.platform.agent import utils
from volttron.platform.messaging import headers as headers_mod
from volttron.platform.agent.known_identities import (
    VOLTTRON_CENTRAL, VOLTTRON_CENTRAL_PLATFORM, CONTROL, CONFIGURATION_STORE)

from . import settings


utils.setup_logging()
_log = logging.getLogger(__name__)
__version__ = '1.0'


##############################################################################
class UIAgent(Agent):
    """
    Runs SunDial Executive state machine
    """

    def __init__(self, config_path, **kwargs):
        super(UIAgent, self).__init__(**kwargs)
        self.default_config = {
            "DEFAULT_MESSAGE" :'UI Message',
            "DEFAULT_AGENTID": "UI",
            "DEFAULT_HEARTBEAT_PERIOD": 5,
            "log-level":"INFO"
        }
        self._config = self.default_config.copy()
        self._agent_id = self._config.get("DEFAULT_AGENTID")
        self._message = self._config.get("DEFAULT_MESSAGE")
        self._heartbeat_period = self._config.get('DEFAULT_HEARTBEAT_PERIOD')        
        #self.configure(None,None,self.default_config)
        self.vip.config.subscribe(
            self.configure,
            actions=["NEW", "UPDATE"],
            pattern="config")

 


    ##############################################################################
    def configure(self,config_name, action, contents):
        self._config.update(contents)
        log_level = self._config.get('log-level', 'INFO')
        if log_level == 'ERROR':
            self._logfn = _log.error
        elif log_level == 'WARN':
            self._logfn = _log.warn
        elif log_level == 'DEBUG':
            self._logfn = _log.debug
        else:
            self._logfn = _log.info
        
        # make sure config variables are valid
        try:
            pass
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
    
    @Core.receiver('onsetup')
    def onsetup(self, sender, **kwargs):
        # Demonstrate accessing a value from the config file
        _log.info(self._message)
        self._agent_id = self._config.get('agentid')

    @Core.receiver('onstart')
    def onstart(self, sender, **kwargs):
        if self._heartbeat_period != 0:
            self.vip.heartbeat.start_with_period(self._heartbeat_period)
            self.vip.health.set_status(STATUS_GOOD, self._message)


    @Core.periodic(10)
    def set_point(self):
        """
        This is a method that periodically polls a designated file for a command to set a point for a
        SiteManager via an RPC call.
        Could be altered so that it is instead polling a database, or just issuing a command
        based on a specific set of internal variables / values.

        assume csv file is rows with:
        agentID, siteDERDevicepath, Attribute, EndPt, value
        e.g.,
        ShirleySouth,ShirleySouth,ModeCtrl,OpModeCtrl,1

        :return:
        """

        cwd = os.getcwd()
        cwd = cwd+"/../../../../"
        _log.info("Current directory is: "+cwd)
        fname = cwd+"UI_cmd.json" #"/home/matt/sundial/UI/system_cmds.csv"
        try:
            #ret = self.vip.rpc.call("executiveagent-1.0_1", "set_mode", 2).get()

            with open(fname, 'rb') as jsonfile:
                cmds = json.load(jsonfile)
            
            for cur_cmd in cmds:
               _log.info("UI_CMD: New incoming command: "+cur_cmd["AgentID"]+"; function - "+cur_cmd["FcnName"])
               for arg in cur_cmd["args"]:
                   _log.info("UI_CMD: Args = "+str(arg))
               # Not sure why this is required, but vip.rpc.call required me to recast cur_cmd["AgentID"]
               # as a string
               self.vip.rpc.call(str(cur_cmd["AgentID"]), cur_cmd["FcnName"], *cur_cmd["args"])               

            try:
                os.remove(fname) # delete after commands have been issued
            except OSError:
                pass

        except IOError as e:
            # file name not found implies that the device does not have any children
            print("NO Site Manager Cmd found!! Skipping!")
            cwd = os.getcwd()
            _log.info("Current directory: "+cwd)
            pass


    @PubSub.subscribe('pubsub', 'devices/Shirley-MA/South/PMC/all')
    def ieb_scrape_to_datafile(self, peer, sender, bus,  topic, headers, message):

        if sender == 'pubsub.compat':
            message = compat.unpack_legacy_message(headers, message)
        data = message[0]

        TimeStamp = datetime.strptime(
            headers["TimeStamp"][:19],
            "%Y-%m-%dT%H:%M:%S"
        )

        fname = "/home/matt/sundial/UI/testlogfile.txt"
        with open(fname, 'a') as datafile:
            for k, v in data.items():
                datafile.write(str(TimeStamp)+" "+str(k)+" "+str(v)+"\n")



def main(argv=sys.argv):
    '''Main method called by the eggsecutable.'''
    try:
        utils.vip_main(UIAgent)
    except Exception as e:
        _log.exception('unhandled exception')

        
if __name__ == '__main__':
    # Entry point for script 
    sys.exit(main())
