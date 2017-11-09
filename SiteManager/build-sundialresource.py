

import DERDevice
import json

class SunDialResource():
    def __init__(self, resource_id, plant_list, resource_type):
        """
    
        1. Read a configuration file that tells what resources to include
        2. populate
        """

        self.resource_type     = resource_type
        self.resource_id       = resource_id

        self.der_member_list   = []
        # get der members from config file
        # parse config file - this should link to DERSite objects.  get site_id
        # curSite = find_site(site_id)
        # self.der_member_list.append(cur_site)

        # now I have a list of der member sites

        # now I need to figure out which cost functions to include.

        self.plant = DERDevice.VirtualDERPlant(device_id=resource_id, device_list=plant_list)

        # I think this should take the plant list and use that build a new virtual plant...
        # using a "virtual plant" data type / constructor
        # the virtual plant object type would take a new set of ...


        # I think you want to have some update functions....

        pass


    def get_health_status(self):
        """
        traverses the list of DER member resources to get status (e.g., online / offline)
        """
        pass


    def get_op_status(self):
        """
        traverses the list of DER member resources to get operataional state (e.g., current pwr)
        """
        pass

    def get_forecast(self):
        """
        retrieves forecast for all of the member resouces
        for each DERSite --> retrieve forcast, add to running tally of Resource forecast
        """


    def set_schedule(self):
        pass


    def execute(self):
        """
        Just a placeholder for describing how the mechnaics of this object would work
        """
        # for each SunDial Resource in SunDial-resource-file
        # initialize either to a "DERsite" or a "SunDial resource"
        # would parse some config files similar to what is done to build a site in the DERDevice class
        # THEN, you would do something like initiate a generate_dispatch() function call
        # For each SunDial resource, it would aggregate...

        # How would htis work?? How do we know what SunDial resources get passed to the optimizer?
        # you need to send it each of tge controllable resource classes, the baseline demand, and...
        # is the top level "SunDial" object - mostly a list of objective functionst to use that are based
        # on....net_demand of the system.

        # Maybe you can assume a fairly flat structure for this whole thing...
        # .... what else?



        """
        Latest thinking:
        (1) in the init function, we get pointers to 1 or more DER plants - which have rt conditions and forecasts
        (2) This just consists of a list of links to DER plants and associated cost function.  
        (3) It needs to roll these up into an aggregate - power / health / status / forecast, etc.....
        (4) the top level sundial resource does the same thing..... it totals 
               forecast demand = net_demand_baseline 
               total battery energy available
               load shift potentials
        (5) What is the caller?  is it an optimizer agent?
            sundial_system.get_updates()  
                for each sundial_resource n
                    sundial_resource(n).get_updates()
                get_forecast...
                get_stored_energy_available
                get_load_shift_potentials
                
                
            Here is the function call for GS_SSA_Optimization:
            function [deltaLoadShiftCommand_best, batteryCommand_best, pvCommand_best, 
            Battery_Q, ind_bestLoadProfile, scenarioCosts, cost_best, scenarioCosts_best, 
            weight_disch_best, best_threshold_kW, minFeasibleDemands] = 
            ... 
    GS_optimization_modelFLAME_battery_clusters(
    day,                                            how used? (display only / ignore)
    LoadShiftOptionsFlame,                          lives under load shift forecast (think about this....)
    cost24FLAME,...                                 lives under load shift cost function
    AggDemandBaseline,                              lives under baseline forecast data object 
    essSOE_kWh,                                     lives under ess object
    d_BG,d_BR,d_GS,d_SSA,d_PV,                      config fcns for -- live under objects (but review!) 
    Objective_functions,                            live under relevant data object
    use_objective_functions_lookup,                 don't know - some central place for toggling obj fcns on / off
    PV_i,                                           lives under solar forecast data object
    objfcn_params,                                  lives within individual obj fcns
init_weight)                                        how used? (not really used / experimental)
    
    - ,,,
    
    
    some questions / to do things - 
    - issue tracker
    - let's draw this up in a block diagram
    - fix the site manager / site / devices relationship
    - can you stub out / pseudo code the sequence of things that needs to happen to update a sundial resouce
      and call optimization


how am I bringing the platform in? 
       
       
       1. make a dummy executive that instantiates DerDevice classes for FLAME, baseline demand, PV, ESS
       2. make a sundial class that includes a virtualPlant object (and that includes a cost fcn, eventually)
       3. in the executive - instantiate sundial classes for each of the above. 
       4. and create a list that we can cycle through?
       
       
        """

