from datetime import datetime, timedelta
import logging
import sys
import os
import csv
from volttron.platform.vip.agent import Agent, Core, PubSub, compat, RPC
from volttron.platform.agent import utils
from volttron.platform.messaging import headers as headers_mod

from gs_identities import (INTERACTIVE, AUTO, SITE_IDLE, SITE_RUNNING, PMC_WATCHDOG_RESET)

utils.setup_logging()
_log = logging.getLogger(__name__)
__version__ = '1.0'


##############################################################################
class DERDevice():
    POWERS = {
	-5: 0.00001,
        -4: 0.0001,
	-3: 0.001,
        -2: 0.01,
        -1: 0.1,
        0: 1,
        1: 10,
        2: 100,
        3: 1000,
	4: 10000,
	5: 100000

    }

    ##############################################################################
    def __init__(self, device_info, parent_device=None):

        self.DGDevice = ["PV", "ESS"]
        self.DGPlant = ["ESSCtrlNode", "PVCtrlNode", "LoadShiftCtrlNode"]

        # this stuff just happens for a "site"
        self.parent_device = parent_device

        if self.parent_device == None:
            self.device_id = device_info["ID"]
            self.device_type = "Site"
        else:
            self.device_id = self.parent_device.device_id + "-" + device_info["ID"]
            self.device_type = device_info["ResourceType"]
        self.devices = []
        self.set_nameplate()

        # some other stuff is just applicable for things within a site:
        # (1) for ALL devices you want to go through a list of devices and instantiate DERDevice objects
        # (2) DERDevice object names are formed by concatenating parents to the deviceID
        # (3) for site devices, you have something called


        for device in device_info["DeviceList"]:
            _log.info(device["ResourceType"] + " " + device["ID"])
            if device["ResourceType"] == 'ESS':
                self.devices.append(
                    ESSDevice(device, parent_device=self))
            elif device["ResourceType"] == 'PV':
                self.devices.append(
                    PVDevice(device, parent_device=self))
            elif (device["ResourceType"] in self.DGPlant):
                self.devices.append(
                    DERCtrlNode(device, parent_device=self))
            else:
                self.devices.append(
                    DERDevice(device, parent_device=self))
        self.init_attributes()
        self.pending_cmd = []

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
        _log.info("FindDevice: "+self.device_id)
        for cur_device in self.devices:
            _log.info("FindDevice: "+cur_device.device_id)
            if cur_device.device_id == device_id:
                return cur_device
            else:
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
            self.data_mapping_dict = {"GrpName": attribute_name}
            self.data_dict = {"GrpName": attribute_name}
            self.map_int_to_ext_endpt = {"GrpName": attribute_name}
            self.units = {"GrpName": attribute_name}
            self.topic_map = {"GrpName": attribute_name}
            self.endpt_units = {"GrpName": attribute_name}

            # initialize certain known key word values that are inherited between parent/children devices
            if attribute_name == "OpStatus":
                self.key_update_list = ["Pwr_kW", "FullChargeEnergy_kWh", "Energy_kWh", "MaxDischargePwr_kW",
                                        "MaxChargePwr_kW"]
                for key in self.key_update_list:
                    self.data_dict[key] = 0
            if attribute_name == "HealthStatus":
                self.data_dict["status"] = 1
                self.fail_state = {"status": 0}

        def update_fail_states(self, int_endpt, fail_state, grp_name):
            if grp_name == "HealthStatus":
                print("int endpt = " + int_endpt + " fail state = " + fail_state)
                self.fail_state.update({int_endpt: int(fail_state)})

    ##############################################################################
    def init_data_maps(self, device_id, group_id, int_endpt, ext_endpt, fail_state, units, topic_index):
        """
        This function traverses the device tree to find the object matching device_id,
        then initializes a data_mapping dictionary entry to be associated with that device
        """
        if self.device_id == device_id:
            #FIXME - what happens if a name is duplicated (esp between different devices/topics?)
            self.datagroup_dict_list[group_id].data_mapping_dict.update({ext_endpt: int_endpt})
            self.datagroup_dict_list[group_id].map_int_to_ext_endpt.update({int_endpt: ext_endpt})
            self.datagroup_dict_list[group_id].data_dict.update({int_endpt: 0})
            self.datagroup_dict_list[group_id].update_fail_states(int_endpt, fail_state, group_id)
            self.datagroup_dict_list[group_id].units.update({int_endpt: units})
            self.datagroup_dict_list[group_id].topic_map.update({int_endpt: topic_index})
            self.datagroup_dict.update({ext_endpt: self.datagroup_dict_list[group_id]})
            return self
        else:
            for cur_device in self.devices:
                child_device = cur_device.init_data_maps(device_id, group_id, int_endpt, ext_endpt, fail_state,
                                                         units, topic_index)
                if child_device != None:
                    return child_device

    ##############################################################################
    def display_device_tree(self):
        print(self.device_id + " " + str(self.nameplate))

        for key in self.datagroup_dict_list:
            datagroup = self.datagroup_dict_list[key]
            print("Device is: " + self.device_id + "; group name is: " + datagroup.data_mapping_dict["GrpName"])
            for vals in datagroup.data_mapping_dict:
                print(
                    "Device ID: " + self.device_id + ": Key = " + vals + " Val = " + datagroup.data_mapping_dict[
                        vals])

        for cur_device in self.devices:
            cur_device.display_device_tree()
        pass

    ##############################################################################
    def set_nameplate(self):
        self.nameplate = 0
        pass

    ##############################################################################
    def set_config(self):
        self.config.data_dict.update({"Nameplate_kW": 0})
        _log.info("SetConfig: Device ID = "+self.device_id+"; Nameplate is "+str(self.config.data_dict["Nameplate_kW"]))
        pass

    ##############################################################################
    def get_nameplate(self):
        return self.config.data_dict["Nameplate_kW"]


    ##############################################################################
    def update_op_status(self):
        """
        To do: how to handle non-opstatus devices?
        """

        # FIXME: this really needs to be thought through more carefully.
        #  this should be a routine that updates higherlevel endpts if they don't
        # get populated directly by an end point device by summing up the child-device
        # values....

        # temp fix - assume that end pt dg devices provide the values to be updated...
        if self.device_type not in self.DGDevice:
            for key in self.op_status.key_update_list:
                self.op_status.data_dict[key] = 0            
	
        for cur_device in self.devices:
            cur_device.update_op_status()            
            for key in self.op_status.key_update_list:
                self.op_status.data_dict[key] += int(cur_device.op_status.data_dict[key])

        # IF the current device is an actual generator (as opposed to a virtualized aggregation),
        # it should:
        #     convert to pwr = pwr_raw x sf
        #     if it's of type ess, it should ? populate energy?
        #     What about power available -- ? should be nameplate for PV
        #     should be charge power for ESS, discharge power for ESS
        #     import power available, export power available.

        # for now: do this in the very dumb brute force way, and then later, can fix it for
        # scalability

        #if self.device_type in self.DGDevice:
            # this device is an end point generator
            # FIXME: could automate the below / error trap the below in a number of ways
            # FIXME: SF should be referenced to a 10^SF power, not multiplication
        #    self.op_status.data_dict["Pwr_kW"] = int(self.op_status.data_dict["Pwr_raw"]) * self.POWERS[
        #        int(self.op_status.data_dict["Pwr_SF"])]

        _log.debug("OpStatus: device id is: " + self.device_id)
        for k, v in self.op_status.data_dict.items():
            _log.debug("OpStatus:" +k+": "+str(v))
        pass

    ##############################################################################
    def update_health_status(self):
        """
        Summarizes device health status by rolling up health_status end pts of children devices and
        the current device into a single summary.

        By convention, health_status for a device is defined as the logical AND of the overall_status
        of all children devices and the current device.  This is stored in the "status" value.

        First version is taking a very simple approach - just looking at binary values,
        compare to a "good state", and come up with a binary 0/1 status summary
        """

        # for each child device, set a key called "<childdevicename_status>" to the value of the child
	    # device's "status" entry.  Set the "fail state" for that key = to 0. (i.e., 0 indicates a fail mode)
        for cur_device in self.devices:
            cur_device.update_health_status()
            self.health_status.data_dict[cur_device.device_id + "_status"] = cur_device.health_status.data_dict[
                "status"]
            self.health_status.fail_state[cur_device.device_id + "_status"] = 0

        # Now the status of each child device is summarized in an "xxx_status" variable
	    # go through all of the current device's status keys to determine its summary status
        self.health_status.data_dict["status"] = 1
        for key in self.health_status.fail_state:
            val = 1
            if int(self.health_status.fail_state[key]) == 0:
                if int(self.health_status.data_dict[key]) == 0:
                    val = 0
            else:
                if int(self.health_status.data_dict[key]) > 0:
                    val = 0
            self.health_status.data_dict["status"] = self.health_status.data_dict["status"] and val
            # print(key+": "+str(self.health_status.data_dict[key])+"val = "+str(val))

        _log.debug("Device ID =" + self.device_id + "Health Status is: " + str(self.health_status.data_dict["status"]))

        pass

    ##############################################################################
    def update_mode_status(self):
        """
        Dummy fcn
        """
        for cur_device in self.devices:
            cur_device.update_mode_status()

        # print("device id is: " + self.device_id)
        # for k, v in self.mode_status.data_dict.items():
        #    print k, v

        pass
        
    ##############################################################################
    def convert_units_from_endpt(self, k, endpt_units):
        """
        Method for converting units between external end points and internal values.
        :return:
        """
        # if data map units don't match -->
        #  W to kW, kW to W, Wh to kWh, VA to kVA
        #  in general: (1) if units don't match... ; (2) if no units are included...

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
                _log.info("PopEndpts: converted "+k+"from "+endpt_units+
                          " to "+cur_attribute.units[keyval]+". New val = "+str(cur_attribute.data_dict[keyval]))
            else:
                cur_attribute.data_dict[keyval] /= 1000
                _log.info("PopEndpts: converted "+k+"from "+endpt_units+" to "+
                          cur_attribute.units[keyval]+". New val = "+str(cur_attribute.data_dict[keyval]))

        if (endpt_units == "ScaledW") and (cur_attribute.units[keyval] == "kW"):
            base_name = keyval[:len(keyval)-len("raw")] # assume this has "_raw" on the end of the name
            cur_attribute.data_dict[base_name+"kW"] = \
                (cur_attribute.data_dict[keyval]*10**cur_attribute.data_dict[base_name+"SF"])/1000
            _log.info("PopEndpts: converted "+k+"from "+endpt_units+" to "+
                      cur_attribute.units[keyval]+". New val = "+str(cur_attribute.data_dict[base_name+"kW"]))


        if (endpt_units == "Pct") and (cur_attribute.units[keyval] == "kW"):   # FIXME - make this PctkW?
            # #_log.info("converting pct to kW")
            nameplate = cur_device.get_nameplate()
            _log.info("val is "+str(nameplate))

            #if type(cur_attribute.data_dict[keyval]) is int:
	        #    cur_attribute.data_dict[keyval] = int((float(cur_attribute.data_dict[keyval]) / 100) * cur_device.get_nameplate())
            #elif type(cur_attribute.data_dict[keyval]) is float:
	        #	cur_attribute.data_dict[keyval] = float((float(cur_attribute.data_dict[keyval]) / 100) * cur_device.get_nameplate())
            if type(cur_attribute.data_dict[keyval]) is list:
                _log.info("converting list from pct to kW")
                # FIXME - ugh
                tmplist = [(float(v) / 100) * nameplate for v in cur_attribute.data_dict[keyval]]
                del cur_attribute.data_dict[keyval][:]
                cur_attribute.data_dict[keyval] = tmplist[:]
            else: # assume int
                _log.info("converting single pt from pct to kW")
                _log.info("value is "+str(cur_attribute.data_dict[keyval])+"; nameplate is "+str(nameplate))
                cur_attribute.data_dict[keyval] = int((float(cur_attribute.data_dict[keyval]) / 100) * nameplate)
                _log.info("new value is "+str(cur_attribute.data_dict[keyval]))
                #cur_attribute.data_dict[keyval] = int((float(cur_attribute.data_dict[keyval]) / 100) * cur_device.get_nameplate())
                #_log.info("Unsupported data type for conversion pct to kW")
	        _log.info("PopEndpts: converted "+k+"from "+endpt_units+" to "+cur_attribute.units[keyval]+". New val = "+str(cur_attribute.data_dict[keyval]))

    ##############################################################################
    def convert_units_to_endpt(self, attribute, cmd):

        ext_endpt = self.datagroup_dict_list[attribute].map_int_to_ext_endpt[cmd]
        try:
            _log.info("SetPt: Ext End pt is "+ext_endpt+". Ext units are "+
                      self.datagroup_dict_list[attribute].endpt_units[ext_endpt])
            _log.info("SetPt: Int End pt is "+cmd+".  Int units are "+
                      self.datagroup_dict_list[attribute].units[cmd])
            if (self.datagroup_dict_list[attribute].endpt_units[ext_endpt] == "Pct") and \
                    (self.datagroup_dict_list[attribute].units[cmd] == "kW"):   # FIXME - make this PctkW?
                self.datagroup_dict_list[attribute+"Cmd"].data_dict[cmd + "_cmd"] = \
                    int((float(self.datagroup_dict_list[attribute+"Cmd"].data_dict[cmd + "_cmd"]) /
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
                cur_attribute_name = cur_attribute.data_mapping_dict["GrpName"]
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
	    


        self.dirtyFlag = 0  # indicates that end points have finished updating.

        #self.update_op_status()
        #self.update_health_status()
        #self.update_mode_status()

    ##############################################################################
    #@RPC.export
    def set_point(self, attribute, cmd, sitemgr):
        """
        sets an arbitrary point to this device's command space.
        Reserves modbus, strips out "device from the data path, ...
        """
        #FIXME - this should either be a standalone method or it should be part of a "ModbusDevice Class"
        #FIXME - ID in the RPC call should be the VIP agent identity...

        device_prefix = "devices/"  # was /devices/
        task_id       = sitemgr.site.device_id #"ShirleySouth" #FIXME need to automatically query from sitemgr #"set_point"

        #TODO - make this generic - not tied to mode_ctrl
        #TODO - error trap to make sure that this value is writeable....
        _log.info("SetPt: Cmd - "+str(cmd)+"; attribute - "+str(attribute)+"; topic # = " + str(self.datagroup_dict_list[attribute].topic_map[cmd]))
        _log.info("SetPt: topic = "+sitemgr.topics[self.datagroup_dict_list[attribute].topic_map[cmd]]["TopicPath"])

        # indicates that a command has been sent to the target device, but target device has not
        # been re-read with updated values since the command was issued.
        self.dirtyFlag = 1

        device_topic = sitemgr.topics[self.datagroup_dict_list[attribute].topic_map[cmd]]["TopicPath"]
        if device_topic.startswith(device_prefix) == True:
            device_path = device_topic[len(device_prefix):]
            _log.info("SetPt: Device path: "+device_path)
            cmd_path = device_path+"/"+self.datagroup_dict_list[attribute].map_int_to_ext_endpt[cmd]
            _log.info("SetPt: Cmd Path: "+cmd_path)
            _log.info("SetPt: path is " + cmd_path + "; end pt = " + str(cmd) + "; val = " + str(self.datagroup_dict_list[attribute+"Cmd"].data_dict[cmd + "_cmd"]))
        else:
            _log.info("SetPt: Error in DERDevice.set_interactive_mode: device type invalid")

        #res = reserve_modbus(self, task_id, sitemgr, device_path)
	    res = 0
        #FIXME check for exceptions
        # convert units if necessary:
        self.convert_units_to_endpt(attribute, cmd)
        ret = sitemgr.vip.rpc.call(
            "platform.actuator",
            "set_point",
            "SiteManager",
            cmd_path,
            self.datagroup_dict_list[attribute+"Cmd"].data_dict[cmd + "_cmd"])

        #res = release_modbus(self, task_id, sitemgr)

        val = sitemgr.vip.rpc.call(
            "platform.actuator",
            "get_point",
            cmd_path).get()

        if val != self.datagroup_dict_list[attribute + "Cmd"].data_dict[cmd + "_cmd"]:
            # command wasn't written - raise an error
            _log.info("SetPt: SiteManager.set_point: Command "+str(cmd_path)+" not written. for "+self.device_id)
            _log.info("SetPt: Expected "+str(self.datagroup_dict_list[attribute+"Cmd"].data_dict[cmd + "_cmd"])+"; Read: "+str(val))


        self.pending_cmd.append({"Attribute": attribute, "Cmd": cmd})
        #return pending_cmd

    ##############################################################################
    def check_command(self):
        """
        checks that internal ("xxx_cmd") registers are the same as the corresponding
        end point register on the target device
        This is called after the target device has been scraped
        """
        # FIXME: this is not exactly right - if a third party controller writes a command, it
        # FIXME: will not be reflected in the internal _cmd register
        # an alternate approach would be to just check this for cmds that have been issued.

        cmd_failure = 0
        for cmd in self.pending_cmd:
            _log.info("In self.pending_cmd: Attribute = "+cmd["Attribute"])
            _log.info("Cmd = "+cmd["Cmd"])
            _log.info(self.datagroup_dict_list[cmd["Attribute"]].data_dict[cmd["Cmd"]])
            target_val = self.datagroup_dict_list[cmd["Attribute"]].data_dict[cmd["Cmd"]]
            commanded_val = self.datagroup_dict_list[cmd["Attribute"]+"Cmd"].data_dict[cmd["Cmd"]+"_cmd"]

            if  target_val != commanded_val:
                cmd_failure += 1

        for device in self.devices:
            cmd_failure += device.check_command()

    # TODO - not sure if this is the proper place to reset the pending_Cmd queue....
	#self.pending_cmd = []
        return cmd_failure

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
            attempt += 1

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
        self.dirtyFlag = 0
        #self.topics = site_info["Topics"]
        for topics in site_info["Topics"]: #self.topics:
            csv_name = (data_map_dir + self.device_id +"-"+ topics["TopicName"]+"-data-map.csv")
            _log.info(csv_name)

            try:
                with open(csv_name, 'rb') as csvfile:
                    data_map = csv.reader(csvfile)

                    for row in data_map:
                        _log.info("row[0] is " + row[0])
                        cur_device = self.init_data_maps(row[1], row[2], row[3], row[0], row[4], row[5], cnt)
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
        self.set_config()


    ##############################################################################
    def set_mode(self, cmd, val, sitemgr):
        pass

    ##############################################################################
    def check_mode(self):
        """
        checks that the mode set on the target device is synchronized with the target
        device's internal state.
        For example -- if target device has "XXXModeCtrl = 1", then the device's
        "XXXModeStatus" should also = 1
        This is called after the target device has been scraped
        """

        # FIXME: this routine should be generalized to check any arbitrary control
        # FIXME: register against its associated status register
        # FIXME: I think the way to do this would be to identify registers in the data
        # FIXME: map as control registers, and then to identify an associated status register
        # FIXME: so __init__ would build a table mapping control->status registers, and this
        # FIXME: routine would make sure that they match

        mode_failure = 0

        if self.mode_ctrl.data_dict["OpModeCtrl"] != self.mode_status.data_dict["OpModeStatus"]:
            mode_failure += 1
        if self.mode_ctrl.data_dict["SysModeCtrl"] != self.mode_status.data_dict["SysModeStatus"]:
            mode_failure += 1

        return mode_failure

    ##############################################################################
    def set_config(self):
        """
        traverses the site tree and sets configuration info
        """
        for cur_device in self.devices:
            cur_device.set_config()
        self.config.data_dict.update({"Nameplate_kW": 0})
        _log.info("SetConfig: Device ID = "+self.device_id+"; Nameplate is "+str(self.config.data_dict["Nameplate_kW"]))
        # TODO: should a site have a nameplate that represents aggregate of children CtrlNodes?
        pass

    ##############################################################################
    def get_nameplate(self):
        return self.config.data_dict["Nameplate_kW"]


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



##############################################################################
class DERModbusSite(DERSite):


    ##############################################################################
    #@RPC.export
    def set_interactive_mode(self, sitemgr):
        """
        Sets mode to interactive
        1. changes system op mode to "running"
        2. changes system ctrl mode to "interactive"
        """
        #TODO - does this need to set op mode -> wait for op mode -> then set sys ctrl mode?
        #TODO - for now assume they can be written simultaneously.  REVISIT!
        #TODO - also: when / how does the site go into SITE_IDLE mode?

        # set internal commands to new operating state:
        self.mode_ctrl_cmd.data_dict.update({"OpModeCtrl_cmd": SITE_RUNNING})
        self.mode_ctrl_cmd.data_dict.update({"SysModeCtrl_cmd": INTERACTIVE})

        self.set_point("ModeControl", "OpModeCtrl", sitemgr)
        self.set_point("ModeControl", "SysModeCtrl", sitemgr)


    ##############################################################################
    def set_auto_mode(self, sitemgr):
        """
        Sets mode to interactive
        2. changes system ctrl mode to "interactive"
        3. verifies that change has occurred
        """
        # TODO - does this need to set op mode -> wait for op mode -> then set sys ctrl mode?
        # TODO - for now assume they can be written simultaneously.  REVISIT!
        # TODO - also: when / how does the site go into SITE_IDLE mode?

        # set internal commands to new operating state:
        self.mode_ctrl_cmd.data_dict.update({"SysModeCtrl_cmd": AUTO})
        self.set_point("ModeControl", "SysModeCtrl", sitemgr)

    ##############################################################################
    #@core.periodic(10)
    def check_site_heartbeat(self):
        # function for making sure that heartbeat is incrementing within specified timeout period
        # this should get called at a set interval
        # it should make sure counter is incrementing
        # it should raise a warning if # of misses

        # read current heartbeat counter value
        # compare to previous heartbeat counter value (should be n+1)
        # if not n+1
        #  increment heartbeat_timeout_count (raise warning?)
        # increment total_heartbeat_errors --> just a variable for tracking if heartbeats miss frequently
        # if heartbeat_timeout_count * heartbeat_period >= heartbeat_timeout period
        #    raise heartbeat_timeout_error --> should trigger mode changes, etc in the executive
        #

        #todo -

        #if self.health_status.data_dict["heartbeat_counter"] - self.prev_heartbeat

        #self.prev_heartbeat = self.health_status.data_dict["heartbeat_counter"]

        #self.health_status.data_dict["total_heartbeat_errors"] = \
        #    self.health_status.data_dict["total_heartbeat_errors"]+1
        pass

    ##############################################################################
    #@core.periodic(PMC_WATCHDOG_PD)
    def send_watchdog(self, sitemgr):
        """
        increments the watchdog counter
        :return:
        """
        # TODO - review/test whether this should be incremented from the Watchdog_cmd or the Watchdog
        # TODO - end pt

        #TODO - figure out how to do an update / initialize correctly...
        self.mode_ctrl_cmd.data_dict["PMCWatchDog_cmd"] = self.mode_ctrl.data_dict["PMCWatchDog"]+1
        if self.mode_ctrl_cmd.data_dict["PMCWatchDog_cmd"] == PMC_WATCHDOG_RESET:
            self.mode_ctrl_cmd.data_dict["PMCWatchDog_cmd"] = 0
        self.set_point("ModeControl", "PMCWatchDog", sitemgr)


##############################################################################
class DERCtrlNode(DERDevice):

    ##############################################################################
    def set_config(self):
        self.config.data_dict.update({"Nameplate_kW": 0}) # FIXME - charge vs discharge?
        for device in self.devices:
            device.set_config()
        #FIXME - exception handle for no device
        self.config.data_dict["Nameplate_kW"] += device.get_nameplate()
        _log.info("SetConfig: Device ID = "+self.device_id+"; Nameplate is "+str(self.config.data_dict["Nameplate_kW"]))

    ##############################################################################
    def update_mode_status(self):
        """

        """
        # In general:
        # DERSite has OpCtrlMode and SysCtrlMode.  DERCtrlNodes should inherit these.
        # Devices have status - running / stopped / etc
        #
        for cur_device in self.devices:
            cur_device.update_mode_status()

        self.mode_status.data_dict["OpModeStatus"] = self.parent_device.mode_status.data_dict["OpModeStatus"]
        self.mode_status.data_dict["SysModeStatus"] = self.parent_device.mode_status.data_dict["SysModeStatus"]

        _log.info("device id is: " + self.device_id)
        for k, v in self.mode_status.data_dict.items():
            _log.info(k+": "+str(v))
        pass

    ##############################################################################
    def get_forecast_lowresolution(self):
        """
        Not sure this is needed!!!!
        Retrieves a time-series resource forecast for a specified location and stores
        in a data model associated with that location / resource.

        This forecast looks for topics under the /lowres category, and timing parameters etc
        under the _lowres identifier.

        For the current implementation, it is assumed that the forecast is published on a set
        schedule.  A future modification could change this model to have this function actually
        send an active request to query a forecast service.
        So The resource forecast is published on a topic specified in the xxx configuration
        file.  This function just subscribes to that topic and updates the associated data
        structure.

        FIXME: revisit this: should this function REQUEST a forecast
        or should the forecast be published synchronously?

        Format for forecasts:
            time_horizon_lowres -- indicates the expected time horizon of the forecast
            resolution_lowres -- indicates the expected time resolution of the forecast
            The forecast data structure is a time series of time - power_kWh pairs,
            with length = time_horizon x resolution
        """
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
        self.pwr_ctrl_cmd.data_dict.update({"SetPoint_cmd": int(val)})
        _log.info("Setting Power to "+str(val))
        self.set_point("RealPwrCtrl", "SetPoint", sitemgr)
        # where does the actual pwr ctrl live???

        pass

    ##############################################################################
    def set_power_reactive(self):
        pass



##############################################################################
class ESSCtrlNode(DERCtrlNode):
    pass

##############################################################################
class PVCtrlNode(DERCtrlNode):
    pass


##############################################################################
class ESSDevice(DERDevice):
    ##############################################################################
    def set_config(self):
        # For PV - configure manually.
        # FIXME: should be done through a config file, not hardcoded
        self.config.data_dict["Mfr"] = "Tesla"
        self.config.data_dict.update({"Nameplate_kW": 500}) # FIXME - charge vs discharge?
        _log.info("SetConfig: Device ID = "+self.device_id+"; Nameplate is "+str(self.config.data_dict["Nameplate_kW"]))
        _log.info("SetConfig: Mfr = "+self.config.data_dict["Mfr"])
        pass

    ##############################################################################
    def set_alarm_status(self):
        # for each device - populat a dictionary entry?
        # what I want to do is to read the registry file, and then populate dictionary entries.
        pass

    # def set_mode(self):
    #    pass

    ##############################################################################
    def set_nameplate(self):
        self.nameplate = {'pwr_chg_kw': 500, 'pwr_dis_kw': 500, 'energy': 1000}
        pass

    def get_nameplate(self):
        return self.config.data_dict["Nameplate_kW"]

##############################################################################
class PVDevice(DERDevice):
    ##############################################################################
    def set_config(self):
        # For PV - configure manually.
        # FIXME: should be done through a config file, not hardcoded
        self.config.data_dict["Mfr"] = "Solectria"
        self.config.data_dict.update({"Nameplate_kW": 500}) # FIXME - charge vs discharge?
        _log.info("SetConfig: Device ID = "+self.device_id+"; Nameplate is "+str(self.config.data_dict["Nameplate_kW"]))
        _log.info("SetConfig: Mfr = "+self.config.data_dict["Mfr"])
        pass

    def get_nameplate(self):
        return self.config.data_dict["Nameplate_kW"]

##############################################################################
class VirtualDERCtrlNode(DERCtrlNode):
    ##############################################################################
    def __init__(self, device_id="plant1", device_list=[]):
        _log.info("Device ID = " + str(device_id))

        self.device_id = device_id
        self.device_type = "DERCtrlNode"
        self.parent_device = None
        self.devices = device_list
        self.set_nameplate()
        self.DGDevice = ["PV", "ESS"]
        self.DGPlant = ["ESSCtrlNode", "PVCtrlNode", "LoadShiftCtrlNode"] #self.DGPlant = ["ESS_PLANT", "PV_PLANT"]
        _log.info("Initializing virtual plant....")
        self.init_attributes()

    def set_config(self):
        pass

    pass



##############################################################################
class Deprecated_DERDevice():
    """
    Obsolete Object model for defining a DER Device
    """

    ##############################################################################
    def __init__(self, device_id="site1", device_type="Site", parent_device=None):
        print("Device ID = " + str(device_id))
        print("Device Type = " + device_type)
        # print("Parent Device = "+parent_device)
        self.device_id = device_id
        self.device_type = device_type
        self.parent_device = parent_device
        self.devices = []
        self.set_nameplate()
        self.DGDevice = ["PV", "ESS"]
        self.DGPlant = ["ESS_PLANT", "PV_PLANT"]

        # First, build a logical model of the site - starting with the top-level
        # "site", and then building a tree of one or more child devices.
        # The device-list file naming convention and syntax is as follows:
        # filename = "fullDeviceNamePath-device-list.csv"
        # children devices are listed within the file as "UniqueDeviceID,device_type"
        # The site is built recursively, with each child device corresponding to a new
        # DERDevice instance
        csv_dir = "./data/"
        csv_name = (csv_dir + device_id + "-device-list.csv")
        print(csv_name)
        try:
            with open(csv_name, 'rb') as csvfile:
                self.device_list = csv.reader(csvfile)
                for row in self.device_list:
                    print(row[0] + " " + row[1])
                    if row[1] == 'ESS':
                        self.devices.append(
                            ESSDevice(device_id=(device_id + "-" + row[0]), device_type=row[1], parent_device=self))
                    elif (row[1] in self.DGPlant):
                        self.devices.append(
                            DERCtrlNode(device_id=(device_id + "-" + row[0]), device_type=row[1], parent_device=self))
                    else:
                        self.devices.append(
                            DERDevice(device_id=(device_id + "-" + row[0]), device_type=row[1], parent_device=self))
        except IOError as e:
            # file name not found implies that the device does not have any children
            print(device_id + " is a TERMINAL DEVICE")
            pass

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

        print("device is ..." + self.device_id)
        self.datagroup_dict_list = {}
        self.datagroup_dict_list.update({"Config": self.config})
        self.datagroup_dict_list.update({"OpStatus": self.op_status})
        self.datagroup_dict_list.update({"HealthStatus": self.health_status})
        self.datagroup_dict_list.update({"ModeStatus": self.mode_status})
        self.datagroup_dict_list.update({"ModeControl": self.mode_ctrl})
        self.datagroup_dict_list.update({"RealPwrCtrl": self.pwr_ctrl})


    ##############################################################################
    def populate_device(self):
        """
        This populates DERDevice variables based on a dummy topic message from a data file
        """
        self.lock = 1  # indicates that values are updating / need to wait

        pubsub_msg_fname = ("test-msg.csv")

        try:
            with open(pubsub_msg_fname, 'rb') as csvfile:
                incoming_msg = csv.reader(csvfile)
                for endpt in incoming_msg:
                    print(str(endpt[0]))
                    cur_device = self.extpt_to_device_dict[endpt[0]].device_id
                    cur_attribute = self.extpt_to_device_dict[endpt[0]].datagroup_dict[endpt[0]]
                    cur_attribute_name = cur_attribute.data_mapping_dict["GrpName"]
                    keyval = cur_attribute.data_mapping_dict[endpt[0]]
                    cur_attribute.data_dict[keyval] = endpt[1]
                    print("Keyval is " + cur_device + "." + cur_attribute_name + "." + keyval + "; value is " +
                          cur_attribute.data_dict[keyval])

                    # update_endpoint(endpt, self.vpt_to_datagroup_dict, self.vpt_to_device_endpoint_dict)
        except IOError as e:
            print("No Msg Found!")

        self.update_op_status()
        self.update_health_status()
        self.update_mode_status()
