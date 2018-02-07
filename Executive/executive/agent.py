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
import gevent
from pytz import timezone
from volttron.platform.messaging.health import STATUS_GOOD
from volttron.platform.vip.agent import Agent, Core, PubSub, compat, RPC
from volttron.platform.agent import utils
from volttron.platform.messaging import headers as headers_mod
from volttron.platform.agent.known_identities import (
    VOLTTRON_CENTRAL, VOLTTRON_CENTRAL_PLATFORM, CONTROL, CONFIGURATION_STORE)

from . import settings
import HistorianTools

import DERDevice
from gs_identities import (IDLE, USER_CONTROL, APPLICATION_CONTROL, EXEC_STARTING,
                           EXECUTIVE_CLKTIME, GS_SCHEDULE, ESS_SCHEDULE, ENABLED, DISABLED, STATUS_MSG_PD,
                           SSA_SCHEDULE_RESOLUTION, SSA_PTS_PER_SCHEDULE, SSA_SCHEDULE_DURATION, START_LATENCY)
from gs_utilities import get_schedule

#utils.setup_logging()
_log = logging.getLogger("Executive")#__name__)
__version__ = '1.0'

import DERDevice
import json
import numpy
from SunDialResource import SundialSystemResource, SundialResource, SundialResourceProfile, build_SundialResource_to_SiteManager_lookup_table
from SSA_Optimization import SimulatedAnnealer


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
        setpoint = discharge_energy_available / (float(setpoint_cmd_interval) / float(sec_per_hr))
    elif energy_required > charge_energy_available:
        # (charge) set point needs to be adjusted to meet a max_SOE_kWh constraint
        setpoint = charge_energy_available / (float(setpoint_cmd_interval) / float(sec_per_hr))

    return setpoint

    pass


