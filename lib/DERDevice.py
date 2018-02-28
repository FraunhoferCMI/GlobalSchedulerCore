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




from datetime import datetime, timedelta
import logging
import sys
import os
import csv
import HistorianTools
from volttron.platform.vip.agent import Agent, Core, PubSub, compat, RPC
from volttron.platform.agent import utils
from volttron.platform.messaging import headers as headers_mod

from gs_identities import (INTERACTIVE, AUTO, SITE_IDLE, SITE_RUNNING, PMC_WATCHDOG_RESET, IGNORE_HEARTBEAT_ERRORS,
                           SSA_PTS_PER_SCHEDULE, USE_LABVIEW, MODBUS_PTS_PER_WINDOW, MODBUS_WRITE_ATTEMPTS)

utils.setup_logging()
_log = logging.getLogger(__name__)
__version__ = '1.0'


# SysModeReason Codes for Shirley RTAC
GS_REQ = 1
HMI_REQ = 2
LOSS_OF_COMMS = 3
PLANT_ALARMS = 4


default_units = {"CommStatus": "",
                 "DeviceStatus": "",
                 "ReadStatus": "",
                 "WriteStatus": "",
                 "ControlMode": "",
                 "Pwr_kW": "kW",
                 "AvgPwr_kW": "kW",
                 "DemandForecast_kW": "kW",
                 "Nameplate_kW": "kW",
                 "MaxSOE_kWh": "kWh",
                 "SOE_kWh": "kWh",
                 "MaxChargePwr_kW": "kW",
                 "MaxDischargePwr_kW": "kW",
                 "ChgEff": "",
                 "DischgEff": "",
                 "MinSOE_kWh": "kWh",
                 "SetPt": "kW",
                 "SetPtCmd": "Pct"}

ess_update_list = ["MaxSOE_kWh", "SOE_kWh", "MaxChargePwr_kW", "MaxDischargePwr_kW", "MinSOE_kWh",
                   "Nameplate_kW", "Pwr_kW", "AvgPwr_kW", "ChgEff", "DischgEff"]

device_update_list = ["Nameplate_kW", "Pwr_kW", "AvgPwr_kW"]

site_lookup = {"Shirley":"ShirleySite(site_info, None, data_map_dir)",
               "FLAME": "FLAMESite(site_info, None, data_map_dir)",
               "ModbusSite": "DERModbusSite(site_info, None, data_map_dir)",
               "Site": "DERSite(site_info, None, data_map_dir)"}


##############################################################################
def get_site_handle(site_info, data_map_dir):
    try:
        _log.info("Site instance is: "+site_lookup[site_info["SiteModel"]])
        site_handle =eval(site_lookup[site_info["SiteModel"]])
        return site_handle
    except KeyError:
        _log.info("Error - invalid Site Configuration! SiteModel = "+site_info["SiteModel"])
        return None
    pass

