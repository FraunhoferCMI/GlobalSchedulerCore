#
# -*- coding: utf-8 -*- {{{
# vim: set fenc=utf-8 ft=python sw=4 ts=4 sts=4 et:

# Copyright (c) 2016, Battelle Memorial Institute
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
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# The views and conclusions contained in the software and documentation
# are those of the authors and should not be interpreted as representing
# official policies, either expressed or implied, of the FreeBSD
# Project.
#
# This material was prepared as an account of work sponsored by an
# agency of the United States Government.  Neither the United States
# Government nor the United States Department of Energy, nor Battelle,
# nor any of their employees, nor any jurisdiction or organization that
# has cooperated in the development of these materials, makes any
# warranty, express or implied, or assumes any legal liability or
# responsibility for the accuracy, completeness, or usefulness or any
# information, apparatus, product, software, or process disclosed, or
# represents that its use would not infringe privately owned rights.
#
# Reference herein to any specific commercial product, process, or
# service by trade name, trademark, manufacturer, or otherwise does not
# necessarily constitute or imply its endorsement, recommendation, or
# favoring by the United States Government or any agency thereof, or
# Battelle Memorial Institute. The views and opinions of authors
# expressed herein do not necessarily state or reflect those of the
# United States Government or any agency thereof.
#
# PACIFIC NORTHWEST NATIONAL LABORATORY
# operated by BATTELLE for the UNITED STATES DEPARTMENT OF ENERGY
# under Contract DE-AC05-76RL01830

# }}}

from __future__ import absolute_import

from datetime import datetime, timedelta
import logging
import sys
import os
import csv
import json
import DERDevice
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
            "log-level":"INFO",
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
        self.path = ['Shirley-MA/South/PMC'] # was 'devices/Shirley-MA/South/PMC/all'
        self.data_map_dir = "/home/matt/sundial/SiteManager/data/" #"./data/"

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

        for topics in self.path:
            self.vip.pubsub.subscribe(peer='pubsub',prefix='devices/'+topics+'/all',callback=self.on_match)

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
        data = message[0]
        #for k, v in data.items():
        #    _log.info("Message is: "+k+": "+str(v))

        try:
            self.site.populate_endpts(data)
        except:
            # indicates that agent is still initializing - init_sites has not yet been called.
            # There is possibly a better way to handle this issue
            #FIXME - this should probably look for specific error to trap, right now this is
            # a catch-all....
            _log.info("Skipped populate end_pts!!!")
        pass

        # FIXME: This is legacy code, should be reintegrated.  Not currently doing anything
        # with timestamps.
        TimeStamp = datetime.strptime(
            headers["TimeStamp"][:19],            
            "%Y-%m-%dT%H:%M:%S"
        )      
        self.cache[TimeStamp] = self.cache.get(
            TimeStamp,{})

        out = self.cache.pop(TimeStamp)
        print(str(TimeStamp)+ " " + str(out.items))

        self.last_scrape_time = TimeStamp# datetime.now()


        # self.summarize(out,headers)

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

        if self.site.dirtyFlag == 0:
            # FIXME: needs to be a different flag for each topic <?>
            # indicates that site has been scraped since the last command was posted.

            #WriteError = self.site.check_command()

            self.site.update_op_status()
            self.site.update_health_status()
            self.site.update_mode_status()

            if self.site.health_status.data_dict["status"] == 0:
                DeviceError = 1

            CmdError = self.site.check_mode()


            if (self.mode != self.mode_ctrl.data_dict["OpModeCtrl"]) or \
                (self.mode != self.mode_ctrl.data_dict["SysModeCtrl"]):
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

                # Try to resend.
                self.set_SiteManager_mode(self.mode)
                WriteError = 1 #self.site.check_command()

                pass

        else:
            # the site has not been scraped since the last command was posted.
            # Assume data from the site is suspect, and set "CmdPending" to 1
            CmdPending = 1
            pass



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
        val = self.site.set_interactive_mode(self)

    ##############################################################################
    @RPC.export
    def set_auto_mode(self):
        """
        changes site's mode from "AUTO" to "INTERACTIVE"
        """
        _log.info("updating op mode!!")
        self.mode = AUTO
        val = self.site.set_auto_mode(self)

    ##############################################################################
    @RPC.export
    def set_real_pwr_cmd(self, device_id, cmd):
        """
        sends a real power command to the specified device
        """
        _log.info("updating site power output!!")

        # find the device
        device = self.site.find_device(device_id)

        if device == None:
            _log.info("ERROR! Device "+device_id+" not found in "+self.site.device_id)
            # FIXME: other error trapping needed?
        elif device.device_type != "DERCtrlNode":
            _log.info("ERROR! Pwr dispatch command sent to non-controllable device "+device_id)
            # FIXME: other error trapping needed?
        else:
            # send the command
            device.set_power_real(cmd, val, sitemgr)

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
        self.site.send_watchdog(self)


    ##############################################################################
    @RPC.export
    def get_device_data(self, device_id, attribute):
        """
        sends a real power command to the specified device
        """
        _log.info("updating site power output!!")

        # find the device
        device = self.site.find_device(device_id)

        # return the attribute data dict
        return device.datagroup_dict_list[attribute].data_dict

    ##############################################################################
    @RPC.export
    def set_SiteManager_mode(self, new_mode):
        """
        changes SiteManager's mode on call from Executive
        """
        _log.info("updating op mode!!")

        self.mode = new_mode

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
