"This is a tool to exchange messagers with the IPKeys webserver FLAME"
from datetime import datetime, timedelta

import websocket
from websocket import create_connection
import ssl
import json
import pandas as pd
import os
import logging
from random import randint
import copy
import ipdb # be sure to comment this out while running in Volttron instance
from functools import reduce
import pytz
from gs_identities import *
from gs_utilities import Forecast
import numpy as np

websocket.setdefaulttimeout(10) # set timeout quicker for testing purposes, normally 60

test_start_time  = datetime.utcnow()

_log = logging.getLogger(__name__)

scale_factors = {"School": 1.0,
                 "Canner": 0.2,
                 "Mill": 0.1}

SAVE_LS_FORECAST = False

# Classes
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
        # check if request has already been processed
        if self.fo:
            _log.info('request already processed')
            return None

        # (2) send request
        _log.info("Sending Request from %s" % self.type)
        try:
            self.ws.send(self.request)
        except websocket.WebSocketTimeoutException:
            return "WEB_SOCKET_TIMEOUT" #raise
            # TODO: add a means of handling what to do when a timeout happens
        # TODO: add a means of confirming that the request was received (200?)
        _log.info("Request set from %s" % self.type)


        # (3) check for response
        _log.info("Receiving Response from %s" % self.type)
        try:
            #print("I GET HERE!!!")
            #print(type(self.ws))
            result_json = self.ws.recv()
            _log.info("Received Response from %s" % self.type)
        except websocket.WebSocketTimeoutException:
            _log.warning("""\
WebSocket Timeout Exception While Waiting to Receive Response from %s
Dummy Message Loaded""" % self.type)
            # the object of filling the following response is to allow for the remaining processes to execute their processes
            self.response = json.loads(json.dumps({"message":"WARNING TIMEOUT OCCURRED",
                                        "msg": {"loadSchedule" : [99999],
                                                "options" : {"implementationCost": "ERROR",
                                                             "optionID": "9999",
                                                             "loadSchedule": [9999]
                                                             },
                                                "facility": "ERROR",
                                                "alertStatus": "ERROR",
                                                "currentProfile": "ERROR",
                                                }
                                        }
                                       ))

            ## TODO put all the desired
        except:
            _log.warning("An unforseen error has ocurred")
            print("An unforseen error has ocurred")
            raise
        else:
            self.response = json.loads(result_json)
            # (4) check for errors
            assert self.response['type'] == self.type + 'Response', 'msg received is wrong type %s' % self.type + 'Response'

        return None