class StorageResource(SunDialResource):
    def __init__(self, resource_id, plant_list, resource_type):
        SunDialResource.__init__(self, resource_id, plant_list, resource_type)
        pass

class PVResource(SunDialResource):
    def __init__(self, resource_id, plant_list, resource_type):
        SunDialResource.__init__(self, resource_id, plant_list, resource_type)
        pass

class LoadShiftResource(SunDialResource):
    def __init__(self, resource_id, plant_list, resource_type):
        SunDialResource.__init__(self, resource_id, plant_list, resource_type)
        pass

class BaselineLoadResource(SunDialResource):
    def __init__(self, resource_id, plant_list, resource_type):
        SunDialResource.__init__(self, resource_id, plant_list, resource_type)
        pass

class SundialSystemResource(SunDialResource):
    def __init__(self, resource_id, plant_list, resource_type):
        SunDialResource.__init__(self, resource_id, plant_list, resource_type)
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



def find_device(device_list, device_id):
    """
     This function traverses the device tree to find the object matching device_id and returns the object.
     """

    for cur_device in device_list:
        if cur_device.device_id == device_id:
            return cur_device
        else:
            child_device = find_device(cur_device.devices, device_id)
            if child_device != None:
                return child_device



if __name__ == "__main__":

    # the following is a rough demo of how a system gets constructed.
    # this is a hard-coded version of what might happen in the executive
    # would eventually do all this via external configuration files, etc.


    # first, instantiate dummy devices for some different sites
    # for the real version, this would be constructed from a site configuration file
    SiteCfgFile = "SiteConfiguration.json"
    SiteCfgList = json.load(open(SiteCfgFile, 'r'))

    sites = []
    for site in SiteCfgList:
        print(str(site["ID"]))
        print(str(site))
        #for jj in ii["DeviceList"]:
        #    print(str(jj["DeviceID"]))
        # (this should actually call an agent for each one, and retrieve a handle for the associated site)
        sites.append(DERDevice.DERSite(site, None))


    #IPKeysDevice       = DERDevice.DERSite(device_type="site", device_id="flame")
    #ShirleySouth       = DERDevice.DERSite(device_type="site", device_id="site1")
    #ShirleyNorth       = DERDevice.DERSite(device_type="site", device_id="site2")

    # build a list of sites
    #sites = [IPKeysDevice, ShirleySouth, ShirleyNorth]

    # a second configuration file provides instructions for building the "sundial_resource" objects:
    # in this example, a sundial_resource config consists of: (name, [member_plants], resource_type)
    sundial_cfg_list = [
        ("loadshift_sdr", ["IPKeys-FLAME_loadshift"], "LoadShiftCtrlNode"),
        ("load_sdr", ["IPKeys-FLAME_baseline"], "Load"),
        ("pv_sdr", ["ShirleySouth-PVPlant", "ShirleyNorth-PVPlant"], "PVCtrlNode"), #ShirleySouth
        ("ess_sdr", ["ShirleySouth-ESSPlant-ESS1"], "ESSCtrlNode"), #ShirleySouth-ESSPlant
        ("system_sdr", ["loadshift_sdr", "load_sdr", "pv_sdr", "ess_sdr"], "SYSTEM")]

    # using the configuration information, the following code constructs a list of "sundial_resource" objects,
    # one for each resource specified in the configuration file.
    # it is assumed that a final "system" object consists of plants from each of the member resources
    sundial_resources = []
    for new_resource in sundial_cfg_list:
        # find devices matching the specified device names....
        plant_list = []
        for new_plant in new_resource[1]:
            new_plant = find_device(sites, new_plant)
            plant_list.append(new_plant)
            print(new_plant.device_id)
        sundial_resources.append(SunDialResource(new_resource[0], plant_list, new_resource[2]))
        sites.append(sundial_resources[len(sundial_resources)-1].plant)


    # other things to do:
    # 1. really figure out how a site is structured
    # 2. clean up the relationship betewen site manager & DERDevices
    # 3. make separate sundial_resource classes for different data types consisting of cost functions....
    # 4. make list of cost functions in the sdr init functions
    # 5. revisit / clean up naming conventions.
    # 6. make a list of things to do - e.g., move things to config files, etc....
    # 7. do a semi real flame / load instance


    for site in sites:
        print(site.device_id)

        #"LOADSHIFT", plant_id_list=devicelist)


    #sundial_resources = [flame_sdr, load_sdr, pv_sdr, ess_sdr, system_sdr]

    #print(dir(res1.site))
    print(dir())
    #res1.site.display_device_tree()
    #res1.site.populate_device()