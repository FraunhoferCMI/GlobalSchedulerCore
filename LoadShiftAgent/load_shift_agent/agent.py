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
import pandas as pd
from .VirtualPlant import VirtualESS

utils.setup_logging()
_log = logging.getLogger(__name__)
__version__ = '1.0'



##############################################################################
class LoadShiftAgent(Agent):
    """
    Interface for sending instructions from command line to GS
    """

    ##############################################################################
    def __init__(self, config_path, **kwargs):
        super(LoadShiftAgent, self).__init__(**kwargs)
        self.default_config = {
            "DEFAULT_MESSAGE" :'VP Message',
            "DEFAULT_AGENTID": "VP",
            "DEFAULT_HEARTBEAT_PERIOD": 5,
            "loadshift_forecast_topic": "devices/flame/loadshift_forecast/all",
            "load_option_select_topic": "devices/flame/load_shift_select/all",
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

        self.options_pending = False
        self.load_option_dict = {'Forecast': None,
                                 'ID': None,
                                 'Duration': None,
                                 'Resolution': None,
                                 'Time': None,
                                 'nOptions': None}


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


        # Subscribe to the loadshift topic
        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=self._config["loadshift_forecast_topic"],
                                  callback=self.parse_load_option_msgs)



        #self.query_loadshift_options()

    ##############################################################################
    @Core.periodic(3600)
    def query_loadshift_options(self):
        """
        wrapper to generate a call to the FLAME server to do a load shift query
        :return:
        """
        cur_time = datetime.now()
        scheduled_hr = 16
        _log.info('******** LoadShiftAgent: Checking Load Shift Query Schedule *************')
        if cur_time.hour == scheduled_hr:
            tst = self.vip.rpc.call('flameagent-0.1_1',
                                                  'query_loadshift',
                                                  use_static_price_map=True).get()
            self.options_pending = True
        else:
            _log.info('LoadShiftAgent: Not Scheduled Time (configured to '+str(scheduled_hr)+')')
        # to check!!! do we need to update the time stamp to addres utc issues?
        pass


    ##############################################################################
    def parse_load_option_msgs(self, peer, sender, bus, topic, headers, message):

        """
        Consumes load options published on the message bus.
        Parses load options message into a DataFrame, selects the best, and
        communicates the selection to the FLAME agent
        :return:
        """
        _log.info("******** LoadShiftAgent: Receiving Load Shift Messages!!!*******")

        if type(message) is dict:
            data = message
            meta_data = None
        else:
            data = message[0]
            meta_data = message[1]

        # populate load_option_dict with incoming data
        for k,v in data.items():
            try:
                self.load_option_dict[k] = v
            except KeyError:
                _log.info('Parse Load Options: ' +k+' not found - skipping!')

        # once the load_option_dict data structure is fully populated, convert to a dataframe and send to
        # load option select routine
        if ((self.load_option_dict['Forecast'] is not None) &
            (self.load_option_dict['ID'] is not None) &
            (self.load_option_dict['Time'] is not None)):
            self.options_pending = True
            _log.info('***** Load Options - Message Complete - Parsing!!! ****')
            self.load_options = pd.DataFrame(data=self.load_option_dict['Forecast']).T
            self.load_options.index = pd.to_datetime(self.load_option_dict['Time'])
            self.load_options.columns = self.load_option_dict['ID']
            _log.debug(self.load_options)

            self.load_option_select()

    ##############################################################################
    #@Core.periodic(60)
    def load_option_select(self):
    #def parse_load_option_msgs(self, peer, sender, bus, topic, headers, message):
        val = self.load_options.columns[1]

        self.vip.rpc.call('flameagent-0.1_1',
                          'load_option_select',
                          val,
                          enable_load_select=True)


        self.load_option_dict['Forecast'] = None
        self.load_option_dict['ID'] = None
        self.load_option_dict['Time'] = None
        pass



def main(argv=sys.argv):
    '''Main method called by the eggsecutable.'''
    try:
        utils.vip_main(LoadShiftAgent)
    except Exception as e:
        _log.exception('unhandled exception')

        
if __name__ == '__main__':
    # Entry point for script 
    sys.exit(main())
