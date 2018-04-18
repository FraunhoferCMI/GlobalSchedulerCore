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
import pytz
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
from gs_identities import *
from gs_utilities import get_schedule, get_gs_time

#utils.setup_logging()
_log = logging.getLogger("Executive")#__name__)
__version__ = '1.0'

import DERDevice
import json
import numpy
from SunDialResource import SundialSystemResource, SundialResource, SundialResourceProfile, build_SundialResource_to_SiteManager_lookup_table
from SSA_Optimization import SimulatedAnnealer

default_units = {"setpoint":"kW",
                 "targetPwr_kW": "kW",
                 "curPwr_kW": "kW",
                 "expectedPwr_kW": "kW",
                 "DemandForecast_kW": "kW",
                 "EnergyAvailableForecast_kWh": "kWh",
                 "netDemand_kW": "kW",
                 "timestamp": "datetime",
                 "gs_start_time": "datetime",
                 "SIM_START_TIME": "datetime",
                 "total_cost": ""}

##############################################################################
def calc_ess_setpoint(targetPwr_kW, curPwr_kW, SOE_kWh, min_SOE_kWh, max_SOE_kWh, max_charge_kW, max_discharge_kW):
    """
    Calculates a setpoint command to an ESS resource to bridge the gap between forecast and actual generation
    (1) first determines delta between forecast and actual.
    (2) Checks for power constraint
    (3) Checks for energy constraint
    and adjusts accordingly
    :param targetPwr_kW: expected amount of generation, in kW
    :param curPwr_kW: actual generation, in kW
    :param SOE_kWh: current ESS state of energy, in kWh
    :param min_SOE_kWh: minimum allowable SOE, in kWh
    :param max_SOE_kWh: max allowable SOE, in kWh
    :param max_charge_kW: max charge power available, in kW (ALWAYS POSITIVE!)
    :param max_discharge_kW: max discharge available, in kW (ALWAYS POSITIVE!)
    :return: ESS setpoint, in kW.  Negative = discharge, positive value = charge
    """
    # setpoint_cmd_interval indicates how frequently the target setpoint is recalculated.
    # it is used to determine what the max sustainable charge / discharge rate is for the
    # battery before the next time that we receive a high level schedule request.
    setpoint_cmd_interval = GS_SCHEDULE #FIXME - this needs to be tied to globals defined in gs_identities
    sec_per_hr = 60.0 * 60.0

    setpoint = targetPwr_kW-curPwr_kW  #FIXME sign convention for charge vs discharge?
    _log.info("Optimizer: target Setpoint ="+str(setpoint))

    # check that we are within power limits of the storage system
    if setpoint < -1 * max_discharge_kW:
        setpoint = -1 * max_discharge_kW
    if setpoint > max_charge_kW:
        setpoint = max_charge_kW

    # now check that the target setpoint is within the energy limits
    _log.info("Optimizer: Power-limited Setpoint =" + str(setpoint))

    # calculate what the remaining charge will be at the end of the next period
    # TODO - still need to correct for losses!!
    energy_required = setpoint * setpoint_cmd_interval / sec_per_hr
    discharge_energy_available = min_SOE_kWh - SOE_kWh
    charge_energy_available = max_SOE_kWh - SOE_kWh

    if energy_required < discharge_energy_available:
        # (discharge) set point needs to be adjusted to meet a min_SOE_kWh constraint 
        setpoint = discharge_energy_available / (float(setpoint_cmd_interval) / float(sec_per_hr))
    elif energy_required > charge_energy_available:
        # (charge) set point needs to be adjusted to meet a max_SOE_kWh constraint
        setpoint = charge_energy_available / (float(setpoint_cmd_interval) / float(sec_per_hr))

    return setpoint

