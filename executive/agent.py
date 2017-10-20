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
import gevent
#import DERDevice
from volttron.platform.messaging.health import STATUS_GOOD
from volttron.platform.vip.agent import Agent, Core, PubSub, compat, RPC
from volttron.platform.agent import utils
from volttron.platform.messaging import headers as headers_mod
from volttron.platform.agent.known_identities import (
    VOLTTRON_CENTRAL, VOLTTRON_CENTRAL_PLATFORM, CONTROL, CONFIGURATION_STORE)

from . import settings


utils.setup_logging()
_log = logging.getLogger(__name__)
__version__ = '1.0'


##############################################################################
class ExecutiveAgent(Agent):
    """
    Runs SunDial Executive state machine
    """

    def __init__(self, config_path, **kwargs):
        super(ExecutiveAgent, self).__init__(**kwargs)
        self.default_config = {
            "DEFAULT_MESSAGE" :'Executive Message',
            "DEFAULT_AGENTID": "executive",
            "DEFAULT_HEARTBEAT_PERIOD": 5,
            "log-level":"INFO"
        }

        self.OperatingMode = ["MONITORING", "USER_CONTROL", "APPLICATION_CONTROL"]
        self.OperatingModeInd = 0     
        self._config = self.default_config.copy()
        self._agent_id = self._config.get("DEFAULT_AGENTID")
        self._message = self._config.get("DEFAULT_MESSAGE")
        self._heartbeat_period = self._config.get('DEFAULT_HEARTBEAT_PERIOD')        
        #self.configure(None,None,self.default_config)
        self.vip.config.subscribe(
            self.configure,
            actions=["NEW", "UPDATE"],
            pattern="config")
        
        #FIXME - this should be set up with a configurable path....        
        sys.path.append("/home/matt/sundial/SiteManager")
        SiteCfgFile = "/home/matt/sundial/SiteManager/ShirleySouthSiteConfiguration.json"
        self.SiteCfgList = json.load(open(SiteCfgFile, 'r'))
        self.cnt = 0
 


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
    
    @Core.receiver('onsetup')
    def onsetup(self, sender, **kwargs):
        # Demonstrate accessing a value from the config file
        _log.info(self._message)
        self._agent_id = self._config.get('agentid')

    @Core.receiver('onstart')
    def onstart(self, sender, **kwargs):
        if self._heartbeat_period != 0:
            self.vip.heartbeat.start_with_period(self._heartbeat_period)
            self.vip.health.set_status(STATUS_GOOD, self._message)

        # I think right here is where I want to do my "init"-type functions...
        # one thought is to instantiate a new DERDevice right here and see if that works!
        _log.info("**********INSTANTIATING NEW SITES*******************")

        self.sitemgr_list = []
        for site in self.SiteCfgList:
            _log.info(str(site["ID"]))
            _log.info(str(site))
            
            # start a new SiteManager agent 
            # FIXME - path to site manager.....
            # TODO - you could name the installed agent after the site's ID
            fname = "/home/matt/.volttron/packaged/site_manageragent-1.0-py2-none-any.whl"
            uuid = self.vip.rpc.call(CONTROL, "install_agent_local", fname,vip_identity=site["ID"],secretkey=None,publickey=None).get(timeout=30)
            _log.info("Agent uuid is:" + uuid) 
            self.vip.rpc.call(CONTROL, "start_agent", uuid).get(timeout=5)  
            gevent.sleep(0.5)
           
            agents = self.vip.rpc.call(CONTROL, "list_agents").get(timeout=5)
            for cur_agent in agents:
                if cur_agent["uuid"] == uuid:
                    self.sitemgr_list.append(cur_agent)
                    _log.info("Agent name is: "+cur_agent["name"])
                    _log.info("Agent dir is: "+str(dir(cur_agent)))
                    _log.info("Agent id is: "+cur_agent["identity"])
                    break
            # TODO - return something?             
            self.vip.rpc.call(cur_agent["identity"], "init_site", site)
            #self.sites.append(new_site) #DERDevice.DERSite(site, None))
            #    self.vip.rpc.call(CONTROL, "start_agent", a["uuid"]).get(timeout=5)
            #    self.l_agent = a
            #_log.info("agent id: ", listener_uuid)



    @Core.periodic(60)
    def run_executive(self):
        #if self.cnt == 1:
        #    agents = self.vip.rpc.call(CONTROL, "list_agents").get(timeout=5)
        #    for cur_agent in agents:
        #        #    print("Agent name is:" + a["name"] + "; UUID = " + a["uuid"])
        #        if cur_agent["uuid"] == self.a:
        #            new_site_manager = cur_agent
        #            _log.info("Agent name is: "+new_site_manager["name"])
        #            _log.info("Agent dir is: "+str(dir(new_site_manager)))
        #            _log.info("Agent id is: "+new_site_manager["identity"])
        #            break
        #    
        #    new_site = self.vip.rpc.call(new_site_manager["identity"], "init_site", self.sitecfg) #.get()
        #_log.info("New Site - dir"+dir(new_site))
        #_log.info("New site's device id is"+new_site.device_id)
        #self.sites.append(new_site) #DERDevice.DERSite(site, None))
        #    self.vip.rpc.call(CONTROL, "start_agent", a["uuid"]).get(timeout=5)
        #    self.l_agent = a
        #_log.info("agent id: ", listener_uuid)
        # read something
        # build sdr file?
        # I might want keys of dev id / agent....
        _log.info("Publishing op mode!!")
        self.vip.pubsub.publish('pubsub', 
                                'data/Executive/all', 
                                headers={}, 
                                message=[self.OperatingMode[self.OperatingModeInd]]).get(timeout=10.0)        
   

        pass
        #self.cnt = self.cnt + 1
        
    @PubSub.subscribe('pubsub', 'data/NewSite/all')
    def add_site(self, peer, sender, bus,  topic, headers, message):
        _log.info("New Site found!!")
        data = message[0]
        _log.info("message is "+data) #str(dir(data)))


    @RPC.export
    def set_point(self, cmd):
        """
        This method writes an end point to a specified DER Device path
        """
        fname = "/home/matt/sundial/Executive/cmdfile.txt"
        cmd_agentid = cmd[0]
        cmd_method = cmd[1]
        cmd_val = cmd[2]

        with open(fname, 'a') as datafile:
            self.OperatingModeInd = int(cmd_val)
            _log.info("Changing operating mode to: "+ self.OperatingMode[self.OperatingModeInd])
            datafile.write(str(cmd_method)+" "+str(cmd_val)+ " "+self.OperatingMode[self.OperatingModeInd])


    @Core.receiver('onstop')
    def onstop(self, sender, **kwargs):
        for site in self.sitemgr_list:
            self.vip.rpc.call(CONTROL, "remove_agent", site["uuid"]).get(timeout=5)
        pass



def main(argv=sys.argv):
    '''Main method called by the eggsecutable.'''
    try:
        utils.vip_main(ExecutiveAgent)
    except Exception as e:
        _log.exception('unhandled exception')

        
if __name__ == '__main__':
    # Entry point for script 
    sys.exit(main())
