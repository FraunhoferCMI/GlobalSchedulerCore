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

from datetime import datetime, timedelta
import logging
import sys
import os
import csv
from volttron.platform.vip.agent import Agent, Core, PubSub, compat, RPC
from volttron.platform.agent import utils
from volttron.platform.messaging import headers as headers_mod

from gs_identities import (SSA_SCHEDULE_RESOLUTION, USE_VOLTTRON)

utils.setup_logging()
_log = logging.getLogger(__name__)
__version__ = '1.0'


def get_schedule():
    """
    Returns the start time of the next dispatch schedule command
    :return: new_time - the start time of the next dispatch schedule period
    """

    if USE_VOLTTRON == 1:
        # FIXME - implicitly assumes SSA_SCHEDULE_RESOLUTION <= 60 minutes
        TimeStamp = utils.get_aware_utc_now()
    else:
        TimeStamp = datetime.utcnow()
    minutes = TimeStamp.minute
    rem = minutes % SSA_SCHEDULE_RESOLUTION  # GS_SCHEDULE
    new_time = TimeStamp + timedelta(minutes=SSA_SCHEDULE_RESOLUTION - rem)  # GS_SCHEDULE
    new_time = new_time.replace(second=0, microsecond=0)

    # this gives now + gs_schedule period, truncated to the top of the minute
    # e.g., 1208 --> set to 1223.
    # now we need to round down.
    # so you want to get minutes mod GS_SCHEDULE - remainder

    # new_time  = new_time.replace(minute=0, second=0, microsecond=0)
    print("TimeStamp = " + TimeStamp.strftime("%Y-%m-%dT%H:%M:%S.%f"))
    print("new_time = " + new_time.strftime("%Y-%m-%dT%H:%M:%S.%f"))
    time_str = new_time.strftime("%Y-%m-%dT%H:%M:%S.%f")
    return time_str


class ForecastObject():
    ##############################################################################
    def __init__(self, length, units, datatype):
        forecast_values = {"Forecast": [0.0]*length,
                           "Time": [0]*length}
        forecast_meta_data = {"Forecast": {"units": units, "type": datatype},
                              "Time": {"units": "UTC", "type": "str"}}

        self.forecast_obj = [forecast_values, forecast_meta_data]