## subclasses
class Baseline(IPKeys):

    def __init__(self, start, granularity, duration, websocket):
        '''
        start:
        granularity: time given in minutes
        duration:
        websocket:
        '''
        IPKeys.__init__(self, websocket)

        self.type = u'Baseline'
        self.start = start
        self.granularity = granularity
        self.duration = duration

        full_time_string = format_timeperiod(granularity)
        self.request = json.dumps({'type': 'BaselineRequest',
                                   'msg': {'dstart': start,
                                           'granularity': full_time_string,
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
        datatype = str(full_forecast.value.dtype)
        self.fo = dict(forecast=forecast,
                       time=time,
                       units=units,
                       datatype=datatype)
        # self.fo = ForecastObject(forecast, time, units, datatype)

        return None

class LoadShift(IPKeys):

    def __init__(self, websocket=None, start_time=None, price_map=None, nLoadOptions=12):
        IPKeys.__init__(self, websocket)

        self.type = u'LoadOptions'

        if price_map is None:
            self.request, self.start_time = read_load_request()
            req_start_time = self.start_time
        else:
            self.price_map  = price_map
            self.start_time = start_time

            # set the load shift request for the start of the next day:
            req_start_time = start_time.replace(hour=0) + timedelta(days=1)
            dstart         = req_start_time.strftime(TIME_FORMAT)
            self.request = create_load_request(price_map=price_map, start_time=dstart, nLoadOptions=nLoadOptions)

        print(req_start_time)

        if start_time is None:
            self.base_index = "2018-10-19"
        else:
            self.base_index = req_start_time.strftime("%Y-%m-%d")

        #self.baseline_index = start_time.strftime("%Y-%m-d")+"--ZERO"
        print(self.base_index)

        _log.info("REQUEST LENGTH!!!")
        _log.info(len(self.request))
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

            absolute_forecast, costs = parse_LoadShift_response(self.response)
            ### FIXME - just have hard coded column name - needs to be fixed. ###
            #print(bl.forecast)

            absolute_forecast = absolute_forecast.loc[:, ~absolute_forecast.columns.duplicated()]

            #absolute_forecast.loc[:,"2018-10-12--ZERO"] = bl.forecast #[:,"value"]
            #print(absolute_forecast["2018-10-12--ZERO"])

            #correction = pd.DataFrame(data=[100,100,100,130,115,15,10,10,10,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
            #                          index=absolute_forecast.index)
            correction = pd.DataFrame(data=[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
                                      index=absolute_forecast.index)

            baseline_index = self.base_index + "--ZERO"
            delta_index    = self.base_index + "--DELTA"
            absolute_forecast[baseline_index] = absolute_forecast[baseline_index]+correction[0]
            #print(absolute_forecast[baseline_index])
            forecast = absolute_forecast.sub(absolute_forecast[baseline_index], axis=0)

            try:
                forecast = forecast.drop(delta_index, axis=1)
            except:
                print("DELTA label not found!")

            #print(absolute_forecast)

            #current_tz = pytz.timezone('US/Eastern')
            #utc_start_time = current_tz.localize(self.start_time).astimezone(pytz.timezone('UTC'))
            utc_start_time = self.start_time.astimezone(pytz.timezone('UTC'))
            pad_length = 24-self.start_time.hour
            #utc_start_time = ts.astimezone(pytz.timezone('UTC')))

            columns = forecast.columns
            #df2 = pd.DataFrame(data=np.array(lst).transpose(), columns=df.columns)
            padding = pd.DataFrame(data  = np.zeros(shape=(pad_length, len(columns))), #[[0.0]*pad_length]*len(columns),
                                   index = [(utc_start_time.replace(tzinfo=None) +
                                            timedelta(hours=t)).strftime(TIME_FORMAT) for t in range(0, pad_length)],
                                   columns = columns)

            forecast = forecast.combine_first(padding)
            print(forecast)
            if SAVE_LS_FORECAST == True:
                forecast.to_csv('LSForecast.csv')

            forecast_lst = []
            forecast_id  = []
            forecast_dict = {}

            for f in forecast.columns:
                forecast_lst.append(forecast[f].tolist())
                forecast_id.append(f)
                forecast_dict.update({f: forecast[f].tolist()})

        except ValueError:
            print("Error Found!")
            print(self.response['msg']['error'])
            costs = {}
            forecast = pd.DataFrame()
            return None
        self.costs = costs

        units    = "kW"
        datatype = "float"
        self.forecast = Forecast(forecast_lst,
                                 forecast.index.tolist(),
                                 units,
                                 datatype)
        self.forecast_id = forecast_id
        self.forecast_dict = forecast_dict
        self.baseline_index = self.base_index+'--ZERO'
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

class LoadSelect(IPKeys):
    def __init__(self, websocket, optionID):
        IPKeys.__init__(self, websocket)

        self.type = u'LoadSelect'

        self.request = json.dumps({'type': 'LoadSelectRequest',
                                            'msg': {"optionID": optionID}
                                            }
                                           )
        return None

    def __repr__(self):
        return ('\n'.join(['%s(' % self.__class__.__name__,
                           # '%s,' % self.start,
                           # '%s,' % self.granularity,
                           # '%s)' % self.duration,
                           ]))

    def process(self):

        self._send_receive()
        self.status = self.response['msg']['status']

class LoadReport(IPKeys):
    def __init__(self, websocket, dstart, sampleInterval, duration, facilities=None):
        IPKeys.__init__(self, websocket)

        self.type = u'LoadReport'

        self.websocket = websocket
        self.dstart = dstart
        self.sampleInterval = sampleInterval
        self.duration = duration
        self.facilities = facilities

        baseline_request = {
            'type': 'LoadReportRequest',
            'msg': {
                "dstart": dstart,        #start time for report
                "sampleInterval": sampleInterval,            #sample interval
                "duration": duration            # duration of request
            }
        }
        if facilities:
            _log.info("FACILITIES ARE PRESENT")
            requests =  []
            for facility in self.facilities:
                request = copy.deepcopy(baseline_request) #.copy()
                request['msg']['facility'] = facility
                requests.append(request)
        else:
            _log.info("FACILITIES ARE NOT PRESENT")
            requests = [baseline_request]
        self.requests = requests

        return None

    def __repr__(self):
        return ('\n'.join(['%s(' % self.__class__.__name__,
                           '%s,' % self.websocket,
                           '%s,' % self.dstart,
                           '%s,' % self.sampleInterval,
                           '%s,' % self.duration,
                           '%s,' % self.facilities,
                           ')'
                           ]))

    def generate_facility_load_report(self):
        _log.info("Processing %s" % self.type)
        loadSchedules = []
        loadSchedules_scaled = []
        missing_vals = []
        for request in self.requests:
            if 'facility' in request['msg'].keys():
                facility = request['msg']['facility']
            self.request = json.dumps(
               request
            )
            self._send_receive()
            # assert facility is self.response['msg']['facility'],\
            #     'facility response does not match requested facility'

            try:
                sf = scale_factors[self.response['msg']["facility"]]
            except KeyError:
                sf = 1.0

            _log.info(sf)
            try:
                facility_loadSchedule = pd.DataFrame(self.response['msg']['loadSchedule'])
                scaled_facility_loadSchedule = pd.DataFrame(self.response['msg']['loadSchedule'])
                scaled_facility_loadSchedule["value"] = scaled_facility_loadSchedule["value"] * sf
                #_log.info(facility_loadSchedule)
                _log.debug("loadSchedule:\n" + str(facility_loadSchedule))
            except KeyError:
                _log.warn('previous request yielded no response')

            # set the index to the time stamp
            facility_loadSchedule.index        = facility_loadSchedule["dstart"]
            scaled_facility_loadSchedule.index = scaled_facility_loadSchedule["dstart"]

            facility_loadSchedule.index        = convert_FLAME_time_to_UTC(facility_loadSchedule.index)
            scaled_facility_loadSchedule.index = convert_FLAME_time_to_UTC(scaled_facility_loadSchedule.index)

            for ii in range(0, len(facility_loadSchedule)):
                if facility_loadSchedule["value"][ii] == -1:
                    missing_vals.append(facility_loadSchedule.index[ii])

            loadSchedules.append(facility_loadSchedule)
            loadSchedules_scaled.append(scaled_facility_loadSchedule)

        return loadSchedules, loadSchedules_scaled, missing_vals

    def generate_facility_load_report2(self, scale_values=False):
        _log.info("Processing %s" % self.type)
        loadSchedules = []
        missing_vals = []
        for request in self.requests:
            if 'facility' in request['msg'].keys():
                facility = request['msg']['facility']
            self.request = json.dumps(
               request
            )
            self._send_receive()
            # assert facility is self.response['msg']['facility'],\
            #     'facility response does not match requested facility'

            if self.response['msg']['loadSchedule'] != []:

                if scale_values == True:
                    try:
                        sf = scale_factors[self.response['msg']["facility"]]
                    except KeyError:
                        sf = 1.0
                else:
                    sf = 1.0
                _log.info('Facility Scale Factor = '+str(sf))
                try:
                    facility_loadSchedule = pd.DataFrame(self.response['msg']['loadSchedule'])
                    facility_loadSchedule["value"] = facility_loadSchedule["value"] * sf
                    #_log.info(facility_loadSchedule)
                    #_log.info("loadSchedule:\n" + str(facility_loadSchedule))
                except KeyError:
                    _log.warn('previous request yielded no response')

                # set the index to the time stamp
                facility_loadSchedule.index        = facility_loadSchedule["dstart"]
                facility_loadSchedule.index        = convert_FLAME_time_to_UTC(facility_loadSchedule.index)

                for ii in range(0, len(facility_loadSchedule)):
                    if facility_loadSchedule["value"][ii] == -1:
                        missing_vals.append(facility_loadSchedule.index[ii])

                loadSchedules.append(facility_loadSchedule)
            else:
                _log.info("FLAME - Warning - No schedule data returned")

        return loadSchedules, missing_vals


    def process(self):
        loadSchedules, missing_vals        = self.generate_facility_load_report2(scale_values=False)
        loadSchedules_scaled, missing_vals = self.generate_facility_load_report2(scale_values=True)

        # sum facility schedules
        #_log.info(loadSchedules)
        #_log.info(loadSchedules_scaled)
        self.loadSchedule = reduce(lambda x, y: x.add(y, fill_value=0), loadSchedules)
        self.loadSchedule_scaled = reduce(lambda x, y: x.add(y, fill_value=0), loadSchedules_scaled)

        # mark any indices with missing values as -1
        #_log.info(missing_vals)
        self.loadSchedule.loc[missing_vals,"value"] = -1
        self.loadSchedule_scaled.loc[missing_vals, "value"] = -1


        #print(self.loadSchedule)
        return None

class HiResLoadReport(LoadReport):

    def get_load_schedule(self, loadSchedules):
        clean_data = True
        for ii in range(0,len(loadSchedules)):
            loadSchedules[ii] = loadSchedules[ii].drop("dstart", axis=1)
            if clean_data == True:
                loadSchedules[ii] = self.clean_data(loadSchedules[ii])

        # adds up each of the individual load schedules when all available.
        if clean_data == False:
            loadSchedule = reduce(lambda x, y: x.add(y, fill_value=0), loadSchedules)
        else:
            loadSchedule = reduce(lambda x, y: x.add(y), loadSchedules)
            loadSchedule = loadSchedule.dropna(axis=0,how='any')
        #print(loadSchedule)

        return loadSchedule, loadSchedules


    def clean_data(self, loadSchedule):
        """
        aligns data to top of the minute and removes "0" values
        :return:
        """

        new_index = []
        to_remove = []
        for jj in range(0, len(loadSchedule)):
            # mark all values where data is < epsilon from removal
            if loadSchedule["value"][jj] < EPSILON:  # 0 value recorded - ignore
                to_remove.append(jj)
            # generate a new index in which all values are aligned to top of the minute
            tmp_dt = datetime.strptime(loadSchedule.index[jj], TIME_FORMAT).replace(second=0, microsecond=0)
            new_index.append(tmp_dt.strftime(TIME_FORMAT))

        #print(loadSchedules[ii])

        # replace w/new indices and remove zero values:
        loadSchedule.index = new_index
        loadSchedule       = loadSchedule.drop(index=loadSchedule.index[to_remove])
        return(loadSchedule)


    def process(self):
        """
        process method for high resolution load reports.  In this case (1) data that is unavailable is not returned,
        not marked as -1.  (2) we publish data available for each of the individual facilities; (3) we find the latest
        timestamp for which all facilities have data and use this to generate a total.
        :return:
        """

        # FIXME - this approach is opening the socket twice - once for scaled and once for unscaled values.
        # FIXME - this was done for the sake of modularity, but it's probably better to just do one call
        self.loadSchedules, missing_vals        = self.generate_facility_load_report2(scale_values=False)
        self.loadSchedules_scaled, missing_vals = self.generate_facility_load_report2(scale_values=True)
        #self.loadSchedules, self.loadSchedules_scaled, missing_vals = self.generate_facility_load_report()
        # 1. need to return individual facilities and publish each of them
        # 2. find the most recent time stamp that has all three values.

        #nElements = [len(ls) for ls in self.loadSchedules]
        #last_ts_index = min(nElements)

        #print(last_ts_index)
        self.loadSchedule, self.loadSchedules               = self.get_load_schedule(self.loadSchedules)
        self.loadSchedule_scaled, self.loadSchedules_scaled = self.get_load_schedule(self.loadSchedules_scaled)

        #_log.info(last_ts_index)

        #print(self.loadSchedule)
        #print(self.loadSchedule_scaled)

        pass


class Status(IPKeys):
    def __init__(self, websocket):
        IPKeys.__init__(self, websocket)

        self.type = u'Status'

        self.request = json.dumps({'type': 'StatusRequest',
                                   'msg': {
                                       }
                                   }
                                   )
        return None

    def __repr__(self):
        return ('\n'.join(['%s(' % self.__class__.__name__,
                           # '%s,' % self.start,
                           # '%s,' % self.granularity,
                           # '%s)' % self.duration,
                           ]))
    def process(self):

        self._send_receive()
        # self.loadSchedule = pd.DataFrame(self.response['msg']['loadSchedule'])
        print(self.response['msg'])
        self.alertStatus = self.response['msg']['alertStatus']
        try:
            self.currentProfile = self.response['msg']['currentProfile']
        except KeyError:
            self.currentProfile = None

# functions
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
    forecast_values['value'] = forecast_values['value'] * DEMAND_ADJUST
    forecast_values.set_index('dstart', inplace=True)
    forecast_values.index = convert_FLAME_time_to_UTC(forecast_values.index)
    return forecast_values

def read_load_request():
    # use a price map stored from a file
    # # OLD STATIC WAY
    gs_root_dir = os.environ['GS_ROOT_DIR'] #'/Users/mkromer/PycharmProjects/GlobalSchedulerCore/'
    flame_path = "FLAME/flame/"
    fname = 'Example4A_04262019.json'  # 'Example4A.json' #''defaultLoadRequest.json'
    filepath = os.path.join(gs_root_dir, flame_path, fname)
    with open(filepath) as f:
        msg = json.load(f)

    start_time = datetime.strptime(msg['marginalCostCurve'][0]['dstart'],TIME_FORMAT).replace(tzinfo=pytz.timezone('US/Eastern'))

    payload_request = json.dumps(
        {"type": "LoadRequest",
         "msg": msg
         }
    )
    return payload_request, start_time



def create_load_request(duration='PT1H', start_time = None, nLoadOptions=12, price_map=None):

    if start_time is None:
        # get set of times
        now = pd.datetime.utcnow()
        start_time = datetime(now.year, now.month, now.day, 0).isoformat()

    hourlist = pd.date_range(start_time,
                             freq='H',
                             periods=24)

    if price_map:
        priceMaps = price_map
    else:   # deprecated, used for initial testing
        borders=[randint(10, 30) * 10 for i in range(24)]
        priceMaps =[build_priceMap(border) for border in borders]

    marginalCostCurve = [{'dstart': unicode(hourlist[i].isoformat()),
                          'duration': unicode(duration),
                          'priceMap': priceMaps[i]} for i in range(len(hourlist))]
    msg = {'nLoadOptions': unicode(nLoadOptions),
           'marginalCostCurve': marginalCostCurve}

    payload_request = json.dumps(
        {"type": "LoadRequest",
         "msg": msg
         }
    )
    return payload_request

def build_priceMap(border):
    assert isinstance(border, int)

    low = {u"LB": u"-Infinity",
           u"UB": u"0",
           u"price": u"0.05"}
    med = {u"LB": u"0",
           u"UB": unicode(border),
           u"price": u"0.0"}
    high = {u"LB": unicode(border),
            u"UB": u"Infinity",
            u"price": u"4.94"}
    priceMap = [low, med, high]

    return priceMap

def parse_LoadShift_response(response):
    # forecast = response
    # ops = ls.forecast['msg']['options']
    response_options = response['msg']['options']
    ind_options = []
    costs = {}
    #print(response['msg'])
    #print(response_options)
    for option in response_options:
        #print(option)
        implementationCost = option['implementationCost']
        optionID = option['optionID']
        costs[optionID] = implementationCost

        loadSchedule = option['loadSchedule']
        df = pd.DataFrame(loadSchedule)
        option_values = df.set_index('dstart')['value']
        option_values.name = optionID
        ind_options.append(option_values)
    forecast = pd.concat(ind_options, axis=1)

    forecast.index = convert_FLAME_time_to_UTC(forecast.index)
    return forecast, costs

def convert_FLAME_time_to_UTC(FLAME_time):
    datetime_aware = pd.to_datetime(FLAME_time)
    timezone_aware = datetime_aware.tz_localize('US/Eastern')
    converted_timezone = timezone_aware.tz_convert('UTC').to_datetime()
    stringified = converted_timezone.strftime("%Y-%m-%dT%H:%M:%S")#converted_timezone.to_native_types() # use for removing timezone info .tz_localize(None)
    return stringified

def format_timeperiod(granularity):
    # print(granularity/60)
    assert isinstance(granularity, int)
    hours = int(granularity/60)
    minutes = int(granularity%60)
    if granularity/60 > 0:
        if hours > 0:
            time_string = str(hours)
            time_designator = 'H'
        elif hours == 0:
            time_string = str(minutes)
            time_designator = 'M'
    elif granularity/60 ==  0:
            time_string = str(minutes)
            time_designator = 'M'

    full_time_string = ''.join(['PT',
                                time_string,
                                time_designator])
    return full_time_string


def store_forecasts(start_time, end_time, res=24):
    query_start = datetime.strptime(start_time, TIME_FORMAT)
    end_datetime   = datetime.strptime(end_time, TIME_FORMAT)
    cur_end_time = query_start
    forecasts = None
    forecast_dict = {}
    #pd.DataFrame([], columns=range(0, 24))

    while query_start < end_datetime:
        # 0. Connect to server
        ws_url = "wss://flame.ipkeys.com:9443/socket/msg"
        sslopt = {"ca_certs": 'IPKeys_Root.pem'}
        try:
            ws = create_connection(ws_url, sslopt=sslopt)

            # 1. query server

            start =  query_start.strftime(TIME_FORMAT)
            granularity = 1
            # granularity =  'PT1H'
            duration = 'PT24H'

            repeat = True
            print("Querying " + start)
            bl = Baseline(start, granularity, duration, ws)
            try:
                bl.process()
                repeat = False

                # 2. combine with existing dataset
                if forecasts is None:
                    forecasts = bl.forecast
                else:
                    forecasts = forecasts.combine_first(bl.forecast)

                forecast_dict.update({bl.forecast.index[0]:bl.forecast['value'].tolist()})
                cur_end_time = query_start
            except:
                print("query failed - skipping!")
        except:
            print('query failed - no connection?')
            pass

        # 3. increment query_start
        query_start = query_start +timedelta(hours=res)

    orig_start_time = datetime.strptime(start_time, TIME_FORMAT)

    suffix = str(query_start.second) + '_' + str(res)+'_'+orig_start_time.strftime('%Y%m%d') + '_' + cur_end_time.strftime('%Y%m%d')
    matrix_fname    = 'forecast_matrix_'+suffix+'.csv'
    forecasts_fname = 'forecasts_' + suffix + '.csv'

    forecast_matrix = pd.DataFrame(forecast_dict).T
    forecast_matrix.to_csv(matrix_fname)
    forecasts.to_csv(forecasts_fname)
    #forecast_matrix.to_csv('forecast_matrix_mill_020719.csv')
    #forecasts.to_csv("forecasts_mill_020719.csv")

    pass


def store_loadreports(start_time, end_time):
    query_start = datetime.strptime(start_time, TIME_FORMAT)
    end_datetime = datetime.strptime(end_time, TIME_FORMAT)

    load_reports = None

    while query_start < end_datetime:
        # 0. Connect to server
        ws_url = "wss://flame.ipkeys.com:9443/socket/msg"
        sslopt = {"ca_certs": 'IPKeys_Root.pem'}
        ws = create_connection(ws_url, sslopt=sslopt)

        # 1. query server

        start = query_start.strftime(TIME_FORMAT)

        print("Querying " + start)


        loadReport_kwargs = {
            "dstart": start, #"2018-07-14T00:00:00",        #start time for report
            "sampleInterval": "PT1H",            #sample interval
            "duration": "PT24H",           # duration of request
            "facilities": ["Facility2"] #"["Facility1", "Facility2", "Facility3"]
        }
        lr = LoadReport(ws, **loadReport_kwargs)

        try:
            lr.process()

            # 2. combine with existing dataset
            if load_reports is None:
                load_reports = lr.loadSchedule
            else:
                load_reports = load_reports.combine_first(lr.loadSchedule)
        except:
            print("query failed - skipping!")

        # 3. increment query_start
        query_start = query_start + timedelta(days=1)

    load_reports.to_csv("stored_loadreports.csv")

    pass





if __name__ == '__main__':

    ws_url = "wss://flame.ipkeys.com:9443/socket/msg"
    # old way
    # ws = create_connection(ws_url, timeout=None)
    # insecure way, use this if certificate is giving problems
    # sslopt = {"cert_reqs": ssl.CERT_NONE}
    # secure way
    sslopt = {"ca_certs": 'IPKeys_Root.pem'}

    ws = create_connection(ws_url, sslopt=sslopt)

    TEST_BASELINE   = False
    TEST_STATUS     = False
    TEST_LOADSHIFT  = True
    TEST_STATUS     = False
    TEST_LOADSELECT = False
    TEST_LOADREPORT = False
    STORE_FORECASTS = False


    # Baseline
    def test_Baseline():
        print("running Baseline")
        start =  '2019-03-29T00:00:00'
        granularity = 1
        # granularity =  'PT1H'
        duration = 'PT24H'
        bl = Baseline(start, granularity, duration, ws)
        print("processing Baseline")
        bl.process()
        print("Here's the Baseline forecast:\n", bl.forecast)
        print("done processing Baseline")
        return bl
    if TEST_BASELINE == True:
        bl = test_Baseline()
##
    def test_LoadShift():
        print("running LoadShift")
        # LoadShift
        current_tz = pytz.timezone('US/Eastern')
        start_time = current_tz.localize(datetime(year=2019,month=04,day=26,hour=15))
        ls = LoadShift(websocket = ws,
                       start_time = start_time)
        ls.process()
        print("Here's the LoadShift forecast:\n", ls.forecast)
        print("done processing LoadShift")
        return ls
    if TEST_LOADSHIFT == True:
        ls = test_LoadShift()
        #ls.forecast.to_csv("loadshift.csv")

    ##
    def test_LoadSelect():
        print("running LoadSelect")
        lsel = LoadSelect(ws, 1234)
        lsel.process()
        # print("Here's the LoadSelect response:\n", lsel.response)
        print("Here's the LoadSelect status:\n", lsel.status)
        print("done processing LoadSelect")
        return lsel
    if TEST_LOADSELECT == True:
        # Actuates things!!
        lsel = test_LoadSelect()

    ##
    def test_LoadReport():
        print("running LoadReport")
        current_time = datetime.now().replace(microsecond=0, second=0, minute=0)
        time_delta = timedelta(hours=24)
        start_time = datetime.strptime('2018-10-16T02:25:00', "%Y-%m-%dT%H:%M:%S")#current_time - time_delta
        print(start_time)
        loadReport_kwargs = {
            "dstart": start_time.strftime("%Y-%m-%dT%H:%M:%S"), #"2018-07-14T00:00:00",        #start time for report
            "sampleInterval": "PT1M",            #sample interval
            "duration": "PT1H",           # duration of request
            "facilities": ["Facility1", "Facility2", "Facility3"]
            # "facilities": ["Mill", "Canner", "School"]
        }
        lr = HiResLoadReport(ws, **loadReport_kwargs)
        lr.process()
        # print("Here's the LoadReport response:\n", lr.response)
        print("Here's the LoadReport loadSchedule:\n")# str(lr.loadSchedule))
        print(lr.loadSchedule)
        print("done processing LoadReport")
        return lr
    if TEST_LOADREPORT == True:
        lr = test_LoadReport()
    ##

    def test_Status():
        print("running Status")
        status = Status(ws)
        print("Status processing")
        status.process()
        # print("Here's the Status response:\n", status.response)
        print("Here's the Status alertStatus:\n", status.alertStatus)
        print("Here's the Status currentProfile:\n", status.currentProfile)
        print("done processing Status")
        return status
    if TEST_STATUS == True:
        status = test_Status()
    ##

    if STORE_FORECASTS == True:
        start_time = "2019-01-03T00:00:04"
        end_time   = "2019-03-29T00:00:04"
        store_forecasts(start_time, end_time, res=1)
        #store_loadreports(start_time, end_time)
