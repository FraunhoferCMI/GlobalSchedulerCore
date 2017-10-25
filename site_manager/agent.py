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

from datetime import datetime
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
from gs_identities import (INTERACTIVE, AUTO)

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

        self.site = DERDevice.DERSite(cursite, None, self.data_map_dir)
        self.vip.pubsub.publish('pubsub', 
                                'data/NewSite/all', 
                                headers={}, 
                                message=[self.site.device_id]).get(timeout=10.0)        
   


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
        _log.info("HI Cameron!!!")

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

        # self.summarize(out,headers)

    ##############################################################################
    @Core.periodic(20)
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
    def set_interactive_mode(self, new_mode):
        """
        changes site's mode from "AUTO" to "INTERACTIVE"
        """
        _log.info("updating op mode!!")
        val = self.site.set_mode(INTERACTIVE)

    ##############################################################################
    @RPC.export
    def set_auto_mode(self):
        """
        changes site's mode from "AUTO" to "INTERACTIVE"
        """
        _log.info("updating op mode!!")
        val = self.site.set_mode(AUTO)



    def find_device(device_list, device_id):
        """
        This function traverses the device tree to find the object matching device_id and returns the object.
        """
        #FIXME - this method is duplicated / not where this should live.  Should be in one spot, probably in DERDevice
        # class and re-used everywhere
        for cur_device in device_list:
            if cur_device.device_id == device_id:
                return cur_device
            else:
                child_device = find_device(cur_device.devices, device_id)
                if child_device != None:
                    return child_device

    @RPC.export
    def set_point(self, cmd):
        """
        This method writes an end point to a specified DER Device path
        """
        cmd_agentid = cmd[0]
        cmd_device_id = cmd[1]
        cmd_attribute = cmd[2]
        cmd_endpt = cmd[3]
        cmd_val = cmd[4]
        if self.site.device_id != cmd_device_id:
            cmd_device = find_device(self.site.devices, cmd_device_id)
        else:
            cmd_device = self.site
        #cmd_device.datagroup_dict_list[cmd_attribute].data_dict[cmd_endpt] = val
        
        #val = self.site.mode_ctrl.data_dict["OpModeCtrl"]+1
        if cmd_attribute == "ModeControl":
            cmd_device.set_mode(cmd_endpt,int(cmd_val), self)
        elif cmd_attribute == "PowerControl":
            cmd_device.set_power(cmd_endpt, val, self)

        #self.site.set_mode("OpModeCtrl",val, self)

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