##############################################################################
class ExecutiveAgent(Agent):
    """
    Runs SunDial Executive state machine
    """
    OperatingModes = ["IDLE", "USER_CONTROL", "APPLICATION_CONTROL", "EXEC_STARTING"]

    ##############################################################################
    def __init__(self, config_path, **kwargs):
        super(ExecutiveAgent, self).__init__(**kwargs)

        # Configuration Set Up
        self.default_config = {
            "DEFAULT_MESSAGE" :'Executive Message',
            "DEFAULT_AGENTID": "executive",
            "DEFAULT_HEARTBEAT_PERIOD": 5,
            "log-level":"INFO"
        }
        self._config = self.default_config.copy()
        self._agent_id = self._config.get("DEFAULT_AGENTID")
        self._message = self._config.get("DEFAULT_MESSAGE")
        self._heartbeat_period = self._config.get('DEFAULT_HEARTBEAT_PERIOD')
        # self.configure(None,None,self.default_config)
        self.vip.config.subscribe(
            self.configure,
            actions=["NEW", "UPDATE"],
            pattern="config")

        # Initialize State Machine
        # OperatingMode tracks the state of the Executive's state machine
        # OperatingMode_set is where you write to change the state.  Once
        # state has actually changed, OperatingMode gets updated
        # OptimizerEnable - toggles optimizer process on / off
        # UICtrlEnables   - toggles control from the User Interface on / off
        # refer to Executive state machine documentation
        self.OperatingMode_set = EXEC_STARTING #IDLE
        self.OperatingMode     = self.OperatingMode_set
        self.OptimizerEnable   = DISABLED
        self.UICtrlEnable      = DISABLED

        # Initialize Configuration Files
        #TODO - move to a config store?
        # Set up paths for config files.
        self.volttron_root = os.getcwd()
        self.volttron_root = self.volttron_root+"/../../../../"
        SiteCfgFile        = self.volttron_root+"gs_cfg/SiteConfiguration.json"
        SundialCfgFile     = self.volttron_root+"gs_cfg/SundialSystemConfiguration.json"
        self.packaged_site_manager_fname = self.volttron_root + "packaged/site_manageragent-1.0-py2-none-any.whl"
        self.SiteCfgList   = json.load(open(SiteCfgFile, 'r'))
        self.sundial_resource_cfg_list = json.load(open(SundialCfgFile, 'r'))
        _log.info("SiteConfig is "+SiteCfgFile)
        _log.info("SundialConfig is"+SundialCfgFile)

        self.optimizer_info = {}
        self.optimizer_info.update({"setpoint": 0.0})
        self.optimizer_info.update({"targetPwr_kW": 0.0})
        self.optimizer_info.update({"curPwr_kW": 0.0})
        self.optimizer_info.update({"expectedPwr_kW": 0.0})
        self.optimizer_info.update({"netDemand_kW": 0.0})

        self.opt_cnt = 0



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

        # publish OperatingMode on start up to the historian
        HistorianTools.publish_data(self, 
                                    "Executive", 
                                    "", 
                                    "OperatingMode", 
                                    self.OperatingMode)


        ######### This section initializes SiteManager agents that correspond to sites identified in the #############
        ######### SiteConfiguration.json file ########################################################################
        # The following reads a json site configuration file and installs / starts a new site
        # manager for each site identified in the configuration file.
        # agents are stored in an object list called "self.sitemgr_list"
        _log.info("SiteMgrConfig: **********INSTANTIATING NEW SITES*******************")
        self.sitemgr_list = []
        for site in self.SiteCfgList:
            _log.info("SiteMgr Config: "+str(site["ID"]))
            _log.info("SiteMgr Config: "+str(site))
            
            # start a new SiteManager agent 
            # FIXME - needs error trapping: (1) is agent already installed? (2) does site mgr agent exist?
            # FIXME - (3) did it start successfully?


            # check to see if an agent associated with the site already exists:
            uuid = None
            agents = self.vip.rpc.call(CONTROL, "list_agents").get(timeout=5)
            for cur_agent in agents:
                _log.info("Cur agent is "+cur_agent["identity"]+"; site id is"+site["ID"])
                if cur_agent["identity"] == site["ID"]:
                    uuid = cur_agent["uuid"]
                    _log.info("Match found!!")
                    break
            if uuid != None:  # remove existing agent
                _log.info("removing agent "+site["ID"])
                self.vip.rpc.call(CONTROL,
                                  "remove_agent",
                                  uuid)
                gevent.sleep(1.0)

            uuid = self.vip.rpc.call(CONTROL,
                                     "install_agent_local",
                                     self.packaged_site_manager_fname,
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
            # to finish its initialization.  There is a more elegant / robust way to accomplish this.
            gevent.sleep(1.0)

            # The following gets a handle to the agent that we've just created.
            # It gets a list of agents and find one that matches to the uuid, then breaks
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

        # SiteManager Initialization complete

        ###This section instantiates a SundialResource tree based on SystemConfiguration.json, and an Optimizer ########
        #self.gs_start_time_exact = utils.get_aware_utc_now()
        #self.gs_start_time       = get_schedule(self.gs_start_time_exact)
        self.gs_start_time = utils.get_aware_utc_now().replace(microsecond=0)
        _log.info("GS Start time is "+str(self.gs_start_time))
        self.sundial_resources = SundialSystemResource(self.sundial_resource_cfg_list, self.get_gs_start_time())
        self.sdr_to_sm_lookup_table = build_SundialResource_to_SiteManager_lookup_table(self.sundial_resource_cfg_list,
                                                                                        self.sundial_resources,
                                                                                        sitemgr_list=self.sitemgr_list,
                                                                                        use_volttron=1)
        for entries in self.sdr_to_sm_lookup_table:
            _log.info("SundialResource Init: "+entries.sundial_resource.resource_id + ":" + str(entries.device_list))
        self.optimizer = SimulatedAnnealer()
        self.sundial_resources.init_test_values(SSA_PTS_PER_SCHEDULE)

        ### This section retrieves direct references to specific resource types (avoids the need to traverse tree)
        # There is an implicit assumption that there is only one SundialResource node per resource type.  (i.e. we are
        # grabbing the 0th element in each list returned by find_resource_type
        # FIXME - to handle multiple resources groupings of the same type, code will need to be modified
        _log.info("Finding Nodes")
        self.ess_resources = self.sundial_resources.find_resource_type("ESSCtrlNode")[0]
        self.pv_resources  = self.sundial_resources.find_resource_type("PVCtrlNode")[0]
        self.system_resources = self.sundial_resources.find_resource_type("System")[0]
        try:
            self.loadshift_resources = self.sundial_resources.find_resource_type("LoadShiftCtrlNode")[0]
        except:
            self.loadshift_resources = []
        self.load_resources = self.sundial_resources.find_resource_type("Load")[0]

        # get a time stamp of start time to database
        HistorianTools.publish_data(self,
                                    "Executive",
                                    default_units["gs_start_time"],
                                    "gs_start_time",
                                    self.get_gs_start_time())

        HistorianTools.publish_data(self,
                                    "Executive",
                                    default_units["SIM_START_TIME"],
                                    "SIM_START_TIME",
                                    SIM_START_TIME.strftime("%Y-%m-%dT%H:%M:%S.%f"))

        self.OperatingMode_set = IDLE


    ##############################################################################
    def enable_site_interactive_mode(self):
        """
        send command to each site to transition to interactive mode
        :return:
        """
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
            site_status = self.vip.rpc.call(site["identity"], "update_site_status").get() #timeout=10)
            #for k,v in site_errors.items():
            #    if k=="Mode":
            #        pass
            #    elif site_errors[k] != 1:
            #        #self.OperatingMode_set = IDLE
            #        _log.info("ExecutiveStatus: Warning: Error detected - " +k+".  Transition to IDLE Mode")


    ##############################################################################
    @RPC.export
    def get_gs_start_time(self):
        """
        Returns a time stamp of the point at which GS execution began
        :return: self.gs_start_time - an ISO8601 datetime string that corresponds to the GS's start time
        Format is: "%Y-%m-%dT%H:%M:%S.%f"
        """
        return self.gs_start_time.strftime("%Y-%m-%dT%H:%M:%S") #, self.gs_start_time_exact.strftime("%Y-%m-%dT%H:%M:%S.%f") #start_time_str

    ##############################################################################
    def update_sundial_resources(self, sdr_to_sm_lookup_table):
        """
        This method updates the sundial resource data structure with the most recvent data from SiteManager
        agents.
        todo - consider modifying the update routine to retrieve data published on the message bus instead of retrieving
        todo - from RPC calls.  Plan on revisiting.

        :param sdr_to_sm_lookup_table: maps DERDevice instances to SundialResource instances.  This is an object of
        type SundialResource_to_SiteManager_lookup_table
        :return: None
        """

        for entries in sdr_to_sm_lookup_table:
            # for each SundialResource that maps to an end point device (i.e., terminal nodes in the
            # the resource tree)

            for devices in entries.device_list: # for each device associated with that SundialResource

                # TODO: Right here is where we would check the health status, availability, etc of end point devices
                # TODO: to see if we should include within the next optimization pass

                for k in entries.sundial_resource.update_list_end_pts:
                    # now map data end points from devices to SundialResources
                    _log.debug("UpdateSDR: "+entries.sundial_resource.resource_id+": SM Device ="+devices["DeviceID"]+"; k="+str(k))
                    if devices["isAvailable"] == 1:
                        # FIXME - should this extrapolate values to schedule start time.
                        # FIXME - e.g., assuming battery continues to charge / discharge at present rate what would the
                        # FIXME - value be at that time?
                        try:
                            dev_state_var = self.vip.rpc.call(str(devices["AgentID"]),
                                                              "get_device_state_vars",
                                                              devices["DeviceID"]).get(timeout=5)
                            _log.info(str(k)+": "+str(dev_state_var[k]))

                            entries.sundial_resource.state_vars[k] = dev_state_var[k]

                        except KeyError:
                            _log.debug("Key not found!!")

        self.sundial_resources.update_sundial_resource() # propagates new data to non-terminal nodes



    ##############################################################################
    @Core.periodic(ESS_SCHEDULE)
    def send_ess_commands(self):
        """
        Called periodically by executive.  This (1) updates sundial_resources data with latest data from end point
        devices; (2) generates target battery set points; and (3) propagates battery set point commands to end point
        devices
        :return: None
        """

        if self.OptimizerEnable == ENABLED:

            # update sundial_resources instance with the most recent data from end-point devices
            self.update_sundial_resources(self.sdr_to_sm_lookup_table)

            # Now we need to determine the target battery set point.  To do so, look at the total current system
            # power output, subtracting the contribution from the battery.  The delta between total current system
            # output and the schedule output determines the target ESS set point.
            # Note: As currently implemented, this is totally reactive to whatever the last power reading was, so high
            # likelihood that this will chase noise (at the very least, probably should look at a rolling average).
            # 
            # retrieve the current power output of the system, not including energy storage.
            # taking a shortcut here - implicit assumption that there is a single pool of ESS
            curPwr_kW    = self.system_resources.state_vars["Pwr_kW"] - self.ess_resources.state_vars["Pwr_kW"]
            netDemand_kW = self.system_resources.state_vars["Pwr_kW"]
            # retrieve the current scheduled value:
            # Taking a shortcut where we just grab the zero element of the most recently generated schedule.
            # This is fine (For now) - BUT presents a known issue as follows -
            # FIXME - The schedule generated by SimulatedAnnealer starts one time step in the future - so the zero
            # FIXME - elements of the schedule corresponds to current_t+1.  But this routine treats the retrieved
            # FIXME - schedule value as the **current** target.  This is a definite issue to be addressed!!
            # FIXME - possible fixes - (1) modify SSA to generate schedules started at t=now; (2) append, rather than
            # FIXME - replace, the schedule (so we would maintain values from previous optimization passes).  Also need
            # FIXME - to consider what happens if optimization pass occurs during a time step


            #cur_gs_time_step = get_schedule(self.gs_start_time) # get_gs_time(self.gs_start_time)
            cur_gs_time = get_gs_time(self.gs_start_time, timedelta(0))
            ii = 0
            _log.info(str(cur_gs_time))
            for t in self.system_resources.schedule_vars["timestamp"]:
                _log.info(str(t))
                if cur_gs_time < t:
                    break
                ii += 1
            ii -= 1

            _log.info("Generating dispatch: ii = "+str(ii))
            if (ii < 0): # shouldn't ever happen
                ii = 0

            targetPwr_kW = self.system_resources.schedule_vars["DemandForecast_kW"][ii]
            expectedPwr_kW = self.pv_resources.schedule_vars["DemandForecast_kW"][ii]
            _log.info("Expected power is " + str(expectedPwr_kW))
            _log.info("Target power is " + str(targetPwr_kW))
            _log.info("Current power is "+str(curPwr_kW))

            SOE_kWh = self.ess_resources.state_vars["SOE_kWh"]
            min_SOE_kWh = self.ess_resources.state_vars["MinSOE_kWh"]
            max_SOE_kWh = self.ess_resources.state_vars["MaxSOE_kWh"]
            max_charge_kW = self.ess_resources.state_vars["MaxChargePwr_kW"]
            max_discharge_kW = self.ess_resources.state_vars["MaxDischargePwr_kW"]

            if REGULATE_ESS_OUTPUT == True:
                # figure out set point command
                # note that this returns a setpoint command for a SundialResource ESSCtrlNode, which can group together
                # potentially multiple ESS end point devices
                setpoint = calc_ess_setpoint(targetPwr_kW,
                                             curPwr_kW,
                                             SOE_kWh,
                                             min_SOE_kWh,
                                             max_SOE_kWh,
                                             max_charge_kW,
                                             max_discharge_kW)

            else:
                setpoint = self.ess_resources.schedule_vars["DemandForecast_kW"][0]


            _log.info("Optimizer: setpoint = " + str(setpoint))

            # figure out how to divide set point command between and propagate commands to end point devices
            for entries in self.sdr_to_sm_lookup_table:
                if entries.sundial_resource.resource_type == "ESSCtrlNode":  # for each ESS
                    for devices in entries.device_list:   # for each end point device associated with that ESS
                        if devices["isAvailable"] == 1:   # device is available for control
                            # retrieve a reference to the device end point operational registers
                            device_state_vars = self.vip.rpc.call(str(devices["AgentID"]),
                                                                  "get_device_state_vars",
                                                                  devices["DeviceID"]).get(timeout=5)

                            _log.info("state vars = "+str(device_state_vars))

                            # Divides the set point command across the available ESS sites.
                            # currently divided pro rata based on kWh available.
                            # Right now configured with only one ESS - has not been tested this iteration with more
                            # than one ESS end point in this iteration
                            if (setpoint > 0):  # charging
                                # todo - check for div by zero
                                pro_rata_share = float(device_state_vars["SOE_kWh"]+0.001) / (float(SOE_kWh)+0.001) * float(setpoint)
                                #todo - need to check for min SOE - implication of the above is that min = 0
                            else: # discharging
                                pro_rata_share = float(device_state_vars["MaxSOE_kWh"] - device_state_vars["SOE_kWh"]+0.001) /\
                                                 (max_SOE_kWh - float(SOE_kWh)+0.001) * float(setpoint)
                            _log.info("Optimizer: Sending request for " + str(pro_rata_share) + "to " + devices["AgentID"])
                            # send command
                            self.vip.rpc.call(str(devices["AgentID"]),
                                              "set_real_pwr_cmd",
                                              devices["DeviceID"],
                                              pro_rata_share)


            self.optimizer_info["setpoint"] = setpoint
            self.optimizer_info["targetPwr_kW"] = targetPwr_kW
            self.optimizer_info["curPwr_kW"] = curPwr_kW
            self.optimizer_info["expectedPwr_kW"] = expectedPwr_kW
            self.optimizer_info["netDemand_kW"]   = netDemand_kW
            self.print_status_msg()

    ##############################################################################
    def generate_schedule_timestamps(self, sim_time_corr = timedelta(seconds=0)):
        """
        generates a list of time stamps associated with the next schedule to be generated by the optimizer.  These
        are the time indices of the scheduled power commmands (i.e., from SundialResource.schedule_var
        :return: schedule_timestamps - a list of datetimes, starting at the next schedule start, time step
        equal to SSA_SCHEDULE_RESOLUTION, and continuing until SSA_SCHEDULE_DURATION
        """
        MINUTES_PER_HR = 60
        schedule_start_time = get_gs_time(self.gs_start_time,
                                          sim_time_corr).replace(second = 0, microsecond=0)

        #schedule_start_time = datetime.strptime(get_schedule(self.gs_start_time,
        #                                                     sim_time_corr=sim_time_corr),
        #                                        "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=pytz.UTC)

        # generate the list of timestamps that will comprise the next forecast:
        schedule_timestamps = [schedule_start_time +
                               timedelta(minutes=t) for t in range(0,
                                                                   SSA_SCHEDULE_DURATION*MINUTES_PER_HR,
                                                                   SSA_SCHEDULE_RESOLUTION)]
        return schedule_timestamps

    ##############################################################################
    @Core.periodic(GS_SCHEDULE)
    def run_optimizer(self):
        """
        runs optimizer on specified schedule
        assumes that self.sundial_resources has up to date information from end point
        devices.
        :return: None
        """
        self.last_optimization_start = utils.get_aware_utc_now()  # not currently used
        if self.OptimizerEnable == ENABLED:
            #self.opt_cnt += 1
            if self.opt_cnt <= 1:  # fixme: use for debug, remove eventually
                try:
                    sim_time_corr = timedelta(seconds = self.vip.rpc.call("forecast_simagent-0.1_1",
                                                                          "get_sim_time_corr").get())
                    schedule_timestamps = self.generate_schedule_timestamps(sim_time_corr=sim_time_corr)  # associated timestamps
                    if schedule_timestamps[0] == self.system_resources.schedule_vars["timestamp"][0]:
                        # temporary work around to indicate to optimizer to use previous solution if cost was lower
                        # fixme - this work around does not account for contingency if forecast or system state changes unexpectedly
                        # same time window as previously
                        self.optimizer.persist_lowest_cost = 1
                    else:
                        self.optimizer.persist_lowest_cost = 0
                    _log.info("persist lower cost = "+str(self.optimizer.persist_lowest_cost)+"; new time = "+str(schedule_timestamps[0])+"; old time = "+str(self.system_resources.schedule_vars["timestamp"][0]))

                except:
                    _log.info("Forecast Sim RPC failed!")
                    schedule_timestamps = self.generate_schedule_timestamps()

                self.sundial_resources.interpolate_forecast(schedule_timestamps)
                self.optimizer.run_ssa_optimization(self.sundial_resources, schedule_timestamps) # SSA optimization

                HistorianTools.publish_data(self,
                                            "SystemResource/Schedule",
                                            default_units["DemandForecast_kW"],
                                            "DemandForecast_kW",
                                            self.system_resources.schedule_vars["DemandForecast_kW"].tolist())
                HistorianTools.publish_data(self,
                                            "SystemResource/Schedule",
                                            default_units["timestamp"],
                                            "timestamp",
                                            [t.strftime("%Y-%m-%dT%H:%M:%S") for t in self.system_resources.schedule_vars["timestamp"]])
                HistorianTools.publish_data(self,
                                            "SystemResource/Schedule",
                                            default_units["total_cost"],
                                            "total_cost",
                                            self.system_resources.schedule_vars["total_cost"])
                HistorianTools.publish_data(self,
                                            "ESSResource/Schedule",
                                            default_units["DemandForecast_kW"],
                                            "DemandForecast_kW",
                                            self.ess_resources.schedule_vars["DemandForecast_kW"].tolist())
                HistorianTools.publish_data(self,
                                            "ESSResource/Schedule",
                                            default_units["EnergyAvailableForecast_kWh"],
                                            "EnergyAvailableForecast_kWh",
                                            self.ess_resources.schedule_vars["EnergyAvailableForecast_kWh"].tolist())
                HistorianTools.publish_data(self,
                                            "ESSResource/Schedule",
                                            default_units["timestamp"],
                                            "timestamp",
                                            [t.strftime("%Y-%m-%dT%H:%M:%S") for t in self.ess_resources.schedule_vars["timestamp"]])
                HistorianTools.publish_data(self,
                                            "PVResource/Schedule",
                                            default_units["DemandForecast_kW"],
                                            "DemandForecast_kW",
                                            self.pv_resources.schedule_vars["DemandForecast_kW"].tolist())
                HistorianTools.publish_data(self,
                                            "PVResource/Schedule",
                                            default_units["timestamp"],
                                            "timestamp",
                                            [t.strftime("%Y-%m-%dT%H:%M:%S") for t in self.pv_resources.schedule_vars["timestamp"]])
                try:
                    HistorianTools.publish_data(self,
                                                "LoadResource/Schedule",
                                                default_units["DemandForecast_kW"],
                                                "DemandForecast_kW",
                                                self.load_resources.schedule_vars["DemandForecast_kW"].tolist())
                    HistorianTools.publish_data(self,
                                                "LoadResource/Schedule",
                                                default_units["timestamp"],
                                                "timestamp",
                                                [t.strftime("%Y-%m-%dT%H:%M:%S") for t in self.load_resources.schedule_vars["timestamp"]])
                except:    # assume demand module is not implemented
                    pass

                self.send_ess_commands()

    ##############################################################################
    #@Core.periodic(STATUS_MSG_PD)
    def print_status_msg(self):
        """
        prints status to log file and to database
        :return:
        """

        _log.info("ExecutiveStatus: Mode = "+self.OperatingModes[self.OperatingMode])

        for k,v in self.optimizer_info.items():
            _log.info("ExecutiveStatus: " + k + "=" + str(v))
            #TODO - still need to add meta data associated with optimizer_info to the historian message
            units = default_units[k]
            HistorianTools.publish_data(self, 
                                        "Executive", 
                                        units,
                                        k, 
                                        v)

    ##############################################################################
    @Core.periodic(EXECUTIVE_CLKTIME)
    def run_executive(self):
        """
        Periodically polls system mode and health indicators and transitions system state accordingly
        :return:
        """

        _log.info("ExecutiveStatus: Running Executive.  Curent Mode = "+self.OperatingModes[self.OperatingMode])

        # Wait until initialization has completed before checking on sites
        if self.OperatingMode != EXEC_STARTING:
            self.check_site_statuses()

        if self.OperatingMode_set != self.OperatingMode:
            # indicates that a mode change has been requested
            _log.info("ExecutiveStatus: Changing operating mode to: " + self.OperatingModes[self.OperatingMode_set])

            self.OperatingMode = self.OperatingMode_set

            HistorianTools.publish_data(self, 
                                        "Executive", 
                                        "", 
                                        "OperatingMode", 
                                        self.OperatingMode)

            if self.OperatingMode == IDLE:
                # change sites to AUTO mode
                self.disable_site_interactive_mode()
                self.OptimizerEnable = DISABLED # shut down optimizer
                self.UICtrlEnable = DISABLED # placeholder
            elif self.OperatingMode == APPLICATION_CONTROL:
                # change sites to interactive mode
                self.enable_site_interactive_mode()
                self.OptimizerEnable = ENABLED
                self.UICtrlEnable = DISABLED
                self.update_sundial_resources(self.sdr_to_sm_lookup_table)
                self.run_optimizer()
                # instantiate and build a new sundial resource manager when we switch to app ctrl mode

                # (re)start optimizer - would call "build_sundial"
                # instead, this can just be implied by checking op mode in the scheduled 'optimizer'
                # routine
            elif self.OperatingMode == USER_CONTROL:
                # change sites to interactive mode
                self.enable_site_interactive_mode()
                self.OptimizerEnable = DISABLED # shut down optimizer
                self.UICtrlEnable = ENABLED
            elif self.OperatingMode == EXEC_STARTING:
                # should not ever transition INTO starting mode.  don't know how you'd get here.
                pass

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
        _log.info("SetPt: wrote: "+str(mode_val)+ " "+self.OperatingModes[self.OperatingMode_set]+"\n")

    ##############################################################################
    @Core.receiver('onstop')
    def onstop(self, sender, **kwargs):
        """
        removes each SiteManager agent that was installed / initialized on Executive start
        :param sender:
        :param kwargs:
        :return:
        """
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
