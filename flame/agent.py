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

import logging
import sys
import requests
import pprint, pickle
from datetime import timedelta, datetime
import pytz
import os
from volttron.platform.messaging.health import STATUS_GOOD
from volttron.platform.vip.agent import Agent, PubSub, Core, RPC
from volttron.platform.agent import utils
from volttron.platform.agent.utils import jsonapi
from volttron.platform.messaging import topics
from volttron.platform.messaging import headers as headers_mod
import xml.etree.ElementTree as ET
from gs_identities import *
from gs_utilities import get_schedule, ForecastObject, Forecast
import csv
import pandas

from .FLAME import Baseline, LoadShift
from websocket import create_connection
WEBSOCKET_URL = "ws://flame.ipkeys.com:8888/socket/msg"

utils.setup_logging()
_log = logging.getLogger(__name__)

__version__ = "0.1"

# constants
MINUTES_PER_HR = 60
MINUTES_PER_DAY = 24 * MINUTES_PER_HR
MINUTES_PER_YR = 365 * MINUTES_PER_DAY


class FLAMECommsAgent(Agent):
    """
    Stubbed out version of a FLAME communications agent.
    """

    ##############################################################################
    def __init__(self, config_path, **kwargs):
        super(FLAMECommsAgent, self).__init__(**kwargs)

        self.volttron_root = os.getcwd()
        self.volttron_root = self.volttron_root + "/../../../../"

        self.default_config = {
            "demand_forecast_topic": "devices/flame/forecast/all",
            "loadshift_forecast_topic": "devices/flame/loadshift_forecast/all",     #FIXME - doublecheck naming
            "DEFAULT_HEARTBEAT_PERIOD": 5,
            "DEFAULT_MESSAGE": 'FLAME_COMMS_MSG',
            "DEFAULT_AGENTID": "FLAME_COMMS_AGENT",
        }
        self._config = self.default_config.copy()
        self._agent_id = self._config.get("DEFAULT_AGENTID")
        self._message = self._config.get("DEFAULT_MESSAGE")
        self._heartbeat_period = self._config.get('DEFAULT_HEARTBEAT_PERIOD')

        self.vip.config.set_default("config", self.default_config)
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")


        # initialize class variables here:
        self.initialization_complete = 0
        # instantiate messages
        # ...
        # baseline_msg = new_baseline_constructor
        # loadshift_msg = new_loadshift_constructor


    ##############################################################################
    def configure(self, config_name, action, contents):
        self._config.update(contents)
        # make sure config variables are valid
        try:
            pass
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))

    ##############################################################################
    @Core.receiver('onstart')
    def onstart(self, sender, **kwargs):
        if self._heartbeat_period != 0:
            self.vip.heartbeat.start_with_period(self._heartbeat_period)
            self.vip.health.set_status(STATUS_GOOD, self._message)

        ### Get gs_start_time
        try:
            v1 = self.vip.rpc.call("executiveagent-1.0_1", "get_gs_start_time").get(timeout=5)
            self.gs_start_time = datetime.strptime(v1, "%Y-%m-%dT%H:%M:%S")  # .replace()  # was .%f
        except:
            _log.info("FLAME comms - gs_start_time not found.  Using current time as gs_start_time")
            self.gs_start_time = utils.get_aware_utc_now().replace(microsecond=0)
            self.gs_start_time = self.gs_start_time.replace(tzinfo=None)
            _log.info("GS STart time is " + str(self.gs_start_time))

        self.initialization_complete = 1


    ##############################################################################
    @RPC.export
    def load_option_select(self):
        """
        maybe -
        :return:
        """

        pass


    ##############################################################################
    @Core.periodic(period=DEMAND_FORECAST_QUERY_INTERVAL)   #### code for calling something periodically
    def query_baseline(self):
        "Queries the FLAME server for baseline message"
        if self.initialization_complete == 1:
            _log.info("querying baseline")
            # Baseline
            start =  '2018-03-01T00:00:00'
            granularity = 'PT1H'
            duration = 'PT24H'
            ws = create_connection(WEBSOCKET_URL, timeout=None)
            bl = Baseline(start, granularity, duration, ws)
            bl.process()
            ws.close()

            #### code for publishing to the volttron bus
            message_parts = bl.fo
            forecast = Forecast(**message_parts)
            message = forecast.forecast_obj
            _log.info(message)
            # message = bl.forecast    # call to demand forecast object class thingie
            # message = self.baseline_msg.process()    # call to demand forecast object class thingie
            comm_status = 1 # were there errors?
            self.vip.pubsub.publish(
                peer="pubsub",
                topic=self._config['demand_forecast_topic'],
                headers={},
                message=message)


            #self.vip.pubsub.publish(
            #    peer="pubsub",
            #    topic=self._config['demand_forecast_topic'],
            #    headers={},
            #    message=[{"comm_status": 1}, {"comm_status": {'type': 'int', 'units': 'none'}}])

        else:
            _log.info("initialization incomplete!!")


    ##############################################################################
    @Core.periodic(period=LOADSHIFT_QUERY_INTERVAL)
    def query_loadshift(self):
        """
        queries the FLAME server for baseline message
        """
        if self.initialization_complete == 1:
            _log.info("querying loadshift")


            ws = create_connection(WEBSOCKET_URL, timeout=None)
            ls = LoadShift(ws)
            ls.process()
            # message = ls.fo.forecast_values    # call to demand forecast object class thingie
            ws.close()
            # message = self.load_shift_msg.process()    # call to demand forecast object class thingie
            comm_status = 1 # were there errors?
            for option, message_parts in ls.fos.items():
                forecast = Forecast(**message_parts)
                message = forecast.forecast_obj
                _log.info(message)
                self.vip.pubsub.publish(
                    peer="pubsub",
                    topic=self._config['loadshift_forecast_topic'],
                    headers={},
                    message=message)


            # self.vip.pubsub.publish(
            #     peer="pubsub",
            #     topic=self._config['loadshift_forecast_topic'],
            #     headers={},
            #     message=[{"comm_status": 1}, {"comm_status": {'type': 'int', 'units': 'none'}}])

        else:
            _log.info("initialization incomplete!!")


def main(argv=sys.argv):
    '''Main method called by the platform.'''
    utils.vip_main(FLAMECommsAgent)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