##############################################################################
class DERDevice():

    ##############################################################################
    def __init__(self, device_info, parent_device=None):

        self.DGPlant = ["ESSCtrlNode", "PVCtrlNode", "LoadShiftCtrlNode"]

        self.parent_device = parent_device
        if self.parent_device == None:
            self.device_id = device_info["ID"]
            self.device_type = "Site"
        else:
            self.device_id = self.parent_device.device_id + "-" + device_info["ID"]
            self.device_type = device_info["ResourceType"]
        self.devices = []
        self.metered = device_info["Metered"]

        _log.info("Initializing "+ self.device_id)

        # some other stuff is just applicable for things within a site:
        # (1) for ALL devices you want to go through a list of devices and instantiate DERDevice objects
        # (2) DERDevice object names are formed by concatenating parents to the deviceID
        # (3) for site devices, you have something called

        self.comms_status   = 0
        self.device_status  = 0
        self.read_status    = 0
        self.write_status   = 1
        self.control_mode   = 0
        self.isDataValid    = 0
        self.isControllable = 1    # FIXME: currently set all devices to controllable. this should be device-specific.
        self.isControlAvailable = 0

        for device in device_info["DeviceList"]:
            _log.info(device["ResourceType"] + " " + device["ID"])
            if device["ResourceType"] == 'ESS':
                self.devices.append(
                    ESSDevice(device, parent_device=self))
            elif device["ResourceType"] == 'Tesla':
                self.devices.append(
                    TeslaPowerPack(device, parent_device=self))
            elif device["ResourceType"] == 'Solectria':
                _log.info("SOLECTRICA INVERTER!!")
                self.devices.append(
                    SolectriaInverter(device, parent_device=self))
            elif device["ResourceType"] == 'PV':
                self.devices.append(
                    PVDevice(device, parent_device=self))
            elif (device["ResourceType"] == "ESSCtrlNode"):
                self.devices.append(
                    ESSCtrlNode(device, parent_device=self))
            elif (device["ResourceType"] == "PVCtrlNode"):
                self.devices.append(
                    PVCtrlNode(device, parent_device=self))
            elif (device["ResourceType"] in self.DGPlant):
                self.devices.append(
                    DERCtrlNode(device, parent_device=self))
            else:
                self.devices.append(
                    DERDevice(device, parent_device=self))
        self.init_attributes()

        # todo: think about if this should happen at end of site __init__
        self.state_vars = {"CommStatus": self.comms_status,
                           "DeviceStatus": self.device_status,
                           "ReadStatus": self.read_status,
                           "WriteStatus": self.write_status,
                           "ControlMode": self.control_mode,
                           "Pwr_kW": 0,
                           "AvgPwr_kW": 0,
                           "DemandForecast_kW": [0.0] * SSA_PTS_PER_SCHEDULE,
                           "Nameplate_kW": 0}

        self.avg_pwr_buffer = []

        # initialize data table for tracking pending commands
        self.chkReg = []
        self.chkRegAttributes = {}
        self.writeReg = {}
        self.writeRegAttributes = {}
        self.writePending = {}
        self.expectedValue = {}
        self.nTries = {}
        self.writeError = {}

        _log.info(self.device_id+" Init complete")

    ##############################################################################
    def init_attributes(self):
        # Several different dictionaries are created from the config file -
        # extpt_to_device_dict maps the modbus end point to a device within the current site
        # On __init__, each device is initialized with several DeviceAttribute objects (config,
        # op_status, health_status, etc).  A second dictionary (datagropu_dict) is created that
        # maps the "logical
        # group" column in the config file to the corresponding DeviceAttribute object
        # Each DeviceAttribute object then includes two different mapping dictionaries.  The first
        # (DeviceAttribute.data_mapping_dict) maps modbus endpoint to a key in the DeviceAttribute
        # namespace.  The second dictionary (DeviceAttribute.data_dict) maps the local key to actual
        # data payload.
        # In combination, these dictionaries are used to map incoming modbus values to logical end
        # points within site's data model.
        # An example "mapping chain" is as follows -
        # SiteEndPtDeviceObject = vpt_to_device["ModbusEndPt"]
        # SiteEndPtDataGroup    = ModbusEndPtDeviceObject.datagroup_dict["ModbusEndPt"]
        # SiteEndPtDataLabel    = ModbusEndPtDataGroup.data_mapping_dict["ModbusEndPt"]
        # SiteEndPtData         = ModbusEndPtDataGroup.data_mapping_dict["SiteEndPtDataLabel"]

        self.datagroup_dict = {}
        self.config = self.DeviceAttributes("Config")
        self.op_status = self.DeviceAttributes("OpStatus")
        self.health_status = self.DeviceAttributes("HealthStatus")
        self.mode_status = self.DeviceAttributes("ModeStatus")
        self.mode_ctrl = self.DeviceAttributes("ModeControl")
        self.pwr_ctrl = self.DeviceAttributes("RealPwrCtrl")
        self.forecast = self.DeviceAttributes("Forecast")
        self.mode_ctrl_cmd = self.DeviceAttributes("ModeControlCmd")
        self.pwr_ctrl_cmd = self.DeviceAttributes("RealPwrCtrlCmd")

        _log.info("device is ..." + self.device_id)
        self.datagroup_dict_list = {}
        self.datagroup_dict_list.update({"Config": self.config})
        self.datagroup_dict_list.update({"OpStatus": self.op_status})
        self.datagroup_dict_list.update({"HealthStatus": self.health_status})
        self.datagroup_dict_list.update({"ModeStatus": self.mode_status})
        self.datagroup_dict_list.update({"ModeControl": self.mode_ctrl})
        self.datagroup_dict_list.update({"RealPwrCtrl": self.pwr_ctrl})
        self.datagroup_dict_list.update({"Forecast": self.forecast})
        self.datagroup_dict_list.update({"ModeControlCmd": self.mode_ctrl_cmd})
        self.datagroup_dict_list.update({"RealPwrCtrlCmd": self.pwr_ctrl_cmd})

    ##############################################################################
    def find_device(self, device_id):
        """
        This function traverses the device tree to find the device object matching device_id and returns the object.
        """
        #FIXME - this functionality is duplicated elsewhere.  (E.g., in init_device fcns...)  Should reference
        #FIXME - against this method
        _log.debug("FindDevice: "+self.device_id)
        if self.device_id == device_id:
            return self
        else:
            for cur_device in self.devices:
                _log.debug("FindDevice: "+cur_device.device_id)
                child_device = cur_device.find_device(device_id)
                if child_device != None:
                    return child_device
            return None

    ##############################################################################
    class DeviceAttributes():
        """
        This is a class that constructs an "attribute" object for a device
        """
        def __init__(self, attribute_name):
            self.name = attribute_name
            self.data_mapping_dict = {}
            self.data_dict = {}
            self.map_int_to_ext_endpt = {}
            self.units = {}
            self.topic_map = {}
            self.endpt_units = {}

            # initialize certain known key word values that are inherited between parent/children devices
            if attribute_name == "HealthStatus":
                self.data_dict["status"] = 1
            if attribute_name == "ModeStatus":
                self.data_dict["GSHeartBeat"] = 0
                self.data_dict["GSHeartBeat_prev"] = 0 

    ##############################################################################
    def init_data_maps(self, device_id, group_id, int_endpt, ext_endpt, units, topic_index):
        """
        This function traverses the device tree to find the object matching device_id,
        then initializes a data_mapping dictionary entry to be associated with that device
        """
        if self.device_id == device_id:
            #FIXME - what happens if a name is duplicated (esp between different devices/topics?)
            self.datagroup_dict_list[group_id].data_mapping_dict.update({ext_endpt: int_endpt})
            self.datagroup_dict_list[group_id].map_int_to_ext_endpt.update({int_endpt: ext_endpt})
            self.datagroup_dict_list[group_id].data_dict.update({int_endpt: 0})
            self.datagroup_dict_list[group_id].units.update({int_endpt: units})
            self.datagroup_dict_list[group_id].topic_map.update({int_endpt: topic_index})
            self.datagroup_dict.update({ext_endpt: self.datagroup_dict_list[group_id]})
            return self
        else:
            for cur_device in self.devices:
                child_device = cur_device.init_data_maps(device_id, group_id, int_endpt, ext_endpt,
                                                         units, topic_index)
                if child_device != None:
                    return child_device

    ##############################################################################
    def display_device_tree(self):
        print(self.device_id + " " + str(self.nameplate))

        for key in self.datagroup_dict_list:
            datagroup = self.datagroup_dict_list[key]
            print("Device is: " + self.device_id + "; group name is: " + datagroup.name)
            for vals in datagroup.data_mapping_dict:
                print(
                    "Device ID: " + self.device_id + ": Key = " + vals + " Val = " + datagroup.data_mapping_dict[
                        vals])

        for cur_device in self.devices:
            cur_device.display_device_tree()
        pass

    ##############################################################################
    def get_nameplate(self):
        return self.state_vars["Nameplate_kW"]


    ##############################################################################
    def check_device_status(self):
        """
        generalized function for checking whether a device's self-reported
        stated is ok.  Device-specific versions of this method
        interpret error codes and raise exceptions as needed.
        sets self.device_status
        """
        pass


    ##############################################################################
    def check_comm_status(self):
        """
        generalized function for checking the communications status of a device.
        The current implementation simply checks the CommsStatus field associated
        with the parent device and the current device.
        Still to do - need to handle devices that have separate meters
        (which have their own comms status, but which are not represented as a discrete
        device in the site data model).
        :return:
        """
        if self.parent_device != None:
            self.comms_status = self.parent_device.comms_status
        try:
            if (self.health_status.data_dict["CommsStatus"] == 0):
                self.comms_status = 0
        except KeyError:
            pass
        pass

    ##############################################################################
    def check_mode(self):
        """
        Dummy fcn - this function only does something for DERCtrlNodes.  Otherwise it just
        traverses the site tree to find a DERCtrlNodes
        """
        self.control_mode = self.parent_device.control_mode
        pass

    ##############################################################################
    def set_read_status(self, topic_index, read_status):
        """
        called if a read error is found on a partiuclar topic
        """

        # FIXME - make this so it sets individually registers as invalid.
        # the current version just marks everything invalid.

        #for attribute in self.datagroup_dict_list:
        #    for k,v in attribute.topic_map.items():
        #        if topic_index == v:
        #            attribute.isValid[k] = 0
        #self.isDataValid = 0
        self.read_status = read_status

        if self.read_status == 0:
            self.isDataValid = 0
            self.isControlAvailable = 0
        for cur_device in self.devices:
            cur_device.set_read_status(topic_index, read_status)        

    ##############################################################################
    def print_site_status(self):
        #_log.debug("DERDevice Status: "+self.device_id)
        #_log.debug("DERDevice Status: isControllable="+str(self.isControllable)+"; isDataValid="+str(self.isDataValid)+"; isControlAvailable="+str(self.isControlAvailable))
        #_log.debug("DERDevice Status: comms="+str(self.comms_status)+"; device_status="+str(self.device_status)+"; control mode="+str(self.control_mode)+"; read_status="+str(self.read_status)+"; mode_mismatch="+str(self.mode_state_mismatch))

        #opstatus_str = ""
        #for key in self.op_status.key_update_list:
        #    opstatus_str += key+": "+str(self.op_status.data_dict[key])+"; "
        #_log.debug("DERDevice Status: Opstatus - "+opstatus_str)

        for k, v in self.state_vars.items():
            _log.info("Status-" + self.device_id + ": " + k + ": " + str(v))


        for cur_device in self.devices:
            cur_device.print_site_status()

    ##############################################################################
    def calc_avg_pwr(self, val):
        """
        maintains a circular buffer of length defined by MODBUS_PTS_PER_WINDOW
        and calculates the average power output over that time window
        TODO - Note - does not currently address missed readings.  Not sure if this matters.
        :param val: most recent power reading
        :return: average power over the last MODBUS_PTS_PER_WINDOW duration
        """
        if len(self.avg_pwr_buffer) < MODBUS_PTS_PER_WINDOW:
            # buffer is not fully populated (when process first starts), so
            # append values until buffer is fully populated
            self.avg_pwr_buffer.append(val)
        else:
            # buffer is fully populated, so treat as a circular buffer -
            # remove oldest value from the list
            self.avg_pwr_buffer.append(val)
            self.avg_pwr_buffer = self.avg_pwr_buffer[1:]

        return sum(self.avg_pwr_buffer) / float(len(self.avg_pwr_buffer))

    ##############################################################################
    def update_state_vars(self):
        """
        updates external holding registers

        what should this do now?
        this is the general version of this routine.

        it should just map state vars to universal ones.

        :return:
        """
        #_log.info("Update state_vars: "+self.device_id)
        self.state_vars.update({"CommStatus": self.comms_status,
                                "DeviceStatus": self.device_status,
                                "ReadStatus": self.read_status,
                                "WriteStatus": self.write_status,
                                "ControlMode": self.control_mode})

        #for k in self.state_vars_update_list:
        #    self.state_vars.update({k: self.op_status.data_dict[k]})

        try:
            self.state_vars.update({"Pwr_kW": self.op_status.data_dict["Pwr_kW"]})
            self.state_vars.update({"AvgPwr_kW": self.calc_avg_pwr(self.op_status.data_dict["Pwr_kW"])})
        except KeyError:
            pass

        try:
            self.state_vars.update({"DemandForecast_kW": self.forecast.data_dict["Pwr"]})
            # todo - add in time variable
        except KeyError:
            pass

        try:
            self.state_vars.update({"SetPt": self.pwr_ctrl.data_dict["SetPoint"],
                                    "SetPtCmd": self.pwr_ctrl_cmd.data_dict["SetPoint_cmd"]})
        except KeyError:
            pass


        #_log.info(self.device_id+": Statevars = "+str(self.state_vars))

        # todo: (1) reconsider how you handle forecasts (forecast object?)
        # todo: (2) reconsider treatment of ess-specific vars - more sophisticate about if / when defined?
        # todo: (3) set point - remove from inits?

        # todo: check if chg/dischg/minsoe get propagated.

    ##############################################################################
    def check_write_status(self):
        """

        :return:
        """
        self.write_status = 1
        for reg in self.chkReg:
            if self.writePending[reg] == 1:
                # there is a command pending - check to see if corresponding register has updated
                if self.writeRegAttributes[reg].data_dict[self.writeReg[reg]] == self.expectedValue[reg]:
                    # write completed successfully - clear all the write pending registers:
                    self.nTries[reg]       = 0
                    self.writePending[reg] = 0
                    self.writeError[reg]   = 0
                else:
                    # write has not completed successfully - increment nTries, check for if a timeout is triggered
                    self.nTries[reg] += 1
                    _log.info("Write missed for " + str(reg) + "- try # " + str(self.nTries[reg]) + "expected - "+str(self.expectedValue[reg])+
                              "; read "+str(self.writeRegAttributes[reg].data_dict[self.writeReg[reg]]))
                    if self.nTries[reg] >= MODBUS_WRITE_ATTEMPTS:
                        self.writeError[reg] = 1
                        self.write_status    = 0
                        _log.info("Timeout!!")

    ##############################################################################
    def update_status(self):
        """
        Called after populate end points has completed.  Traverses the site tree to do the following:
        (1) checks the latest modbus scrape to interpret the current status of the site and all its devices.  
            It checks for whether device end points have reported any errors, if communications between devices 
            are functioning, and the mode of devices
            - comms_status: tracks whether the device is communicating with upstream components
            - device_status: tracks whether the device has triggered any alarms
            - mode_status: tracks whether the device is in an interactive (GS control-enabled) state
            - mode_failure: FIXME - to do
 
        (2) propagates device properties up or down the device tree: 
            - op_status properties are propagated "upward" such that the power output and energy available from
              parent devices reflects the sum of associated children.  If device data is invalid (e.g., comms_status=0)
              then op_status data is zero-ed out.
            - device and comms status are propagated upward such that the parent knows whether to, e.g., trust data
              reported from children.
            - mode_status is propagated "downward" such that if control is disabled for the parent device, it will also
              be disabled for that device's children.
           
        (3) based on status indicators, determines whether:
            - data stored in the GS's device registers is valid ("isDataValid") - if 0, this indicates that the device is 
              offline, so data is stale
            - GS can control the device - if 0, this could indicate that it is set in a non GS-enabled mode, that the device
              is offline, that there is an error with the device, or that the device is not controllable.

        """

        # To start, assume that data is valid and control is available.  
        # then check for whether there is anything to indicate that this assumption is invalid
        self.isDataValid = 1
        self.isControlAvailable = self.isControllable

        self.comms_status = 1
        self.device_status = 1

        # update mode_status for this device before recursing down the site tree.
        # this lets us propagate this property to the children devices
        self.check_mode()
        # check for comms & device failures
        self.check_comm_status()
        self.check_device_status()

        self.check_write_status()

        # call this routine for each child:
        for cur_device in self.devices:
            cur_device.update_status()

        # FIXME: check reg_mismatch - (either check specific registers associated with a derDevice, or
        # make a descriptor that links ctrl --> status registers in the datamap file)
        # check meter mismatch - should happen inside the op_status routine?
        
        if self.comms_status == 0:
            # read data from a device is invalid
            self.isDataValid = 0
            self.isControlAvailable = 0
        if self.device_status == 0:
            # device status --> probably should be handled on a case-by-case basis.
            # for now, assume this only affects controllability.
            self.isControlAvailable = 0
        if self.read_status == 0:
            # indicates that communications with the site has timed out
            self.isDataValid = 0
            self.isControlAvailable = 0
        if self.control_mode == 0:
            self.isControlAvailable = 0

        # update registers for exporting to other agents
        self.update_state_vars()

        #_log.info("UpdateStatus: "+self.device_id+": data valid = "+str(self.isDataValid)+"; ControlAvailable = "+str(self.isControlAvailable))

    ##############################################################################
    def convert_units_from_endpt(self, k, endpt_units):
        """
        Method for converting units between external end points and internal values.
        Only a few conversions are implemented -
        - W to kW, Wh to kWh.
        - SunSpec scale factors
        - Pct to kW
        This is a bit kludgy but it works...
        :return:
        """

        cur_device = self.extpt_to_device_dict[k]
        cur_attribute = self.extpt_to_device_dict[k].datagroup_dict[k]
        keyval = cur_attribute.data_mapping_dict[k]

        if ((endpt_units == "W") and
                (cur_attribute.units[keyval] == "kW")) or\
                ((endpt_units == "Wh") and
                     (cur_attribute.units[keyval] == "kWh")):
            if type(cur_attribute.data_dict[keyval]) is list:
                # FIXME - ugh
                tmplist = [v/1000 for v in cur_attribute.data_dict[keyval]]
                del cur_attribute.data_dict[keyval][:]
                cur_attribute.data_dict[keyval] = tmplist[:]
                _log.debug("PopEndpts: converted "+k+"from "+endpt_units+
                          " to "+cur_attribute.units[keyval]+". New val = "+str(cur_attribute.data_dict[keyval]))
            else:
                cur_attribute.data_dict[keyval] /= 1000
                _log.debug("PopEndpts: converted "+k+"from "+endpt_units+" to "+
                          cur_attribute.units[keyval]+". New val = "+str(cur_attribute.data_dict[keyval]))

        if (endpt_units == "ScaledW") and (cur_attribute.units[keyval] == "kW"):
            base_name = keyval[:len(keyval)-len("raw")] # assume this has "_raw" on the end of the name
            cur_attribute.data_dict[base_name+"kW"] = \
                (cur_attribute.data_dict[keyval]*10**cur_attribute.data_dict[base_name+"SF"])/1000
            _log.debug("PopEndpts: converted "+k+"from "+endpt_units+" to "+
                      cur_attribute.units[keyval]+". New val = "+str(cur_attribute.data_dict[base_name+"kW"]))

        if (endpt_units == "NegScaledW") and (cur_attribute.units[keyval] == "kW"):
            base_name = keyval[:len(keyval)-len("raw")] # assume this has "_raw" on the end of the name
            cur_attribute.data_dict[base_name+"kW"] = \
                -1*(cur_attribute.data_dict[keyval]*10**cur_attribute.data_dict[base_name+"SF"])/1000
            _log.debug("PopEndpts: converted "+k+"from "+endpt_units+" to "+
                      cur_attribute.units[keyval]+". New val = "+str(cur_attribute.data_dict[base_name+"kW"]))

        if (endpt_units == "Pct") and (cur_attribute.units[keyval] == "kW"):   # FIXME - make this PctkW?
            # #_log.info("converting pct to kW")
            nameplate = cur_device.get_nameplate()
            _log.debug("val is "+str(nameplate))

            if type(cur_attribute.data_dict[keyval]) is list:
                _log.debug("converting list from pct to kW")
                # FIXME - ugh
                tmplist = [(float(v) / 100) * nameplate for v in cur_attribute.data_dict[keyval]]
                del cur_attribute.data_dict[keyval][:]
                cur_attribute.data_dict[keyval] = tmplist[:]
            else: # assume int
                _log.debug("converting single pt from pct to kW")
                _log.debug("value is "+str(cur_attribute.data_dict[keyval])+"; nameplate is "+str(nameplate))
                cur_attribute.data_dict[keyval] = int((float(cur_attribute.data_dict[keyval]) / 100) * nameplate)
                _log.debug("new value is "+str(cur_attribute.data_dict[keyval]))
                #cur_attribute.data_dict[keyval] = int((float(cur_attribute.data_dict[keyval]) / 100) * cur_device.get_nameplate())
                #_log.info("Unsupported data type for conversion pct to kW")
	        _log.debug("PopEndpts: converted "+k+"from "+endpt_units+" to "+cur_attribute.units[keyval]+". New val = "+str(cur_attribute.data_dict[keyval]))

        if (endpt_units == "NegPct") and (cur_attribute.units[keyval] == "kW"):  # FIXME - make this PctkW?
            # #_log.info("converting pct to kW")
            nameplate = cur_device.get_nameplate()
            _log.debug("val is " + str(nameplate))

            if type(cur_attribute.data_dict[keyval]) is list:
                _log.debug("converting list from neg pct to kW")
                # FIXME - ugh
                tmplist = [-1*(float(v) / 100) * nameplate for v in cur_attribute.data_dict[keyval]]
                del cur_attribute.data_dict[keyval][:]
                cur_attribute.data_dict[keyval] = tmplist[:]
            else:  # assume int
                _log.debug("converting single pt from pct to kW")
                _log.debug("value is " + str(cur_attribute.data_dict[keyval]) + "; nameplate is " + str(nameplate))
                cur_attribute.data_dict[keyval] = int(-1*(float(cur_attribute.data_dict[keyval]) / 100) * nameplate)
                _log.debug("new value is " + str(cur_attribute.data_dict[keyval]))
                # cur_attribute.data_dict[keyval] = int((float(cur_attribute.data_dict[keyval]) / 100) * cur_device.get_nameplate())
                # _log.info("Unsupported data type for conversion pct to kW")
            _log.debug("PopEndpts: converted " + k + "from " + endpt_units + " to " + cur_attribute.units[
                keyval] + ". New val = " + str(cur_attribute.data_dict[keyval]))

    ##############################################################################
    def convert_units_to_endpt(self, attribute, cmd):

        ext_endpt = self.datagroup_dict_list[attribute].map_int_to_ext_endpt[cmd]
        try:
            _log.debug("SetPt: Ext End pt is "+ext_endpt+". Ext units are "+
                      self.datagroup_dict_list[attribute].endpt_units[ext_endpt])
            _log.debug("SetPt: Int End pt is "+cmd+".  Int units are "+
                      self.datagroup_dict_list[attribute].units[cmd])
            if (self.datagroup_dict_list[attribute].endpt_units[ext_endpt] == "Pct") and \
                    (self.datagroup_dict_list[attribute].units[cmd] == "kW"):   # FIXME - make this PctkW?
                self.datagroup_dict_list[attribute+"Cmd"].data_dict[cmd + "_cmd"] = \
                    int((float(self.datagroup_dict_list[attribute+"Cmd"].data_dict[cmd + "_cmd"]) /
                         self.get_nameplate()) * 100)
            if (self.datagroup_dict_list[attribute].endpt_units[ext_endpt] == "NegPct") and \
                    (self.datagroup_dict_list[attribute].units[cmd] == "kW"):   # FIXME - make this PctkW?
                self.datagroup_dict_list[attribute+"Cmd"].data_dict[cmd + "_cmd"] = \
                    int(-1*(float(self.datagroup_dict_list[attribute+"Cmd"].data_dict[cmd + "_cmd"]) /
                         self.get_nameplate()) * 100)

            _log.info("SetPt: New val = "+str(self.datagroup_dict_list[attribute+"Cmd"].data_dict[cmd + "_cmd"]))

        except KeyError as e:
            _log.info("SetPt: No units found for "+ext_endpt+".  Assume no conversion is needed.")        


    ##############################################################################
    def populate_endpts(self, incoming_msg, meta_data = None):
        """
        This populates DERDevice variables based on the topic list
        """
        _log.info("PopEndpts: New scrape found")
        for k in incoming_msg:
            try:
                cur_device = self.extpt_to_device_dict[k].device_id
                cur_attribute = self.extpt_to_device_dict[k].datagroup_dict[k]
                cur_attribute_name = cur_attribute.name
                keyval = cur_attribute.data_mapping_dict[k]
                cur_attribute.data_dict[keyval] = incoming_msg[k]

                # TODO  correct for units!!!
                # if cur_attribute.units_dict[k] != incoming_msg[k] units then call convert_units....

                _log.debug("PopEndpts: "+cur_device + "." + cur_attribute_name + "." + keyval + "= " + str(
                    cur_attribute.data_dict[keyval]))

                if meta_data != None:
                    #_log.info("PopEndpts: Units - "+meta_data[k]["units"])
                    cur_attribute.endpt_units.update({k: meta_data[k]["units"]})
                else:
                    _log.info("PopEndpts: No Meta data found!")

            except KeyError as e:
                _log.info("Warning: Key "+k+" not found")
                pass

        for k in incoming_msg:
            try:
                self.convert_units_from_endpt(k, meta_data[k]["units"])
            except KeyError as e:
                _log.info("Skipping: Key "+k+" not found")
        self.update_status()

    ##############################################################################
    def write_cmd(self, attribute, pt, val, sitemgr):
        """
        writes an arbitrary point to the target location
        """
        cmd_pt = pt+"_cmd"
        cmd_attribute = attribute+"Cmd"
        #FIXME - right now, this is only writing int data types..
        self.datagroup_dict_list[cmd_attribute].data_dict.update({cmd_pt: int(val)})
        self.set_point(attribute, pt, sitemgr)

    ##############################################################################
    def set_point(self, attribute, cmd, sitemgr):
        """
        generalized routine for calling a set point

        can this be generalized?
        it would be an
            rpc call
            to an agent
            to a routine in that agent
            with a value?

        :param attribute:
        :param cmd:
        :param sitemgr:
        :return:
        """


        _log.info("Set Point: DERDevice instance - place holder!!!")
        #ret = sitemgr.vip.rpc.call(
        #    "platform.actuator",
        #    "set_point",
        #    "SiteManager",
        #    cmd_path,
        #    self.datagroup_dict_list[attribute + "Cmd"].data_dict[cmd + "_cmd"])


        pass

    ##############################################################################
    #@RPC.export
    def publish_device_data(self, SiteMgr):
        """
        This method publishes DERDevice data to a specific topic
        it traverses the site tree
        and for each var, it would write the site/attribute/value.     
        """

        device_path_str = self.device_id.replace('-', '/')
        for k, v in self.state_vars.items():
            # units for state_vars are defined in the default_units global dictionary
            # We may want to change this later to have device-specific unit definitions.
            # in particular - SetPtCmd is problematic.  Currently SetPtCmd units are defined by the end point device,
            # so it cannot be universally defined.  Another approach (which lets one keep using default_units) woudl be
            # to make the units of SetPtCmd internally defined and do the unit conversion subsequent to writing to the
            # SetPtCmd end point.
            units = default_units[k]

            HistorianTools.publish_data(SiteMgr,
                                        device_path_str,
                                        units,
                                        k,
                                        v)

        if (0):
            for attribute in self.datagroup_dict_list:
                for k,v in self.datagroup_dict_list[attribute].data_dict.items():
                    # 1. build the path:
                    # change "-" to "/" in the device_id:
                    device_path_str = self.device_id.replace('-', '/')+"/"+attribute

                    try:
                        units = self.datagroup_dict_list[attribute].units[k]
                    except KeyError:
                        units = ""

                    HistorianTools.publish_data(SiteMgr,
                                                device_path_str,
                                                units,
                                                k,
                                                v)

        # now recursively call for each child device:
        for cur_device in self.devices:
            cur_device.publish_device_data(SiteMgr)



