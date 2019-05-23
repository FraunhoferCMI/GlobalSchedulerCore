# Copyright (c) 2018, The Fraunhofer Center for Sustainable Energy
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

from datetime import datetime, timedelta
import logging
import sys
import os
import csv
from volttron.platform.vip.agent import Agent, Core, PubSub, compat, RPC
from volttron.platform.agent import utils
from volttron.platform.messaging import headers as header_mod

from gs_identities import *
import pytz
import pandas as pd

MINUTES_PER_YR = 365 * MINUTES_PER_DAY  # valid for our database files - assume no leap years
SOLAR_NAMEPLATE = 500

utils.setup_logging()
_log = logging.getLogger(__name__)
__version__ = '1.0'

##############################################################################
def get_schedule(gs_start_time,
                 resolution = SSA_SCHEDULE_RESOLUTION,
                 sim_time_corr = timedelta(seconds=0),
                 adj_sim_run_time = timedelta(hours=0)):
    """
    Returns the start time of the next dispatch schedule command
    Strips out seconds, microseconds, etc.  Rounds to the next SSA_SCHEDULE_RESOLUTION time step
    :return: new_time - the start time of the next dispatch schedule period
    """
    TimeStamp = get_gs_time(gs_start_time,sim_time_corr)

    gs_run_time = TimeStamp-gs_start_time   # time, in gs frame of reference, since gs start

    baseline = datetime(year=1900, month=1, day=1) # arbitrary starting point

    minutes = (baseline+gs_run_time).minute

    #if USE_VOLTTRON == 1:
    #    # FIXME - implicitly assumes SSA_SCHEDULE_RESOLUTION <= 60 minutes
    #    TimeStamp = utils.get_aware_utc_now() - sim_time_corr + adj_sim_run_time
    #else:
    #    TimeStamp = datetime.utcnow() - sim_time_corr + adj_sim_run_time

    #
    # minutes = TimeStamp.minute
    rem = minutes % resolution

    start_of_schedule = (baseline+(gs_run_time - timedelta(minutes=rem))).replace(second=0, microsecond=0) -baseline # todo - temp fix - moves forecast to tstep-1
    new_time = gs_start_time+start_of_schedule

    #new_time = TimeStamp + timedelta(minutes=SSA_SCHEDULE_RESOLUTION - rem)  # GS_SCHEDULE
    #new_time = TimeStamp - timedelta(minutes=rem) # todo - temp fix - moves forecast to tstep-1
    #new_time = new_time.replace(second=0, microsecond=0)

    # this gives now + gs_schedule period, truncated to the top of the minute
    # e.g., 1208 --> set to 1223.
    # now we need to round down.
    # so you want to get minutes mod GS_SCHEDULE - remainder

    # new_time  = new_time.replace(minute=0, second=0, microsecond=0)
    #_log.info("Sim time adjustment = "+str(adj_sim_run_time))
    _log.info("TimeStamp = " + TimeStamp.strftime("%Y-%m-%dT%H:%M:%S.%f"))
    _log.info("new_time = " + new_time.strftime("%Y-%m-%dT%H:%M:%S.%f"))
    _log.info("time corr= "+ str(sim_time_corr))
    time_str = new_time.strftime("%Y-%m-%dT%H:%M:%S.%f")
    return time_str


##############################################################################
def get_gs_time(gs_start_time, sim_time_corr):
    """
    returns the time in the Global Scheduler frame of reference.
    :return:
    """

    # need to fix this so that it works(?) before gs_start_time is assigned?
    if USE_VOLTTRON == 1:
        # FIXME - implicitly assumes SSA_SCHEDULE_RESOLUTION <= 60 minutes
        now = utils.get_aware_utc_now()
    else:
        now = datetime.utcnow()
    #gs_aware = gs_start_time.replace(tzinfo=pytz.UTC)
    _log.info("Cur time: " + now.strftime("%Y-%m-%dT%H:%M:%S") )
    _log.info("gs start time= " + gs_start_time.strftime("%Y-%m-%dT%H:%M:%S"))

    # now = now.replace(tzinfo=None) # TODO understand what needs timezone and what doesn't
    # gs_start_time = gs_start_time.replace(tzinfo=now.tzinfo)
    run_time         = (now - gs_start_time).total_seconds() # tells the elapsed real time
    sim_run_time     = timedelta(seconds=SIM_HRS_PER_HR * run_time)  # tells the elapsed "accelerated" time
    # was .total_seconds()
    #adj_sim_run_time = timedelta(seconds=sim_run_time - run_time)  # difference between GS frame of reference and real time

    _log.info("sim run time = " + str(sim_run_time) + "; actual run time = " + str(run_time))
    gs_time = gs_start_time + sim_run_time - sim_time_corr  # current time, in the GS frame of reference

    return gs_time