##############################################################################
def get_current_forecast(forecast):
    """
    figure out what time it is right now
    extract the right forecast from that time
    """
    #cur_time = datetime.now()
    return forecast["Pwr"][11]

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
        #FIXME - this should be set up with a configurable path....
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

        # FIXME: Temporary!  Used to track status of optimizer
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

        # publish OperatingMode on start up to the historian
        HistorianTools.publish_data(self, 
                                    "Executive", 
                                    "", 
                                    "OperatingMode", 
                                    self.OperatingMode)


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
            # to finish its initialization.
            # FIXME: There is probably a more robust way to do this, but this seems to work ok
            gevent.sleep(1.0)

            # The following gets a handle to the agent that we've just created.
            # It's not done very efficiently though - It gets a list of agents and find one that
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

        self.sundial_resources = SundialSystemResource(self.sundial_resource_cfg_list)
        _log.info("about to call lookup!")
        self.sdr_to_sm_lookup_table = build_SundialResource_to_SiteManager_lookup_table(self.sundial_resource_cfg_list,
                                                                                        self.sundial_resources,
                                                                                        sitemgr_list=self.sitemgr_list,
                                                                                        use_volttron=1)
        _log.info("done with lookup!!")
        for entries in self.sdr_to_sm_lookup_table:
            _log.info("SDRInit: "+entries.sundial_resource.resource_id + ":" + str(entries.device_list))

        self.optimizer = SimulatedAnnealer()
        self.sundial_resources.init_test_values(SSA_PTS_PER_SCHEDULE)

        _log.info("Finding Nodes")
        #FIXME - indices in lists
        self.ess_resources = self.sundial_resources.find_resource_type("ESSCtrlNode")[0]
        self.pv_resources  = self.sundial_resources.find_resource_type("PVCtrlNode")[0]
        self.system_resources = self.sundial_resources.find_resource_type("System")[0]
        self.loadshift_resources = self.sundial_resources.find_resource_type("LoadShiftCtrlNode")[0]
        self.load_resources = self.sundial_resources.find_resource_type("Load")[0]

        self.opt_cnt = 0

        self.OperatingMode_set = IDLE
        self.gs_start_time     = get_schedule() #utils.get_aware_utc_now()


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
            site_status = self.vip.rpc.call(site["identity"], "update_site_status").get(timeout=10)
            #for k,v in site_errors.items():
            #    if k=="Mode":
            #        pass
            #    elif site_errors[k] != 1:
            #        #self.OperatingMode_set = IDLE
            #        _log.info("ExecutiveStatus: Warning: Error detected - " +k+".  Transition to IDLE Mode")


    ##############################################################################
    @RPC.export
    def get_gs_start_time(self):
        #start_time_str = self.gs_start_time.strftime("%Y-%m-%dT%H:%M:%S.%f")
        return self.gs_start_time #start_time_str

    ##############################################################################
    def update_sundial_resources(self, sdr_to_sm_lookup_table):
        """
        This method updates the sundial resource data structure with the most recvent data from SiteManager
        agents.

        FIXME - maybe publish on the IEB instead - revisit.
        the lookup table contains devices that are connected to sdrs
        so this cycles through the lookup table and retrieves them.


        :param sdr_to_sm_lookup_table:
        :return:
        """

        # brainstorm idea - to handle the intermediate control loop
        # what if the "update_der_device_commands" method writes to a register that is called
        # "schedule command"
        # but the executive is in charge of calling the routine that actually writes the
        # scheduled command?
        # what if the sundial resource data objects have ?



        for entries in sdr_to_sm_lookup_table:

            for devices in entries.device_list:

                # TODO: check site health to see if we should update

                # MaxSOE_kWh, MinSOE_kWh, SOE_kWh, Nameplate(?), ChgEff, DischgEff, MaxChargePwr_kW... etc.
                for (a, v) in zip(entries.sundial_resource.update_list_attributes, entries.sundial_resource.update_list_end_pts):
                    # set up mapping keys from a to b
                    # set up a mapping file and mapping keys from sdr to derdevice and back
                    # these are intialized in the SDR routine.

                    _log.debug("UpdateSDR: "+entries.sundial_resource.resource_id+": SM Device ="+devices["DeviceID"]+"; a="+str(a)+"v="+str(v))
                    if devices["isAvailable"] == 1:
                        _log.debug(str(entries.sundial_resource.update_list_attributes[a]))
                        _log.debug(str(entries.sundial_resource.update_list_end_pts[v]))

                        attribute = self.vip.rpc.call(str(devices["AgentID"]),  # self.sundial_pv.sites[nodes["AgentID"]],
                                          "get_device_data",
                                          devices["DeviceID"],
                                          entries.sundial_resource.update_list_attributes[a]).get(timeout=5)

                        try:
                            _log.info(str(attribute[str(entries.sundial_resource.update_list_end_pts[v])]))
                            entries.sundial_resource.state_vars[a] = attribute[str(entries.sundial_resource.update_list_end_pts[v])] #.copy()

                        except KeyError:
                            _log.debug("Key not found!!")

                    #entries.sundial_resource. attribute[v]
        self.sundial_resources.update_sundial_resource() # propagates new data to non-ternminal nodes



    ##############################################################################
    @Core.periodic(ESS_SCHEDULE)
    def send_ess_commands(self):
        """
        What this is supposed to do - after optimizer is called
        we call this. it takes schedule data from the optimizer data structures
        and preps it for consumption by the forecast follower
        :param sdr_to_sm_lookup_table:
        :return:
        """

        # this should get called on a schedule - say every 30 seconds.`

        # (how are you going to deal with time?)
        # target power - sum of all (scheduled resources - ESS scheduled)
        # current power - sum of all resources (not including ess)
        # SOE_kWh - from battery
        # min_SOE_kWh
        # max_SOE_kWh
        # max_charge_kW
        # max_charge_kW
        # max_discharge_kW


        # get target power - how?
        # self.sundial_resources --> tree of SDRs
        # ESS = sdr.get_resource(resource_type)
        # what are the
        # target_pwr = update
        # should update just get called every 30 seconds on its own?
        # (let's assume yes)
        # let's say that this gets called


        # get_schedule --> implies that sch
        # should schedule be a pandas-time stamped list?

        # this needs to regulate power to target at time = now.
        # so I need to retrieve my schedule
        # the schedule data structure could be....
        # (1) pandas series of time stamped values
        # (2) there should be a routine that lets me query what the current target power output should be.
        # i.e., in sundialResource - get_scheduled_pwr(t) - returns the scheduled power at the specified time.
        #


        if self.OptimizerEnable == ENABLED:
            # update sundial_resources instance with the most recent data from end-point devices
            self.update_sundial_resources(self.sdr_to_sm_lookup_table)

            # retrieve the current power output of the system, not including energy storage.
            # taking a shortcut here - implicit assumption that there is a single pool of ESS
            curPwr_kW    = self.system_resources.state_vars["Pwr_kW"] - self.ess_resources.state_vars["Pwr_kW"]

            # retrieve the current scheduled value:
            # FIXME - taking a shortcut where we just grab the zero element of the schedule.  This is fine (For now) -
            # FIXME - the premise is that the schedule starts now.  There is a timing error, where I think that right
            # FIXME - now I'm generating a schedule for starting n minutes in the future.
            # first, get the "current" time slice.
            next_scheduled_time = datetime.strptime(get_schedule(),"%Y-%m-%dT%H:%M:%S.%f")
            cur_scheduled_time  = next_scheduled_time - timedelta(SSA_SCHEDULE_RESOLUTION)
            _log.info("Trying to retrieve next schedule")
            targetPwr_kW = self.system_resources.schedule_vars["DemandForecast_kW"][0]
            _log.info("Target power is " + str(targetPwr_kW))
            _log.info("Current power is "+str(curPwr_kW))

            SOE_kWh = self.ess_resources.state_vars["SOE_kWh"]
            min_SOE_kWh = self.ess_resources.state_vars["MinSOE_kWh"]
            max_SOE_kWh = self.ess_resources.state_vars["MaxSOE_kWh"]
            max_charge_kW = self.ess_resources.state_vars["MaxChargePwr_kW"]
            max_discharge_kW = self.ess_resources.state_vars["MaxDischargePwr_kW"]


            # figure out set point command to send to sites
            setpoint = calc_ess_setpoint(targetPwr_kW, curPwr_kW, SOE_kWh, min_SOE_kWh, max_SOE_kWh, max_charge_kW,
                                         max_discharge_kW)

            # divide set point between resources -
            # now send commands to the actual ESS's...
            _log.info("Optimizer: setpoint = " + str(setpoint))

            # Divide the set point command across the available ESS sites.
            # currently divided pro rata based on kWh available.
            # Rght now only one ESS - haven't tested with more
            for entries in self.sdr_to_sm_lookup_table:
                if entries.sundial_resource.resource_type == "ESSCtrlNode":
                    for devices in entries.device_list:
                        if devices["isAvailable"] == 1:
                            op_status = self.vip.rpc.call(str(devices["AgentID"]),
                                                          "get_device_data",
                                                          devices["DeviceID"],
                                                          "OpStatus").get(timeout=5)
                            if (setpoint > 0):  # charging
                                pro_rata_share = float(op_status["Energy_kWh"]) / float(SOE_kWh) * float(setpoint)
                            else:
                                pro_rata_share = float(op_status["FullChargeEnergy_kWh"] - op_status["Energy_kWh"]) / \
                                                 (max_SOE_kWh - float(SOE_kWh)) * float(setpoint)
                            _log.info("Optimizer: Sending request for " + str(pro_rata_share) + "to " + devices["AgentID"])
                            self.vip.rpc.call(str(devices["AgentID"]),
                                              "set_real_pwr_cmd",
                                              devices["DeviceID"],
                                              pro_rata_share)


            self.optimizer_info["setpoint"] = setpoint
            self.optimizer_info["targetPwr_kW"] = targetPwr_kW
            self.optimizer_info["curPwr_kW"] = curPwr_kW


    ##############################################################################
    def generate_schedule_timestamps(self):
        """

        :return:
        """
        MINUTES_PER_HR = 60
        schedule_start_time = datetime.strptime(get_schedule(),"%Y-%m-%dT%H:%M:%S.%f")

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

        self.last_optimization_start = utils.get_aware_utc_now()  # not currently used for anything
        if self.OptimizerEnable == ENABLED:
            schedule_timestamps = self.generate_schedule_timestamps()
            self.optimizer.run_ssa_optimization(self.sundial_resources, schedule_timestamps)

    ##############################################################################
    @Core.periodic(STATUS_MSG_PD)
    def print_status_msg(self):
        """
        prints status to log file and to database
        :return:
        """

        _log.info("ExecutiveStatus: Mode = "+self.OperatingModes[self.OperatingMode])

        for k,v in self.optimizer_info.items():
            _log.info("ExecutiveStatus: " + k + "=" + str(v))
            #FIXME need units for optimizer_info!!!
            HistorianTools.publish_data(self, 
                                        "Executive", 
                                        "", 
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