##############################################################################
def reserve_modbus(device, task_id, sitemgr, device_path):
    #request_status = "FAILURE"
    #attempt        = 0

    # FIXME - this should (a) have some pause in between attempts; and (c) triage errors
    # what the failure reason is...
    # TODO - double check that topic path should include "devices"
    #while (request_status == "FAILURE") & (attempt<10):
    _log.info("Requesting to reserve modbus, requester: " + device.device_id + "; task " + task_id)
    start = datetime.now().strftime(
	    "%Y-%m-%d %H:%M:%S")
    end = (datetime.now() + timedelta(seconds=0.5)).strftime(
	    "%Y-%m-%d %H:%M:%S")

    try:
        res = sitemgr.vip.rpc.call(
            "platform.actuator",
            "request_new_schedule",
            device.device_id, task_id, "HIGH",
            [device_path, start, end]).get()

        request_status = res["result"]
        if request_status == "FAILURE":
            _log.info("Request failed, reason is " + res["info"])
            #attempt += 1

    except:
        #FIXME - error handling not done correctly!!!
        #_log.info("Request failed, reason is " + res["info"])
	_log.info("Request failed - agent not open")
        res = "FAILURE"
    return res

##############################################################################
def release_modbus(device, task_id, sitemgr):
    
    try:
        res = sitemgr.vip.rpc.call(
            "platform.actuator",
            "request_cancel_schedule",
            device.device_id, task_id).get()

        if res["result"] == "FAILURE":
            _log.info("Release Modbus: Request failed, reason is " + res["info"])
        return res
    except:
        #FIXME: error trapping not done correctly
        res = "FAILURE'"
        return res


