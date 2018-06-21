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
from volttron.platform.messaging import headers as headers_mod

from gs_identities import (SSA_SCHEDULE_RESOLUTION, SSA_SCHEDULE_DURATION, USE_VOLTTRON, SIM_HRS_PER_HR)
import pytz

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
    _log.info("Cur time: " + now.strftime("%Y-%m-%dT%H:%M:%S") + "; gs start time= " + gs_start_time.strftime("%Y-%m-%dT%H:%M:%S"))

    run_time         = (now - gs_start_time).total_seconds() # tells the elapsed real time
    sim_run_time     = timedelta(seconds=SIM_HRS_PER_HR * run_time)  # tells the elapsed "accelerated" time
    # was .total_seconds()
    #adj_sim_run_time = timedelta(seconds=sim_run_time - run_time)  # difference between GS frame of reference and real time

    _log.info("sim run time = " + str(sim_run_time) + "; actual run time = " + str(run_time))
    return gs_start_time+sim_run_time-sim_time_corr  # current time, in the GS frame of reference

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
    return gs_root_dir + local_path + fname


##############################################################################
class ForecastObject():
    """
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
    def __init__(self, forecast, time, units, datatype):
        assert isinstance(forecast, list)
        assert isinstance(time, list)
        self.forecast = forecast
        self.time = time
        self.units = units
        self.datatype = datatype

        self.serialize()
        return None

    def serialize(self):
        self.forecast_values = {"Forecast": self.forecast,
                                "Time": self.time,
                                "Duration": SSA_SCHEDULE_DURATION,
                                "Resolution": SSA_SCHEDULE_RESOLUTION}
        self.forecast_meta_data = {"Forecast": {"units": self.units, "type": self.datatype},
                                   "Time": {"units": "UTC", "type": "str"},
                                   "Duration": {"units": "hr", "type": "int"},
                                   "Resolution": {"units": "min", "type": "int"}}

        self.forecast_obj = [self.forecast_values, self.forecast_meta_data]

        return self.forecast_obj

    def check_forecast(self):
        "Check the consistency of data of Forecast attributes"
        assert len(self.forecast_values["Forecast"]) == len(self.forecast_values["Time"])
        return None


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
