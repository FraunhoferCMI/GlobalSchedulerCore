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

from __future__ import absolute_import

from datetime import datetime
import logging
import sys
import os
import csv
import json
import gevent
from volttron.platform.messaging.health import STATUS_GOOD
from volttron.platform.vip.agent import Agent, Core, PubSub, compat, RPC
from volttron.platform.agent import utils
from volttron.platform.messaging import headers as headers_mod
from volttron.platform.agent.known_identities import (
    VOLTTRON_CENTRAL, VOLTTRON_CENTRAL_PLATFORM, CONTROL, CONFIGURATION_STORE)

from gs_identities import (UI_CMD_POLLING_FREQUENCY)

from .VirtualPlant import VirtualESS

utils.setup_logging()
_log = logging.getLogger(__name__)
__version__ = '1.0'

VP_UPDATE_PD = 10  # seconds
TEST_PD = 10 # seconds
TEST_MODE = False
test_schedule = [500, -500, -300, -250, 100, -100, -1000, 1000, -50, 50, 0, 500]


##############################################################################
class VirtualPlantAgent(Agent):
    """
    Interface for sending instructions from command line to GS
    """

    ##############################################################################
    def __init__(self, config_path, **kwargs):
        super(VirtualPlantAgent, self).__init__(**kwargs)
        self.default_config = {
            "DEFAULT_MESSAGE" :'VP Message',
            "DEFAULT_AGENTID": "VP",
            "DEFAULT_HEARTBEAT_PERIOD": 5,
            "log-level":"INFO"
        }
        self._config = self.default_config.copy()
        self._agent_id = self._config.get("DEFAULT_AGENTID")
        self._message = self._config.get("DEFAULT_MESSAGE")
        self._heartbeat_period = self._config.get('DEFAULT_HEARTBEAT_PERIOD')        
        self.vip.config.subscribe(
            self.configure,
            actions=["NEW", "UPDATE"],
            pattern="config")

        self.virtual_plant = VirtualESS()
        self.topic = "devices/VirtualESSPlant/all"
        self.test_ind = 0


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
    
    ##############################################################################
    @Core.receiver('onsetup')
    def onsetup(self, sender, **kwargs):
        # Demonstrate accessing a value from the config file
        _log.info(self._message)
        self._agent_id = self._config.get('agentid')

    ##############################################################################
    @Core.receiver('onstart')
    def onstart(self, sender, **kwargs):
        if self._heartbeat_period != 0:
            self.vip.heartbeat.start_with_period(self._heartbeat_period)
            self.vip.health.set_status(STATUS_GOOD, self._message)


    ##############################################################################
    @RPC.export
    def set_real_pwr(self, cmd):
        """
        publishes current state of the ESS
        :return:
        """
        _log.info('Received new command: setting power to '+str(cmd))
        self.virtual_plant.set_real_pwr(float(cmd))
        _log.info('New Power Commnad = '+str(self.virtual_plant.pwrCmd_kW))
        pass

    ##############################################################################
    @Core.periodic(VP_UPDATE_PD)
    def publish_state(self):
        """
        publishes current state of the ESS

        to do
        publish end points (from data map file) onto IEB --> possibly want to auto generate these from data map
        configure siteConfiguration to include a virtual plant
        configure system configuration to include a virtual plant
        write a set point routine that sends a real power commmand to this agent in DERDevice
        :return:
        """
        self.virtual_plant.update_state()
        message = self.virtual_plant.serialize()
        _log.info('VP Agent: '+str(message))
        self.vip.pubsub.publish(
            peer="pubsub",
            topic=self.topic,  # self._conf['topic'], self.topics[k]
            headers={},
            message=message)

        pass

    ##############################################################################
    @Core.periodic(TEST_PD)
    def test_virtual_plant(self):
        if TEST_MODE == True:

            self.set_real_pwr(test_schedule[self.test_ind])
            if self.test_ind == (len(test_schedule) - 1):
                self.test_ind = 0
            else:
                self.test_ind = self.test_ind+1


def main(argv=sys.argv):
    '''Main method called by the eggsecutable.'''
    try:
        utils.vip_main(VirtualPlantAgent)
    except Exception as e:
        _log.exception('unhandled exception')

        
if __name__ == '__main__':
    # Entry point for script 
    sys.exit(main())
