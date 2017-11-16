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
from gs_identities import (INTERACTIVE, AUTO, SCRAPE_TIMEOUT, ENABLED, DISABLED, PMC_WATCHDOG_PD)

utils.setup_logging()
_log = logging.getLogger(__name__)
__version__ = '1.0'


##############################################################################
class SiteManagerAgent(Agent):
    """
    ...
    """

    def __init__(self, config_path, **kwargs):
        super(SiteManagerAgent, self).__init__(**kwargs)
        self.default_config = {
            "DEFAULT_MESSAGE" :'SM Message',
            "DEFAULT_AGENTID": "site_manager",
            "DEFAULT_HEARTBEAT_PERIOD": 5,
            "log-level":"DEBUG",
            "moving_averages" :{
	        "length" : 12,
                "keys":[
                    "analysis/Shirley-MA/PV/RealPower",
                    "analysis/Shirley-MA/RealPower",
                ]
            }

        }
        #FIXME - shouldn't be hard-coded!!!
        #FIXME - need to (1) add mapping of topic in the device mapping file; (2) parse this in on_match
        #self.path = ['Shirley-MA/South/PMC'] # was 'devices/Shirley-MA/South/PMC/all'
        self.volttron_root = os.getcwd()
        self.volttron_root = self.volttron_root+"/../../../../"
        self.data_map_dir = self.volttron_root+"gs_cfg/"
        _log.info("data dir is "+self.data_map_dir)
        #self.data_map_dir = "/home/matt/sundial/SiteManager/data/" #"./data/"
        self.cnt = 0
        self._config = self.default_config.copy()
        self._agent_id = self._config.get("DEFAULT_AGENTID")
        self._message = self._config.get("DEFAULT_MESSAGE")
        self._heartbeat_period = self._config.get('DEFAULT_HEARTBEAT_PERIOD')
        
        self.setpoint = 0 
        self.cache = {}
        self.moving_averages = {}
        self.configure(None,None,self.default_config)
        self.vip.config.subscribe(
            self.configure,
            actions=["NEW", "UPDATE"],
            pattern="config")

        _log.info("Agent ID is "+self._agent_id)
        _log.debug("TEST Debug message!!")

        #for topics in self.path:
        #    self.vip.pubsub.subscribe(peer='pubsub',prefix='devices/'+topics+'/all',callback=self.on_match)

        TimeStamp = datetime.strftime(
            datetime.now(),
            "%Y-%m-%dT%H:%M:%S"
        )      
        self.last_scrape_time = datetime.now() #TimeStamp
        self.SiteErrors = {}
        self.SiteErrors.update({"ReadError": 0})
        self.SiteErrors.update({"WriteError": 0})
        self.SiteErrors.update({"DeviceError": 0})
        self.SiteErrors.update({"CmdError": 0})
        self.SiteErrors.update({"HeartbeatError": 0})
        self.SiteErrors.update({"CmdPending": 0})

        self.mode = AUTO
        self.write_error_count = 0
        # FIXME - need to have dirty flag for each topic!
        self.dirtyFlag = 1 
        _log.info("**********INITIALIIZING SITE MANAGER*******************")


    ##############################################################################
    @RPC.export
    def init_site(self,cursite):
        """
        Instantiates a new site. Publishes an example message.
        Called by the Executive
        cursite is a site constructor JSON object (from a SiteConfiguration.json file)
        """
        _log.info("**********INSTANTIATING A NEW SITE*******************")
        _log.info("Site name is: "+cursite["ID"])

        self.topics = cursite["Topics"]

        #_log.info("old topic was: "+'devices/'+self.path[0]+'/all')

        for topics in self.topics:
            self.vip.pubsub.subscribe(peer='pubsub',prefix=topics["TopicPath"],callback=self.on_match) #+'/all'
            _log.info("Subscribing to new topic: "+topics["TopicPath"]+'/all')

        #self.vip.pubsub.subscribe(peer='pubsub',prefix=topics["TopicPath"],callback=self.on_match)


        self.site = DERDevice.DERModbusSite(cursite, None, self.data_map_dir)
        self.vip.pubsub.publish('pubsub', 
                                'data/NewSite/all', 
                                headers={}, 
                                message=[self.site.device_id]).get(timeout=10.0)        
   
        #ret = self.vip.rpc.call("executiveagent-1.0_1", "set_mode", 1).get()
        #_log.info(str(dir(ret)))

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
    #@PubSub.subscribe('pubsub', 'devices/Shirley-MA/South/PMC/all')
    def on_match(self, peer, sender, bus,  topic, headers, message):
        """
        parses message on IEB published to the SiteManager's specified path, and 
        populates endpts (populate_endpts) based on message contents

        TODO: keep track fo complete time stamps. 

        """
        _log.info("Topic found - "+str(topic))
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

        try:
            self.site.populate_endpts(data, meta_data)
            self.dirtyFlag = 0 # clear dirtyFlag on new read
        except:
            # indicates that agent is still initializing - init_sites has not yet been called.
            # There is possibly a better way to handle this issue
            #FIXME - this should probably look for specific error to trap, right now this is
            # a catch-all....
            _log.info("Exception: in populate end_pts!!!")
        pass

        

        # FIXME: This is legacy code, should be reintegrated.  Not currently doing anything
        # with timestamps.
        if 0:
            TimeStamp = datetime.strptime(
                headers["TimeStamp"][:19],            
                "%Y-%m-%dT%H:%M:%S"
            )      
            self.cache[TimeStamp] = self.cache.get(
                TimeStamp,{})

            out = self.cache.pop(TimeStamp)
            print(str(TimeStamp)+ " " + str(out.items))

        #if str(topic) == self.topics[0]["TopicPath"]: # FIXME temporary
        self.last_scrape_time = datetime.now() #TimeStamp# datetime.now()  #FIXME - need to separate by topic...
        #else:
        #    _log.info("topic is "+topic)
        #    _log.info("topic[0] is "+self.topics[0]["TopicPath"])

        # self.summarize(out,headers)

    ##############################################################################
    def publish_data(self, TimeStamp_str):
        """
        method for publishing database topics.  First publishes data for SiteManager
        agent itself, then it publishes it for the associated DERSite
        this is a very rough first cut

        Input is a timestamp that has been converted to a string
        """

        HistorianTools.publish_data(self, 
                                    self.site.device_id+"Agent", 
                                    TimeStamp_str, 
                                    "Mode", 
                                    self.mode)
        self.site.publish_device_data(TimeStamp_str, self)



    ##############################################################################
    @RPC.export
    def update_site_status(self):
        """
        Used to poll the status of the site
        Detects errors that impact the validity of data being monitored from the site and recalculates values
        Periodically called by Executive

        :return: SiteError - dictionary of errors associated with the site:
        1. DeviceError: Issues with downstream DERDevices are captured within the "health_status" dictionary associated
        with each DERDevice.  site.update_health_status() aggregates this information.  if health_status["status"] = 0,
        it indicates an exception occurred with a downstream device

        2. ReadError: Detected by checking that the time interval since the last time SiteManager received an
        incoming pub/sub message on the IEB from the site communication agent is < the configured timeout period

        3. WriteError: Indicates that a command was written to the site, but does not appear to have been received.

        4. CmdError: Indicates that the site has not responded as expected to a command that it has received.

        5. HeartbeatError: Indicates that the site has not updated its heartbeat counter within the expected timeout
        period

        6. CmdPending: Indicates that the site has not been scraped since the last command was sent.

        """

        # 1. when was the last scrape?
        # 2. do _cmd registers = base registers?
        # 3. do base registers = base status registers?

        ReadError      = 0
        CmdError       = 0
        WriteError     = 0
        DeviceError    = 0
        HeartbeatError = 0
        CmdPending     = 0

        _log.info("Checking Site Status.  Curent Site Mode = "+str(self.mode))

        if self.dirtyFlag == 0:
            # FIXME: needs to be a different flag for each topic <?>
            # indicates that site has been scraped since the last command was posted.

            #WriteError = self.site.check_command()

            self.site.update_op_status()
            self.site.update_health_status()
            self.site.update_mode_status()

            if self.site.health_status.data_dict["status"] == 0:
                DeviceError = 1

            CmdError = self.site.check_mode()


            if (self.mode != self.site.mode_ctrl.data_dict["SysModeCtrl"]):
                # Indicates that the site is in a different mode than the SiteMgr thinks
                # it should be.

                # check reason - possible reasons include:
                # (1) changed by non-GS 3rd party.  (Not an error, but needs to be communicated to Executive
                # (2) GS failed to send
                # (3) Site failed to receive
                #TODO - need to check status code, etc...
                #if self.write_error_count == 0:
                # Try to resend.
                #    self.write_error_count += 1
                #else:
                    # Has previously failed, assume that there is a problem
                    # try to resend

                if self.write_error_count < 2:
                    # Try to resend.
                    _log.info("Retrying write mode")
                    self.set_SiteManager_mode(self.mode)
                WriteError = 1 #self.site.check_command()
                self.write_error_count += 1

            else:
                self.write_error_count = 0

        else:
            # the site has not been scraped since the last command was posted.
            # Assume data from the site is suspect, and set "CmdPending" to 1
            CmdPending = 1
            pass

        for k,v in self.site.op_status.data_dict.items():
            _log.info("Status-"+self.site.device_id+"-Ops: "+k+": "+str(v))
        for k,v in self.site.mode_status.data_dict.items():
            _log.info("Status-"+self.site.device_id+"-Mode: "+k+": "+str(v))
        for k,v in self.site.health_status.data_dict.items():
            _log.info("Status-"+self.site.device_id+"-Health: "+k+": "+str(v))
        for k,v in self.site.pwr_ctrl.data_dict.items():
            _log.info("Status-"+self.site.device_id+"-PwrCtrl: "+k+": "+str(v))
        for k,v in self.site.mode_ctrl.data_dict.items():
            _log.info("Status-"+self.site.device_id+"-ModeCtrl: "+k+": "+str(v))
        # Now check if the site is communicating with the site manager.
        # we check this by seeing if the time interval since the last scrape is > the
        # configured scrape timeout period.  (something like 2x the scrape interval).

        # FIXME - need to do this for each topic -

        TimeStamp = datetime.now()
        #datetime.strftime(
        #    datetime.now(),
        #    "%Y-%m-%dT%H:%M:%S"
        #)      
        _log.info("Current Time = " + datetime.strftime(TimeStamp, "%Y-%m-%dT%H:%M:%S") + 
        "; Last Scrape = " + datetime.strftime(self.last_scrape_time, "%Y-%m-%dT%H:%M:%S"))

        deltaT = TimeStamp - self.last_scrape_time
        _log.info("delta T "+str(deltaT)) 
        tot_sec = deltaT.total_seconds()

        _log.info("Delta T = "+str(deltaT)+"; SCRAPE_TIMEOUT = "+ str(SCRAPE_TIMEOUT)+"; tot sec = "+str(tot_sec))


        if tot_sec > SCRAPE_TIMEOUT:
            ReadError = 1

        self.SiteErrors.update({"ReadError": ReadError})
        self.SiteErrors.update({"WriteError": WriteError})
        self.SiteErrors.update({"DeviceError": DeviceError})
        self.SiteErrors.update({"CmdError": CmdError})
        self.SiteErrors.update({"HeartbeatError": HeartbeatError})
        self.SiteErrors.update({"CmdPending": CmdPending})

        for k, v in self.SiteErrors.items():
            _log.info(k+": "+str(v))
 
        self.publish_data(TimeStamp.strftime("%Y-%m-%dT%H:%M:%S"))

        return self.SiteErrors


    ##############################################################################
    #@Core.periodic(20)
    def test_write(self):
        """
        example method to demonstrate a write operation.  Just incrementing periodically increments a counter
        assumes a valid end point (consumer) of this command is running.
        """
        _log.info("updating op mode!!")
        val = self.site.mode_ctrl.data_dict["OpModeCtrl"]+1
        self.site.set_point("OpModeCtrl",val, self)
        #self.cnt += 1
        #print("Cnt = "+str(self.cnt))


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
        elif device.device_type not in self.site.DGPlant:
            _log.info("SetPt: ERROR! Pwr dispatch command sent to non-controllable device "+device.device_id)
            _log.info("SetPt: Device type = "+device.device_type)
            # FIXME: other error trapping needed?
        else:
            # send the command
            self.dirtyFlag = 1 # set dirtyFlag - indicates a new write has occurred, so site data needs to update
            _log.info("SetPt: Sending Cmd!")
            device.set_power_real(val, self)

    ##############################################################################
    #@Core.periodic(PMC_WATCHDOG_PD)
    def increment_site_watchdog(self):
        """
        Commands site to increment watchdog counter
        :return:
        """
        #FIXME - this need to be more nuanced - not every site has the same heartbeat period
        #FIXME - or requires a heartbeat.
        #FIXME - also is it assumed that only the "site" has a heartbeat? (i.e., not the forecast device?)
        self.site.send_watchdog(self)


    ##############################################################################
    @RPC.export
    def get_device_data(self, device_id, attribute):
        """
        sends a real power command to the specified device
        """
        
        # find the device
        _log.info("FindDevice: device id is "+device_id)
        device = self.site.find_device(device_id)       
        #_log.info("attribute is "+attribute)
        #_log.info("site is "+self.site.device_id)

        # return the attribute data dict
        return device.datagroup_dict_list[attribute].data_dict #self.site.datagroup_dict_list[attribute].data_dict 

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

    def handle_moving_averages (self, msg):
        for k,v in msg.items():
            if k not in self._config["moving_averages"]["keys"]:
                continue
            l = self.moving_averages.get(k,[])
            l.append(v)
            if len(l) > self._config["moving_averages"]["length"]:
                l.pop(0)
            msg[ k +".MA"] = sum(l)/len(l)
            self.moving_averages[k]=l
        
    def summarize(self,state,headers):
        self.vip.rpc.call(
            "essagent-1.0_1",
            "set_direct",
            10)

        self.handle_moving_averages(out)
        new_topic = prefix + "all"
        meta = dict([(k,{"type":"float"}) for k,v in out.items()])
        self.vip.pubsub.publish('pubsub', 
                                new_topic, 
                                headers=headers, 
                                message=[out,meta]).get(timeout=10.0)        
        
def main(argv=sys.argv):
    '''Main method called by the eggsecutable.'''
    try:
        utils.vip_main(SiteManagerAgent)
    except Exception as e:
        _log.exception('unhandled exception')

        
if __name__ == '__main__':
    # Entry point for script 
    sys.exit(main())
