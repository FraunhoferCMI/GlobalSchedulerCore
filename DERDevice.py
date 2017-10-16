from datetime import datetime, timedelta
import logging
import sys
import os
import csv


##############################################################################
class DERDeviceOld():
    """
    Object model for defining a DER Device
    """

    POWERS = {
        -3: 0.001,
        -2: 0.01,
        -1: 0.1,
        0: 1,
        1: 10,
        2: 100,
        3: 1000

    }

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
                            DERPlant(device_id=(device_id + "-" + row[0]), device_type=row[1], parent_device=self))
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
    class DeviceAttributes():
        def __init__(self, grp_name):
            self.data_mapping_dict = {"GrpName": grp_name}
            self.data_dict = {"GrpName": grp_name}
            self.map_int_to_ext_endpt = {"GrpName": grp_name}
            self.units = {"GrpName": grp_name}

            # initialize certain known key word values that are inherited between parent/children devices
            if grp_name == "OpStatus":
                self.key_update_list = ["Pwr_kW", "FullChargeEnergy_kWh", "Energy_kWh", "PwrAvailableIn_kW",
                                        "PwrAvailableOut_kW"]
                for key in self.key_update_list:
                    self.data_dict[key] = 0
            if grp_name == "HealthStatus":
                self.data_dict["status"] = 1
                self.fail_state = {"status": 0}

        def update_fail_states(self, int_endpt, fail_state, grp_name):
            if grp_name == "HealthStatus":
                print("int endpt = " + int_endpt + " fail state = " + fail_state)
                self.fail_state.update({int_endpt: int(fail_state)})

        def convert_units(self):
            # if data map units don't match -->
            # W to kW, kW to W, Wh to kWh, VA to kVA
            # in general: (1) if units don't match... ; (2) if no units are included...
            pass

    ##############################################################################
    def init_data_maps(self, device_id, group_id, int_endpt, ext_endpt, fail_state, units):
        """
        This function traverses the device tree to find the object matching device_id,
        then initializes a data_mapping dictionary entry to be associated with that device
        """
        if self.device_id == device_id:
            self.datagroup_dict_list[group_id].data_mapping_dict.update({ext_endpt: int_endpt})
            self.datagroup_dict_list[group_id].map_int_to_ext_endpt.update({int_endpt: ext_endpt})
            self.datagroup_dict_list[group_id].data_dict.update({int_endpt: 0})
            self.datagroup_dict_list[group_id].update_fail_states(int_endpt, fail_state, group_id)
            self.datagroup_dict_list[group_id].units.update({int_endpt: units})
            self.datagroup_dict.update({ext_endpt: self.datagroup_dict_list[group_id]})
            return self
        else:
            for cur_device in self.devices:
                child_device = cur_device.init_data_maps(device_id, group_id, int_endpt, ext_endpt, fail_state, units)
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
                "Device ID: " + self.device_id + ": Key = " + vals + " Val = " + datagroup.data_mapping_dict[vals])

        for cur_device in self.devices:
            cur_device.display_device_tree()
        pass

    def set_nameplate(self):
        self.nameplate = 0
        pass

    def reserve_modbus(self):
        start = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S")
        end = (datetime.now() + timedelta(seconds=5)).strftime(
            "%Y-%m-%d %H:%M:%S")
        return self.vip.rpc.call(
            "platform.actuator",
            "request_new_schedule",
            "", "SiteManager" + self.PATH, "HIGH",
            [self.PATH, start, end]).get()

    def release_modbus(self):
        return self.vip.rpc.call(
            "platform.actuator",
            "request_cancel_schedule",
            "curtail", "SiteManager" + self.PATH).get()

    def set_config(self):
        pass

    def update_config(self):
        pass

    ##############################################################################
    def update_op_status(self):
        """
        To do: how to handle non-opstatus devices?
        """
        for cur_device in self.devices:
            cur_device.update_op_status()
            for key in self.op_status.key_update_list:
                self.op_status.data_dict[key] += int(cur_device.op_status.data_dict[key])
            pass

        # IF the current device is an actual generator (as opposed to a virtualized aggregation),
        # it should:
        #     convert to pwr = pwr_raw x sf
        #     if it's of type ess, it should ? populate energy?
        #     What about power available -- ? should be nameplate for PV
        #     should be charge power for ESS, discharge power for ESS
        #     import power available, export power available.

        # for now: do this in the very dumb brute force way, and then later, can fix it for
        # scalability

        if self.device_type in self.DGDevice:
            # this device is an end point generator
            # FIXME: could automate the below / error trap the below in a number of ways
            # FIXME: SF should be referenced to a 10^SF power, not multiplication
            self.op_status.data_dict["Pwr_kW"] = int(self.op_status.data_dict["Pwr_raw"]) * self.POWERS[
                int(self.op_status.data_dict["Pwr_SF"])]

        print("device id is: " + self.device_id)
        for k, v in self.op_status.data_dict.items():
            print k, v
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

        for cur_device in self.devices:
            cur_device.update_health_status()
            self.health_status.data_dict[cur_device.device_id + "_status"] = cur_device.health_status.data_dict[
                "status"]
            self.health_status.fail_state[cur_device.device_id + "_status"] = 0

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

        print("Device ID =" + self.device_id + "Health Status is: " + str(self.health_status.data_dict["status"]))

        pass

    def update_mode_status(self):
        """
        Dummy fcn
        """
        for cur_device in self.devices:
            cur_device.update_mode_status()

        print("device id is: " + self.device_id)
        for k, v in self.mode_status.data_dict.items():
            print k, v

        pass

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

    ##############################################################################
    def populate_endpts(self, incoming_msg):
        """
        This populates DERDevice variables based on the topic list
        """
        self.lock = 1  # indicates that values are updating / need to wait

        for k in incoming_msg:
            try:
                cur_device = self.extpt_to_device_dict[k].device_id
                cur_attribute = self.extpt_to_device_dict[k].datagroup_dict[k]
                cur_attribute_name = cur_attribute.data_mapping_dict["GrpName"]
                keyval = cur_attribute.data_mapping_dict[k]
                cur_attribute.data_dict[keyval] = incoming_msg[k]

                # Todo!!  correct for units!!!
                # if cur_attribute.units_dict[k] != incoming_msg[k] units then call convert_units....

                print("Keyval is " + cur_device + "." + cur_attribute_name + "." + keyval + "; value is " + str(
                    cur_attribute.data_dict[keyval]))
            except KeyError as e:
                # print("Warning: Key "+k+" not found")
                pass

        self.update_op_status()
        self.update_health_status()
        self.update_mode_status()