##############################################################################
def get_gs_path(local_path, fname):
    """
    method for returning a system-independent file path.  Requires user to define environment variable GS_ROOT_DIR,
    which should provide a full path to the GlobalSchedulerCore directory (i.e., "xxx/GlobalSchedulerCore/"
    :param local_path: relative path from the top node in the GS directory tree (i.e., GlobalSchedulerCore/)
    :param fname: file name
    :return: full path name within the GS_ROOT_DIR directory tree for a data file
    """
    gs_root_dir = os.environ['GS_ROOT_DIR']
    return os.path.join(gs_root_dir , local_path , fname)

##############################################################################
def get_pv_correction_factors(forecast, ts, reference_forecast,
                              correction_type='Matrix',
                              correction_file='pv_correction_factors_v2.csv'):
    if correction_type == 'Matrix':
        ghi_high_threshold = 5000
        ghi_med_threshold = 3000
        fname_fullpath = get_gs_path('lib/', correction_file)
        corr_factors = pd.read_csv(fname_fullpath)
        # reference_forecast = np.array(ref)
        total_ghi = sum(reference_forecast)

        if total_ghi > ghi_high_threshold:
            k = 'High'
        elif total_ghi > ghi_med_threshold:
            k = 'Med'
        else:
            k = 'Low'

        for ii in range(0, len(forecast)):
            forecast[ii] = corr_factors[k][ts[ii].hour] * forecast[ii]
            #_log.info("Corr: "+str(corr_factors[k][ts[ii].hour])+" - "+str(forecast[ii]))

    elif correction_type == 'ML': # Machine-learning based approach
        fname_fullpath = get_gs_path('lib/', correction_file)
        #get_solar_predictions(forecast, reference_forecast, ts, fname_fullpath)
        pass
    return forecast
    # return corr_factors[k]

##############################################################################
class ForecastObject():
    """
    deprecated?
    Data class for storing forecast data in a serializable format that is consumable by the VOLTTRON Historian
    """
    ##############################################################################
    def __init__(self, length, units, datatype, nForecasts = 1):
        self.forecast_values = {"Forecast": [[0.0]*length]*nForecasts,
                                "Time": [0]*length,
                                "Duration": SSA_SCHEDULE_DURATION,
                                "Resolution": SSA_SCHEDULE_RESOLUTION}
        self.forecast_meta_data = {"Forecast": {"units": units, "type": datatype},
                                   "Time": {"units": "UTC", "type": "str"},
                                   "Duration": {"units": "hr", "type": "int"},
                                   "Resolution": {"units": "min", "type": "int"}}

        self.forecast_obj = [self.forecast_values, self.forecast_meta_data]

