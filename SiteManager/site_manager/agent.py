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

from datetime import datetime, timedelta
import logging
import sys
import os
import csv
import json
import DERDevice
import HistorianTools
from volttron.platform.messaging.health import STATUS_GOOD
from volttron.platform.vip.agent import Agent, Core, PubSub, compat, RPC
from volttron.platform.agent import utils
from volttron.platform.messaging import headers as headers_mod
from volttron.platform.agent.known_identities import (
    VOLTTRON_CENTRAL, VOLTTRON_CENTRAL_PLATFORM, CONTROL, CONFIGURATION_STORE)

from . import settings
from gs_identities import *

utils.setup_logging()
_log = logging.getLogger(__name__)
__version__ = '1.0'


##############################################################################
class SiteManagerAgent(Agent):
    """
    ...
    """

    ##############################################################################
    def __init__(self, config_path, **kwargs):
        super(SiteManagerAgent, self).__init__(**kwargs)

        # Agent Configuration - legacy code
        self.default_config = {
            "DEFAULT_MESSAGE" :'SM Message',
            "DEFAULT_AGENTID": "site_manager",
            "DEFAULT_HEARTBEAT_PERIOD": 5,
            "log-level":"DEBUG"
        }
        self._config = self.default_config.copy()
        self._agent_id = self._config.get("DEFAULT_AGENTID")
        self._message = self._config.get("DEFAULT_MESSAGE")
        self._heartbeat_period = self._config.get('DEFAULT_HEARTBEAT_PERIOD')
        self.cache = {}
        self.moving_averages = {}
        self.configure(None,None,self.default_config)
        self.vip.config.subscribe(
            self.configure,
            actions=["NEW", "UPDATE"],
            pattern="config")

        # set location for data map files.
        # FIXME - shouldn't be hard-coded!!!
        self.data_map_dir = GS_ROOT_DIR+CFG_PATH+"DataMap/"
        _log.info("SiteManagerConfig: **********INITIALIIZING SITE MANAGER*******************")
        _log.info("SiteManagerConfig: Agent ID is "+self._agent_id)
        _log.info("SiteManagerConfig: data dir is "+self.data_map_dir)


        # Initialize mode, settings for the SiteManager Agent's state machine
        self.mode = STARTING
        TimeStamp = datetime.strftime(
            datetime.now(),
            "%Y-%m-%dT%H:%M:%S"
        )      
        self.last_scrape_time = datetime.now() #TimeStamp
        self.SiteStatus = {}
        self.SiteStatus.update({"ReadError": 0})
        self.SiteStatus.update({"WriteError": 0})
        self.SiteStatus.update({"DeviceError": 0})
        self.SiteStatus.update({"CmdError": 0})
        self.SiteStatus.update({"HeartbeatError": 0})
        self.SiteStatus.update({"CmdPending": 0})
        # FIXME - need to have dirty flag for each topic!
        self.dirtyFlag = 1 
        self.updating  = 0
        self.write_error_count = 0
        self.devices_to_display = ["ShirleySouth-ESSPlant-ESS1"]


    ##############################################################################
    @RPC.export
    def init_site(self,cursite):
        """
        Instantiates / initializes a new site.
        Called by the Executive
        cursite is a site constructor JSON object (from a SiteConfiguration.json file)
        """
        _log.info("SiteManagerConfig: **********INITIALIZING A NEW SITE*******************")
        _log.info("SiteManagerConfig: Site name is: "+cursite["ID"])

        # for each topic in the SiteConfiguration json object, subscribe to the designated
        # topic ID on the msg bus
        self.topics = cursite["Topics"]
        for topics in self.topics:
            self.vip.pubsub.subscribe(peer='pubsub', prefix=topics["TopicPath"], callback=self.parse_IEB_msgs) #+'/all'
            topics.update({"isValid": "N"})
            topics.update({"last_read_time": utils.get_aware_utc_now()})
            topics.update({"SCRAPE_TIMEOUT": eval(topics["TopicScrapeTimeout"])})
            _log.info("SiteManagerConfig: Subscribing to new topic: "+topics["TopicPath"]+'/all')

        self.site = DERDevice.get_site_handle(cursite, self.data_map_dir)
        self.vip.pubsub.publish('pubsub', 
                                'data/NewSite/all', 
                                headers={}, 
                                message=[self.site.device_id]).get(timeout=10.0)
        self.mode = AUTO # site is initialized - transition to auto        

    ##############################################################################
    def configure(self,config_name, action, contents):
        self._config.update(contents)
        log_level = self._config.get('log-level', 'INFO')
        if log_level == 'ERROR':
            self._logfn = _log.error
        elif log_level == 'WARN':
            self._logfn = _log.warn
        elif log_level == 'DEBUG':
            self._logfn = _log.debug
        else:
            self._logfn = _log.info
        
        # make sure config variables are valid
        try:
            pass
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
   
    ##############################################################################
    @Core.receiver('onsetup')
    def onsetup(self, sender, **kwargs):
        # Demonstrate accessing a value from the config file
        _log.info(self._message)
        self._agent_id = self._config.get('agentid')

    ##############################################################################
    @Core.receiver('onstart')
    def onstart(self, sender, **kwargs):
        if self._heartbeat_period != 0:
            self.vip.heartbeat.start_with_period(self._heartbeat_period)
            self.vip.health.set_status(STATUS_GOOD, self._message)

    ##############################################################################
    def parse_IEB_msgs(self, peer, sender, bus, topic, headers, message):
        """
        parses message on IEB published to the SiteManager's specified path, and 
        populates endpts (populate_endpts) based on message contents
        """
        _log.info("SiteManagerStatus: Topic found - "+str(topic))
        if sender == 'pubsub.compat':
            message = compat.unpack_legacy_message(headers, message)

        #_log.info("Message length is: "+message.len())
        _log.debug("Msg: "+str(message)+"\n")
        if type(message) is dict:  #FIXME temporary fix
            data = message
            meta_data = None
        else: 
            data = message[0]
            meta_data = message[1]
            #ii = 1
            #for m in message[1:]:
            #    _log.debug("Msg: "+str(ii)+" is "+str(m)+"\n")
            #    ii+=1
        #for k, v in data.items():
        #    _log.info("Message is: "+k+": "+str(v))

        # update the current topic's last read time to indicate data is fresh
        for topic_obj in self.topics:
            cur_topic_str = topic_obj["TopicPath"]+"/all"
            if cur_topic_str == topic:
                topic_obj["last_read_time"] = utils.get_aware_utc_now()
                cur_topic_name = topic_obj["TopicName"]
                _log.info("SiteManagerStatus: Topic "+topic+" read at "+datetime.strftime(topic_obj["last_read_time"], "%Y-%m-%dT%H:%M:%S"))
                break

        try:
            self.updating = 1  # indicates that data is updating - do not trust until populate end pts is complete
            self.site.populate_endpts(data, meta_data, cur_topic_name)
            self.dirtyFlag = 0 # clear dirtyFlag on new read
            self.updating = 0
        except:
            #FIXME - this should probably look for specific error to trap, right now this is
            # a catch-all for any errors in parsing incoming msg
            _log.info("Exception: in populate end_pts!!!")
        pass

    ##############################################################################
    def publish_data(self):
        """
        method for publishing database topics.  First publishes data for SiteManager
        agent itself, then it publishes it for the associated DERSite
        this is a very rough first cut

        Input is a timestamp that has been converted to a string
        """
        HistorianTools.publish_data(self,
                                    self.site.device_id+"Agent", 
                                    "", 
                                    "Mode", 
                                    self.mode)
        self.site.publish_device_data(self)

    ##############################################################################
    def log_device_status(self, device):
        _log.info(device.device_id)
        for k,v in device.op_status.data_dict.items():
            _log.info("Status-"+device.device_id+"-Ops: "+k+": "+str(v))
        for k,v in device.mode_status.data_dict.items():
            _log.info("Status-"+device.device_id+"-Mode: "+k+": "+str(v))
        for k,v in device.health_status.data_dict.items():
            _log.info("Status-"+device.device_id+"-Health: "+k+": "+str(v))
        for k,v in device.pwr_ctrl.data_dict.items():
            _log.info("Status-"+device.device_id+"-PwrCtrl: "+k+": "+str(v))
        for k,v in device.mode_ctrl.data_dict.items():
            _log.info("Status-"+device.device_id+"-ModeCtrl: "+k+": "+str(v))

        try:
            for k,v in device.config.data_dict.items():
                _log.info("Status-"+device.device_id+"-Config: "+k+": "+str(v))
        except:
            _log.info("Warning! Config not found")
            pass

        try:
            for k,v in device.qSetPtr_ctrl.data_dict.items():
                _log.info("Status-"+device.device_id+"-QSetPt: "+k+": "+str(v))

            for k,v in device.q_ctrl.data_dict.items():
                _log.info("Status-"+device.device_id+"-QModeCtrl: "+k+": "+str(v))

        except:
            _log.info("Warning! Q SetPt not found")
            pass


    ##############################################################################
    @RPC.export
    def set_devices_to_display(self, dev_str): 
       self.devices_to_display = []
       for devs in dev_str:
           self.devices_to_display.append(devs)
       #self.devices_to_display = [dev_str]

    ##############################################################################
    @RPC.export
    def update_site_status(self):

        # check if any of the assigned topics have exceeded their timeout period.
        # if so - set a readError
        # TODO: eventually make it so that each data end point has meta data that
        # TODO: links it to a topic so that you can mark individual data points as dirty
        cnt = 0
        read_status = 1
        for topic_obj in self.topics:
            TimeStamp = utils.get_aware_utc_now() # datetime.now() 

            _log.debug("Topic "+topic_obj["TopicPath"]+": Current Time = " + datetime.strftime(TimeStamp, "%Y-%m-%dT%H:%M:%S") +
            "; Last Scrape = " + datetime.strftime(topic_obj["last_read_time"], "%Y-%m-%dT%H:%M:%S"))

            deltaT = TimeStamp - topic_obj["last_read_time"]
            _log.debug("delta T "+str(deltaT))
            tot_sec = deltaT.total_seconds()

            _log.debug("Delta T = "+str(deltaT)+"; SCRAPE_TIMEOUT = "+ str(topic_obj["SCRAPE_TIMEOUT"])+"; tot sec = "+str(tot_sec))


            if tot_sec > topic_obj["SCRAPE_TIMEOUT"]:
                # need to set data as invalid.  
                # in theory, this should be done by topic, but for right now, I can just do it for the whole topic 
                # topic tree.
                #self.site.set_read_error(cnt)
                _log.info(topic_obj["TopicPath"]+": Error - Communications Timeout - time since last read is "+ str(tot_sec) + " sec")
                read_status = 0

            cnt += 1

        self.site.set_read_status(cnt,read_status)
        self.site.print_site_status()
        self.publish_data()

        for dev_str in self.devices_to_display:
            device = self.site.find_device(dev_str)
            self.log_device_status(device)

        self.SiteStatus.update({"ReadStatus": self.site.read_status})
        #self.SiteStatus.update({"WriteError": WriteError})
        self.SiteStatus.update({"DeviceStatus": self.site.device_status})
        #self.SiteStatus.update({"CmdError": CmdError})
        self.SiteStatus.update({"CommStatus": self.site.comms_status})
        self.SiteStatus.update({"CtrlMode": self.site.control_mode})
        self.SiteStatus.update({"DataAvailable": self.site.isDataValid})
        self.SiteStatus.update({"CtrlAvailable": self.site.isControlAvailable})

        return self.SiteStatus

    ##############################################################################
    @RPC.export
    def set_interactive_mode(self):
        """
        changes site's mode from "AUTO" to "INTERACTIVE"
        """
        _log.info("updating op mode!!")
        self.mode = INTERACTIVE
        self.dirtyFlag = 1 # set dirtyFlag - indicates a new write has occurred, so site data needs to update
        val = self.site.set_interactive_mode(self)

    ##############################################################################
    @RPC.export
    def set_auto_mode(self):
        """
        changes site's mode from "AUTO" to "INTERACTIVE"
        """
        _log.info("updating op mode!!")
        self.mode = AUTO
        self.dirtyFlag = 1 # set dirtyFlag - indicates a new write has occurred, so site data needs to update
        val = self.site.set_auto_mode(self)

    ##############################################################################
    @RPC.export
    def set_watchdog_timeout_enable(self, val):
        """
        changes site's watchdog timeout enable per val (either ENABLED or DISABLED
        """
        _log.info("updating watchdog timeout enable flag!!")
        self.dirtyFlag = 1 # set dirtyFlag - indicates a new write has occurred, so site data needs to update
        val = self.site.set_watchdog_timeout_enable(int(val), self)


    ##############################################################################
    @RPC.export
    def set_ramprate_real(self, device_id, val):
        # find the device
        device = self.site.find_device(device_id)

        if device == None:
            _log.info("SetPt: ERROR! Device "+device_id+" not found in "+self.site.device_id)
            # FIXME: other error trapping needed?
        else:
            # send the command
            self.dirtyFlag = 1 # set dirtyFlag - indicates a new write has occurred, so site data needs to update
            _log.info("Ramp Rate: Sending Cmd!")
            success = device.set_ramprate_real(val, self)
            if success == 0:
                self.dirtyFlag = 0 # invalid write

    ##############################################################################
    @RPC.export
    def set_real_pwr_cmd(self, device_id, val):
        """
        sends a real power command to the specified device
        """
        _log.info("SetPt: updating site power output for "+self.site.device_id)

        # find the device
        #device_id = args[0] #*args
        #val = args[1]
        device = self.site.find_device(device_id)

        if device == None:
            _log.info("SetPt: ERROR! Device "+device_id+" not found in "+self.site.device_id)
            # FIXME: other error trapping needed?
        #elif device.device_type not in self.site.DGPlant:
        #    _log.info("SetPt: ERROR! Pwr dispatch command sent to non-controllable device " + device.device_id)
        #    _log.info("SetPt: Device type = " + device.device_type)
        else:
            # send the command
            self.dirtyFlag = 1 # set dirtyFlag - indicates a new write has occurred, so site data needs to update
            _log.info("SetPt: Sending Cmd!")
            success = device.set_power_real(val, self)
            if success == 0:
                self.dirtyFlag = 0 # invalid write

    ##############################################################################
    @RPC.export
    def set_arbitrary_pt(self, device_id, attribute, pt, val):
        """
        sends a real power command to the specified device
        """
        _log.info("SetPt: setting "+self.site.device_id+"."+attribute+"."+pt)

        # find the device
        device = self.site.find_device(str(device_id))

        if device == None:
            _log.info("SetPt: ERROR! Device "+device_id+" not found in "+self.site.device_id)            
        else:
            # FIXME: other error trapping needed?
            # send the command
            self.dirtyFlag = 1 # set dirtyFlag - indicates a new write has occurred, so site data needs to update
            _log.info("SetPt: Sending Cmd!")
            device.write_cmd(str(attribute), str(pt), val, self)



    ##############################################################################
    @Core.periodic(PMC_WATCHDOG_PD)
    def increment_site_watchdog(self):
        """
        Commands site to increment watchdog counter
        :return:
        """
        #FIXME - this need to be more nuanced - not every site has the same heartbeat period
        #FIXME - or requires a heartbeat.
        #FIXME - also is it assumed that only the "site" has a heartbeat? (i.e., not the forecast device?)
        try:
            self.site.send_watchdog(self)
        except:
            _log.info("error setting watchdog....")
            pass

    ##############################################################################
    @Core.periodic(PMC_HEARTBEAT_PD)
    def check_heartbeat(self):
        """
        Checks hearbeat from the site
        :return:
        """
        if self.mode != STARTING:
            self.site.check_site_heartbeat()

    ##############################################################################
    @RPC.export
    def get_device_data(self, device_id, attribute):
        """
        sends a real power command to the specified device
        """
        
        # find the device
        _log.debug("FindDevice: device id is "+device_id)
        device = self.site.find_device(device_id)       
        #_log.info("attribute is "+attribute)
        #_log.info("site is "+self.site.device_id)

        # return the attribute data dict
        return device.datagroup_dict_list[attribute].data_dict #self.site.datagroup_dict_list[attribute].data_dict 

    ##############################################################################
    @RPC.export
    def get_device_state_vars(self, device_id):
        """
        sends a real power command to the specified device
        """

        # find the device
        _log.debug("FindDevice: device id is " + device_id)
        device = self.site.find_device(device_id)
        # _log.info("attribute is "+attribute)
        # _log.info("site is "+self.site.device_id)

        # return the attribute data dict
        return device.state_vars  # self.site.datagroup_dict_list[attribute].data_dict

    ##############################################################################
    @RPC.export
    def set_SiteManager_mode(self, new_mode):
        """
        changes SiteManager's mode on call from Executive
        """
        _log.info("updating op mode!!")

        self.mode = new_mode
        self.dirtyFlag = 1 # set dirtyFlag - indicates a new write has occurred, so site data needs to update
        if self.mode == AUTO:
            self.pwr_ctrl_en = DISABLED
            val = self.site.set_auto_mode(self)
        else:
            self.pwr_ctrl_en = ENABLED
            val = self.site.set_interactive_mode(self)

def main(argv=sys.argv):
    '''Main method called by the eggsecutable.'''
    try:
        utils.vip_main(SiteManagerAgent)
    except Exception as e:
        _log.exception('unhandled exception')

        
if __name__ == '__main__':
    # Entry point for script 
    sys.exit(main())