##############################################################################
class DERSite(DERDevice):
    """
    Defines a DERSite object.
    """
    def __init__(self, site_info, parent_device, data_map_dir):
        """
        calls generic init for DERDevice class, then initializes a data map associated with the site based on an
        external data mapping file
        :param device_id: unique identifier for the device
        :param device_type: should always be site -- remove?.
        :param parent_device: should always none....
        """
        _log.info("Initializing a Site....")
        DERDevice.__init__(self, site_info, parent_device) #device_id, device_type, parent_device)
        # need to change how this is called.....
        #device_id = "site1", device_type = "Site", parent_device = None


        # Now that we have a logical model of the site, we map devices to real-world
        # end points (coming from, e.g., modbus scrape, api calls, etc)
        # Mapping is done in a file called "<SiteID>-<TopicName>-data-map.csv"
        # Open the config file that maps modbus end pts to device data dictionaries

        self.extpt_to_device_dict = {}
        cnt = 0
        #self.topics = site_info["Topics"]
        for topics in site_info["Topics"]: #self.topics:
            csv_name = (data_map_dir + self.device_id +"-"+ topics["TopicName"]+"-data-map.csv")
            _log.info(csv_name)

            try:
                with open(csv_name, 'rb') as csvfile:
                    data_map = csv.reader(csvfile)

                    for row in data_map:
                        _log.info("row[0] is " + row[0])
                        cur_device = self.init_data_maps(row[1], row[2], row[3], row[0], row[5], cnt)
                        if cur_device != None:
                            _log.info("cur_device id is "+cur_device.device_id)
                        else:
                            _log.info("no device?")
                        self.extpt_to_device_dict.update({row[0]: cur_device})
            except IOError as e:
                _log.info("data map file "+csv_name+" not found")
                pass
            cnt += 1

            for keyval in self.extpt_to_device_dict:
                _log.info("Key = " + keyval + ", Val = " + self.extpt_to_device_dict[keyval].device_id)