class Forecast():
    """
    Stores forecast data in a serializable format that is consumable by the
    VOLTTRON Historian
    """
    def __init__(self, forecast, time, units, datatype, ghi = None,
                 duration =  SSA_SCHEDULE_DURATION,
                 resolution = SSA_SCHEDULE_RESOLUTION,
                 labels = None,
                 use_correction = False,
                 correction_type = None,
                 correction_file = None):
        assert isinstance(forecast, list)
        assert isinstance(time, list)
        self.time = time
        self.units = units
        self.datatype = datatype
        self.duration = duration
        self.resolution = resolution
        self.ghi      = ghi

        ts = [datetime.strptime(v, TIME_FORMAT) for v in time]
        if use_correction == True:
            self.forecast = get_pv_correction_factors(forecast[:], ts[:], ghi[:], correction_type, correction_file)
        else:
            self.forecast = forecast[:]

        self.orig_forecast = forecast[:]

        if labels == None:
            self.labels = {"Forecast": "Forecast",
                           "OrigForecast": "OrigForecast",
                           "Time": "Time",
                           "Duration": "Duration",
                           "Resolution": "Resolution",
                           "ghi": "ghi"}
        else:
            self.labels = labels


        self.serialize()
        return None

    def serialize(self):
        if self.ghi == None:
            self.forecast_values = {self.labels["Forecast"]: self.forecast,
                                    self.labels["OrigForecast"]: self.orig_forecast,
                                    self.labels["Time"]: self.time,
                                    self.labels["Duration"]: self.duration,
                                    self.labels["Resolution"]: self.resolution}
            self.forecast_meta_data = {self.labels["Forecast"]: {"units": self.units, "type": self.datatype},
                                       self.labels["OrigForecast"]: {"units": self.units, "type": self.datatype},
                                       self.labels["Time"]: {"units": "UTC", "type": "str"},
                                       self.labels["Duration"]: {"units": "hr", "type": "int"},
                                       self.labels["Resolution"]: {"units": "min", "type": "int"}}
        else:
            self.forecast_values = {self.labels["Forecast"]: self.forecast,
                                    self.labels["OrigForecast"]: self.orig_forecast,
                                    self.labels["ghi"]: self.ghi,
                                    self.labels["Time"]: self.time,
                                    self.labels["Duration"]: self.duration,
                                    self.labels["Resolution"]: self.resolution}
            self.forecast_meta_data = {self.labels["Forecast"]: {"units": self.units, "type": self.datatype},
                                       self.labels["OrigForecast"]: {"units": self.units, "type": self.datatype},
                                       self.labels["ghi"]: {"units": self.units, "type": self.datatype},
                                       self.labels["Time"]: {"units": "UTC", "type": "str"},
                                       self.labels["Duration"]: {"units": "hr", "type": "int"},
                                       self.labels["Resolution"]: {"units": "min", "type": "int"}}


        self.forecast_obj = [self.forecast_values, self.forecast_meta_data]

        return self.forecast_obj

    def check_forecast(self):
        "Check the consistency of data of Forecast attributes"
        assert len(self.forecast_values["Forecast"]) == len(self.forecast_values["Time"])
        return None

    ##############################################################################
    def shift_timestamps(self, gs_start_time):

        gs_aware = gs_start_time.replace(tzinfo=pytz.UTC)
        next_forecast_start_time = datetime.strptime(get_schedule(gs_aware),
                                                     "%Y-%m-%dT%H:%M:%S.%f")
        # Need to convert panda series to flat list of timestamps and irradiance data
        # that will comprise the next forecast:
        next_forecast_timestamps = [next_forecast_start_time +
                                    timedelta(minutes=t) for t in range(0,
                                                                        SSA_SCHEDULE_DURATION*MINUTES_PER_HR,
                                                                        SSA_SCHEDULE_RESOLUTION)]

        self.forecast_values['Time'] = [datetime.strftime(ts, "%Y-%m-%dT%H:%M:%S") for ts in
                                        next_forecast_timestamps]



