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
import math


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

FORCE_TIME = USE_SIM  # for debugging - lets user force a start time.
max_load_report_length = 60

### WEBSOCKET ###
ws_url = "wss://flame.ipkeys.com/socket/msg"
# old way
# ws = create_connection(url, timeout=None)
# insecure way, use this if certificate is giving problems
sslopt = {"cert_reqs": ssl.CERT_NONE}
# secure way
# sslopt = {"ca_certs": 'IPKeys_Root.pem'}

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
        """
        Class Variables:

        self.pending_loadshift_options - most recent load shift options provided from flame server
        self.forecast_load_option_profile -
        self.OptionID
        self.options_pending
        self.load_report
        self.initialization_complete
        self.comm_status
        :param config_path:
        :param kwargs:
        """


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
            "facility_load_report_topic": "datalogger/flame/facility",
            #"current_load_topic": "datalogger/flame/load_report/all",
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


        _log.info("Web Socket INITIALIZED")

        self.cur_load = {"load": -1,
                         "time": None}

        self.load_report = None
        self.pending_loadshift_options = None
        self.options_pending = 0
        self.optionID = None
        self.forecast_load_option_profile = None

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
            self.gs_start_time = datetime.utcnow().replace(microsecond=0, tzinfo=pytz.UTC)
            # self.gs_start_time = utils.get_aware_utc_now().replace(microsecond=0)
            #self.gs_start_time = self.gs_start_time.replace(tzinfo=None)
            #self.gs_start_time = datetime.now().replace(microsecond=0)
            _log.info("GS STart time is " + str(self.gs_start_time))

        self.initialization_complete = 1

        # for debugging - lets user force a start time for queries
        self.force_start_time = SIM_START_TIME #datetime(year=2018,month=10,day=16,hour=2,minute=57,second=0) #'2018-10-16T02:00:00'
        self.agent_start_time = datetime.utcnow()

        #self.get_load_report()   # do this first - pre-load with values for other fcns to reference
        self.publish_load_option_forecast()
        self.get_hi_res_load_report()
        self.query_baseline()

        if SEARCH_LOADSHIFT_OPTIONS:
            self.query_loadshift()
        #self.request_status()



    ##############################################################################
    def initialize_load_option_forecast(self):
        """
        Initializes a forecast data frame that is initialized to zeros, with timestamps going from top of the hour
        until the end of the next SSA schedule time horizon.
        :return: forecast_load_option_profile - used to keep track of currently selected load option profiles
        """

        # set start time to top of the current hour
        start_time = datetime.utcnow()
        start_time = start_time.replace(minute=0, second=0, microsecond=0)

        # make a list of time stamps in string format.....
        time_stamps_str = [(start_time + timedelta(minutes=t)).strftime(TIME_FORMAT)
                           for t in range(0,
                                          SSA_SCHEDULE_DURATION * MINUTES_PER_HR,
                                          SSA_SCHEDULE_RESOLUTION)]
        pred_load = [0.0] * SSA_PTS_PER_SCHEDULE

        return pd.DataFrame(data=pred_load,
                            index=time_stamps_str)


    ##############################################################################
    #@Core.periodic(period=LOADSHIFT_FORECAST_UPDATE_INTERVAL)
    def publish_load_option_forecast(self):
        """

        :return:
        """

        if self.initialization_complete == 1:

            # it seems like it should update on load option select
            # because that's when there is a new forecast available.
            # so there should be a data structure that has data points starting now
            # and continuing at least to the end of the forecast period.

            # initialize


            # periodic updates to make sure that the forecast at least covers the boundaries of the next SSA window


            # now we have a data structure that holds the load option forecast
            # need to trim to only hold from t = now, going forward

            default_forecast = self.initialize_load_option_forecast()

            if self.forecast_load_option_profile is None:
                self.forecast_load_option_profile = default_forecast
            else:
                current_time = datetime.now(pytz.timezone('UTC')).replace(microsecond=0, second=0, minute=0)
                self.forecast_load_option_profile = self.forecast_load_option_profile[self.forecast_load_option_profile.index >=
                                                                                      current_time.strftime(TIME_FORMAT)]

                self.forecast_load_option_profile = self.forecast_load_option_profile.combine_first(default_forecast)

            #_log.info(self.forecast_load_option_profile[0])


            load_option_forecast_labels = {"Forecast": "SelectedProfileLoad",
                                           "OrigForecast": "OrigSelectedProfileLoad",
                                           "Time": "SelectedProfileTime",
                                           "Duration": "SelectedProfileDuration",
                                           "Resolution": "SelectedProfileResolution",
                                           "ghi": "ghi"}


            load_option_forecast = Forecast(self.forecast_load_option_profile[0].tolist(),
                                            self.forecast_load_option_profile.index.tolist(),
                                            'kW',
                                            'float',
                                            labels = load_option_forecast_labels)

            message = load_option_forecast.forecast_obj
            _log.debug("***** load shift message!! ******")
            _log.debug(message)
            self.vip.pubsub.publish(
                peer="pubsub",
                topic=self._config['loadshift_forecast_topic'],
                headers={},
                message=message)


    ##############################################################################
    @RPC.export
    def load_option_select(self, optionID):
        """
        Communicate load option choice to IPKeys and publish this to VOLTTRON
        topic.
        """

        _log.info("selecting load option")

        if ENABLE_LOAD_SELECT == True:
            ws = create_connection(ws_url, sslopt=sslopt)
            lsel = LoadSelect(websocket=ws,
                              optionID=optionID)
            lsel.process()

            _log.info("LoadSelect status: " + lsel.status) # TODO setup self.comm_status check based on status
            self.vip.pubsub.publish(
                peer="pubsub",
                topic=self._config['load_option_select_topic'],
                headers={},
                message=optionID) # CHECK if this is what's wanted
                # message=lsel.status) # CHECK if this is what's wanted
            ws.close()

        _log.info("selecting option "+optionID)
        #_log.info(self.pending_loadshift_options.forecast_dict[optionID])

        self.options_pending = 0
        self.optionID        = optionID

        # When a new load option is selected, update with the new data:
        new_selected_profile = pd.DataFrame(data=self.pending_loadshift_options.forecast_dict[optionID],
                                            index=self.pending_loadshift_options.forecast.time)
        self.forecast_load_option_profile = new_selected_profile.combine_first(self.forecast_load_option_profile)

        message = [{"OptionsPending": self.options_pending}, {"OptionsPending": {'type': 'int', 'units': 'none'}}]
        self.vip.pubsub.publish(
            peer="pubsub",
            topic=self._config['loadshift_forecast_topic'],
            headers={},
            message=message)

        self.publish_load_option_forecast()

        return None

    @Core.periodic(period=STATUS_REPORT_SCHEDULE)
    def request_status(self):
        # ws = create_connection(WEBSOCKET_URL, timeout=None)
        if self.initialization_complete == 1:
            ws = create_connection(ws_url, sslopt=sslopt)
            status = Status(websocket=ws)
            status.process()
            _log.info("LoadSelect alertStatus: " + str(status.alertStatus))
            _log.info("LoadSelect currentProfile: " + str(status.currentProfile))

            ws.close()
        return None

    ##############################################################################
    def get_forecast_request_start_time(self, hrs_offset=0):
        ###  convert GS time to local time #####
        real_start_time = datetime.strptime(get_schedule(self.gs_start_time,
                                                         resolution=SSA_SCHEDULE_RESOLUTION),
                                            "%Y-%m-%dT%H:%M:%S.%f")
        _log.info(real_start_time)
        start_time = real_start_time
        if FORCE_TIME == True:
            elapsed_time = (datetime.utcnow().replace(tzinfo=pytz.UTC) - self.gs_start_time)*SIM_HRS_PER_HR #self.agent_start_time
            start_time = (self.force_start_time + elapsed_time).replace(microsecond=0, second=0)
        ## need to convert the start time request to local time.  get_schedule returns a time stamp in UTC, but
        ## as a string, so it is time naive.  It needs to be recast as UTC and then changed to local time.

        start_time = start_time.replace(tzinfo=pytz.UTC)+timedelta(hours=hrs_offset)
        start_time = start_time.astimezone(pytz.timezone('US/Eastern'))
        print(start_time)

        return start_time

    ##############################################################################
    @Core.periodic(period=DEMAND_FORECAST_QUERY_INTERVAL)   #### code for calling something periodically
    def query_baseline(self):
        "Queries the FLAME server for baseline message"
        if self.initialization_complete == 1:
            # Baseline

            start_time = self.get_forecast_request_start_time()
            ### Setting seconds = 3 in the forecast request scales the resulting forecast to a 750kW baseline
            #   Setting seconds = 7 scales to a 1,500kW baseline
            #   Any other value (typically 0) uses raw (unscaled) facility data
            if USE_SCALED_LOAD == True:
                start_time = start_time.replace(minute=0, second=3, microsecond=0)
            else:
                start_time = start_time.replace(minute=0, second=0, microsecond=0)

            start_time_str = start_time.strftime("%Y-%m-%dT%H:%M:%S")
            _log.info("Querying baseline at "+start_time_str)
            ws = create_connection(ws_url, sslopt=sslopt)
            baseline_kwargs = dict(
                start =  start_time_str,
                granularity = DEMAND_FORECAST_RESOLUTION,
                duration = 'PT24H',
                websocket = ws
            )
            _log.debug('setup baseline')
            bl = Baseline(**baseline_kwargs)
            bl.process()
            # websocket.close()
            _log.debug('baseline setup')

            #### code for publishing to the volttron bus
            message_parts = bl.fo
            forecast = Forecast(**message_parts)
            if FORCE_TIME == True:  # modify timestamps to match with GS time
                forecast.shift_timestamps(self.gs_start_time)
            message = forecast.forecast_obj
            _log.info(message)
            # message = bl.forecast    # call to demand forecast object class thingie
            # message = self.baseline_msg.process()    # call to demand forecast object class thingie
            comm_status = 1 # were there errors?
            _log.info(self.cur_load["time"])
            _log.info(forecast.forecast_values["Time"][0])

            if self.cur_load["time"]:
                if (datetime.strptime(self.cur_load["time"], "%Y-%m-%dT%H:%M:%S") >=
                    datetime.strptime(forecast.forecast_values["Time"][0], "%Y-%m-%dT%H:%M:%S")):
                    if math.isnan(self.cur_load["load"]) == False:
                        _log.info("Replacing forecast load = "+str(forecast.forecast_values["Forecast"][0])+" with "+ str(self.cur_load["load"]))
                        forecast.forecast_values["Forecast"][0] = self.cur_load["load"]
                    else:
                        _log.info("no recent values found for current load - using predicted value")

            publish_data(self,
                         "flame/forecast",
                         forecast.forecast_meta_data["Forecast"]["units"],
                         "tPlus1",
                         forecast.forecast_values["Forecast"][1],
                         TimeStamp_str=forecast.forecast_values["Time"][1],
                         ref_time=self.gs_start_time)

            publish_data(self,
                         "flame/forecast",
                         forecast.forecast_meta_data["Forecast"]["units"],
                         "tPlus5",
                         forecast.forecast_values["Forecast"][5],
                         TimeStamp_str=forecast.forecast_values["Time"][5],
                         ref_time=self.gs_start_time)

            publish_data(self,
                         "flame/forecast",
                         forecast.forecast_meta_data["Forecast"]["units"],
                         "tPlus23",
                         forecast.forecast_values["Forecast"][23],
                         TimeStamp_str=forecast.forecast_values["Time"][23],
                         ref_time=self.gs_start_time)

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

            ws.close()
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

            _log.info(price_map)


            current_time = datetime.now(pytz.timezone('US/Eastern')).replace(minute=0, microsecond=0, second=0)
            _log.info("requesting load shift starting at time "+current_time.strftime(TIME_FORMAT))

            #start_time   = self.get_forecast_request_start_time(hrs_offset=1) # start time for 1 hr in the future
            #start_time = start_time.replace(minute=0, second=0, microsecond=0)
            #start_time_str = start_time.strftime("%Y-%m-%dT%H:%M:%S")

            ws = create_connection(ws_url, sslopt=sslopt)
            ls = LoadShift(websocket=ws,
                           start_time = current_time,
                           price_map=price_map,
                           nLoadOptions = N_LOADSHIFT_PROFILES)
            ls.process()
            # message = ls.fo.forecast_values    # call to demand forecast object class thingie
            # ws.close()
            # message = self.load_shift_msg.process()    # call to demand forecast object class thingie
            comm_status = 1 # were there errors?

            self.pending_loadshift_options = ls
            self.options_pending           = 1

            message = ls.forecast.forecast_obj
            _log.info(message)
            self.vip.pubsub.publish(
                peer="pubsub",
                topic=self._config['loadshift_forecast_topic'],
                headers={},
                message=message)

            message = [{"nOptions": len(ls.forecast.forecast)}, {"nOptions": {'type': 'int', 'units': 'none'}}]
            _log.info(message)
            self.vip.pubsub.publish(
                peer="pubsub",
                topic=self._config['loadshift_forecast_topic'],
                headers={},
                message=message)

            message = [{"ID": ls.forecast_id}, {"ID": {'type': 'str', 'units': 'none'}}]
            _log.info(message)
            self.vip.pubsub.publish(
                peer="pubsub",
                topic=self._config['loadshift_forecast_topic'],
                headers={},
                message=message)

            message = [{"OptionsPending": self.options_pending}, {"OptionsPending": {'type': 'int', 'units': 'none'}}]
            _log.info(message)
            self.vip.pubsub.publish(
                peer="pubsub",
                topic=self._config['loadshift_forecast_topic'],
                headers={},
                message=message)




            #for option, message_parts in ls.fos.items():
            #    forecast = Forecast(**message_parts)
            #    message = forecast.forecast_obj
            #    _log.info(message)
            #    self.vip.pubsub.publish(
            #        peer="pubsub",
            #        topic=self._config['loadshift_forecast_topic'],
            #        headers={},
            #        message=message)


            # self.vip.pubsub.publish(
            #     peer="pubsub",
            #     topic=self._config['loadshift_forecast_topic'],
            #     headers={},
            #     message=[{"comm_status": 1}, {"comm_status": {'type': 'int', 'units': 'none'}}])
            ws.close()

        else:
            _log.info("initialization incomplete!!")

    ##############################################################################
    #@Core.periodic(period=DEMAND_REPORT_SCHEDULE)
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

            ws = create_connection(ws_url, sslopt=sslopt)
            lr = LoadReport(websocket=ws, **loadReport_kwargs)
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
                    self.cur_load.update({"load": float(lr.loadSchedule_scaled['value'][ind]),
                                          "time": lr.loadSchedule_scaled.index[ind]})
                else:
                    self.cur_load.update({"load": float(lr.loadSchedule['value'][ind]),
                                          "time": lr.loadSchedule.index[ind]})

                self.vip.pubsub.publish(
                    peer="pubsub",
                    topic=self._config["current_load_topic"],
                    headers={},
                    message=msg)


            except AttributeError:
                _log.warn('Response requested not available')
            ws.close()

        return None


    ##############################################################################
    def merge_load_report(self, new_vals, old_vals):
        new_vals.index = pd.to_datetime(new_vals.index,
                                        format="%Y-%m-%dT%H:%M:%S")
        if old_vals is None:
            return new_vals
        else:
            # combine with old values
            return new_vals.combine_first(old_vals)


    ##############################################################################
    @Core.periodic(period=HI_RES_DEMAND_REPORT_SCHEDULE)
    def get_hi_res_load_report(self):
        '''
        Request and publish high resolution Load Reports from FLAME server.
        A few different reports are generated:
        (1) datalogger-style data captures are published for each individual facility on the
        "facility_load_report_topic".  In this case, the time stamp stored in the database is the actual timestamp of
        the measurement recorded at the facility.  Each facility is uniquely labeled as facilityN, facilityN+1, etc.  Data
        is published for both the load and the scaledLoad
        (2) datalogger-style data captures are published for the aggregate sum of all facilities on the
        "load_report_topic".  Format is the same as for the individual facility load reports.  The most recent data
        point published is the most recent data point for which data is available from ALL facilities.
        (3) device-style data captures are published for the -predicted- aggregate sum of all facility loads on
        "current_load_topic".   In this case, ...

        '''
        # determine report start time
        #FIXME - should use get_schedule()

        if self.initialization_complete == 1:
            current_time = datetime.now(pytz.timezone('US/Eastern')).replace(microsecond=0, second=0)

            # there is a bug on the FLAME server in which it seems to process hi res load report requests
            # as DST, not as local time.  So during standard time, it returns results that are offset by 
            # 1 hour from the request.
            request_time = None
            # dst returns a timedelta required to move the time from dst to current time.
            # what I want to do is the following:
            #
            # (1) get current time in eastern
            # (2) figure out the time stamp that I want to query
            # (3) During DST,
            #     - offset the request by 1 hour.  request_time = current_time - 1 hr
            #     - after the response comes in, we need to adjust the time stamps forward by 1 hr
            # (4) During EST,
            #     - offset by 0
            #     - adjust time stamps by 0
            #current_time += current_time.dst() - timedelta(hours=1)


            # there are a few different values I need to track:
            # (1) current time = now, in eastern time
            # (2) then get the time that I want forecasts for
            # (3) then get the time that I need to send forecast requests for
            # (4) then get a correction factor, that accounts for both DST correction and the sim time correction

            #utc_now_str = current_time.astimezone(pytz.timezone('UTC')).strftime(TIME_FORMAT)
            time_delta     = timedelta(minutes=HI_RES_DEMAND_REPORT_DURATION)

            #start_time      = current_time - time_delta
            #orig_start_time = start_time

            if FORCE_TIME == True:
                now = datetime.utcnow().replace(tzinfo=pytz.UTC)
                elapsed_time = (now-self.gs_start_time)*SIM_HRS_PER_HR    #self.agent_start_time

                base_time = (self.force_start_time+elapsed_time).replace(microsecond=0,second=0)
                base_time = base_time.replace(tzinfo=pytz.UTC)
                base_time = base_time.astimezone(pytz.timezone('US/Eastern'))

                #start_time   = (self.force_start_time+elapsed_time).replace(microsecond=0,second=0)-time_delta
                #start_time = start_time.replace(tzinfo=pytz.UTC)
                #start_time = start_time.astimezone(pytz.timezone('US/Eastern'))
                #dst_correction = start_time.dst() - timedelta(hours=1)

                sim_time_correction = self.gs_start_time - self.force_start_time.replace(tzinfo=pytz.UTC)
            else:
                #start_time = current_time - time_delta
                base_time = current_time
                #dst_correction = current_time.dst() - timedelta(hours=1)
                sim_time_correction = timedelta(0)

            #dst_correction = start_time.dst() - timedelta(hours=1)
            dst_correction = base_time.dst() - timedelta(hours=1)
            start_time     = base_time - time_delta + dst_correction
            ts_correction  = sim_time_correction
            #ts_correction = orig_start_time-start_time
            print(ts_correction)

            dstart = start_time.strftime(TIME_FORMAT)
            _log.info("requesting load report starting at time "+dstart)
            duration = format_timeperiod(HI_RES_DEMAND_REPORT_DURATION)
            sampleInterval = format_timeperiod(HI_RES_DEMAND_REPORT_RESOLUTION)

            loadReport_kwargs = {
                "dstart": dstart, # start time for report
                "sampleInterval": sampleInterval, # sample interval
                "duration": duration, # "PT" + str(DEMAND_REPORT_DURATION) + "H"            # duration of request
                "facilities": self._config['facilities']
            }

            ws = create_connection(ws_url, sslopt=sslopt)
            lr = HiResLoadReport(websocket=ws, **loadReport_kwargs)
            lr.process()

            #print(lr.loadSchedule)
            try:
                # Generate load reports for the individual facilities
                for yy in range(0, len(lr.loadSchedules)):
                    #_log.info("length of ls is "+str(len(lr.loadSchedules[yy])))
                    lr.loadSchedules[yy].index = (pandas.to_datetime(lr.loadSchedules[yy].index)+ts_correction).strftime(TIME_FORMAT)
                    lr.loadSchedules_scaled[yy].index = (pandas.to_datetime(lr.loadSchedules_scaled[yy].index)+ts_correction).strftime(TIME_FORMAT)
                    for xx in range(0, len(lr.loadSchedules[yy])):
                        msg = {"Load": {"Readings": [lr.loadSchedules[yy].index[xx],
                                                 float(lr.loadSchedules[yy]["value"][xx])],
                                    "Units": "kW",
                                    "tz": "UTC",
                                    "data_type": "float"}}
                        #_log.info(msg)
                        self.vip.pubsub.publish(
                            peer="pubsub",
                            topic=self._config['facility_load_report_topic']+str(yy+1),
                            headers={},
                            message=msg)

                    for xx in range(0, len(lr.loadSchedules_scaled[yy])):
                        msg = {"ScaledLoad": {"Readings": [lr.loadSchedules_scaled[yy].index[xx],
                                                           float(lr.loadSchedules_scaled[yy]["value"][xx])],
                                        "Units": "kW",
                                        "tz": "UTC",
                                        "data_type": "float"}}

                        #_log.info(msg)
                        self.vip.pubsub.publish(
                            peer="pubsub",
                            topic=self._config['facility_load_report_topic']+str(yy+1),
                            headers={},
                            message=msg)

                # now generate a load report for the aggregate of all facilities
                lr.loadSchedule_scaled.index = (pandas.to_datetime(lr.loadSchedule_scaled.index)+ts_correction).strftime(TIME_FORMAT)
                lr.loadSchedule.index = (pandas.to_datetime(lr.loadSchedule.index)+ts_correction).strftime(TIME_FORMAT)

                for xx in range(0, len(lr.loadSchedule_scaled)):
                    msg = {"ScaledLoad": {"Readings": [lr.loadSchedule_scaled.index[xx],
                                                       float(lr.loadSchedule_scaled["value"][xx])],
                                    "Units": "kW",
                                    "tz": "UTC",
                                    "data_type": "float"}}
                    self.vip.pubsub.publish(
                        peer="pubsub",
                        topic=self._config['load_report_topic'],
                        headers={},
                        message=msg)

                for xx in range(0, len(lr.loadSchedule)):
                    msg = {"Load": {"Readings": [lr.loadSchedule.index[xx],
                                                 float(lr.loadSchedule["value"][xx])],
                                    "Units": "kW",
                                    "tz": "UTC",
                                    "data_type": "float"}}
                    self.vip.pubsub.publish(
                        peer="pubsub",
                        topic=self._config['load_report_topic'],
                        headers={},
                        message=msg)

                # Now get a predicted value for the load at t=now
                # for right now, this is just using a rolling average of the last 15 minutes of good data
                # but this could be modified to do something more sophisticated (e.g., looking at upcoming schedule
                # changes)
                if USE_SCALED_LOAD == True:
                    self.load_report = self.merge_load_report(lr.loadSchedule_scaled, self.load_report)
                else:
                    self.load_report = self.merge_load_report(lr.loadSchedule, self.load_report)

                # Use the most recent 15 minutes worth of data for prediction purposes.
                # Keep track of the last 60 minutes worth of data
                most_recent_ts = max(self.load_report.index)
                last_15_min    = self.load_report[self.load_report.index > most_recent_ts - timedelta(minutes=15)]
                self.load_report = self.load_report[self.load_report.index >
                                                    most_recent_ts - timedelta(minutes=max_load_report_length)]
                cur_predicted_value = last_15_min.mean().value
                if math.isnan(cur_predicted_value) == True:
                    _log.info("Warning - One or more facility meters appears to be offline")

                _log.info("last 15 minutes load report is:")
                _log.info(last_15_min)

                # publish resulting current predicted value on a device/ topic for consumption by a site manager agent
                self.cur_load.update({"load": cur_predicted_value,
                                      "time": most_recent_ts.strftime('%Y-%m-%dT%H:%M:%S')})
                msg = [self.cur_load,
                       {'load': {"units": 'kW',
                                 "tz": "UTC",
                                 "data_type": "float"},
                        'time': {"units": "datetime",
                                 "tz": "UTC",
                                 "data_type": "datetime"}}]
                _log.info(msg)
                self.vip.pubsub.publish(
                    peer="pubsub",
                    topic=self._config["current_load_topic"],
                    headers={},
                    message=msg)


            except AttributeError:
                _log.warn('Response requested not available')
            ws.close()

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