##############################################################################
class DERModbusDevice(DERDevice):

    ##############################################################################
    # @RPC.export
    def set_point(self, attribute, cmd, sitemgr):
        """
        sets an arbitrary point to this device's command space.
        Reserves modbus, strips out "device" from the data path (required by actuator/set_point),
        converts units from internal context to external context, and then issues an RPC call
        to actuator/set_point.
        Immediately reads the end point to ensure that the read was successfully completed.
        FIXME: Currently this method is explicitly for modbus devices.  There should be a generic version.
        This should get moved to a DERModbus Class.
        FIXME: Possibly need to include some latency / retry / or timeout period for the "check read" portion
        of this routine.  (i.e., in case there is some command latency...)
        """
        # FIXME - this should either be a standalone method or it should be part of a "ModbusDevice Class"
        # FIXME - ID in the RPC call should be the VIP agent identity...

        device_prefix = "devices/"  # was /devices/
        task_id = sitemgr.site.device_id  # "ShirleySouth" #FIXME need to automatically query from sitemgr #"set_point"

        # TODO - make this generic - not tied to mode_ctrl
        # TODO - error trap to make sure that this value is writeable....
        _log.debug("SetPt: Cmd - " + str(cmd) + "; attribute - " + str(attribute) + "; topic # = " + str(
            self.datagroup_dict_list[attribute].topic_map[cmd]))
        _log.debug("SetPt: topic = " + sitemgr.topics[self.datagroup_dict_list[attribute].topic_map[cmd]]["TopicPath"])

        device_topic = sitemgr.topics[self.datagroup_dict_list[attribute].topic_map[cmd]]["TopicPath"]
        if device_topic.startswith(device_prefix) == True:
            device_path = device_topic[len(device_prefix):]
            _log.debug("SetPt: Device path: " + device_path)
            cmd_path = device_path + "/" + self.datagroup_dict_list[attribute].map_int_to_ext_endpt[cmd]
            _log.debug("SetPt: Cmd Path: " + cmd_path)
            _log.debug("SetPt: path is " + cmd_path + "; end pt = " + str(cmd) + "; val = " + str(
                self.datagroup_dict_list[attribute + "Cmd"].data_dict[cmd + "_cmd"]))
            _log.debug("SetPt: Setting " + str(cmd) + "= " + str(
                self.datagroup_dict_list[attribute + "Cmd"].data_dict[cmd + "_cmd"]))


        else:
            _log.info("SetPt: Error in DERDevice.set_interactive_mode: device type invalid")

        # res = reserve_modbus(self, task_id, sitemgr, device_path)
        res = 0
        # FIXME check for exceptions
        # convert units if necessary:
        self.convert_units_to_endpt(attribute, cmd)
        ret = sitemgr.vip.rpc.call(
            "platform.actuator",
            "set_point",
            "SiteManager",
            cmd_path,
            self.datagroup_dict_list[attribute + "Cmd"].data_dict[cmd + "_cmd"])

        # res = release_modbus(self, task_id, sitemgr)

        val = sitemgr.vip.rpc.call(
            "platform.actuator",
            "get_point",
            cmd_path).get()

        if val != self.datagroup_dict_list[attribute + "Cmd"].data_dict[cmd + "_cmd"]:
            # command wasn't written - raise an error
            _log.info("SetPt: SiteManager.set_point: Command " + str(cmd_path) + " not written. for " + self.device_id)
            _log.info("SetPt: Expected " + str(
                self.datagroup_dict_list[attribute + "Cmd"].data_dict[cmd + "_cmd"]) + "; Read: " + str(val))