###################################################################
class StoredForecast(ForecastObject):
    """
    class for handling serializable forecasts from previously stored data
    """

    ###################################################################
    def __init__(self, length, units, datatype, gs_start_time,
                 forecast_fname = PV_FORECAST_FILE,
                 ts_fname = None,
                 time_resolution_min = PV_FORECAST_FILE_TIME_RESOLUTION_MIN,
                 nForecasts = 1,
                 scale = -1*SOLAR_NAMEPLATE/100.0):

        ForecastObject.__init__(self, length, units, datatype, nForecasts)

        volttron_root = os.getcwd()
        volttron_root = volttron_root + "/../../../../gs_cfg/"
        forecast_fname_full = (volttron_root + forecast_fname)
        _log.info(forecast_fname_full)

        if ts_fname is not None:
            ts_fname_full = volttron_root+ts_fname
        else:
            ts_fname_full = None

        self.last_query    = None
        self.gs_start_time = gs_start_time
        self.forecast_database = self.load_forecast_file(forecast_fname_full,
                                                         ts_fname_full,
                                                         time_resolution_min)
        self.scale_factor   = scale
        return None

    ###################################################################
    def load_forecast_file(self,
                           fname = PV_FORECAST_FILE,
                           ts_fname = None,
                           csv_time_resolution_min=PV_FORECAST_FILE_TIME_RESOLUTION_MIN):

        """
        Load a csv file of forecast values.
        The csv file is interpreted as follows:
        (1) each row is an forecast value, starting from jan 1st
        (2) the time step between rows is defined by csv_time_resolution_min
        (3) the file is assumed to comprise exactly a single year of data

        Use user-defined offsets set in gs_identities (SIM_START_DAY, SIM_START_HR) to figure out where to start
        Synchronize this start time to the time when the GS executive started.

        these configuration parameters are set within gs_identities.py:
        SIM_START_DAY
        SIM_START_HR
        PV_FORECAST_FILE - name of an appropriately formatted irradiance csv
        PV_FORECAST_RILE_TIME_RESOLUTION_MIN - time resolution, in minutes, of data in the csv irradiance file
        """

        # Get irradiance data from csv file and populate in ghi_array

        forecast_array = []

        try:
            with open(fname, 'rb') as csvfile:
                csv_data = csv.reader(csvfile)

                for row in csv_data:
                    # _log.info("val = "+str(row[0]))
                    forecast_array.append(float(row[0]))
        except IOError as e:
            _log.info("forecast database " + fname + " not found")

        # Now construct a full year's worth of irradiance data.
        # It re-indexes the irradiance file such that start day / start hour is
        # set to the ACTUAL time at which the GS Executive started.
        pts_per_day = int((MINUTES_PER_DAY) / csv_time_resolution_min)
        start_ind = int((SIM_START_DAY - 1) * pts_per_day + SIM_START_HR * MINUTES_PER_HR / csv_time_resolution_min)

        _log.info("start index is: " + str(start_ind) + "; SIM_START_DAY is " + str(SIM_START_DAY))

        # now set up a panda.Series with indices = timestamp starting from GS start time,
        # time step from csv_time_resolution_min; and with values = ghi_array, starting from the index corresponding
        # to start day / start time
        forecast_timestamps = [self.gs_start_time + timedelta(minutes=t) for t in
                               range(0, MINUTES_PER_YR, csv_time_resolution_min)]
        forecast_array_reindexed = []
        forecast_array_reindexed.extend(forecast_array[start_ind:])
        forecast_array_reindexed.extend(forecast_array[:start_ind])
        forecast_series_init = pd.Series(data=forecast_array_reindexed, index=forecast_timestamps)

        # next resample to the time resolution of the GS optimizer.
        if csv_time_resolution_min != SSA_SCHEDULE_RESOLUTION:  # need to resample!!
            sample_pd_str = str(SSA_SCHEDULE_RESOLUTION) + "min"
            forecast_series = forecast_series_init.resample(sample_pd_str).mean()
            if csv_time_resolution_min > SSA_SCHEDULE_RESOLUTION:  # interpolate if upsampling is necessary
                forecast_series = forecast_series.interpolate(method='linear')
        else:  # resampling is unnecessary
            forecast_series = forecast_series_init

        _log.info(str(forecast_series.head(48)))

        return forecast_series


    ##############################################################################
    def get_timestamps(self,
                       sim_time_corr = timedelta(0)):

        gs_aware = self.gs_start_time.replace(tzinfo=pytz.UTC)
        next_forecast_start_time = datetime.strptime(get_schedule(gs_aware,
                                                                  sim_time_corr = sim_time_corr),
                                                     "%Y-%m-%dT%H:%M:%S.%f")
        # Need to convert panda series to flat list of timestamps and irradiance data
        # that will comprise the next forecast:
        next_forecast_timestamps = [next_forecast_start_time +
                                    timedelta(minutes=t) for t in range(0,
                                                                        SSA_SCHEDULE_DURATION*MINUTES_PER_HR,
                                                                        SSA_SCHEDULE_RESOLUTION)]

        return next_forecast_timestamps


    ###################################################################
    def parse_query(self, sim_time_corr):

        pass

