
#import gs_identities
#from gs_utilities import get_schedule
from datetime import datetime, timedelta

from websocket import create_connection
import json
import pandas as pd
import os
# import ipdb

import logging
#from gs_identities import *

## Stubbed out version of a standalone FLAME application
# This is a tool to exchange messagers with the IPKeys webserver FLAME





#### The following are global variables that are defined in a central location (gs_identities) in the
#### global scheduler code base.  For simplicity, I've just pasted at the top here.
SIM_HRS_PER_HR           = 1  # used for running in acceleration mode
SSA_SCHEDULE_RESOLUTION  = 60 # minutes
LOAD_FORECAST_RESOLUTION = SSA_SCHEDULE_RESOLUTION # minutes, assume it is the same as SSA
SSA_SCHEDULE_DURATION    = 24 # hours
N_LOAD_SHIFT_PROFILES    = 10

LOAD_REPORT_DURATION    = 24 # hours
LOAD_REPORT_RESOLUTION  = 15 # minutes
LOAD_REPORT_SCHEDULE    = 15 # minutes

LOAD_FORECAST_SCHEDULE = 15 # minutes.  currently unused
LOADSHIFT_FORECAST_SCHEDULE = 60 # minutes.  currently unused

test_start_time  = datetime.utcnow()

_log = logging.getLogger(__name__)

###########################
def get_marginal_cost_curve():
    """
    For now - this can just send a dummy message
    Next revision will need to derive a price map based on actual cost functions
    :return: price_map - a matrix of time/demand/price that indicates the unit cost of energy as a function
             of time and demand
    """

    price_map = {}

    # returns an compliant dict object with a price_map for the requested
    # forecast period
    return price_map





###########################
def get_load_forecast():
    """
    send baseline request to FLAME server
    check for baseline response
        raise error if there is a timeout or if a status code is returned
        otherwise populate incoming forecast in an instance of forecast object class
    :return:
    """

    # (1) build message
    # (2) send request
    # (3) check for response
    # (4) check for errors
    # (5) populate into a ForecastObject class
    # (6) output response

    pass


###########################
def get_load_shift_forecast():
    """
    builds a load shift request message
    send load shift request message to FLAME server
    receives and parses result

    load_shift_request message -

        get_marginal_cost_curve()

    :return:
    """

    # build message:
    price_map    = get_marginal_cost_curve()
    nLoadOptions = N_LOAD_SHIFT_PROFILES
    duration     = SSA_SCHEDULE_DURATION
    dstart       = get_schedule(test_start_time)  # get_schedule routine in gs_utilities
    # turn into a json struct


    # (2) send request

    # (3) get response
    # (4) check for errors
    # (5) if no errors, parse response, put in a data structure that looks like this:
    #       {"nProfiles": "",
    #        "comm_status": "",
    #        "Profiles": [
    #           {"OptionID": "",
    #           "Profile": ForecfastObj.forecast_obj,
    #           "implementationCost": "",
    #           "energyCost": ""},
    #        ....]
    #       }



    pass


###########################
def select_load_profile(load_profile_id):
    """
    sends a LoadSelectRequest message to FLAME server
    :return:
    """
    pass


###########################
def get_load_report():
    """
    requests a load report from the FLAME server
    message format needs to be re-specified
    #FIXME - message request & response format is not fully specified yet!!
    :return:
    """

    duration  = LOAD_REPORT_DURATION

    cur_time   = datetime.strptime(get_schedule(test_start_time), "%Y-%m-%dTHH:MM:SS")
    start_time = cur_time - timedelta(hours=LOAD_REPORT_DURATION)
    resolution = LOAD_REPORT_RESOLUTION
    pass



###########################
def register_with_server():
    """
    this has not been specified.  May not be necessary.
    This would register the GS with the FLAME server
    :return:
    """
    pass

###########################
def poll_server():
    """
    this has not been specified.
    it will periodically poll the web server to check for alerts and to find out what load option is being
    implemented
    :return:
    """
    pass