##############################################################################
class DERDevice(DERDeviceOld):

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
            print(device["ResourceType"] + " " + device["ID"])
            if device["ResourceType"] == 'ESS':
                self.devices.append(
                    ESSDevice(device, parent_device=self))
            elif (device["ResourceType"] in self.DGPlant):
                self.devices.append(
                    DERPlant(device, parent_device=self))
            else:
                self.devices.append(
                    DERDevice(device, parent_device=self))
        # except IOError as e:
        # file name not found implies that the device does not have any children
        # print(device_id + " is a TERMINAL DEVICE")
        # pass

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
class ESSDevice(DERDevice):
    def __init__(self, device_info, parent_device=None):
        #device_id = "site1", device_type = "Site", parent_device = None):
        #DERDevice.__init__(self, device_id, device_type, parent_device)
        DERDevice.__init__(self, device_info, parent_device)
        # self.set_nameplate
        pass

    def set_config(self):
        # For ESS - most config data is stored / transmitted from the device
        pass

    def set_alaram_status(self):
        # for each device - populat a dictionary entry?
        # what I want to do is to read the registry file, and then populate dictionary entries.
        pass

    # def set_mode(self):
    #    pass

    def set_nameplate(self):
        self.nameplate = {'pwr_chg_kw': 500, 'pwr_dis_kw': 500, 'energy': 1000}

    def set_power_real(self):
        # 1. Enable
        # 2. Verify that it is enabled
        # 3. set the value
        # 4. set the trigger
        # 5. make sure that the value has propagated
        # 6. <optional> read output

        pass

    def set_power_reactive(self):
        pass


