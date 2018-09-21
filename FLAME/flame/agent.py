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
# import datetime
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
from HistorianTools import publish_data
import csv
import pandas

# from .FLAME import Baseline, LoadShift, LoadSelect, LoadReport, Status, format_timeperiod
from .FLAME import *
import websocket
from websocket import create_connection
websocket.setdefaulttimeout(60)
import ssl

utils.setup_logging()
_log = logging.getLogger(__name__)

__version__ = "0.1"

# constants
MINUTES_PER_HR = 60
MINUTES_PER_DAY = 24 * MINUTES_PER_HR
MINUTES_PER_YR = 365 * MINUTES_PER_DAY

# TODO migrate constants that gs_identities

# Time interval at which real-time load data should be retrieved from FLAME server and published to IEB
# DEMAND_REPORT_SCHEDULE = 10 # already in gs_identities

# Time interval at which load forecast data should be retrieved from FLAME server and published to IEB
# DEMAND_FORECAST_QUERY_INTERVAL = 5 # already in gs_identities

# Time interval at which real-time load data should be retrieved from FLAME server and published to IEB
# LOADSHIFT_QUERY_INTERVAL = 5 # seconds # already in gs_identities

# Desired resolution of forecast data points.  (ISO 8601 duration)
# DEMAND_FORECAST_RESOLUTION = "PT1H"
# DEMAND_REPORT_DURATION =  24 # Duration of load request reports in hours
# Time resolution of load request report
# DEMAND_REPORT_RESOLUTION = "PT1H"
# STATUS_REPORT_SCHEDULE = 1 # in hours # Time interval at which the GS should poll the FLAME to check for status