### These functions are pasted from gs_utilities, and are shared among many Global Scheduler agents
##############################################################################
def get_schedule(gs_start_time,
                 resolution = SSA_SCHEDULE_RESOLUTION,
                 sim_time_corr = timedelta(seconds=0)):
    """
    Returns the start time of the next dispatch schedule command
    Strips out seconds, microseconds, etc.  Rounds to the next SSA_SCHEDULE_RESOLUTION time step,
    indexed to the global scheduler's start time.
    :param gs_start_time: start time to use for indexing dispatch schedule
    :param resolution: time step, in minutes, of dispatch schedules
    :param sim_time_corr: time correction factor to account for interruptions during simulation runs
    :return: new_time - the start time of the next dispatch schedule period, as a string.

    """
    TimeStamp = get_gs_time(gs_start_time,sim_time_corr)
    gs_run_time = TimeStamp-gs_start_time   # time, in gs frame of reference, since gs start
    baseline = datetime(year=1900, month=1, day=1) # arbitrary starting point
    minutes = (baseline+gs_run_time).minute
    rem = minutes % resolution
    start_of_schedule = (baseline+(gs_run_time - timedelta(minutes=rem))).replace(second=0, microsecond=0) -baseline # todo - temp fix - moves forecast to tstep-1
    new_time = gs_start_time+start_of_schedule
    time_str = new_time.strftime("%Y-%m-%dT%H:%M:%S.%f")
    return time_str   # needs to return as a serializable object due to volttron limitations.


##############################################################################
def get_gs_time(gs_start_time, sim_time_corr):
    """
    returns the time in the Global Scheduler frame of reference.
    :return:
    """
    now = datetime.utcnow()
    run_time         = (now - gs_start_time).total_seconds() # tells the elapsed real time
    sim_run_time     = timedelta(seconds=SIM_HRS_PER_HR * run_time).total_seconds()  # tells the elapsed "accelerated" time
    return gs_start_time+sim_run_time-sim_time_corr  # current time, in the GS frame of reference




## ForecastObject is a data structure that is used throughout the GS code base.
## it lives in gs_utilities.py
## BaselineResponses and LoadShiftOptions should both be mapped to a ForecastObject
##############################################################################
#class ForecastObject():
#    """
#    Data class for storing forecast data in a serializable format that is consumable by the VOLTTRON Historian
#    """
#    ##############################################################################
#    def __init__(self, forecast, time, units, datatype):
#        self.forecast_values = {"Forecast": forecast,
#                                "Time": time,
#                                "Duration": SSA_SCHEDULE_DURATION,
#                                "Resolution": SSA_SCHEDULE_RESOLUTION}
#        self.forecast_meta_data = {"Forecast": {"units": units, "type": datatype},
#                                   "Time": {"units": "UTC", "type": "str"},
#                                   "Duration": {"units": "hr", "type": "int"},
#                                   "Resolution": {"units": "min", "type": "int"}}

#        self.forecast_obj = [self.forecast_values, self.forecast_meta_data]
##############################################################################
class IPKeys(object):
    """Parent class for request & response interactions with IPKeys"""
    def __init__(self, websocket):
        self.ws = websocket

        # initialize ForecastObject placeholder to indicate unprocessed request
        self.fo = None
        return None

    def _send_receive(self):
        """
        Sends, receives and error checks response.
        Ensures request can only be processed once.
        """
        # ipdb.set_trace()
        # check if request has already been processed
        if self.fo:
            _log.info('request already processed')
            return None

        # (2) send request
        _log.info("Sending Request")
        self.ws.send(self.request)
        _log.info("Request sent")

        # (3) check for response
        _log.info("Receiving")
        result_json = self.ws.recv()
        self.response = json.loads(result_json)
        _log.info("Received")

        # (4) check for errors
        assert self.response['type'] == self.type, 'msg received is wrong type'

        return None

