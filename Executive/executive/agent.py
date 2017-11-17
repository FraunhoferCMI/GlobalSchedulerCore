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

from datetime import datetime
import logging
import sys
import os
import csv
import json
import gevent
from volttron.platform.messaging.health import STATUS_GOOD
from volttron.platform.vip.agent import Agent, Core, PubSub, compat, RPC
from volttron.platform.agent import utils
from volttron.platform.messaging import headers as headers_mod
from volttron.platform.agent.known_identities import (
    VOLTTRON_CENTRAL, VOLTTRON_CENTRAL_PLATFORM, CONTROL, CONFIGURATION_STORE)

from . import settings
import HistorianTools

import DERDevice
from gs_identities import (IDLE, USER_CONTROL, APPLICATION_CONTROL, EXECUTIVE_CLKTIME, GS_SCHEDULE, ENABLED, DISABLED, STATUS_MSG_PD)

utils.setup_logging()
_log = logging.getLogger(__name__)
__version__ = '1.0'

import DERDevice
import json

class SunDialResource():
    def __init__(self, resource_cfg, sites):
        """

        1. Read a configuration file that tells what resources to include
        2. populate
        """

        self.resource_type = resource_cfg["ResourceType"]
        self.resource_id   = resource_cfg["ID"]
        self.virtual_plant = DERDevice.VirtualDERCtrlNode(device_id=self.resource_id, device_list=resource_cfg["DeviceList"])
        self.sites         = sites
        self.obj_fcns     = []

class ESSResource(SunDialResource):
    def __init__(self, resource_cfg, sites):
        SunDialResource.__init__(self, resource_cfg, sites)
        pass

class PVResource(SunDialResource):
    def __init__(self, resource_cfg, sites):
        SunDialResource.__init__(self, resource_cfg, sites)
        pass

class LoadShiftResource(SunDialResource):
    def __init__(self, resource_cfg, sites):
        SunDialResource.__init__(self, resource_cfg, sites)
        pass

class BaselineLoadResource(SunDialResource):
    def __init__(self, resource_cfg, sites):
        SunDialResource.__init__(self, resource_cfg, sites)
        pass

class SundialSystemResource(SunDialResource):
    def __init__(self, resource_cfg, sites):
        SunDialResource.__init__(self, resource_cfg, sites)
        self.obj_fcns = [self.obj_fcn_energy, self.obj_fcn_demand]
        pass

    def obj_fcn_energy(self):
        """
        placeholder for a function that calculates an energy cost for a given net demand profile
        :return:
        """
        pass

    def obj_fcn_demand(self):
        """
        placeholder for a function that calculates a demadn charge for a given net demand profile
        :return:
        """
        pass

def calc_ess_setpoint(targetPwr_kW, curPwr_kW, SOE_kWh, min_SOE_kWh, max_SOE_kWh, max_charge_kW, max_discharge_kW):
    
    # setpoint_cmd_interval indicates how frequently the target setpoint is recalculated.
    # it is used to determine what the max sustainable charge / discharge rate is for the
    # battery before the next time that we receive a high level schedule request.
    setpoint_cmd_interval = 300
    sec_per_hr = 60 * 60

    setpoint = curPwr_kW - targetPwr_kW
    _log.info("Optimizer: target Setpoint ="+str(setpoint))

    # check that we are within power limits of the storage system
    if setpoint < -1 * max_discharge_kW:
        setpoint = -1 * max_discharge_kW
    if setpoint > max_charge_kW:
        setpoint = max_charge_kW

    # now check that the target setpoint is within the energy limits
    _log.info("Optimizer: Power-limited Setpoint =" + str(setpoint))

    # calculate what the remaining charge will be at the end of the next period
    # FIXME - need to correct for losses!!
    energy_required = setpoint * setpoint_cmd_interval / sec_per_hr
    discharge_energy_available = min_SOE_kWh - SOE_kWh
    charge_energy_available = max_SOE_kWh - SOE_kWh

    if energy_required < discharge_energy_available:
        # (discharge) set point needs to be adjusted to meet a min_SOE_kWh constraint 
        setpoint = discharge_energy_available / (setpoint_cmd_interval / sec_per_hr)
    elif energy_required > charge_energy_available:
        # (charge) set point needs to be adjusted to meet a max_SOE_kWh constraint
        setpoint = charge_energy_available / (setpoint_cmd_interval / sec_per_hr)

    return setpoint

    pass