class FLAMECommsAgent(Agent):
    """
    Stubbed out version of a FLAME communications agent.
    """

    ##############################################################################
    def __init__(self, config_path, **kwargs):
        super(FLAMECommsAgent, self).__init__(**kwargs)

        _log.info("CONFIGURATION PATH IS %s" % config_path)
        self.volttron_root = os.getcwd()
        self.volttron_root = self.volttron_root + "/../../../../"

        self.default_config = {
            "demand_forecast_topic": "devices/flame/forecast/all",
            "comm_status_topic": "devices/flame/all",
            "loadshift_forecast_topic": "devices/flame/loadshift_forecast/all",     #FIXME - doublecheck naming
            "load_option_select_topic": "devices/flame/load_shift_select/all",
            "load_report_topic": "datalogger/flame/load_report",
            "current_load_topic": "devices/flame/load_report/all",
            "DEFAULT_HEARTBEAT_PERIOD": 5,
            "DEFAULT_MESSAGE": 'FLAME_COMMS_MSG',
            "DEFAULT_AGENTID": "FLAME_COMMS_AGENT",
            "facilities": ["Facility1", "Facility2", "Facility3"]
        }
        self._config = self.default_config.copy()
        self._agent_id = self._config.get("DEFAULT_AGENTID")
        self._message = self._config.get("DEFAULT_MESSAGE")
        self._heartbeat_period = self._config.get('DEFAULT_HEARTBEAT_PERIOD')

        self.vip.config.set_default("config", self.default_config)
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

        self.comm_status = 1 # indicates if communications are ok


        # initialize class variables here:
        self.initialization_complete = 0
        # instantiate messages
        # ...
        # baseline_msg = new_baseline_constructor
        # loadshift_msg = new_loadshift_constructor

        ### CREATE WEBSOCKET ###
        ws_url = "wss://flame.ipkeys.com:9443/socket/msg"
        # old way
        # ws = create_connection(url, timeout=None)
        # insecure way, use this if certificate is giving problems
        sslopt = {"cert_reqs": ssl.CERT_NONE}
        # secure way
        # sslopt = {"ca_certs": 'IPKeys_Root.pem'}

        ws = create_connection(ws_url, sslopt=sslopt)

        self.websocket = ws
        _log.info("Web Socket INITIALIZED")

        self.cur_load = {"Load": -1,
                         "Time": None}

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
            self.gs_start_time = datetime.strptime(v1, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=pytz.UTC)
        except:
            _log.info("FLAME comms - gs_start_time not found.  Using current time as gs_start_time")
            # self.gs_start_time = utils.get_aware_utc_now().replace(microsecond=0)
            self.gs_start_time = datetime.now().replace(microsecond=0, tzinfo=pytz.UTC)
            # self.gs_start_time = utils.get_aware_utc_now().replace(microsecond=0)
            #self.gs_start_time = self.gs_start_time.replace(tzinfo=None)
            #self.gs_start_time = datetime.now().replace(microsecond=0)
            _log.info("GS STart time is " + str(self.gs_start_time))

        self.initialization_complete = 1
        self.get_load_report()   # do this first - pre-load with values for other fcns to reference
        self.query_baseline()
        #self.query_loadshift()
        #self.request_status()

    ##############################################################################
    @RPC.export
    def load_option_select(self, optionID):
        """
        Communicate load option choice to IPKeys and publish this to VOLTTRON
        topic.
        """

        _log.info("selecting load option")
        # ws = create_connection(WEBSOCKET_URL, timeout=None)
        lsel = LoadSelect(websocket=self.websocket, optionID=optionID)
        lsel.process()

        _log.info("LoadSelect status: " + lsel.status) # TODO setup self.comm_status check based on status
        self.vip.pubsub.publish(
            peer="pubsub",
            topic=self._config['load_option_select_topic'],
            headers={},
            message=optionID) # CHECK if this is what's wanted
            # message=lsel.status) # CHECK if this is what's wanted
        return None

    @Core.periodic(period=STATUS_REPORT_SCHEDULE)
    def request_status(self):
        # ws = create_connection(WEBSOCKET_URL, timeout=None)
        if self.initialization_complete == 1:
            status = Status(websocket=self.websocket)
            status.process()
            _log.info("LoadSelect alertStatus: " + str(status.alertStatus))
            _log.info("LoadSelect currentProfile: " + str(status.currentProfile))

        return None

    ##############################################################################
    @Core.periodic(period=DEMAND_FORECAST_QUERY_INTERVAL)   #### code for calling something periodically
    def query_baseline(self):
        "Queries the FLAME server for baseline message"
        if self.initialization_complete == 1:
            _log.info("querying baseline")
            # Baseline

            ###  convert GS time to local time #####
            start_time = datetime.strptime(get_schedule(self.gs_start_time,
                                                        resolution=SSA_SCHEDULE_RESOLUTION),
                                           "%Y-%m-%dT%H:%M:%S.%f")

            # websocket = create_connection( WEBSOCKET_URL, timeout=None)
            if USE_SCALED_LOAD == True:
                start_time = start_time.replace(minute=0, second=3, microsecond=0)
            else:
                start_time = start_time.replace(minute=0, second=0, microsecond=0)
            start_time = start_time.replace(tzinfo=pytz.UTC)
            start_time = start_time.astimezone(pytz.timezone('US/Eastern')).strftime("%Y-%m-%dT%H:%M:%S")

            baseline_kwargs = dict(
                start =  start_time,
                granularity = DEMAND_FORECAST_RESOLUTION,
                duration = 'PT24H',
                websocket = self.websocket
            )
            _log.debug('setup baseline')
            bl = Baseline(**baseline_kwargs)
            bl.process()
            # websocket.close()
            _log.debug('baseline setup')

            #### code for publishing to the volttron bus
            message_parts = bl.fo
            forecast = Forecast(**message_parts)
            message = forecast.forecast_obj
            _log.info(message)
            # message = bl.forecast    # call to demand forecast object class thingie
            # message = self.baseline_msg.process()    # call to demand forecast object class thingie
            comm_status = 1 # were there errors?

            _log.info(self.cur_load["Time"])
            _log.info(forecast.forecast_values["Time"][0])

            if self.cur_load["Time"] == forecast.forecast_values["Time"][0]:
                _log.info("Replacing forecast load = "+str(forecast.forecast_values["Forecast"][0])+" with "+ str(self.cur_load["Load"]))
                forecast.forecast_values["Forecast"][0] = self.cur_load["Load"]

            publish_data(self,
                         "flame/forecast",
                         forecast.forecast_meta_data["Forecast"]["units"],
                         "tPlus1",
                         forecast.forecast_values["Forecast"][1],
                         TimeStamp_str=forecast.forecast_values["Time"][1])

            publish_data(self,
                         "flame/forecast",
                         forecast.forecast_meta_data["Forecast"]["units"],
                         "tPlus5",
                         forecast.forecast_values["Forecast"][5],
                         TimeStamp_str=forecast.forecast_values["Time"][5])

            publish_data(self,
                         "flame/forecast",
                         forecast.forecast_meta_data["Forecast"]["units"],
                         "tPlus23",
                         forecast.forecast_values["Forecast"][23],
                         TimeStamp_str=forecast.forecast_values["Time"][23])

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
    #@Core.periodic(period=LOADSHIFT_QUERY_INTERVAL)
    def query_loadshift(self):
        """
        queries the FLAME server for baseline message
        """
        if self.initialization_complete == 1:
            _log.info("querying loadshift")

            gcm_kwargs = {'n_time_steps': 24,
                          'search_resolution': 25}
            price_map = self.vip.rpc.call('executiveagent-1.0_1',
                                         'generate_cost_map'
                                         # **gcm_kwargs
                                         ).get(timeout=5)

            # ws = create_connection(WEBSOCKET_URL, timeout=None)
            ls = LoadShift(websocket=self.websocket, price_map=price_map)
            ls.process()
            # message = ls.fo.forecast_values    # call to demand forecast object class thingie
            # ws.close()
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

    ##############################################################################
    @Core.periodic(period=DEMAND_REPORT_SCHEDULE)
    def get_load_report(self):
        '''
        Request standardized Load Report from FLAME server.
        '''
        # determine report start time
        #FIXME - should use get_schedule()

        if self.initialization_complete == 1:
            current_time = datetime.now(pytz.timezone('US/Eastern')).replace(microsecond=0, second=0, minute=0)
            utc_now_str = current_time.astimezone(pytz.timezone('UTC')).strftime("%Y-%m-%dT%H:%M:%S")
            time_delta = timedelta(minutes=DEMAND_REPORT_DURATION)
            start_time = current_time - time_delta
            dstart = start_time.strftime("%Y-%m-%dT%H:%M:%S")
            duration = format_timeperiod(DEMAND_REPORT_DURATION)
            sampleInterval = format_timeperiod(DEMAND_REPORT_RESOLUTION)

            loadReport_kwargs = {
                "dstart": dstart, # start time for report
                "sampleInterval": sampleInterval, # sample interval
                "duration": duration, # "PT" + str(DEMAND_REPORT_DURATION) + "H"            # duration of request
                "facilities": self._config['facilities']
            }

            # ws = create_connection("ws://flame.ipkeys.com:8888/socket/msg", timeout=None)
            lr = LoadReport(websocket=self.websocket, **loadReport_kwargs)
            lr.process()

            #print(lr.loadSchedule)
            try:
                ind = -1
                for xx in range(0, len(lr.loadSchedule)):
                    msg = {"Load": {"Readings": [lr.loadSchedule.index[xx],
                                                 float(lr.loadSchedule["value"][xx])],
                                    "Units": "kW",
                                    "tz": "UTC",
                                    "data_type": "float"}}
                    if utc_now_str == lr.loadSchedule.index[xx]:
                        ind = xx
                        while (lr.loadSchedule["value"][ind] == -1) & (ind>-2):
                            ind -= 1

                    _log.info(msg)
                    self.vip.pubsub.publish(
                        peer="pubsub",
                        topic=self._config['load_report_topic'],
                        headers={},
                        message=msg)

                for xx in range(0, len(lr.loadSchedule_scaled)):
                    msg = {"ScaledLoad": {"Readings": [lr.loadSchedule_scaled.index[xx],
                                                       float(lr.loadSchedule_scaled["value"][xx])],
                                    "Units": "kW",
                                    "tz": "UTC",
                                    "data_type": "float"}}

                    _log.info(msg)
                    self.vip.pubsub.publish(
                        peer="pubsub",
                        topic=self._config['load_report_topic'],
                        headers={},
                        message=msg)


                # FIXME - temporary fix - need to figure out what to do if valid reading isn't found.
                if ind == -1:
                    _log.info('warning - index not found.  Current time = '+ utc_now_str)
                    ind = len(lr.loadSchedule['value'])-1
                if ind == -2:
                    _log.info("warning - no valid readings found")
                msg = [{'load': float(lr.loadSchedule['value'][ind])},
                       {'load': {"units": 'kW',
                                 "tz": "UTC",
                                 "data_type": "float"}}]
                _log.info(msg)
                self.vip.pubsub.publish(
                    peer="pubsub",
                    topic=self._config["current_load_topic"],
                    headers={},
                    message=msg)


                msg = [{'scaled_load': float(lr.loadSchedule_scaled['value'][ind])},
                       {'scaled_load': {"units": 'kW',
                                 "tz": "UTC",
                                 "data_type": "float"}}]
                _log.info(msg)

                if USE_SCALED_LOAD == True:
                    self.cur_load.update({"Load": float(lr.loadSchedule_scaled['value'][ind]),
                                          "Time": lr.loadSchedule_scaled.index[ind]})
                else:
                    self.cur_load.update({"Load": float(lr.loadSchedule['value'][ind]),
                                          "Time": lr.loadSchedule.index[ind]})

                self.vip.pubsub.publish(
                    peer="pubsub",
                    topic=self._config["current_load_topic"],
                    headers={},
                    message=msg)


            except AttributeError:
                _log.warn('Response requested not available')

        return None

def main(argv=sys.argv):
    '''Main method called by the platform.'''
    utils.vip_main(FLAMECommsAgent)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