###################################################################
class StoredSolarForecast(StoredForecast):

    def parse_query(self, sim_time_corr):
        """
        Retrieves a solar forecast in units of "Pct"
            - start time of the forecast is defined by calling get_schedule()
            - Forecast duration is defined by SSA_SCHEDULE_DURATION
            - Forecast time step is defined by SSA_SCHEDULE_RESOLUTION
        """

        # get the start time of the forecast

        # to do so: (1) check if we went to sleep since the last forecast retrieved.  If so, use a correction to
        # make it look like no time has elapsed; (2) if accelerated time is being used, translate actual elapsed time
        # into accelerated time

        now = utils.get_aware_utc_now()

        if self.last_query != None:
            delta = now - self.last_query
            expected_delta = timedelta(seconds=CPR_QUERY_INTERVAL)
            if delta > expected_delta * 2:
                # maybe we went to sleep?
                _log.info("Expected Delta = " + str(expected_delta))
                _log.info("Delta = " + str(delta))
                sim_time_corr += delta - expected_delta
                _log.info("CPR: Found a time correction!!!!")
                _log.info("Cur time: " + now.strftime("%Y-%m-%dT%H:%M:%S") + "; prev time= " + self.last_query.strftime(
                    "%Y-%m-%dT%H:%M:%S"))

        self.last_query = now
        _log.info("ForecastSim time correction: " + str(sim_time_corr))

        next_forecast_timestamps = self.get_timestamps(sim_time_corr=sim_time_corr)
        next_forecast = self.forecast_database.get(next_forecast_timestamps)

        print("NEXT FORECAST SOLAR")

        minute_next_forecast = next_forecast.resample('min').mean().interpolate()
        print(minute_next_forecast)

        # Convert irradiance to a percentage
        self.forecast_values["Forecast"] = [100 * v / 1000 for v in next_forecast]
        self.forecast_values["Time"] = [datetime.strftime(ts, "%Y-%m-%dT%H:%M:%S") for ts in
                                        next_forecast_timestamps]  # was .%f
        _log.info("Solar forecast is:" + str(self.forecast_values["Forecast"]))
        _log.info("timestamps are:" + str(self.forecast_values["Time"]))

        # for publication to IEB:
        return self.forecast_obj, sim_time_corr

###################################################################
class StoredMatrixForecast(StoredForecast):


    ###################################################################
    def format_index(self, df):
        df.index = df.ts
        df.index = pd.to_datetime(df['ts'])
        df.index = df.index.tz_localize('UTC', ambiguous='NaT')
        df = df.drop('ts', axis=1)
        return df


    ###################################################################
    def load_forecast_file(self,
                           forecast_fname = PV_FORECAST_FILE,
                           ts_fname = None,
                           csv_time_resolution_min = PV_FORECAST_FILE_TIME_RESOLUTION_MIN):

        forecast_database = pd.read_csv(forecast_fname)
        forecast_database = self.format_index(forecast_database)
        ts_database       = pd.read_csv(ts_fname)
        ts_database       = self.format_index(ts_database)
        print(ts_database['0'].iloc[0:100])
        return forecast_database, ts_database

    ##############################################################################
    def get_correction_factors(self, forecast, ts, reference_forecast):
        return forecast

    ###################################################################
    def parse_query(self, sim_time_corr, reference_forecast = None):
        """
        parses a solar query from a pandas dataframe that is organized as ts x 24 data points (1 per hr)
        this lets us use historical forecasts as they are stored in the database.
        :return:
        """

        # load ts matrix
        # load generation matrix
        # load ghi matrix
        # set time stamps to utc

        # assume file has been loaded

        # where does gs time come from?

        gs_start_time_aware = self.gs_start_time.replace(tzinfo=pytz.UTC)
        cur_gs_time = get_gs_time(gs_start_time_aware, timedelta(0))

        print(cur_gs_time)
        print(gs_start_time_aware)

        elapsed_time = cur_gs_time - gs_start_time_aware

        cur_ts = SIM_START_TIME.replace(tzinfo=pytz.UTC) + elapsed_time


        _log.info("cur gs time is: "+str(cur_ts))
        # publish the last forecast whose index is closest to the cur_gs_time
        # don't publish forecasts more than 1 hr old?


        values_database = self.forecast_database[0]
        ts_database     = self.forecast_database[1]

        sl = values_database.loc[values_database.index < cur_ts]
        time_sl = ts_database.loc[ts_database.index < cur_ts]
        # sl = df.loc[df.index < ts]

        if (cur_ts - sl.index[len(sl) - 1]) <= timedelta(minutes=60):
            # only use if forecast is < 1 hr old
            most_recent_forecast = sl.index[len(sl) - 1]
            _log.info("Getting Solar forecast from: " + str(most_recent_forecast))
            actual_timestamps = pd.to_datetime(time_sl.iloc[len(time_sl)-1])
            next_forecast_timestamps = self.get_timestamps(sim_time_corr)

            # Convert irradiance to a percentage
            self.forecast_values["Forecast"] = [v / self.scale_factor for v in sl.iloc[len(sl) - 1]]
            self.forecast_values["Forecast"] = self.get_correction_factors(self.forecast_values["Forecast"],
                                                                           actual_timestamps,
                                                                           reference_forecast)
            self.forecast_values["Time"] = [datetime.strftime(ts, "%Y-%m-%dT%H:%M:%S") for ts in
                                            next_forecast_timestamps]

            #self.forecast_values["Time"] = time_sl.iloc[len(time_sl) - 1].tolist()  # was .%f
            _log.info("Solar forecast is:" + str(self.forecast_values["Forecast"]))
            _log.info("timestamps are:" + str(self.forecast_values["Time"]))

            # for publication to IEB:
            return self.forecast_obj, sim_time_corr
        else:
            return None, sim_time_corr


        pass