## subclasses
class Baseline(IPKeys):

    def __init__(self, start, granularity, duration, websocket):
        IPKeys.__init__(self, websocket)

        self.type = u'BaselineResponse'
        self.start = start
        self.granularity = granularity
        self.duration = duration

        self.request = json.dumps({'type': 'BaselineRequest',
                                            'msg': {'dstart': start,
                                                    'granularity': granularity,
                                                    'duration': duration}
                                            }
                                           )
        return None

    def __repr__(self):
        return ('\n'.join(['%s(' % self.__class__.__name__,
                           '%s,' % self.start,
                           '%s,' % self.granularity,
                           '%s' % self.duration,
                           '%s)' % self.websocket.__repr__()]))

    def process(self):

        self._send_receive()

        full_forecast = parse_Baseline_response(self.response)
        self.forecast = full_forecast

        forecast = full_forecast['value'].tolist()
        time = full_forecast.index.tolist()
        units = "units"
        # ipdb.set_trace()
        datatype = str(full_forecast.value.dtype)
        self.fo = dict(forecast=forecast,
                       time=time,
                       units=units,
                       datatype=datatype)
        # self.fo = ForecastObject(forecast, time, units, datatype)

        return None

class LoadShift(IPKeys):

    def __init__(self, websocket):
        IPKeys.__init__(self, websocket)

        self.type = u'LoadOptionsResponse'
        self.request = create_load_request()
        return None

    def __repr__(self):
        return ('\n'.join(['%s(' % self.__class__.__name__,
                           # '%s,' % self.start,
                           # '%s,' % self.granularity,
                           # '%s)' % self.duration,
                           ]))

    def process(self):

        self._send_receive()
        try:
            forecast, costs = parse_LoadShift_response(self.response)
        except ValueError:
            print(self.response['msg']['error'])
            costs = {}
            forecast = pd.DataFrame()
            return None
        self.costs = costs
        self.forecast = forecast

        # prepare ForecastObject from response values
        # units = forecast.units[0]

        # units = self.response['msg']['loadSchedule'][0]['units']
        # print(self.response['msg']['options'][0]['loadSchedule'].keys())
        self.fos = {}
        for optionNum, profile in forecast.items():
            datatype = str(profile.dtype)
            fo = dict(
                forecast=profile.tolist(),
                time=profile.index.tolist(),
                units=optionNum,
                datatype=datatype)
            self.fos[optionNum] = fo
            # self.fos[optionNum] = ForecastObject(profile.tolist(),
            #                                      profile.index.tolist(),
            #                                      optionNum,
            #                                      datatype)

        return None

# helper functions
def create_baseline_request(start, granularity, duration):
    baseline_request = json.dumps({'type': 'BaselineRequest',
                                   'msg': {'dstart': start,
                                           'granularity': granularity,
                                           'duration': duration}
                                   }
                                  )
    return baseline_request

def parse_Baseline_response(result):
    forecast_values = pd.DataFrame(result['msg']['loadSchedule'])
    forecast_values.set_index('dstart', inplace=True)
    return forecast_values


def create_load_request():
    gs_root_dir = os.environ['GS_ROOT_DIR']
    flame_path  = "FLAME-v2/flame/"
    fname       = 'defaultLoadRequest.json'
    filepath    = gs_root_dir+flame_path+fname
    #filepath = '/home/cstark/bin/volttron/services/contrib/GlobalSchedulerCore/FLAME/flame/defaultLoadRequest.json'

    with open(filepath) as f:
        msg = json.load(f)
    payload_request = json.dumps(
        {"type": "LoadRequest",
         "msg": msg
         }
    )
    return payload_request


def parse_LoadShift_response(response):
    # forecast = response
    # ops = ls.forecast['msg']['options']
    response_options = response['msg']['options']
    ind_options = []
    costs = {}
    for option in response_options:
        implementationCost = option['implementationCost']
        optionID = option['optionID']
        costs[optionID] = implementationCost

        loadSchedule = option['loadSchedule']
        df = pd.DataFrame(loadSchedule)
        option_values = df.set_index('dstart')['value']
        option_values.name = optionID
        ind_options.append(option_values)
    forecast = pd.concat(ind_options, axis=1)

    return forecast, costs

###########################
if __name__ == '__main__':

    ws = create_connection("ws://flame.ipkeys.com:8888/socket/msg", timeout=None)

    # Baseline
    print("running Baseline")
    start =  '2018-03-01T00:00:00'
    granularity =  'PT1H'
    duration = 'PT24H'
    bl = Baseline(start, granularity, duration, ws)
    print("processing Baseline")
    bl.process()
    print(bl.forecast)
    print("done processing Baseline")
##
    print("running LoadShift")
    # LoadShift
    ls = LoadShift(ws)
    ls.process()
    print(ls.forecast)
    ##