##############################################################################
class ShirleySite(DERSite, DERModbusDevice):

    ##############################################################################
    def __init__(self, site_info, parent_device, data_map_dir):
        DERSite.__init__(self, site_info, parent_device, data_map_dir)
        self.chkReg = ["SysModeStatus", "WatchDogTimeoutEnable"]
        self.chkRegAttributes = {"SysModeStatus": self.mode_status,
                                 "WatchDogTimeoutEnable": self.mode_ctrl}
        self.writeReg = {"SysModeStatus": "SysModeCtrl",
                         "WatchDogTimeoutEnable": "WatchDogTimeoutEnable"}
        self.writeRegAttributes = {"SysModeStatus": self.mode_ctrl,
                                   "WatchDogTimeoutEnable": self.mode_ctrl}
        self.writePending = {"SysModeStatus": 0,
                             "WatchDogTimeoutEnable": 0}
        self.expectedValue = {"SysModeStatus": 0,
                              "WatchDogTimeoutEnable": 0}
        self.nTries = {"SysModeStatus": 0,
                       "WatchDogTimeoutEnable": 0}
        self.writeError = {"SysModeStatus": 0,
                           "WatchDogTimeoutEnable": 0}




    ##############################################################################
    def check_device_status(self):
        # TODO - check for register mismatch (i.e., status != mode)
        # Maybe: check what the mode is...
        try:
            if (self.mode_ctrl.data_dict["SysModeCtrl"] != self.mode_status.data_dict["SysModeStatus"]):
            #FIXME - NEED to TEST!: will this need to see multiple fails to actually fail?
            #FIXME - not necessarily an error - ? could just mean that the HMI user changed?
                self.device_status = 0

        except KeyError:
            _log.info("Key Error")
            pass

    ##############################################################################
    #@RPC.export
    def set_interactive_mode(self, sitemgr):
        """
        Sets mode to interactive
        1. changes system op mode to "running"
        2. changes system ctrl mode to "interactive"
        """
        #TODO - also: when / how does the site go into SITE_IDLE mode?

        _log.info("Shirley Site!!!!!!")
        # set internal commands to new operating state:
        if USE_LABVIEW == 1:
            self.mode_ctrl_cmd.data_dict.update({"OpModeCtrl_cmd": SITE_RUNNING}) # deprecated
            self.set_point("ModeControl", "OpModeCtrl", sitemgr) # deprecated

        self.mode_ctrl_cmd.data_dict.update({"SysModeCtrl_cmd": INTERACTIVE})
        self.set_point("ModeControl", "SysModeCtrl", sitemgr)

        self.writePending["SysModeStatus"] = 1
        self.expectedValue["SysModeStatus"] = INTERACTIVE


    ##############################################################################
    def set_auto_mode(self, sitemgr):
        """
        Sets mode to interactive
        2. changes system ctrl mode to "interactive"
        3. verifies that change has occurred
        """
        # TODO - also: when / how does the site go into SITE_IDLE mode?

        # set internal commands to new operating state:
        self.mode_ctrl_cmd.data_dict.update({"SysModeCtrl_cmd": AUTO})
        self.set_point("ModeControl", "SysModeCtrl", sitemgr)

        self.writePending["SysModeStatus"] = 1
        self.expectedValue["SysModeStatus"] = AUTO



    ##############################################################################
    def check_site_heartbeat(self):
        """
        function for making sure that heartbeat is incrementing within specified timeout period
        This is called at the designated heartbeat interval.  It registers a comms error wtih the
        site if the heartbeat has not incremented.
        TODO - should a single miss trigger a timeout?
        """

        if IGNORE_HEARTBEAT_ERRORS == 0:
            if int(self.mode_status.data_dict["GSHeartBeat"]) != self.mode_status.data_dict["GSHeartBeat_prev"]+1:
                # heartbeat has not updated.  Indicates that the site controller may not be functioning properly.
                self.health_status.data_dict["CommsStatus"] = 0
                _log.info("Heartbeat Error: GS Heart Beat = "+str(self.mode_status.data_dict["GSHeartBeat"])+"; prev = "+str(self.mode_status.data_dict["GSHeartBeat_prev"]))
            else:
                self.health_status.data_dict["CommsStatus"] = 1
        else:
            self.health_status.data_dict["CommsStatus"] = 1
        self.mode_status.data_dict["GSHeartBeat_prev"] = int(self.mode_status.data_dict["GSHeartBeat"])


    ##############################################################################
    #@RPC.export
    def set_watchdog_timeout_enable(self, val, sitemgr):
        """
        Sets mode to interactive
        1. changes system op mode to "running"
        2. changes system ctrl mode to "interactive"
        """

        # set internal commands to new operating state:
        self.mode_ctrl_cmd.data_dict.update({"WatchDogTimeoutEnable_cmd": val})
        self.set_point("ModeControl", "WatchDogTimeoutEnable", sitemgr)
        self.writePending["WatchDogTimeoutEnable"] = 1
        self.expectedValue["WatchDogTimeoutEnable"] = val


    ##############################################################################
    def send_watchdog(self, sitemgr):
        """
        No longer needed in latest revision of spec!
        increments the watchdog counter
        :return:
        """
        # TODO - review/test whether this should be incremented from the Watchdog_cmd or the Watchdog
        # TODO - end pt

        _log.info("Shirley Site!!!!!!")
        #TODO - figure out how to do an update / initialize correctly...
        self.mode_ctrl_cmd.data_dict["PMCWatchDog_cmd"] = self.mode_ctrl.data_dict["PMCWatchDog"]+1
        if self.mode_ctrl_cmd.data_dict["PMCWatchDog_cmd"] == PMC_WATCHDOG_RESET:
            self.mode_ctrl_cmd.data_dict["PMCWatchDog_cmd"] = 0
        self.set_point("ModeControl", "PMCWatchDog", sitemgr)

    ##############################################################################
    def check_mode(self):
        """
        checks that the mode set on the target device is synchronized with the target
        device's internal state.
        For example -- if target device has "XXXModeCtrl = 1", then the device's
        "XXXModeStatus" should also = 1
        This is called after the target device has been scraped
        """


        if (((self.mode_status.data_dict["SysModeStatus"] == 0) and (self.control_mode == 1)) or
            ((self.mode_status.data_dict["SysModeStatus"] == 1) and (self.control_mode == 0))):
            # mode has changed since last time we polled the device - check reason for change
            # and act accordingly
            try:
                # todo - need to think this through a little bit better
                # todo - how do faults get cleared?
                if (self.mode_status.data_dict["SysModeReason"] == GS_REQ):
                    # command from GS
                    self.comms_status = 1 # clears any prior comm status faults
                    self.device_status = 1 # clears any prior plant alarm faults
                    pass
                if (self.mode_status.data_dict["SysModeReason"] == HMI_REQ):
                    # command from HMI user
                    self.comms_status = 1 # clears any prior comm status faults
                    self.device_status = 1 # clears any prior plant alarm faults
                    pass
                if (self.mode_status.data_dict["SysModeReason"] == LOSS_OF_COMMS):
                    # loss of communication
                    self.comms_status = 0
                    pass
                if (self.mode_status.data_dict["SysModeReason"] == PLANT_ALARMS):
                    # plant alarms
                    self.device_status = 0 #pass
            except:
                pass

        if self.mode_status.data_dict["SysModeStatus"] == 0:
            self.control_mode   = 0
        #elif self.mode_status.data_dict["OpModeStatus"] == 0:
        #    self.control_mode   = 0
        else:
            self.control_mode = 1


    ##############################################################################
    def set_point(self, attribute, cmd, sitemgr):
        DERModbusDevice.set_point(self,attribute, cmd, sitemgr)


