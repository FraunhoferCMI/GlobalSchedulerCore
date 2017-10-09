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
from volttron.platform.messaging.health import STATUS_GOOD
from volttron.platform.vip.agent import Agent, Core, PubSub, compat, RPC
from volttron.platform.agent import utils
from volttron.platform.messaging import headers as headers_mod

from . import settings


utils.setup_logging()
_log = logging.getLogger(__name__)
__version__ = '1.0'


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
        csv_dir  = "/home/matt/sundial/SiteManager/data/"
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
                        cur_device = self.init_data_maps(row[1], row[2], row[3], row[0], row[4], row[5])                        
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
            self.units                = {"GrpName": grp_name}

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


        def convert_units(self):
            # if data map units don't match --> 
            # W to kW, kW to W, Wh to kWh, VA to kVA
            # in general: (1) if units don't match... ; (2) if no units are included...
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


    def set_mode_ctrl(self, cmd, val):
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
    def populate_endpts(self, incoming_msg):
        """
        This populates DERDevice variables based on the topic list
        """ 
        self.lock = 1 # indicates that values are updating / need to wait

        for k in incoming_msg: 
            try: 
                cur_device = self.extpt_to_device_dict[k].device_id
                cur_attribute = self.extpt_to_device_dict[k].datagroup_dict[k]
                cur_attribute_name = cur_attribute.data_mapping_dict["GrpName"]
                keyval = cur_attribute.data_mapping_dict[k]
                cur_attribute.data_dict[keyval] = incoming_msg[k]
                print("Keyval is "+cur_device+"."+cur_attribute_name+"."+keyval+ "; value is "+ str(cur_attribute.data_dict[keyval]))
            except KeyError as e:
                print("Warning: Key "+k+" not found")
                pass            
        
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



##############################################################################
class SiteManagerAgent(Agent):
    """Listens to everything and publishes a heartbeat according to the
    heartbeat period specified in the settings module.
    """
    POWERS = {
        -3:0.001,
        -2:0.01,
        -1:0.1,
        0:1,
        1:10,
        2:100,
        3:1000        

        }

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
        
        _log.info("**********INITIALIIZING SITE MANAGER*******************")

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


    @RPC.export
    def set_setpoint(self, setpoint, *args, **kwargs):
        self.setpoint = setpoint
        _log.info("Twiddled to %s"%self.setpoint)
        return "DONE"
    
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
        _log.info("**********INSTANTIATING NEW SITE*******************")
        self.site = DERDevice(device_type="site")

    def logical_south(self,data):
        pass 
    
    def logical_north(self,data):
        pass

    @PubSub.subscribe('pubsub', 'devices/Shirley-MA/South/PMC/all')
    def on_match(self, peer, sender, bus,  topic, headers, message):
        """
        Use match_all to receive all messages and print them out.

        TODO: keep track fo complete time stamps. 

        """

        # i'm going to modify this to treat this incoming message as the test-msg
        #test_var = os.environ.get('TEST_VAR')
        #_log.info("Test var is "+str(test_var))

        if sender == 'pubsub.compat':
            message = compat.unpack_legacy_message(headers, message)
        data = message[0]
        for k, v in data.items():
            _log.info("Message is: "+k+": "+str(v))

        self.site.populate_endpts(data) 

        TimeStamp = datetime.strptime(
            headers["TimeStamp"][:19],            
            "%Y-%m-%dT%H:%M:%S"
        )      
        self.cache[TimeStamp] = self.cache.get(
            TimeStamp,{})

        #prefix, out = self.logical_south(data)
        #self.cache[TimeStamp]["South"]=out
        
        #prefix, out = self.logical_north(data)
        #self.cache[TimeStamp]["North"]=out            

        out = self.cache.pop(TimeStamp)
        print(str(TimeStamp)+ " " + out)
        # self.summarize(out,headers)

    @RPC.export
    def set_mode(self, device, cmd, value):
        """
        calls the mode command "cmd" associated with device
        this is the most generic command to actualy actaute something.
        """
        self.reserve_modbus()
        device.set_mode_ctrl(cmd, value)

        ret = self.vip.rpc.call(
            "platform.actuator",
            "set_point",
            device_path,
            value)


        self.release_modbus()

    @RPC.export
    def set_direct(self, power, *args, **kwargs):
        """
        Set battery bank power output level. 
        """
        self.reserve_modbus()
        if power == "max_charge_power":
            power = -self.max_charge_power
        elif power == "max_discharge_power":
            power = self.max_discharge_power
        _log.info("DEMO Set power to %s"%power)
        values = [
            (self.PATH +
            "ESS.Control.RealControl.Mode",self.DIRECT),
            (self.PATH +
             "ESS.Control.RealControl.Power",int(power))
        ]

        ret = self.vip.rpc.call(
            "platform.actuator",
            "set_multiple_points",
            "ess"+self.PATH,
            values)
        _log.info("DEMO Actuated the points, Result: {}".format(ret.get()))
        self.release_modbus()
        return "DONE"


        
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