##############################################################################
class DERSite(DERDevice):
    def __init__(self, site_info, parent_device):
        """
        calls generic init for DERDevice class, then initializes a data map associated with the site based on an
        external data mapping file
        :param device_id: unique identifier for the device
        :param device_type: should always be site -- remove?.
        :param parent_device: should always none....
        """
        DERDevice.__init__(self, site_info, parent_device) #device_id, device_type, parent_device)
        # need to change how this is called.....
        #device_id = "site1", device_type = "Site", parent_device = None


        # Now that we have a logical model of the site, we map devices to real-world
        # end points (coming from, e.g., modbus scrape, api calls, etc)
        # Mapping is done in a file called "<sitename>-data-map.csv"
        # Open the config file that maps modbus end pts to device data dictionaries
        # FIXME - site should probably be its own separate class.
        csv_dir = "./data/"
        csv_name = (csv_dir + self.device_id + "-data-map.csv")
        print(csv_name)
        self.extpt_to_device_dict = {}

        try:
            with open(csv_name, 'rb') as csvfile:
                data_map = csv.reader(csvfile)

                for row in data_map:
                    print ("row[0] is " + row[0])
                    cur_device = self.init_data_maps(row[1], row[2], row[3], row[0], row[4], row[5])
                    self.extpt_to_device_dict.update({row[0]: cur_device})
        except IOError as e:
            print("data map file not found")
            pass

        for keyval in self.extpt_to_device_dict:
            print("Key = " + keyval)
            print("Key = " + keyval + ", Val = " + self.extpt_to_device_dict[keyval].device_id)

    ##############################################################################
    #@RPC.export
    def set_mode(self, cmd, val, sitemgr):
        """
        calls the mode command "cmd" associated with device
        this is the most generic command to actualy actaute something.
        """
        # self.reserve_modbus()
        device_path = sitemgr.path + self.mode_ctrl.map_int_to_ext_endpt[cmd]
        print("device path is " + device_path + "; cmd = " + str(cmd) + "; val = " + str(val))
        ret = sitemgr.vip.rpc.call(
            "platform.actuator",
            "set_point",
            "SiteManager",
            device_path,
            val)
        # self.release_modbus()
        pass

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


        pass

    #@core.periodic(10)
    def send_watchdog(self):
        """
        increments the watchdog counter
        :return:
        """
        # lock modbus
        # increment internal watchdog counter
        # write modbus command
        # unlock modbus
        pass


##############################################################################
class DERPlant(DERDevice):
    ##############################################################################
    def update_mode_status(self):
        """

        """
        # In general:
        # Site has OpCtrlMode and SysCtrlMode.  PV Plant & ESS should inherit these.
        # Devices have status - running / stopped / etc
        #
        for cur_device in self.devices:
            cur_device.update_mode_status()

        self.mode_status.data_dict["OpModeStatus"] = self.parent_device.mode_status.data_dict["OpModeStatus"]
        self.mode_status.data_dict["SysModeStatus"] = self.parent_device.mode_status.data_dict["SysModeStatus"]

        print("device id is: " + self.device_id)
        for k, v in self.mode_status.data_dict.items():
            print k, v
        pass

    ##############################################################################
    def get_forecast_lowresolution(self):
        """
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


class ESSPlant(DERDevice):
    pass


class PVPlant(DERDevice):
    pass


class PVDevice(DERDevice):
    def set_config(self):
        # For PV - configure manually.
        # FIXME: should be done through a config file, not hardcoded
        self.data_dict["Pwr_kW"] = 500
        self.data_dict["Mfr"] = "Solectria"
        pass


class VirtualDERPlant(DERPlant):
    ##############################################################################
    def __init__(self, device_id="plant1", device_list=[]):
        print("Device ID = " + str(device_id))

        self.device_id = device_id
        self.device_type = "DERPlant"
        self.parent_device = None
        self.devices = device_list
        self.set_nameplate()
        self.DGDevice = ["PV", "ESS"]
        self.DGPlant = ["ESSCtrlNode", "PVCtrlNode", "LoadShiftCtrlNode"] #self.DGPlant = ["ESS_PLANT", "PV_PLANT"]

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


    pass