##############################################################################
class DERCtrlNode(DERDevice):

    ##############################################################################
    def update_state_vars(self):
        """
        updates the external registers for DERCtrlNode instance by summing child devices
        :return:
        """
        DERDevice.update_state_vars(self)

        if "ChgEff" in self.state_vars_update_list:
            self.state_vars.update({"ChgEff": 1.0})
        if "DischgEff" in self.state_vars_update_list:
            self.state_vars.update({"DischgEff": 1.0})

        for k in self.state_vars_update_list:
            if (k=="ChgEff") or (k=="DischgEff"):
                self.state_vars.update({k: 1.0})
            else:
                self.state_vars.update({k: 0.0})

        chg_eff_cnt = 0
        dischg_eff_cnt = 0

        for device in self.devices:
            for k in self.state_vars_update_list:
                if (k=="ChgEff"):
                    chg_eff_cnt += device.state_vars["ChgEff"] * device.state_vars["MaxChargePwr_kW"]
                elif (k=="DischgEff"):
                    dischg_eff_cnt += device.state_vars["DischgEff"] * device.state_vars["MaxDischargePwr_kW"]
                else:
                    self.state_vars[k] += device.state_vars[k]

        if "ChgEff" in self.state_vars_update_list:
            self.state_vars["ChgEff"] = chg_eff_cnt / \
                                        self.state_vars["MaxChargePwr_kW"] if \
                (self.state_vars["MaxChargePwr_kW"] != 0) else 1
        if "DischgEff" in self.state_vars_update_list:
            self.state_vars["DischgEff"] = dischg_eff_cnt / \
                                           self.state_vars["MaxDischargePwr_kW"] if \
                (self.state_vars["MaxDischargePwr_kW"] != 0) else 1

    ##############################################################################
    def set_power_real(self, val, sitemgr):
        # 1. Enable
        # 2. Verify that it is enabled
        # 3. set the value
        # 4. set the trigger
        # 5. make sure that the value has propagated
        # 6. <optional> read output

        # This method has a number of issues -
        # TODO: Limit check
        self.pwr_ctrl_cmd.data_dict.update({"SetPoint_cmd": int(val)})
        _log.info("Setting Power to " + str(val))
        self.set_point("RealPwrCtrl", "SetPoint", sitemgr)
        # where does the actual pwr ctrl live???


##############################################################################
class DERModbusCtrlNode(DERModbusDevice, DERCtrlNode):

    ##############################################################################
    def set_ramprate_real(self, val, sitemgr):
        try:
            self.pwr_ctrl_cmd.data_dict.update({"RampRate_cmd": int(val)})
            _log.info("Setting ramp rate to "+str(val))
            self.set_point("RealPwrCtrl", "RampRate", sitemgr)
            self.writePending["RampRate"] = 1
            self.expectedValue["RampRate"] = int(val)
        except:
            pass


    ##############################################################################
    def set_power_real(self, val, sitemgr):
        # 1. Enable
        # 2. Verify that it is enabled
        # 3. set the value
        # 4. set the trigger
        # 5. make sure that the value has propagated
        # 6. <optional> read output

        # This method has a number of issues -
        #TODO: Limit check

        if USE_LABVIEW == 0:
            # implement a complete handshake process for writing a power command -
            try:
                self.pwr_ctrl_cmd.data_dict.update({"Enable": int(1)})
                _log.info("Enabling power control")
                self.set_point("RealPwrCtrl", "Enable", sitemgr)

                # make sure that the enable commmand has been written.

            except:
                pass

        self.pwr_ctrl_cmd.data_dict.update({"SetPoint_cmd": int(val)})
        _log.info("Setting Power to "+str(val))
        self.set_point("RealPwrCtrl", "SetPoint", sitemgr)

        self.writePending["SetPoint"] = 1
        self.expectedValue["SetPoint"] = int(val)

    ##############################################################################
    def set_power_reactive(self):
        pass



