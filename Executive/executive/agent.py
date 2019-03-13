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
from pprint import pprint
import gevent
from volttron.platform.messaging.health import STATUS_GOOD
from volttron.platform.vip.agent import Agent, Core, PubSub, compat, RPC
from volttron.platform.agent import utils
from volttron.platform.messaging import headers as headers_mod
from volttron.platform.agent.known_identities import (
    VOLTTRON_CENTRAL, VOLTTRON_CENTRAL_PLATFORM, CONTROL, CONFIGURATION_STORE)

from . import settings
import sys
import HistorianTools
from gs_identities import *
from gs_utilities import *
import json
import numpy
import pandas
from SunDialResource import SundialSystemResource, SundialResource, SundialResourceProfile, build_SundialResource_to_SiteManager_lookup_table
from SSA_Optimization import SimulatedAnnealer
import GeneratePriceMap
import pandas as pd
from pprint import pformat
#import deque function for rolling average
from collections import deque


# delete this imports
import random


#utils.setup_logging()
_log = logging.getLogger("Executive")#__name__)
__version__ = '1.0'

default_units = {"setpoint":"kW",
                 "targetPwr_kW": "kW",
                 "curPwr_kW": "kW",
                 "expectedPwr_kW": "kW",
                 "forecastError_kW": "kW",
                 "predPwr_kW": "kW",
                 "DemandForecast_kW": "kW",
                 "EnergyAvailableForecast_kWh": "kWh",
                 "expectedSOE_kWh": "kWh",
                 "netDemand_kW": "kW",
                 "netDemandAvg_kW": "kW",
                 "timestamp": "datetime",
                 "gs_start_time": "datetime",
                 "SIM_START_TIME": "datetime",
                 "total_cost": "",
                 "DemandChargeThreshold": "kW"}

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
    setpoint_cmd_interval = GS_SCHEDULE
    sec_per_hr = 60.0 * 60.0

    setpoint = targetPwr_kW-curPwr_kW
    # check that we are within power limits of the storage system
    if setpoint < -1 * max_discharge_kW:
        setpoint = -1 * max_discharge_kW
        _log.info("Optimizer: Power-limited Setpoint =" + str(setpoint))
    if setpoint > max_charge_kW:
        setpoint = max_charge_kW
        _log.info("Optimizer: Power-limited Setpoint =" + str(setpoint))

    # now check that the target setpoint is within the energy limits

    # calculate what the remaining charge will be at the end of the next period
    # TODO - still need to correct for losses!!
    energy_required = setpoint * setpoint_cmd_interval / sec_per_hr
    discharge_energy_available = min(min_SOE_kWh - SOE_kWh,0)
    charge_energy_available = max(max_SOE_kWh - SOE_kWh,0)

    if energy_required < discharge_energy_available:
        # (discharge) set point needs to be adjusted to meet a min_SOE_kWh constraint
        _log.info("energy-limited set point on discharge - old value:  "+str(setpoint))
        setpoint = discharge_energy_available / (float(setpoint_cmd_interval) / float(sec_per_hr))
        _log.info("New value: "+str(setpoint))
    elif energy_required > charge_energy_available:
        # (charge) set point needs to be adjusted to meet a max_SOE_kWh constraint
        _log.info("energy-limited set point on charge - old value: "+str(setpoint))
        setpoint = charge_energy_available / (float(setpoint_cmd_interval) / float(sec_per_hr))
        _log.info("New Value "+str(setpoint))

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
        self.OperatingMode_set = EXEC_STARTING
        self.OperatingMode     = self.OperatingMode_set
        self.OptimizerEnable   = DISABLED
        self.UICtrlEnable      = DISABLED

        # Initialize Configuration Files
        # Set up paths for config files.
        self.volttron_root = os.getcwd()
        self.volttron_root = self.volttron_root+"/../../../../"

        # SiteCfgFile        = GS_ROOT_DIR+CFG_PATH+"SiteCfg/"+SITE_CFG_FILE
        SiteCfgFile        = os.path.join(GS_ROOT_DIR,CFG_PATH,"SiteCfg/",SITE_CFG_FILE)
        # SundialCfgFile     = GS_ROOT_DIR+CFG_PATH+"SystemCfg/"+SYSTEM_CFG_FILE
        SundialCfgFile     = os.path.join(GS_ROOT_DIR,CFG_PATH,"SystemCfg/",SYSTEM_CFG_FILE)
        self.packaged_site_manager_fname = os.path.join(self.volttron_root, "packaged/site_manageragent-1.0-py2-none-any.whl")
        self.SiteCfgList   = json.load(open(SiteCfgFile, 'r'))
        self.sundial_resource_cfg_list = json.load(open(SundialCfgFile, 'r'))
        _log.info("SiteConfig is "+SiteCfgFile)
        _log.info("SundialConfig is"+SundialCfgFile)


        self.optimizer_info = {}
        self.optimizer_info.update({"setpoint": 0.0})
        self.optimizer_info.update({"targetPwr_kW": 0.0})
        self.optimizer_info.update({"curPwr_kW": 0.0})
        self.optimizer_info.update({"expectedPwr_kW": 0.0})
        self.optimizer_info.update({"expectedSOE_kWh": 0.0})
        self.optimizer_info.update({"forecastError_kW": 0.0})
        self.optimizer_info.update({"netDemand_kW": 0.0})
        self.optimizer_info.update({"netDemandAvg_kW": 0.0})
        self.optimizer_info.update({"predPwr_kW": 0.0})

        self.run_optimizer_cnt     = 0
        self.send_ess_commands_cnt = 0
        self.update_endpt_cnt      = 0
        self.data_log_cnt          = 0

        self.prevPwr_kW = None
        #initializes queue for rolling average, maxlen of 600 elements, recommend assigning a variable to this
        self.queuePwr = deque([0], maxlen=600)
        self.last_forecast_start   = datetime(1900, 1, 1, tzinfo=pytz.UTC)


        self.init_tariffs()


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

        self.send_exec_heartbeat()

        ###This section instantiates a SundialResource tree based on SystemConfiguration.json, and an Optimizer ########
        #self.gs_start_time_exact = utils.get_aware_utc_now()
        #self.gs_start_time       = get_schedule(self.gs_start_time_exact)
        self.gs_start_time = utils.get_aware_utc_now().replace(microsecond=0)
        _log.info("Setup: GS Start time is "+str(self.gs_start_time))

        ######### This section initializes SiteManager agents that correspond to sites identified in the #############
        ######### SiteConfiguration.json file ########################################################################
        # The following reads a json site configuration file and installs / starts a new site
        # manager for each site identified in the configuration file.
        # agents are stored in an object list called "self.sitemgr_list"
        _log.info("SiteMgrConfig: **********INSTANTIATING NEW SITES*******************")
        self.sitemgr_list = []
        for site in self.SiteCfgList:
            _log.info("INSTANTIATING NEW SITE: %s" % site)
            if site["Use"] == "Y":
                _log.info("SiteMgr Config: "+str(site["ID"]))
                _log.info("SiteMgr Config: "+str(site))

                # check to see if an agent associated with the site already exists:
                uuid = None
                agents = self.vip.rpc.call(CONTROL, "list_agents").get(timeout=5)
                for cur_agent in agents:
                    if cur_agent["identity"] == site["ID"]:
                        uuid = cur_agent["uuid"]
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
                _log.info("Setup: Installing Agent - uuid is:" + uuid)
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
                        _log.info("Setup: Agent name is: "+cur_agent["name"])
                        #_log.info("Agent dir is: "+str(dir(cur_agent)))
                        _log.info("Setup: Agent id is: "+cur_agent["identity"])
                        break
                # TODO - return something from init_site indicating success??
                self.vip.rpc.call(cur_agent["identity"], "init_site", site)

        # SiteManager Initialization complete

        self.sundial_resources = SundialSystemResource(self.sundial_resource_cfg_list, self.get_gs_start_time())
        _log.info("sundial_resources assigned")
        self.sdr_to_sm_lookup_table = build_SundialResource_to_SiteManager_lookup_table(self.sundial_resource_cfg_list,
                                                                                        self.sundial_resources,
                                                                                        sitemgr_list=self.sitemgr_list,
                                                                                        use_volttron=1)
        for entries in self.sdr_to_sm_lookup_table:
            _log.info("Setup: SundialResource Init: "+entries.sundial_resource.resource_id + ":" + str(entries.device_list))
        self.optimizer = SimulatedAnnealer()

        ### This section retrieves direct references to specific resource types (avoids the need to traverse tree)
        # There is an implicit assumption that there is only one SundialResource node per resource type.  (i.e. we are
        # grabbing the 0th element in each list returned by find_resource_type
        # Note - to handle multiple resources groupings of the same type, code will need to be modified
        self.ess_resources = self.sundial_resources.find_resource_type("ESSCtrlNode")[0]
        self.pv_resources  = self.sundial_resources.find_resource_type("PVCtrlNode")[0]
        self.system_resources = self.sundial_resources.find_resource_type("System")[0]
        try:
            self.loadshift_resources = self.sundial_resources.find_resource_type("LoadShiftCtrlNode")[0]
        except:
            self.loadshift_resources = []
        try:
            self.load_resources = self.sundial_resources.find_resource_type("Load")[0]
        except:
            self.load_resources = []

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


        HistorianTools.publish_data(self,
                                    "Tariffs",
                                    default_units["DemandChargeThreshold"],
                                    "DemandChargeThreshold",
                                    self.tariffs["threshold"])


        self.OperatingMode_set = USER_CONTROL


    ##############################################################################
    def enable_site_interactive_mode(self):
        """
        send command to each site to transition to interactive mode
        :return:
        """
        for site in self.sitemgr_list:
            _log.info("SetPt: Sending interactive mode command for "+site["identity"])
            self.vip.rpc.call(site["identity"], "set_interactive_mode").get(timeout=5)
            # check for success ...


    ##############################################################################
    def disable_site_interactive_mode(self):
        """
        send command to each site to transition to auto (non-interactive) mode
        :return:
        """
        for site in self.sitemgr_list:
            _log.info("SetPt: Sending auto mode command for "+site["identity"])
            self.vip.rpc.call(site["identity"], "set_auto_mode").get(timeout=5)

    ##############################################################################
    def check_site_statuses(self):
        """
        Updates the site status for each active site
        :return:
        """
        for site in self.sitemgr_list:
            #_log.info("Updating status for site "+site["identity"])
            site_status = self.vip.rpc.call(site["identity"], "update_site_status").get() #timeout=10)
            #for k,v in site_status: #site_errors.items():
            #    _log.info("SiteStatus: ")
            #    if k=="Mode":
            #        pass
            #    elif site_errors[k] != 1:
            #        #self.OperatingMode_set = IDLE
            #        _log.info("ExecutiveStatus: Warning: Error detected - " +k+".  Transition to IDLE Mode")


        #self.SiteStatus.update({"ReadStatus": self.site.read_status})
        #self.SiteStatus.update({"WriteError": WriteError})
        #self.SiteStatus.update({"DeviceStatus": self.site.device_status})
        #self.SiteStatus.update({"CmdError": CmdError})
        #self.SiteStatus.update({"CommStatus": self.site.comms_status})
        #self.SiteStatus.update({"CtrlMode": self.site.control_mode})
        #self.SiteStatus.update({"DataAvailable": self.site.isDataValid})
        #self.SiteStatus.update({"CtrlAvailable": self.site.isControlAvailable})



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
    def init_tariffs(self):

        #fname = "energy_price_data.xlsx"
        #volttron_root = os.getcwd()
        #volttron_root = volttron_root + "/../../../../gs_cfg/"
        #fname_fullpath = volttron_root+fname
        #self.energy_price_data = pandas.read_excel(fname_fullpath, header=0, index_col=0)

        start_times = pd.date_range(datetime.now().date(),
                                    periods=24,
                                    freq='H')
        # iso_data = pd.DataFrame([random.random() / 10 for i in range(24)],
        #                         index = start_times)
        iso_data = numpy.array([random.random() / 10 for i in range(SSA_PTS_PER_SCHEDULE)])
        self.tariffs = {"threshold": DEMAND_CHARGE_THRESHOLD,
                        "isone": iso_data
                        }

        #self.tariffs = {"energy_price": }

        #indices = [numpy.argmin(
        #    numpy.abs(
        #        numpy.array([pandas.Timestamp(t).replace(tzinfo=pytz.UTC).to_pydatetime() for t in self.energy_price_data.index]) -
        #        (ts.replace(minute=0, second=0, microsecond=0) + sim_offset))) for ts in schedule_timestamps]
        #self.cur_cost = obj_fcn_data.iloc[indices]  #obj_fcn_data.loc[offset_ts].interpolate(method='linear')



    ##############################################################################
    def update_tariffs(self):
        if UPDATE_THRESHOLD == True:
            if self.system_resources.state_vars["AvgPwr_kW"] > 1.1*self.tariffs["threshold"]:
                self.tariffs["threshold"] = self.system_resources.state_vars["AvgPwr_kW"]/1.1

                HistorianTools.publish_data(self,
        	                                "Tariffs",
                	                        default_units["DemandChargeThreshold"],
                        	                "DemandChargeThreshold",
                                	        self.tariffs["threshold"])

        #self.tariffs["demand_charge_threshold"] = max(self.tariffs["demand_charge_threshold"],self.system_resources.state_vars["Pwr_kW"])
        pass


    ##############################################################################
    def chk_site_errors(self, dev_state_var, devices):
        """
        place holder routine for managing errors in data collection
        :return:
        """
        err_msg = ""
        err_keys = ["ReadStatus",
                    "DeviceStatus",
                    "CommStatus",
                    "WriteStatus"]

        for err_type in err_keys:
            if dev_state_var[err_type] == 0:
                err_msg += err_type + " Error; "
        if err_msg != "":
            _log.info(devices["AgentID"] + "-" + devices["DeviceID"] + ": " + err_msg)
        else:
            _log.info(devices["AgentID"] + "-" + devices["DeviceID"] + ": No Errors Found")

    ##############################################################################
    def update_sundial_resources(self, sdr_to_sm_lookup_table, update_forecasts = False):
        """
        This method updates the sundial resource data structure with the most recvent data from SiteManager
        agents.
        :param sdr_to_sm_lookup_table: maps DERDevice instances to SundialResource instances.  This is an object of
        type SundialResource_to_SiteManager_lookup_table
        :return: None
        """
        for entries in sdr_to_sm_lookup_table:
            # for each SundialResource that maps to an end point device (i.e., terminal nodes in the
            # the resource tree)

            for devices in entries.device_list: # for each device associated with that SundialResource
                if update_forecasts == False:
                    update_list = entries.sundial_resource.end_pt_update_list
                else:
                    update_list = entries.sundial_resource.forecast_update_list

                for k in update_list:
                    # now map data end points from devices to SundialResources
                    _log.debug("UpdateSDR: "+entries.sundial_resource.resource_id+": SM Device ="+devices["DeviceID"]+"; k="+str(k)+"; agent="+str(devices["AgentID"]))
                    if devices["isAvailable"] == 1:
                        try:
                            dev_state_var = self.vip.rpc.call(str(devices["AgentID"]),
                                                              "get_device_state_vars",
                                                              devices["DeviceID"]).get(timeout=5)
                            _log.info(devices["AgentID"]+"-"+devices["DeviceID"]+" - "+str(k) + ": " + str(dev_state_var[k]))
                            entries.sundial_resource.state_vars[k] = dev_state_var[k]

                        except KeyError:
                            _log.debug("Key not found!!")
        if update_forecasts == False:
            self.sundial_resources.update_sundial_resource()  # propagates new data to non-terminal nodes
            self.update_tariffs()



    ##############################################################################
    def calc_cost(self, sundial_resource):
        """
        calculates the cost of the current schedule
        :param sundial_resource: top node in sundial resource tree
        :return: total cost of scheduled output
        """
        total_cost = 0

        for virtual_plant in sundial_resource.virtual_plants:
            total_cost += self.calc_cost(virtual_plant)

        cost = sundial_resource.calc_cost(sundial_resource.schedule_vars)
        total_cost += cost
        return cost

    ##############################################################################
    @RPC.export
    def generate_cost_map(self, n_time_steps = 24, search_resolution = 25):
        """
        generates marginal cost of electricity per kWh as a function of time and demand.
        It generates a matrix of cost as a function of time (on one axis) and demand on the other axis
        First, it calculates an upper and lower bound for demand and generates demand tiers based on
        the search resolution
        Then, for each time step and demand step within the search space, it calculates marignal cost of electricity
        within that bin
        Once the matrix is generated, demand tiers are culled to identify tiers where change in demand occurs.
        :param n_time_steps: number of time steps in the search space
        :param search_resolution: size of the demand tiers for initial search, in kW
        :return: tiers - list of lists of dictionary - each entry is defines price as a function of demand LB/UB and time
        """

        try:
            sim_time_corr = timedelta(seconds=self.vip.rpc.call("forecast_simagent-0.1_1",
                                                                "get_sim_time_corr").get())
            schedule_timestamps = self.generate_schedule_timestamps(sim_time_corr=sim_time_corr)  # associated timestamps
        except:
            _log.info("Forecast Sim RPC failed!")
            schedule_timestamps = self.generate_schedule_timestamps()

        self.sundial_resources.interpolate_forecast(schedule_timestamps)
        self.sundial_resources.cfg_cost(schedule_timestamps,
                                        system_tariff=self.tariffs)


        return GeneratePriceMap.generate_cost_map(self.sundial_resources,
                                                  self.pv_resources,
                                                  n_time_steps,
                                                  search_resolution)

    ##############################################################################
    def find_current_timestamp_index(self):
        ii = 0
        # retrieve the current scheduled value:
        cur_gs_time = get_gs_time(self.gs_start_time, timedelta(0))
        _log.info(str(cur_gs_time))
        for t in self.system_resources.schedule_vars["timestamp"]:
            _log.debug(str(t))
            if cur_gs_time < t:
                break
            ii += 1
        ii -= 1

        _log.debug("Generating dispatch: ii = " + str(ii))
        if (ii < 0):  # shouldn't ever happen
            ii = 0
        return ii


    ##############################################################################
    def get_extrapolation(self, v1, v2, delta_t, pred_t):
        """
        Returns a linear extrapolation of two samples (v1 and v2) separated in time by delta_t for a sample pt
        pred_t time in the future
        :param v1:
        :param v2:
        :param delta_t:
        :param pred_t:
        :return:
        """
        pred_change = pred_t * (v2 - v1)/delta_t
        #pred_val = v2 + pred_change
        return pred_change

    ##############################################################################
    def send_loadshift_commands(self):
        """
        Method for sending select load shift profile(s) to the appropriate Site Manager agents
        :return:
        """
        for entries in self.sdr_to_sm_lookup_table:
            if entries.sundial_resource.resource_type == "LoadShiftCtrlNode":
                for devices in entries.device_list:  # for each end point device associated with that ctrl node
                    if devices["isAvailable"] == 1:  # device is available for control
                        # retrieve a reference to the device end point operational registers
                        device_state_vars = self.vip.rpc.call(str(devices["AgentID"]),
                                                              "get_device_state_vars",
                                                              devices["DeviceID"]).get(timeout=5)

                        val = self.loadshift_resources.schedule_vars["SelectedProfile"]

                        _log.info("Optimizer: Sending request for load shift profile " + str(val) + "to " + devices["AgentID"])
                        # send command
                        self.vip.rpc.call(str(devices["AgentID"]),
                                          "set_real_pwr_cmd",
                                          devices["DeviceID"],
                                          val)

    ##############################################################################
    @Core.periodic(3600)
    def send_exec_heartbeat(self):

        HistorianTools.publish_data(self,
                                    "Executive",
                                    "",
                                    "exec_heartbeat",
                                    1)

        pass

    ##############################################################################
    #@Core.periodic(ESS_SCHEDULE)
    def send_ess_commands(self):
        """
        Called periodically by executive.  This (1) updates sundial_resources data with latest data from end point
        devices; (2) generates target battery set points; and (3) propagates battery set point commands to end point
        devices
        :return: None
        """
        if self.OptimizerEnable == ENABLED:
            # Now we need to determine the target battery set point.  To do so, look at the total current system
            # power output, subtracting the contribution from the battery.  The delta between total current system
            # output and the schedule output determines the target ESS set point.
            # Note: As currently implemented, this is reactive, so high likelihood that this will chase noise
            #
            # retrieve the current power output of the system, not including energy storage.
            # taking a shortcut here - implicit assumption that there is a single pool of ESS
            curPwr_kW    = self.system_resources.state_vars["Pwr_kW"] - self.ess_resources.state_vars["Pwr_kW"]
            netDemand_kW = self.system_resources.state_vars["Pwr_kW"]
            netDemandAvg_kW = self.system_resources.state_vars["AvgPwr_kW"]

            if self.prevPwr_kW is None:
                self.prevPwr_kW = curPwr_kW
            elif SMOOTH_RAMP == False:
                self.prevPwr_kW = curPwr_kW

            #Determines slope between current and previous point
            predchangePwr_kW = self.get_extrapolation(self.prevPwr_kW, curPwr_kW, 1, 1)
                        #Determines if queue(FIFO) is full
            if len(self.queuePwr) == self.queuePwr.maxlen:
                #If full, pop the most element at front of queue(FIFO)
                self.queuePwr.popleft()
            #Push latest calculated slope value into end of queue(FIFO)
            self.queuePwr.append(predchangePwr_kW)
            #Predicted power is equal to the current Power + rolling average of slope
            predPwr_kW = curPwr_kW + (sum(self.queuePwr) / len(self.queuePwr))
            #Updates previous power holding variable
            self.prevPwr_kW = curPwr_kW

            if USE_FORECAST_VALUE == True:
                if ALIGN_SCHEDULES == True:
                    cur_time = datetime.utcnow().replace(minute=0, second=0, microsecond=0,tzinfo=pytz.utc)
                    try:
                        targetPwr_kW = self.sundial_resources.schedule_vars["schedule_kW"][cur_time]
                        expectedPwr_kW = self.pv_resources.schedule_vars["schedule_kW"][cur_time] + self.load_resources.schedule_vars["schedule_kW"][cur_time]
                        essTargetPwr_kW = self.ess_resources.schedule_vars["schedule_kW"][cur_time]
                        expectedSOE_kWh = self.ess_resources.schedule_vars["schedule_kWh"][cur_time]
                        self.system_resources.state_vars["TgtPwr_kW"] = targetPwr_kW
                    except KeyError:
                        _log.info("Error generating target command for time stamp "+str(cur_time))
                        targetPwr_kW = 0
                        expectedPwr_kW = 0
                        essTargetPwr_kW = 0
                        expectedSOE_kWh = 0
                else:
                    ii = self.find_current_timestamp_index()
                    targetPwr_kW = self.system_resources.schedule_vars["DemandForecast_kW"][ii]
                    expectedPwr_kW = self.pv_resources.schedule_vars["DemandForecast_kW"][ii] + self.load_resources.schedule_vars["DemandForecast_kW"][ii]
                    essTargetPwr_kW = self.ess_resources.schedule_vars["DemandForecast_kW"][ii]
                    expectedSOE_kWh = self.ess_resources.schedule_vars["EnergyAvailableForecast_kWh"][ii]
            else:
                ii = 0
                cur_gs_time = get_gs_time(self.gs_start_time, timedelta(0))
                if ((cur_gs_time.hour > 7) & (cur_gs_time.hour < 19)):
                    acc_load = 0
                    _log.info("in the right time window")
                else:
                    acc_load = 0
                _log.info(self.pv_resources.state_vars["AvgPwr_kW"])
                _log.info(self.pv_resources.state_vars["Pwr_kW"])
                _log.info(acc_load)
                _log.info(cur_gs_time.hour)
                targetPwr_kW = self.pv_resources.state_vars["AvgPwr_kW"] + acc_load
                expectedPwr_kW = self.pv_resources.schedule_vars["DemandForecast_kW"][0] + self.load_resources.schedule_vars["DemandForecast_kW"][0]
                essTargetPwr_kW = 0
                expectedSOE_kWh = self.ess_resources.schedule_vars["EnergyAvailableForecast_kWh"][0]

            forecastError_kW = expectedPwr_kW - curPwr_kW
            _log.debug("Regulator: Forecast Power is " + str(expectedPwr_kW))
            _log.debug("Regulator: Scheduled power output is " + str(targetPwr_kW))
            _log.debug("Regulator: Current PV+Load is "+str(curPwr_kW))
            _log.debug("Regulator: Forecast Error "+str(forecastError_kW))
            _log.debug("Regulator: Expected SOE "+str(expectedSOE_kWh))

            SOE_kWh = self.ess_resources.state_vars["SOE_kWh"]
            min_SOE_kWh = self.ess_resources.state_vars["MinSOE_kWh"]
            max_SOE_kWh = self.ess_resources.state_vars["MaxSOE_kWh"]

            if IMPORT_CONSTRAINT == True:
                max_charge_kW = min(-1*self.pv_resources.state_vars["Pwr_kW"],
                                    self.ess_resources.state_vars["MaxChargePwr_kW"])
            else:
                max_charge_kW = self.ess_resources.state_vars["MaxChargePwr_kW"]

            max_discharge_kW = self.ess_resources.state_vars["MaxDischargePwr_kW"]

            if REGULATE_ESS_OUTPUT == True:
                # figure out set point command
                # note that this returns a setpoint command for a SundialResource ESSCtrlNode, which can group together
                # potentially multiple ESS end point devices
                setpoint = calc_ess_setpoint(targetPwr_kW,
                                             predPwr_kW,
                                             SOE_kWh,
                                             min_SOE_kWh,
                                             max_SOE_kWh,
                                             max_charge_kW,
                                             max_discharge_kW)

            else:
                setpoint = essTargetPwr_kW


            _log.debug("Regulator: setpoint = " + str(setpoint))

            # figure out how to divide set point command between and propagate commands to end point devices
            for entries in self.sdr_to_sm_lookup_table:
                if entries.sundial_resource.resource_type == "ESSCtrlNode":  # for each ESS
                    for devices in entries.device_list:   # for each end point device associated with that ESS
                        if devices["isAvailable"] == 1:   # device is available for control
                            # retrieve a reference to the device end point operational registers
                            device_state_vars = self.vip.rpc.call(str(devices["AgentID"]),
                                                                  "get_device_state_vars",
                                                                  devices["DeviceID"]).get(timeout=5)

                            _log.debug("state vars = "+str(device_state_vars))

                            # Divides the set point command across the available ESS sites.
                            # currently divided pro rata based on kWh available.
                            # Right now configured with only one ESS - has not been tested this iteration with more
                            # than one ESS end point in this iteration
                            if (setpoint > 0):  # charging
                                pro_rata_share = float(device_state_vars["SOE_kWh"]+EPSILON) / (float(SOE_kWh)+EPSILON) * float(setpoint)
                                #todo - need to check for min SOE - implication of the above is that min = 0
                            else: # discharging
                                pro_rata_share = float(device_state_vars["MaxSOE_kWh"] - device_state_vars["SOE_kWh"]+EPSILON) /\
                                                 (max_SOE_kWh - float(SOE_kWh)+EPSILON) * float(setpoint)
                            _log.debug("Optimizer: Sending request for " + str(pro_rata_share) + "to " + devices["AgentID"])
                            # send command
                            self.vip.rpc.call(str(devices["AgentID"]),
                                              "set_real_pwr_cmd",
                                              devices["DeviceID"],
                                              pro_rata_share)


            self.optimizer_info["setpoint"] = setpoint
            self.optimizer_info["targetPwr_kW"] = targetPwr_kW
            self.optimizer_info["curPwr_kW"] = curPwr_kW
            self.optimizer_info["expectedPwr_kW"] = expectedPwr_kW
            self.optimizer_info["expectedSOE_kWh"] = expectedSOE_kWh
            self.optimizer_info["forecastError_kW"] = forecastError_kW
            self.optimizer_info["predPwr_kW"] = predPwr_kW
            self.optimizer_info["netDemand_kW"]   = netDemand_kW
            self.optimizer_info["netDemandAvg_kW"] = netDemandAvg_kW
            self.publish_ess_cmds()

    ##############################################################################
    def generate_schedule_timestamps(self, sim_time_corr = timedelta(seconds=0)):
        """
        generates a list of time stamps associated with the next schedule to be generated by the optimizer.  These
        are the time indices of the scheduled power commmands (i.e., from SundialResource.schedule_var
        :return: schedule_timestamps - a list of datetimes, starting at the next schedule start, time step
        equal to SSA_SCHEDULE_RESOLUTION, and continuing until SSA_SCHEDULE_DURATION
        """
        if ALIGN_SCHEDULES == True:
            if self.sundial_resources.schedule_vars["schedule_kW"] == {}:
                # first time we call, generate a schedule for the current time period.
                schedule_start_time = get_gs_time(self.gs_start_time,
                                                  sim_time_corr).replace(minute = 0, second = 0, microsecond=0) + \
                                      timedelta(hours=0)
            else:
                schedule_start_time = get_gs_time(self.gs_start_time,
                                                  sim_time_corr).replace(minute = 0, second = 0, microsecond=0) + \
                                      timedelta(hours=1)
        else:
            schedule_start_time = get_gs_time(self.gs_start_time,
                                              sim_time_corr).replace(second = 0, microsecond=0)


        # generate the list of timestamps that will comprise the next forecast:
        schedule_timestamps = [schedule_start_time +
                               timedelta(minutes=t) for t in range(0,
                                                                   SSA_SCHEDULE_DURATION*MINUTES_PER_HR,
                                                                   SSA_SCHEDULE_RESOLUTION)]
        return schedule_timestamps

    ##############################################################################
    #@Core.periodic(GS_SCHEDULE)
    def run_optimizer(self):
        """
        runs optimizer on specified schedule
        assumes that self.sundial_resources has up to date information from end point
        devices.
        :return: None
        """
        if self.OptimizerEnable == ENABLED:
            # check to make sure that resources have been updated
            # if they have not - ... - request an update and go into a waiting state.

            try:
                sim_time_corr = timedelta(seconds = self.vip.rpc.call("forecast_simagent-0.1_1",
                                                                      "get_sim_time_corr").get())
                schedule_timestamps = self.generate_schedule_timestamps(sim_time_corr=sim_time_corr)  # associated timestamps
            except:
                _log.info("Forecast Sim RPC failed!")
                schedule_timestamps = self.generate_schedule_timestamps()

            ## update forecast information and interopolate from native forecast time to optimizer time
            ## (so that all forecasts are defined from t = now)
            self.update_sundial_resources(self.sdr_to_sm_lookup_table,
                                          update_forecasts=True)
            self.sundial_resources.interpolate_forecast(schedule_timestamps)

            cur_time = datetime.utcnow().replace(microsecond=0, second=0, tzinfo=pytz.UTC)
            self.sundial_resources.interpolate_soe(schedule_timestamps, cur_time)

            if self.sundial_resources.state_vars["DemandForecast_kW"][0] == None:
                _log.info("Forecast(s) unavailable - Skipping optimization")
            else:
                # work around to indicate to optimizer to use previous solution if cost was lower
                # same time window as previously
                # todo - looks only at solar forecast to determine whether new forecast has arrived...should this
                # todo - look at other forecasts also?
                # fixme - this work around does not account for contingency if forecast or system state changes unexpectedly
                if ALIGN_SCHEDULES == True:
                    forecast_start = schedule_timestamps[0]
                else:
                    forecast_start = datetime.strptime(self.pv_resources.state_vars["OrigDemandForecast_t_str"][0],
                                                       "%Y-%m-%dT%H:%M:%S").replace(tzinfo=pytz.UTC)

                if forecast_start == self.last_forecast_start:
                    self.optimizer.persist_lowest_cost = 1
                else:
                    self.optimizer.persist_lowest_cost = 0
                _log.info("persist lower cost = "+str(self.optimizer.persist_lowest_cost)+"; old time = "+self.last_forecast_start.strftime("%Y-%m-%dT%H:%M:%S")+"; new time = "+forecast_start.strftime("%Y-%m-%dT%H:%M:%S"))

                self.last_forecast_start = forecast_start

                ## queue up time-differentiated cost data
                _log.info("THESE ARE THE TARIFFS: {}".format(self.tariffs))
                self.sundial_resources.cfg_cost(schedule_timestamps,
                                                system_tariff=self.tariffs)
                                                #tariffs = self.tariffs)


                ## generate a cost map - for testing
                #tiers = self.generate_cost_map()
                #_log.info(json.dumps(tiers))

                if SEARCH_LOADSHIFT_OPTIONS == True:
                    if self.loadshift_resources.state_vars["OptionsPending"] == 1:
                        _log.info("*** New Optimization Pass: New load options pending - Search Multiple!! ****")
                        self.optimizer.search_load_shift_options(self.sundial_resources,
                                                                 self.loadshift_resources,
                                                                 schedule_timestamps) # SSA optimization - search load shift space
                        self.send_loadshift_commands()
                    else:
                        _log.info("*** New Optimization Pass: No New load options pending! ****")
                        self.optimizer.search_single_option(self.sundial_resources,
                                                            schedule_timestamps)  # SSA optimization - single pass
                else:
                    _log.info("*** New Optimization Pass: Load Shift disabled! ****")
                    self.optimizer.search_single_option(self.sundial_resources,
                                                        schedule_timestamps)  # SSA optimization - single pass
                self.publish_schedules()
                self.send_ess_commands()

    ##############################################################################
    def publish_schedules(self):
        """
        publishes schedule data to the database
        :return: None
        """
        HistorianTools.publish_data(self,
                                    "SystemResource/Schedule",
                                    default_units["DemandForecast_kW"],
                                    "MaxDemand_kW",
                                    max(self.system_resources.schedule_vars["DemandForecast_kW"].tolist()))

        HistorianTools.publish_data(self,
                                    "SystemResource/Schedule",
                                    default_units["DemandForecast_kW"],
                                    "DemandForecast_kW",
                                    self.system_resources.schedule_vars["DemandForecast_kW"].tolist())
        HistorianTools.publish_data(self,
                                    "SystemResource/Schedule",
                                    default_units["DemandForecast_kW"],
                                    "DemandForecast_tPlus1_kW",
                                    self.system_resources.schedule_vars["DemandForecast_kW"][1],
                                    TimeStamp_str=self.system_resources.schedule_vars["timestamp"][1].strftime(
                                        "%Y-%m-%dT%H:%M:%S"))
        HistorianTools.publish_data(self,
                                    "SystemResource/Schedule",
                                    default_units["DemandForecast_kW"],
                                    "DemandForecast_tPlus5_kW",
                                    self.system_resources.schedule_vars["DemandForecast_kW"][5],
                                    TimeStamp_str=self.system_resources.schedule_vars["timestamp"][5].strftime(
                                        "%Y-%m-%dT%H:%M:%S"))
        HistorianTools.publish_data(self,
                                    "SystemResource/Schedule",
                                    default_units["DemandForecast_kW"],
                                    "DemandForecast_tPlus23_kW",
                                    self.system_resources.schedule_vars["DemandForecast_kW"][23],
                                    TimeStamp_str=self.system_resources.schedule_vars["timestamp"][23].strftime(
                                        "%Y-%m-%dT%H:%M:%S"))

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
                                    "ESSResource/Schedule",
                                    default_units["DemandForecast_kW"],
                                    "DemandForecast_tPlus1_kW",
                                    self.ess_resources.schedule_vars["DemandForecast_kW"][1],
                                    TimeStamp_str=self.ess_resources.schedule_vars["timestamp"][1].strftime(
                                        "%Y-%m-%dT%H:%M:%S"))
        HistorianTools.publish_data(self,
                                    "ESSResource/Schedule",
                                    default_units["DemandForecast_kW"],
                                    "DemandForecast_tPlus5_kW",
                                    self.ess_resources.schedule_vars["DemandForecast_kW"][5],
                                    TimeStamp_str=self.ess_resources.schedule_vars["timestamp"][5].strftime(
                                        "%Y-%m-%dT%H:%M:%S"))
        HistorianTools.publish_data(self,
                                    "ESSResource/Schedule",
                                    default_units["DemandForecast_kW"],
                                    "DemandForecast_tPlus23_kW",
                                    self.ess_resources.schedule_vars["DemandForecast_kW"][23],
                                    TimeStamp_str=self.ess_resources.schedule_vars["timestamp"][23].strftime(
                                        "%Y-%m-%dT%H:%M:%S"))
        HistorianTools.publish_data(self,
                                    "ESSResource/Schedule",
                                    default_units["EnergyAvailableForecast_kWh"],
                                    "EnergyAvailableForecast_tPlus1_kWh",
                                    self.ess_resources.schedule_vars["EnergyAvailableForecast_kWh"][1],
                                    TimeStamp_str=self.ess_resources.schedule_vars["timestamp"][1].strftime(
                                        "%Y-%m-%dT%H:%M:%S"))
        HistorianTools.publish_data(self,
                                    "ESSResource/Schedule",
                                    default_units["EnergyAvailableForecast_kWh"],
                                    "EnergyAvailableForecast_tPlus5_kWh",
                                    self.ess_resources.schedule_vars["EnergyAvailableForecast_kWh"][5],
                                    TimeStamp_str=self.ess_resources.schedule_vars["timestamp"][5].strftime(
                                        "%Y-%m-%dT%H:%M:%S"))
        HistorianTools.publish_data(self,
                                    "ESSResource/Schedule",
                                    default_units["EnergyAvailableForecast_kWh"],
                                    "EnergyAvailableForecast_tPlus23_kWh",
                                    self.ess_resources.schedule_vars["EnergyAvailableForecast_kWh"][23],
                                    TimeStamp_str=self.ess_resources.schedule_vars["timestamp"][23].strftime(
                                        "%Y-%m-%dT%H:%M:%S"))

        HistorianTools.publish_data(self,
                                    "PVResource/Schedule",
                                    default_units["DemandForecast_kW"],
                                    "DemandForecast_kW",
                                    self.pv_resources.schedule_vars["DemandForecast_kW"].tolist())

        HistorianTools.publish_data(self,
                                    "PVResource/Schedule",
                                    default_units["DemandForecast_kW"],
                                    "MaxDemand_kW",
                                    min(self.pv_resources.schedule_vars["DemandForecast_kW"].tolist()))

        HistorianTools.publish_data(self,
                                    "PVResource/Schedule",
                                    default_units["DemandForecast_kW"],
                                    "DemandForecast_tPlus1_kW",
                                    self.pv_resources.schedule_vars["DemandForecast_kW"][1],
                                    TimeStamp_str=self.pv_resources.schedule_vars["timestamp"][1].strftime(
                                        "%Y-%m-%dT%H:%M:%S"))
        HistorianTools.publish_data(self,
                                    "PVResource/Schedule",
                                    default_units["DemandForecast_kW"],
                                    "DemandForecast_tPlus5_kW",
                                    self.pv_resources.schedule_vars["DemandForecast_kW"][5],
                                    TimeStamp_str=self.pv_resources.schedule_vars["timestamp"][5].strftime(
                                        "%Y-%m-%dT%H:%M:%S"))
        HistorianTools.publish_data(self,
                                    "PVResource/Schedule",
                                    default_units["DemandForecast_kW"],
                                    "DemandForecast_tPlus23_kW",
                                    self.pv_resources.schedule_vars["DemandForecast_kW"][23],
                                    TimeStamp_str=self.pv_resources.schedule_vars["timestamp"][23].strftime(
                                        "%Y-%m-%dT%H:%M:%S"))
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
                                        default_units["DemandForecast_kW"],
                                        "MaxDemand_kW",
                                        max(self.load_resources.schedule_vars["DemandForecast_kW"].tolist()))

            HistorianTools.publish_data(self,
                                        "LoadResource/Schedule",
                                        default_units["DemandForecast_kW"],
                                        "DemandForecast_tPlus1_kW",
                                        self.load_resources.schedule_vars["DemandForecast_kW"][1],
                                        TimeStamp_str=self.load_resources.schedule_vars["timestamp"][1].strftime(
                                            "%Y-%m-%dT%H:%M:%S"))
            HistorianTools.publish_data(self,
                                        "LoadResource/Schedule",
                                        default_units["DemandForecast_kW"],
                                        "DemandForecast_tPlus5_kW",
                                        self.load_resources.schedule_vars["DemandForecast_kW"][5],
                                        TimeStamp_str=self.load_resources.schedule_vars["timestamp"][5].strftime(
                                            "%Y-%m-%dT%H:%M:%S"))
            HistorianTools.publish_data(self,
                                        "LoadResource/Schedule",
                                        default_units["DemandForecast_kW"],
                                        "DemandForecast_tPlus23_kW",
                                        self.load_resources.schedule_vars["DemandForecast_kW"][23],
                                        TimeStamp_str=self.load_resources.schedule_vars["timestamp"][23].strftime(
                                            "%Y-%m-%dT%H:%M:%S"))
            HistorianTools.publish_data(self,
                                        "LoadResource/Schedule",
                                        default_units["timestamp"],
                                        "timestamp",
                                        [t.strftime("%Y-%m-%dT%H:%M:%S") for t in
                                         self.load_resources.schedule_vars["timestamp"]])
        except:  # assume demand module is not implemented
            pass

        ii = self.find_current_timestamp_index()

        for obj_fcn in self.system_resources.obj_fcns:
            try:
                HistorianTools.publish_data(self,
                                            "System/Cost",
                                            "",
                                            obj_fcn.desc,
                                            self.system_resources.schedule_vars[obj_fcn.desc][ii])
            except:
                HistorianTools.publish_data(self,
                                            "System/Cost",
                                            "",
                                            obj_fcn.desc,
                                            self.system_resources.schedule_vars[obj_fcn.desc])



    ##############################################################################
    def publish_ess_cmds(self):
        """
        prints status to log file and to database
        :return:
        """

        _log.info("ExecutiveStatus: Mode = "+self.OperatingModes[self.OperatingMode])

        for k,v in self.optimizer_info.items():
            _log.info("ExecutiveStatus: " + k + "=" + str(v))
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

            if self.data_log_cnt == DATA_LOG_SCHEDULE:
                self.data_log_cnt = 1
                self.check_site_statuses()
            else:
                self.data_log_cnt += 1

            if ((self.update_endpt_cnt == ENDPT_UPDATE_SCHEDULE) or
                    (self.run_optimizer_cnt == GS_SCHEDULE) or
                    (self.send_ess_commands_cnt == ESS_SCHEDULE)):
                self.update_endpt_cnt = 1
                # update sundial_resources instance with the most recent data from end-point devices
                self.update_sundial_resources(self.sdr_to_sm_lookup_table)
            else:
                self.update_endpt_cnt += 1

            if self.send_ess_commands_cnt == ESS_SCHEDULE:
                self.send_ess_commands_cnt = 1
                self.send_ess_commands()
            else:
                self.send_ess_commands_cnt += 1

            if self.run_optimizer_cnt == GS_SCHEDULE:
                self.run_optimizer_cnt = 1
                self.run_optimizer()
            else:
                self.run_optimizer_cnt += 1


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
        mode_val = args[0]
        self.OperatingMode_set = int(mode_val)

        _log.info("SetPt: "+str(mode_val)+ " "+self.OperatingModes[self.OperatingMode_set]+"\n")

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


    @PubSub.subscribe('pubsub', "datalogger/isone/da_lmp/4332")
    def on_match(self, peer, sender, bus,  topic, headers, message):
        """Use match_all to receive all messages and print them out."""
        _log.info("FOUND A MATCH!!!")
        _log.info(
            "Peer: %r, Sender: %r:, Bus: %r, Topic: %r, Headers: %r, "
            "Message: \n%s", peer, sender, bus, topic, headers, pformat(message))
        # interpreted = json.loads(message)

        _log.info("INTERPRETED TYPE")
        data = message['LMP']['Readings']
        _log.info(type(data))
        _log.info(data)
        price_only = [pricetime[1] for pricetime in data]
        interpreted = numpy.array(price_only)
        _log.info(interpreted)
        _log.info(type(interpreted))
        self.tariffs['isone'] = interpreted
        # interpreted = np
        # print(interpreted['LMP']['Readings'])

def main(argv=sys.argv):
    '''Main method called by the eggsecutable.'''
    try:
        utils.vip_main(ExecutiveAgent)
    except Exception as e:
        _log.exception('unhandled exception')


if __name__ == '__main__':
    # Entry point for script
    sys.exit(main())
