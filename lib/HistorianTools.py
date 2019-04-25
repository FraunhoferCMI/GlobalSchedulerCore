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
import pandas as pd
from gs_identities import TIME_FORMAT, SIM_HRS_PER_HR, USE_SIM
import pytz

utils.setup_logging()
_log = logging.getLogger(__name__)
__version__ = '1.0'


##############################################################################
def publish_data(agent_object, base_topic, units, endpt_label, val, TimeStamp_str=None, ref_time = None):
    """
    method for publishing database topics.  
    Input is a timestamp that has been converted to a string
    """

    # 1. build the path:
    # publish to a root topic that is "datalogger/base_topic":
    topic = "datalogger/"+base_topic

    if TimeStamp_str == None:
        TimeStamp = utils.get_aware_utc_now() # datetime.now()
        TimeStamp_str = TimeStamp.strftime("%Y-%m-%dT%H:%M:%S.%f")

    elif USE_SIM == 1:
        t = datetime.strptime(TimeStamp_str, TIME_FORMAT).replace(tzinfo=pytz.UTC)
        if ref_time is None:
            ref_time = datetime.utcnow().replace(tzinfo=pytz.UTC)
        elapsed = (t - ref_time) / SIM_HRS_PER_HR
        t = ref_time+elapsed
        TimeStamp_str = t.strftime(TIME_FORMAT)

    # 2. build a datalogger-compatible msg:
    msg = {
        endpt_label: {
            "Readings":[TimeStamp_str, val], 
            "Units": units,
            "tz":"UTC",    #FIXME: timezone ?????
            "data_type":"uint"} #FIXME: data type????
        }

    _log.debug("Publish: "+endpt_label+": "+str(msg[endpt_label])+" on "+ topic)

    # 3. publish:
    agent_object.vip.pubsub.publish('pubsub', 
                                    topic, 
                                    headers={}, 
                                    message=msg).get(timeout=10.0)


##############################################################################
def query_data(agent_object, topic_name, query_start, query_end, max_count=1000):
    #topic_name = "datalogger/ShirleySouth/PVPlant/Inverter1/OpStatus/Pwr_kW"
    #query_start = "2019-03-13T21:00:00"
    #query_end   = "2019-03-13T23:00:00"
    data = agent_object.vip.rpc.call("platform.historian",
                                     "query",
                                     topic_name,
                                     start=query_start,
                                     end=query_end,
                                     count=max_count).get(timeout=5)
    return data

##############################################################################
def calc_avg(agent_object, topic ,st, end):
    #_log.info(st + " "+end)
    data = query_data(agent_object, topic, st, end)
    #_log.info(data)
    if len(data) != 0:
        vals = [float(v[1]) for v in data['values']]
        ts   = [pd.to_datetime(v[0]) for v in data['values']]
        df = pd.DataFrame(data=vals,index=ts)
        n_pts = len(df)
        if len(df) != 0:
            avg = df[0].mean()
            #avg  = sum(vals) / float(n_pts)
        else:
            avg = 0
            n_pts = 0
    else:
        avg = 0
        n_pts = 0
    #_log.info("avg value is "+str(avg)+" over "+ str(n_pts)+" points")
    return avg, n_pts