##############################################################################
class ESSCtrlNode(DERModbusCtrlNode):

    ##############################################################################
    def __init__(self, device_info, parent_device=None):
        DERDevice.__init__(self, device_info, parent_device)  # device_id, device_type, parent_device)
        self.state_vars.update({"SetPt": 0,
                                "SetPtCmd": 0})
        self.state_vars_update_list = ess_update_list

        self.chkReg = ["SetPoint", "RampRate"]
        self.chkRegAttributes = {"SetPoint": self.pwr_ctrl,
                                 "RampRate": self.pwr_ctrl}
        self.writeReg = {"SetPoint": "SetPoint",
                         "RampRate": "RampRate"}
        self.writeRegAttributes = {"SetPoint": self.pwr_ctrl,
                                   "RampRate": self.pwr_ctrl}
        self.writePending = {"SetPoint": 0,
                             "RampRate": 0}
        self.expectedValue = {"SetPoint": 0,
                             "RampRate": 0}
        self.nTries = {"SetPoint": 0,
                       "RampRate": 0}
        self.writeError = {"SetPoint": 0,
                           "RampRate": 0}

        _log.info("In ESSCtrlNode init - Device is:"+self.device_id)
        _log.info(str(self.state_vars_update_list))
        self.update_state_vars()

    ##############################################################################
    def update_state_vars(self):
        DERCtrlNode.update_state_vars(self)

##############################################################################
class PVCtrlNode(DERModbusCtrlNode):

    ##############################################################################
    def __init__(self, device_info, parent_device=None):
        DERDevice.__init__(self, device_info, parent_device)  # device_id, device_type, parent_device)

        self.state_vars.update({"SetPt": 0,
                                "SetPtCmd": 0})
        self.state_vars_update_list = device_update_list

        self.chkReg = ["SetPoint", "RampRate"]
        self.chkRegAttributes = {"SetPoint": self.pwr_ctrl,
                                 "RampRate": self.pwr_ctrl}
        self.writeReg = {"SetPoint": "SetPoint",
                         "RampRate": "RampRate"}
        self.writeRegAttributes = {"SetPoint": self.pwr_ctrl,
                                   "RampRate": self.pwr_ctrl}
        self.writePending = {"SetPoint": 0,
                             "RampRate": 0}
        self.expectedValue = {"SetPoint": 0,
                             "RampRate": 0}
        self.nTries = {"SetPoint": 0,
                       "RampRate": 0}
        self.writeError = {"SetPoint": 0,
                           "RampRate": 0}


        _log.info("Device is:"+self.device_id)
        _log.info(str(self.state_vars_update_list))
        self.update_state_vars()

        #self.state_vars.update({"Nameplate_kW": 0.0})

        #for device in self.devices:
        #    self.state_vars["Nameplate_kW"] += device.state_vars["Nameplate_kW"]

    ##############################################################################
    def update_state_vars(self):
        DERCtrlNode.update_state_vars(self)

##############################################################################
class ESSDevice(DERDevice):

    ##############################################################################
    def __init__(self, device_info, parent_device=None):

        DERDevice.__init__(self, device_info, parent_device) #device_id, device_type, parent_device)

        _log.info("Device info is ="+str(device_info))

        self.state_vars.update({"MaxSOE_kWh": float(device_info["max_soe"]) if("max_soe" in device_info) else 0.0,
                                "SOE_kWh": float(device_info["soe_init"]) if("soe_init" in device_info) else 0.0,
                                "MaxChargePwr_kW": float(device_info["max_chg_pwr"]) if("max_chg_pwr" in device_info) else 0.0,
                                "MaxDischargePwr_kW": float(device_info["max_dischg_pwr"]) if("max_dischg_pwr" in device_info) else 0.0,
                                "ChgEff": float(device_info["chg_eff"]) if("chg_eff" in device_info) else 1.0,
                                "DischgEff": float(device_info["dischg_eff"]) if("dischg_eff" in device_info) else 1.0,
                                "MinSOE_kWh": 0.0,
                                "Nameplate_kW": float(device_info["max_dischg_pwr"]) if("max_dischg_pwr" in device_info) else 0.0})
        _log.info("ESS Device init - state vars: "+str(self.state_vars))

##############################################################################
class PVDevice(DERDevice):

    ##############################################################################
    def __init__(self, device_info, parent_device=None):

        DERDevice.__init__(self, device_info, parent_device) #device_id, device_type, parent_device)
        self.state_vars.update({"Nameplate_kW": float(device_info["nameplate_rating_kW"]) if("nameplate_rating_kW" in device_info) else 0.0})

##############################################################################
class TeslaPowerPack(ESSDevice):

    ##############################################################################
    def update_state_vars(self):
        """
        updates external registers with ESS-specific fields
        :return:
        """
        DERDevice.update_state_vars(self)
        self.state_vars.update({"MaxSOE_kWh": self.op_status.data_dict["FullChargeEnergy_kWh"],
                                "SOE_kWh": self.op_status.data_dict["Energy_kWh"],
                                "MaxChargePwr_kW": self.op_status.data_dict["MaxChargePwr_kW"],
                                "MaxDischargePwr_kW": self.op_status.data_dict["MaxDischargePwr_kW"],
                                "Nameplate_kW": self.op_status.data_dict["MaxDischargePwr_kW"]})

    ##############################################################################
    def check_comm_status(self):

        """
        check the device's communications status
        :return:
        """
        if self.parent_device != None:
            self.comms_status = self.parent_device.comms_status

        try:
            if (self.health_status.data_dict["CommsStatus"] == 0):
                self.comms_status = 0
        except KeyError:
            pass

        try:
            if (self.health_status.data_dict["MeterCommsStatus"] == 0):
                self.comms_status = 0
        except KeyError:
            pass

        pass

    ##############################################################################
    def check_device_status(self):
        """
        checks the device's self-reported health status
        :return:
        """
        try:
            if ((self.health_status.data_dict["Alarm_Meter"] == 1) or
                    (self.health_status.data_dict["Alarm_MainBreaker"] == 1) or
                    (self.health_status.data_dict["Alarm_NumCommBlockFail"] != 0) or
                    (self.health_status.data_dict["Alarm_NumOpBlockFail"] != 0)):
                self.device_status = 0
        except KeyError:
            pass

        try:
            if (self.health_status.data_dict["MeterEvt"] == 1):
                self.device_status = 0
        except:
            pass

        pass


##############################################################################
class SolectriaInverter(PVDevice):

    ##############################################################################
    def check_comm_status(self):

        """
        check the device's communications status
        :return:
        """
        #if IGNORE_DEVICE_ERRORS == 0:
        if self.parent_device != None:
            self.comms_status = self.parent_device.comms_status

        try:
            if (self.health_status.data_dict["CommsStatus"] == 0):
                self.comms_status = 0
        except KeyError:
            pass

        try:
            if (self.health_status.data_dict["MeterCommsStatus"] == 0):
                self.comms_status = 0
        except KeyError:
            pass

        pass

    ##############################################################################
    def check_device_status(self):
        """
        checks the device's self-reported health status
        :return:
        """
        try:
            if ((self.health_status.data_dict["Alarms"] == 1) or
                    (self.health_status.data_dict["Warnings"] == 1)):
                # TODO: Add status - not sure what the data model is!!
                self.device_status = 0
        except KeyError:
            pass

        try:
            if (self.health_status.data_dict["MeterEvt"] == 1):
                self.device_status = 0
        except:
            pass

        pass