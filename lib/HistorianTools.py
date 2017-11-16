from datetime import datetime, timedelta
import logging
import sys
import os
import csv
from volttron.platform.vip.agent import Agent, Core, PubSub, compat, RPC
from volttron.platform.agent import utils
from volttron.platform.messaging import headers as headers_mod

from gs_identities import (INTERACTIVE, AUTO, SITE_IDLE, SITE_RUNNING, PMC_WATCHDOG_RESET)

utils.setup_logging()
_log = logging.getLogger(__name__)
__version__ = '1.0'


##############################################################################
def publish_data(agent_object, base_topic, TimeStamp_str, endpt_label, val):
    """
    method for publishing database topics.  
    Input is a timestamp that has been converted to a string
    """

    # 1. build the path:
    # publish to a root topic that is "datalogger/base_topic":
    topic = "datalogger/"+base_topic

    # 2. build a datalogger-compatible msg:
    msg = {
        endpt_label: {
            "Readings":[TimeStamp_str, val], 
            "Units": "",
            "tz":"UTC",    #FIXME: timezone ?????
            "data_type":"uint"} #FIXME: data type????
        }

    _log.debug("Publish: "+endpt_label+": "+str(msg[endpt_label])+" on "+ topic)

    # 3. publish:
    agent_object.vip.pubsub.publish('pubsub', 
                                    topic, 
                                    headers={}, 
                                    message=msg).get(timeout=10.0)

