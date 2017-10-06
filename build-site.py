

import sys
import csv


class DERSite():

    def __init_(self):

        pass

##############################################################################
class DERDevice():
    """
    Object model for defining a DER Device
    """

    ##############################################################################
    def __init__(self, device_id="site1", device_type="Site", parent_device=None):
        print("Device ID = "+str(device_id))
        print("Device Type = "+device_type)
	#print("Parent Device = "+parent_device)
        self.device_id     = device_id
        self.device_type   = device_type
        self.parent_device = parent_device
        self.devices       = []
        self.set_nameplate()
        self.DGDevice      = ["PV", "ESS"]
        self.DGPlant       = ["ESS_PLANT", "PV_PLANT"]

        # First, build a logical model of the site - starting with the top-level
        # "site", and then building a tree of one or more child devices.
        # The device-list file naming convention and syntax is as follows:
        # filename = "fullDeviceNamePath-device-list.csv"
        # children devices are listed within the file as "UniqueDeviceID,device_type"
        # The site is built recursively, with each child device corresponding to a new
        # DERDevice instance
        csv_dir  = "./data/"
        csv_name = (csv_dir + device_id + "-device-list.csv")
        print(csv_name)
        try: 
            with open(csv_name, 'rb') as csvfile:
                self.device_list = csv.reader(csvfile)
                for row in self.device_list: 
                    print(row[0]+" "+row[1])
                    if row[1] == 'ESS':                        
                        self.devices.append(ESSDevice(device_id=(device_id+"-"+row[0]), device_type=row[1], parent_device=self))
                    elif (row[1] in self.DGPlant):
                        self.devices.append(DERPlant(device_id=(device_id+"-"+row[0]), device_type=row[1], parent_device=self))             
                    else:
                        self.devices.append(DERDevice(device_id=(device_id+"-"+row[0]), device_type=row[1], parent_device=self))                    
        except IOError as e:
            # file name not found implies that the device does not have any children
            print(device_id + " is a TERMINAL DEVICE")
            pass
              

        # Now that we have a logical model of the site, we map devices to real-world
        # end points (coming from, e.g., modbus scrape, api calls, etc)
        # Mapping is done in a file called "<sitename>-data-map.csv"
        # Open the config file that maps modbus end pts to device data dictionaries
        # only does this for the site!!!
        # FIXME - site should probably be its own separate class.

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


        

        self.datagroup_dict          = {}
        self.config        = self.DeviceAttributes("Config")
        self.op_status     = self.DeviceAttributes("OpStatus")
        self.health_status = self.DeviceAttributes("HealthStatus")
        self.mode_status   = self.DeviceAttributes("ModeStatus")
        self.mode_ctrl     = self.DeviceAttributes("ModeControl")
        self.pwr_ctrl      = self.DeviceAttributes("RealPwrCtrl")
     

        print("device is ..."+self.device_id)
        self.datagroup_dict_list = {}
        self.datagroup_dict_list.update({"Config":self.config})
        self.datagroup_dict_list.update({"OpStatus":self.op_status})
        self.datagroup_dict_list.update({"HealthStatus":self.health_status})
        self.datagroup_dict_list.update({"ModeStatus":self.mode_status})
        self.datagroup_dict_list.update({"ModeControl":self.mode_ctrl})
        self.datagroup_dict_list.update({"RealPwrCtrl":self.pwr_ctrl})


        if parent_device == None:     # data map file exists only for the site-level parent
            csv_name = (csv_dir+device_id + "-data-map.csv")
            print(csv_name)
            self.extpt_to_device_dict = {}

            try: 
                with open(csv_name, 'rb') as csvfile:
                    data_map = csv.reader(csvfile)
                    
                    for row in data_map:
                        print ("row[0] is "+ row[0])
                        cur_device = self.init_data_maps(row[1], row[2], row[3], row[0], row[4])                        
                        self.extpt_to_device_dict.update({row[0]: cur_device})
            except IOError as e:
                print("data map file not found")
                pass

            for keyval in self.extpt_to_device_dict:
                print("Key = "+keyval)
                print("Key = "+keyval + ", Val = "+self.extpt_to_device_dict[keyval].device_id)

    ##############################################################################
    class DeviceAttributes():
        def __init__(self, grp_name):
            self.data_mapping_dict = {"GrpName": grp_name}
            self.data_dict         = {"GrpName": grp_name}
            self.map_int_to_ext_endpt = {"GrpName": grp_name}

            # initialize certain known key word values that are inherited between parent/children devices 
            if grp_name == "OpStatus":
                self.key_update_list = ["Pwr_kW", "FullChargeEnergy_kWh", "Energy_kWh", "PwrAvailableIn_kW", "PwrAvailableOut_kW"]
                for key in self.key_update_list:
                    self.data_dict[key] = 0
            if grp_name == "HealthStatus":
                self.data_dict["status"] = 1
                self.fail_state = {"status":0}

        def update_fail_states(self, int_endpt, fail_state, grp_name):
            if grp_name == "HealthStatus":
                print("int endpt = "+int_endpt+" fail state = "+fail_state)
                self.fail_state.update({int_endpt: int(fail_state)})    

    def get_forecast(self):
        pass

    ##############################################################################
    def init_data_maps(self, device_id, group_id, int_endpt, ext_endpt, fail_state):
        """
        This function traverses the device tree to find the object matching device_id,
        then initializes a data_mapping dictionary entry to be associated with that device
        """
        if self.device_id == device_id:
            self.datagroup_dict_list[group_id].data_mapping_dict.update({ext_endpt: int_endpt})
            self.datagroup_dict_list[group_id].map_int_to_ext_endpt.update({int_endpt: ext_endpt})
            self.datagroup_dict_list[group_id].data_dict.update({int_endpt: 0})
            self.datagroup_dict_list[group_id].update_fail_states(int_endpt, fail_state, group_id)
            self.datagroup_dict.update({ext_endpt: self.datagroup_dict_list[group_id]})
            return self
        else:
            for cur_device in self.devices:
                child_device = cur_device.init_data_maps(device_id, group_id, int_endpt, ext_endpt, fail_state)
                if child_device != None:
                    return child_device

    ##############################################################################
    def display_device_tree(self):
        print(self.device_id+" "+str(self.nameplate))
        
        for key in self.datagroup_dict_list:
            datagroup = self.datagroup_dict_list[key]
            print("Device is: "+self.device_id+"; group name is: " + datagroup.data_mapping_dict["GrpName"])
            for vals in datagroup.data_mapping_dict:
                print("Device ID: "+ self.device_id + ": Key = "+ vals+ " Val = "+datagroup.data_mapping_dict[vals])

        for cur_device in self.devices:
            cur_device.display_device_tree()
        pass

    def set_nameplate(self):
        self.nameplate=0
        pass


    def set_mode(self, cmd):
        # change operational state of the site... 
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
            self.op_status.data_dict["Pwr_kW"] = int(self.op_status.data_dict["Pwr_raw"]) * int(self.op_status.data_dict["Pwr_SF"])
   
        print("device id is: "+self.device_id)
        for k,v in self.op_status.data_dict.items():
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
            self.health_status.data_dict[cur_device.device_id+"_status"] = cur_device.health_status.data_dict["status"]
            self.health_status.fail_state[cur_device.device_id+"_status"] = 0

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
            #print(key+": "+str(self.health_status.data_dict[key])+"val = "+str(val))

        print("Device ID ="+self.device_id+"Health Status is: "+str(self.health_status.data_dict["status"]))
 
        pass       

    def update_mode_status(self):
        """
        Dummy fcn
        """
        for cur_device in self.devices:               
            cur_device.update_mode_status()

        print("device id is: "+self.device_id)
        for k,v in self.mode_status.data_dict.items():
            print k, v
 
        pass 

    ##############################################################################
    def populate_device(self):
        """
        This populates DERDevice variables based on the topic list
        """ 
        self.lock = 1 # indicates that values are updating / need to wait


        # to practice, use a csv file that represents a pub-sub topic
        pubsub_msg_fname = ("test-msg.csv")
        
        try: 
            with open(pubsub_msg_fname, 'rb') as csvfile:
                incoming_msg = csv.reader(csvfile)
                for endpt in incoming_msg: 
                    cur_device = self.extpt_to_device_dict[endpt[0]].device_id
                    cur_attribute = self.extpt_to_device_dict[endpt[0]].datagroup_dict[endpt[0]]
                    cur_attribute_name = cur_attribute.data_mapping_dict["GrpName"]
                    keyval = cur_attribute.data_mapping_dict[endpt[0]]
                    cur_attribute.data_dict[keyval] = endpt[1]
                    print("Keyval is "+cur_device+"."+cur_attribute_name+"."+keyval+ "; value is "+ cur_attribute.data_dict[keyval])
                    
                    #update_endpoint(endpt, self.vpt_to_datagroup_dict, self.vpt_to_device_endpoint_dict)
        except IOError as e:
            print("No Msg Found!")

        self.update_op_status()
        self.update_health_status()
        self.update_mode_status()