###################################################################
class StoredSolarMatrixForecast(StoredMatrixForecast):

    ##############################################################################
    def get_correction_factors(self, forecast, ts, reference_forecast):
        return get_pv_correction_factors(forecast, ts, reference_forecast)

###################################################################
class StoredDemandForecast(StoredForecast):

    ##############################################################################
    def parse_load_report(self, sim_time_corr):
        """
        Retrieves a load report in units of "kW"
            - start time of the forecast is defined by calling get_schedule()
            - Forecast duration is defined by SSA_SCHEDULE_DURATION
            - Forecast time step is defined by SSA_SCHEDULE_RESOLUTION
        """
        next_forecast_timestamps = self.get_timestamps(sim_time_corr)
        next_forecast            = self.forecast_database.get(next_forecast_timestamps)
        print("Next Forecast")
        # this take hourly data and resamples and interpolates to one minutes
        minute_next_forecast = next_forecast.resample('min').mean().interpolate()
        # print(minute_next_forecast)
        print(minute_next_forecast[0])
        load_report = minute_next_forecast[0]
        # self.load_report = next_forecast[0]


        #TimeStamp = utils.get_aware_utc_now()  # datetime.now()
        #TimeStamp_str = TimeStamp.strftime("%Y-%m-%dT%H:%M:%S.%f")

        # 2. build a device-compatible msg:
        msg =[{'load': load_report}, {'load': {"units": 'kW',
                                               "tz": "UTC",
                                               "data_type": "float"}}]

        now = utils.get_aware_utc_now().isoformat() #datetime.strftime(utils.get_aware_utc_now(), "%Y-%m-%dT%H:%M:%S.f")

        # python code to get this is
        # from datetime import datetime
        # from volttron.platform.messaging import headers as header_mod
        header = {header_mod.DATE: datetime.utcnow().isoformat() + 'Z'}
        #"Date": "2015-11-17T21:24:10.189393Z"

        return msg, header



    ##############################################################################
    def parse_query(self, sim_time_corr):
        """
        Retrieves a demand forecast in units of "kW"
            - start time of the forecast is defined by calling get_schedule()
            - Forecast duration is defined by SSA_SCHEDULE_DURATION
            - Forecast time step is defined by SSA_SCHEDULE_RESOLUTION
        """
        next_forecast_timestamps = self.get_timestamps(sim_time_corr)
        next_forecast            = self.forecast_database.get(next_forecast_timestamps)

        # Convert irradiance to a percentage
        self.forecast_values["Forecast"] = [v for v in next_forecast]
        self.forecast_values["Time"]     = [datetime.strftime(ts, "%Y-%m-%dT%H:%M:%S") for ts in next_forecast_timestamps]
        _log.info("Demand forecast is:"+str(self.forecast_values["Forecast"]))
        _log.info("timestamps are:"+str(self.forecast_values["Time"]))

        # for publication to IEB:
        return self.forecast_obj, sim_time_corr




def from_df(df):
    """ UNDER CONSTRUCTION!!!
    Construct a Forecast from a provided Pandas DataFrame
    """

    kwargs = dict(
        forecast = [val.tolist() for key, val in df.items()],
        time = df.index.tolist(),
        # duration =
        # resolution =
        )
    forecast_class = Forecast(**kwargs)
    return forecast_class