def get_current_forecast(forecast):
    #cur_time = datetime.now()
    return forecast["Pwr"][11]



##############################################################################
class ExecutiveAgent(Agent):
    """
    Runs SunDial Executive state machine
    """
    OperatingModes = ["IDLE", "USER_CONTROL", "APPLICATION_CONTROL"]

    def __init__(self, config_path, **kwargs):
        super(ExecutiveAgent, self).__init__(**kwargs)
        self.default_config = {
            "DEFAULT_MESSAGE" :'Executive Message',
            "DEFAULT_AGENTID": "executive",
            "DEFAULT_HEARTBEAT_PERIOD": 5,
            "log-level":"INFO"
        }

        self.OperatingMode_set = IDLE
        self.OperatingMode     = self.OperatingMode_set
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
        #sys.path.append("/home/matt/sundial/SiteManager")
        #SiteCfgFile = "/home/matt/sundial/SiteManager/ShirleySouthSiteConfiguration.json"
        #SiteCfgFile = "/home/matt/sundial/SiteManager/ShirleySouthSiteConfiguration.json"
        self.volttron_root = os.getcwd()
        self.volttron_root = self.volttron_root+"/../../../../"
        #SiteCfgFile = "/home/matt/sundial/SiteManager/NorthSouthSiteConfiguration.json"
        SiteCfgFile = self.volttron_root+"gs_cfg/SiteConfiguration.json"
        self.SiteCfgList = json.load(open(SiteCfgFile, 'r'))

        #SundialCfgFile = "/home/matt/sundial/SiteManager/SundialSystemConfiguration.json"
        SundialCfgFile = self.volttron_root+"gs_cfg/SundialSystemConfiguration.json"
        self.sundial_resource_cfg_list = json.load(open(SundialCfgFile, 'r'))
        _log.info("SiteConfig is "+SiteCfgFile)
        _log.info("SundialConfig is"+SundialCfgFile)
        self.cnt = 0

        self.OptimizerEnable = DISABLED
        self.UICtrlEnable = DISABLED
 
        self.optimizer_info = {}
        self.optimizer_info.update({"setpoint": 0})
        self.optimizer_info.update({"targetPwr_kW": 0})
        self.optimizer_info.update({"curPwr_kW": 0})



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

        TimeStamp = datetime.now()
        HistorianTools.publish_data(self, 
                                    "Executive", 
                                    TimeStamp.strftime("%Y-%m-%dT%H:%M:%S"), 
                                    "OperatingMode", 
                                    self.OperatingMode)

        # I think right here is where I want to do my "init"-type functions...
        # one thought is to instantiate a new DERDevice right here and see if that works!
        _log.info("**********INSTANTIATING NEW SITES*******************")


        # The following reads a json site configuration file and installs / starts a new site
        # manager for each site identified in the configuration file.
        # agents are stored in an object list called "self.sitemgr_list"
        self.sitemgr_list = []
        for site in self.SiteCfgList:
            _log.info(str(site["ID"]))
            _log.info(str(site))
            
            # start a new SiteManager agent 
            # FIXME - path to site manager.....
            # FIXME - needs error trapping: (1) is agent already installed? (2) does site mgr agent exist?
            # FIXME - (3) did it start successfully?
            fname = self.volttron_root+"packaged/site_manageragent-1.0-py2-none-any.whl"
            # was "/home/matt/.volttron/packaged/site_manageragent-1.0-py2-none-any.whl"
            uuid = self.vip.rpc.call(CONTROL,
                                     "install_agent_local",
                                     fname,
                                     vip_identity=site["ID"],secretkey=None,publickey=None).get(timeout=30)
            _log.info("Agent uuid is:" + uuid) 
            self.vip.rpc.call(CONTROL,
                              "start_agent",
                              uuid).get(timeout=5)

            # I would like the "init_site" routine in SiteManager Agent to be part of the init, but I
            # can't figure out how to pass a parameter to an Agent constructor, so instead we call
            # an init routine ("init_site") that is supposed to follow the SiteManager __init__ function
            # which provides configuration data for the actual site.
            # the following sleep message is supposed to pause operation for long enough for site manager
            # to finish its initialization, but it does not work.

            gevent.sleep(0.5)  # try without this?

            # The idea of the below is to get a handle to the agent that we've just created
            # Not done in a very efficient way though - get a list of agents and find one that
            # matches to the uuid, then break
            agents = self.vip.rpc.call(CONTROL, "list_agents").get(timeout=5)
            for cur_agent in agents:
                if cur_agent["uuid"] == uuid:
                    self.sitemgr_list.append(cur_agent)
                    _log.info("Agent name is: "+cur_agent["name"])
                    _log.info("Agent dir is: "+str(dir(cur_agent)))
                    _log.info("Agent id is: "+cur_agent["identity"])
                    break
            # TODO - return something from init_site indicating success??
            self.vip.rpc.call(cur_agent["identity"], "init_site", site)

        self.init_resources(self.sundial_resource_cfg_list, self.sitemgr_list)


    ##############################################################################
    def init_resources(self, sundial_resource_cfg_list, sitemgr_list):
        """
        This method constructs a list of sundial resource objects based on data stored in a system configuration
        json file.
        This method is called by executive just after the agent is instantiated
        :param sundial_resource_cfg_list: List of sundial resources to be initialized
        :return:
        """
        # 1. get the name of the site from the device list;
        # 2. make sure that site exists.  Make sure that device exists
        # 3. Instantiate SunDial Resource.
        # 3. save agentID in SunDial Resource.
        # 4. system object - perhaps does not need to be defined in the config file?


        self.sundial_resources = []
        for new_resource in sundial_resource_cfg_list:

            # find devices matching the specified device names....
            sitelist = {} #[]
            for device in new_resource["DeviceList"]:
                _log.info("New Resource: "+new_resource["ID"]+" of type "+new_resource["ResourceType"])
                _log.info("Device List entries: ")                
                for site in sitemgr_list:
                    if site["identity"] == device["AgentID"]:
                        _log.info("Agent name: " + site["identity"] + " is a match!!")
                        sitelist.update({device["AgentID"]:site})
                        break
                if site["identity"] != device["AgentID"]:
                    # error trapping - make sure that the agent & associated device are valid entries
                    _log.info("Error - "+device["AgentID"]+" not found.  Skipping...")
                    sitelist.update({device["AgentID"]:None})
                    #FIXME: does not actually skip the not-found element
                    #FIXME: does not check for whether the device exists

            if new_resource["ResourceType"] == "ESSCtrlNode":
                self.sundial_ess = ESSResource(new_resource, sitelist)
                self.sundial_resources.append(self.sundial_ess)
            elif new_resource["ResourceType"] == "PVCtrlNode":
                self.sundial_pv = PVResource(new_resource, sitelist)
                self.sundial_resources.append(self.sundial_pv)
            elif new_resource["ResourceType"] == "LoadShiftCtrlNode":
                self.sundial_loadshift = LoadShiftResource(new_resource, sitelist)
                self.sundial_resources.append(self.sundial_loadshift)
            elif new_resource["ResourceType"] == "Load":
                self.sundial_baseline = BaselineLoadResource(new_resource, sitelist)
                self.sundial_resources.append(self.sundial_baseline)
            else:
                _log.info("Warning: Resoure Type "+new_resource["ResourceType"] +
                          " not found, constructing a generic Sundial Resource")
                self.sundial_resources.append(SunDialResource(new_resource))

        # Next construct a "System" resource.  By convention, the System Resource
        # is composed of all the virtual plants specified in the cfg file
        new_system_resource = {}
        new_system_resource.update({"ID": "System"})
        new_system_resource.update({"ResourceType": "System"})
        new_system_resource.update({"Use": "Y"})
        new_system_resource.update({"DeviceList": [{}]})
        sitelist = {}
        for resources in self.sundial_resources:
            new_system_resource["DeviceList"].append({"AgentID": resources.resource_id, "DeviceID": resources.resource_id})
            sitelist.update({resources.resource_id: site})
        self.sundial_system = SundialSystemResource(new_system_resource, sitelist)
        self.sundial_resources.append(self.sundial_system)

    ##############################################################################
    def build_sundial(self):
        """
        Currently unused.
        This would start up a separate "SunDialResourceManager" agent that is responsible for building
        and managing sundial resources, and possibly would run the optimizer.  Analogous to Executive's
        relationhip with the SiteManager agents
        For simplicity, current implementation is keepin within the umbrella of the "executive" agent
        """
        #sundial_cfg_list = [
        #    ("loadshift_sdr", ["IPKeys-FLAME_loadshift"], "LoadShiftCtrlNode"),
        #    ("load_sdr", ["IPKeys-FLAME_baseline"], "Load"),
        #    ("pv_sdr", ["ShirleySouth-PVPlant", "ShirleyNorth-PVPlant"], "PVCtrlNode"), #ShirleySouth
        #    ("ess_sdr", ["ShirleySouth-ESSPlant-ESS1"], "ESSCtrlNode"), #ShirleySouth-ESSPlant
        #    ("system_sdr", ["loadshift_sdr", "load_sdr", "pv_sdr", "ess_sdr"], "SYSTEM")]

        fname = "/home/matt/.volttron/packaged/sundial_resource_manageragent-1.0-py2-none-any.whl"
        uuid = self.vip.rpc.call(CONTROL, "install_agent_local", fname, vip_identity="SundialResourceManager", secretkey=None,
                                 publickey=None).get(timeout=30)
        _log.info("Agent uuid is:" + uuid)
        self.vip.rpc.call(CONTROL, "start_agent", uuid).get(timeout=5)
        gevent.sleep(0.5)

        agents = self.vip.rpc.call(CONTROL, "list_agents").get(timeout=5)
        for cur_agent in agents:
            if cur_agent["uuid"] == uuid:
                self.sdrm = cur_agent
                _log.info("Agent name is: " + cur_agent["name"])
                _log.info("Agent dir is: " + str(dir(cur_agent)))
                _log.info("Agent id is: " + cur_agent["identity"])
                break

        self.init_resources(self.sundial_resource_cfg_list, self.sitemgr_list)
        #self.vip.rpc.call(self.sdrm, "init_resources", sundial_resource_cfg_list)


    ##############################################################################
    def enable_site_interactive_mode(self):
        """
        send command to each site to transition to interactive mode
        :return:
        """
        # TODO: think about whether this should be one method in SiteManager (not one for auto and one for interactive)
        for site in self.sitemgr_list:
            _log.info("SetPt: sending interactive mode command for "+site["identity"])
            self.vip.rpc.call(site["identity"], "set_interactive_mode").get(timeout=5)
            # check for success ...


    ##############################################################################
    def disable_site_interactive_mode(self):
        """
        send command to each site to transition to auto (non-interactive) mode
        :return:
        """
        for site in self.sitemgr_list:
            _log.info("SetPt: sending auto mode command for "+site["identity"])
            self.vip.rpc.call(site["identity"], "set_auto_mode").get(timeout=5)


    ##############################################################################
    def check_site_statuses(self):
        """
        Updates the site status for each active site
        :return:
        """
        for site in self.sitemgr_list:
            _log.info("Checking status for site "+site["identity"])
            site_errors = self.vip.rpc.call(site["identity"], "update_site_status").get(timeout=5)
            for k,v in site_errors.items():
                if site_errors[k] != 0:
                    #self.OperatingMode_set = IDLE
                    _log.info("Warning: Error detected - " +k+".  Transition to IDLE Mode")



    ##############################################################################
    @Core.periodic(GS_SCHEDULE)
    def run_optimizer(self):
        """
        place holder for optimizer
        :return:
        """

        if self.OptimizerEnable == ENABLED:
            _log.info("Optimizer: Running Optimizer")
            #self.sundial_resources

            # What I was thinking about is this -
            # update each virtual device
            # call calc_setpoint on the sundial system (?)

            # The most simple / hacky version of this:
            # 1. target power = sum of all baseline forecasts  (update_forecast)

            # I need something that can grab the current forecast ...

            # first I need something that baselines the forecast against today.


            curPwr_kW = 0
            targetPwr_kW = 0
            # get what time it is

            for nodes in self.sundial_pv.virtual_plant.devices:
                _log.info("agent ID is "+nodes["AgentID"])
                if self.sundial_pv.sites[nodes["AgentID"]] != None:
                    _log.info("or - "+str(self.sundial_pv.sites[nodes["AgentID"]]["identity"]))
                    forecast = self.vip.rpc.call(str(nodes["AgentID"]),#self.sundial_pv.sites[nodes["AgentID"]],
                                                            "get_device_data",
                                                            nodes["DeviceID"],
                                                            "Forecast").get(timeout=5)

                    op_status = self.vip.rpc.call(str(nodes["AgentID"]),#self.sundial_pv.sites[nodes["AgentID"]],
                                                            "get_device_data",
                                                            nodes["DeviceID"],
                                                            "OpStatus").get(timeout=5)
                    _log.info("Optimizer: "+nodes["AgentID"]+" CurPwr = "+str(op_status))
                    _log.debug("Optimizer: forecast = "+str(forecast))                
                    targetPwr_kW += get_current_forecast(forecast)
                    curPwr_kW    += op_status["Pwr_kW"]
            _log.info("Optimizer: Setting Power Inputs: CurPwr="+str(curPwr_kW)+"; TargetPwr="+str(targetPwr_kW))

            SOE_kWh = 0
            min_SOE_kWh = 0
            max_SOE_kWh = 0
            max_charge_kW = 0
            max_discharge_kW = 0
            for nodes in self.sundial_ess.virtual_plant.devices:
                if self.sundial_ess.sites[nodes["AgentID"]] != None:                
                    op_status = self.vip.rpc.call(str(nodes["AgentID"]),
                                                            "get_device_data",
                                                            nodes["DeviceID"],
                                                            "OpStatus").get(timeout=5)
                    max_SOE_kWh += op_status["FullChargeEnergy_kWh"]
                    max_charge_kW += op_status["MaxChargePwr_kW"]
                    max_discharge_kW += op_status["MaxDischargePwr_kW"]
                    SOE_kWh += op_status["Energy_kWh"]
                    _log.debug("ESS WAS found.")
                else:
                    _log.info("Optimizer: ESS "+nodes["AgentID"]+" not found")

            _log.info("Optimizer: Setting ESS State: CurSOE="+str(SOE_kWh)+"; MaxChg="+str(max_charge_kW)+"; MaxSOE="+str(max_SOE_kWh)+"; MaxDischarge="+str(max_discharge_kW))


            setpoint = calc_ess_setpoint(targetPwr_kW, curPwr_kW, SOE_kWh, min_SOE_kWh, max_SOE_kWh, max_charge_kW,
                                         max_discharge_kW)

            _log.info("Optimizer: setpoint = "+str(setpoint))

            for nodes in self.sundial_ess.virtual_plant.devices:
                if self.sundial_ess.sites[nodes["AgentID"]] != None:                
                    op_status = self.vip.rpc.call(str(nodes["AgentID"]),
                                                  "get_device_data",
                                                  nodes["DeviceID"],
                                                  "OpStatus").get(timeout=5)

                    if (setpoint > 0):                    # charging
                        pro_rata_share = float(op_status["Energy_kWh"]) / float(SOE_kWh) * float(setpoint)
                    else:
                        pro_rata_share = float(op_status["FullChargeEnergy_kWh"]-op_status["Energy_kWh"]) / \
                                         (max_SOE_kWh-float(SOE_kWh)) * float(setpoint)

                    _log.info("Optimizer: Sending request for "+str(pro_rata_share)+"to "+nodes["AgentID"])
                    self.vip.rpc.call(str(nodes["AgentID"]),
                                      "set_real_pwr_cmd",
                                      nodes["DeviceID"],
                                      pro_rata_share)

            self.optimizer_info["setpoint"]     = setpoint
            self.optimizer_info["targetPwr_kW"] = targetPwr_kW
            self.optimizer_info["curPwr_kW"]    = curPwr_kW
            # figure out what time it is right now
            # extract the right forecast from that time

            # figure out the current power output of the system:


            # device list consists of AgentID and DeviceID

            #targetPwr_kW = forecast
            #curPwr_kW    = PVVirtualPlant - curPwrOut

            #for resources in self.sundial_resources:
            #    new_system_resource["DeviceList"].append(
            #        {"AgentID": resources.resource_id, "DeviceID": resources.resource_id})
            #self.sundial_resources.append(SundialSystemResource(new_system_resource))

            # What -should- happen is this:
            # 1. sundial resources all update, aggregate their data - forecasts, power ,etc.
            # THEN, we have a function who has target pwr = resource forecast.  Cur pwr = baseline pwr
            #
            #
            #
            #


            #targetPwr_kW =
            #curPwr_kW
            #SOE_kWh
            #min_SOE_kWh,
            #max_SOE_kWh,
            #max_charge_kW,
            #max_discharge_kW


            #calc_ess_setpoint(targetPwr_kW, curPwr_kW, SOE_kWh, min_SOE_kWh, max_SOE_kWh, max_charge_kW,
            #                      max_discharge_kW)


            # need a series of methods to retrieve site's ctrl node data
            # 1. target power = sum of all baseline forecasts  (update_forecast)
            #
            # 2. cur_pwr_kW = sum of all baseline generation (update_op_status?)
            # 3. SOE - go to battery
            # 4. min_SOE
            # 5. max_SOE
            # 6. max_charge
            # 7. min_charge

            # we know the agent_id for each ctrl device.
        pass

    ##############################################################################
    @Core.periodic(STATUS_MSG_PD)
    def print_status_msg(self):
        """
        prints status to log file and to database
        :return:
        """

        _log.info("ExecutiveStatus: Mode = "+self.OperatingModes[self.OperatingMode])

        TimeStamp = datetime.now()

        for k,v in self.optimizer_info.items():
            _log.info("ExecutiveStatus: " + k + "=" + str(v))
  
            HistorianTools.publish_data(self, 
                                        "Executive", 
                                        TimeStamp.strftime("%Y-%m-%dT%H:%M:%S"), 
                                        k, 
                                        v)

    ##############################################################################
    @Core.periodic(EXECUTIVE_CLKTIME)
    def run_executive(self):
        """
        Periodically polls system mode and health indicators and transitions system state accordingly
        :return:
        """

        _log.info("Running Executive.  Curent Mode = "+self.OperatingModes[self.OperatingMode])

        self.check_site_statuses()

        if self.OperatingMode_set != self.OperatingMode:
            # indicates that a mode change has been requested
            _log.info("Changing operating mode to: " + self.OperatingModes[self.OperatingMode_set])

            self.OperatingMode = self.OperatingMode_set

            TimeStamp = datetime.now()
            HistorianTools.publish_data(self, 
                                        "Executive", 
                                        TimeStamp.strftime("%Y-%m-%dT%H:%M:%S"), 
                                        "OperatingMode", 
                                        self.OperatingMode)

            if self.OperatingMode == IDLE:
                # change sites to AUTO mode
                self.disable_site_interactive_mode()
                self.OptimizerEnable = DISABLED # shut down optimizer
                self.UICtrlEnable = DISABLED # placeholder
                pass
            elif self.OperatingMode == APPLICATION_CONTROL:
                # change sites to interactive mode
                self.enable_site_interactive_mode()
                self.OptimizerEnable = ENABLED
                self.UICtrlEnable = DISABLED
                # instantiate and build a new sundial resource manager when we switch to app ctrl mode

                # (re)start optimizer - would call "build_sundial"
                # instead, this can just be implied by checking op mode in the scheduled 'optimizer'
                # routine
                pass
            elif self.OperatingMode == USER_CONTROL:
                # change sites to interactive mode
                self.enable_site_interactive_mode()
                self.OptimizerEnable = DISABLED # shut down optimizer
                self.UICtrlEnable = ENABLED
                pass





        pass

    ##############################################################################
    @PubSub.subscribe('pubsub', 'data/NewSite/all')
    def add_site(self, peer, sender, bus,  topic, headers, message):
        _log.info("New Site found!!")
        data = message[0]
        _log.info("message is "+data) #str(dir(data)))


    ##############################################################################
    @RPC.export
    def set_mode(self, args):
        """
        This method writes an end point to a specified DER Device path
        """
        #fname = "/home/matt/sundial/Executive/cmdfile.txt"
        mode_val = args[0]
        self.OperatingMode_set = int(mode_val) #self.OperatingModes[self.OperatingModeInd]

        #with open(fname, 'a') as datafile:
        #    datafile.write(str(mode_val)+ " "+self.OperatingModes[self.OperatingMode_set]+"\n")
        _log.info("wrote: "+str(mode_val)+ " "+self.OperatingModes[self.OperatingMode_set]+"\n")

    ##############################################################################
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