##############################################################################
class ESSDevice(DERDevice):
    def __init__(self, device_id="site1", device_type="Site", parent_device=None):
        DERDevice.__init__(self,device_id, device_type, parent_device)
        #self.set_nameplate
        pass

    def set_config(self):
        # For ESS - most config data is stored / transmitted from the device 
        pass

       
    def set_alaram_status(self):
        # for each device - populat a dictionary entry?
        # what I want to do is to read the registry file, and then populate dictionary entries.
        pass

    def set_mode_ctrl(self):
        pass

    def set_nameplate(self):
        self.nameplate = {'pwr_chg_kw': 500, 'pwr_dis_kw': 500, 'energy': 1000}

    def set_power_real(self):

        pass

    def set_power_reactive(self):
        pass


##############################################################################
class DERSite(DERDevice):

    def check_site_heartbeat(self):
        # function for making sure that heartbeat is incrementing within specified timeout period
        # this should get called at a set interval
        # it should make sure counter is incrementing
        # it should raise a warning if # of misses 
        pass

    def send_heartbeat(self):
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

        self.mode_status.data_dict["OpModeStatus"]  = self.parent_device.mode_status.data_dict["OpModeStatus"]
        self.mode_status.data_dict["SysModeStatus"] = self.parent_device.mode_status.data_dict["SysModeStatus"] 

        print("device id is: "+self.device_id)
        for k,v in self.mode_status.data_dict.items():
            print k, v
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
        self.data_dict["Mfr"]    = "Solectria"        
        pass

if __name__ == "__main__":
    site = DERDevice(device_type="site")
    print(dir(site))
    print(dir(DERDevice))
    print(dir())
    site.display_device_tree()
    site.populate_device()


