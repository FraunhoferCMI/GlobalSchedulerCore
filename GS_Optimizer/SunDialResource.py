# Copyright (c) 2018, The Fraunhofer Center for Sustainable Energy
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

import json
import numpy
import math
import copy
from datetime import datetime, timedelta
import pandas
import csv
import pytz
import logging
import os
from ObjectiveFunctions import *
from gs_identities import * #(SSA_SCHEDULE_RESOLUTION, SSA_PTS_PER_SCHEDULE, USE_SIM, SIM_START_TIME)
from gs_utilities import get_gs_time
_log = logging.getLogger("SDR")
_log.setLevel(logging.INFO)


forecast_keys = ["DemandForecast_kW",
                 "EnergyAvailableForecast_kWh",
                 "DemandForecast_t",
                 "OrigDemandForecast_kW",
                 "OrigDemandForecast_t_str",
                 "OrigEnergyAvailableForecast_kWh",
                 "LoadShiftOptions_kW",
                 "LoadShiftOptions_t",
                 "LoadShiftOptions_t_str"]

############################
class SundialResourceProfile():
    """
    Defines an object model for storing information about a proposed DER profile (load shape).
    It is used to generate and evaluate the cost of potential load shapes to search for a least-cost solution
    The object model supports a hierarchical tree structure that aggregates characteristics of children into the
    parent
    SundialResourceProfile has the following instance variables:
    (1) virtual_plant - list of children associated with the DER
    (2) state_vars - data dictionary that stores time-series data for the load shape.  Each dictionary element is a
        numpy array.  The time step and duration of the time-series is implicitly defined by SSA_SCHEDULE_RESOLUTION
        and SSA_SCHEDULE_DURATION.  The following keys are defined:
        (a) ["DemandForecast_kW"] - list of floats.  Represents a proposed time-series demand forecast, in kW for the
            associated DER.  By convention, generation is negative, consumption is positive.
        (b) ["EnergyAvailableForecast_kWh"] - list of floats.  Estimates stored energy available for the resource in
            question if the given DemandForecast_kW is executed.  In kWh
        (c) ["DeltaEnergy_kWh"] - list of floats.  Estimates the change in stored energy of the DER at each time
            step.  For non-storage devices, this is unused.  For storage devices, it is the alculated based on the
            power in DemandForecast_kW, adjusted by the efficiency of the ESS.
    (3) sundial_resources - cross-references to the associated SundialResource data model associated with this DER.
        This enables SundialResourceProfile instances to readily access details about its associated DERs
    (4) cost - the cost of implementing the load profile in question at this SundialResourceProfile Node ONLY
    (5) total_cost - the total cost of implementing the load profile in question, including the cost at this level of
        the SundialResourceProfile tree AND any associated children.

        **To understand the distinction between cost and total_cost:
        - uppose we have a system that includes and ESS + Load + Solar generation.  The system incurs a cost
          of $0.10/kWh import, and uses 1000 kWh
        - Assume the ESS incurs a cost of $0.01/kWh throughput, and uses 100 kWh.  It has no children
        - Assume load and solar have no associated costs
        - The cost and total_cost of the ESS node will be 0.01 x 100 = $1
        - The cost of the system (i.e., the parent node) = 0.10 x 1000 = $100
        - The total_cost of the system = $100 + $1 = $101 = the sum of the parent and all its children
    """

    ##############################################################################
    def __init__(self, sundial_resources, schedule_timestamps):
        """
        Recursively constructs a SundialResourceProfile tree.
        The SundialResourceProfile tree replicates the tree structure of the passed sundial_resource.  Nodes in the
        SundialResourceProfile tree are initialized as follows:
        - self.state_var["DemandForecast_kW"] is initialized with the baseline demand forecast for the associated
          sundial_resource (i.e., the demand forecast prior to applying any optimization).
        - self.sundial_resources is set to the sundial_resource instance
        - self.virtual_plants stores instances of SundialResourceProfile corresponding to the DER's children
        - total_cost is initialized to the cost of executing the baseline profile
        - self.state_var["EnergyAvailableForecast_kWh"] is initialized to the baseline energy forecast for the
          associated sundial_resource (if it exists), otherwise, to 0.
        - all other variables initialized to 0
        :param sundial_resources: An instance of SundialResource class
        """
        self.virtual_plants = []

        # call SundialResourceProfile constructor for children of the associated sundial_resource instance
        for virtual_plant in sundial_resources.virtual_plants:
            self.virtual_plants.append(SundialResourceProfile(virtual_plant, schedule_timestamps))

        # initialize self.state_vars
        # DemandForecast_kW is set to the baseline forecast for the resource in question.
        # other state_vars are set to zero.
        self.state_vars = {"DemandForecast_kW": numpy.array(copy.deepcopy(sundial_resources.state_vars["DemandForecast_kW"])),
                           "EnergyAvailableForecast_kWh": numpy.array([0.0]*len(sundial_resources.state_vars["DemandForecast_kW"])),
                           "DeltaEnergy_kWh": numpy.array([0.0]*len(sundial_resources.state_vars["DemandForecast_kW"]))}
        try:
            # if exists - initialize to same value as the associated sundial_resource instance
            # fixme - energyavailableforecast not getting initialized correctly in sdr
            self.state_vars["EnergyAvailableForecast_kWh"] = copy.deepcopy(sundial_resources.state_vars["EnergyAvailableForecast_kWh"])
        except: # otherwise - resource does not have storage capability, so ignore
            pass

        self.sundial_resources = sundial_resources

        self.cost = 0.0
        self.total_cost = self.calc_cost()

    ##############################################################################
    def copy_profile(self, source):
        self.state_vars = copy.deepcopy(source.state_vars)
        self.cost = source.cost
        self.total_cost = source.total_cost

    ##############################################################################
    def calc_cost(self):
        """
        Calculates cost of implementing the associated demand profile.  The cost of implementing a demand
        profile is calculated by recursively traversing the sundial resource tree, and for each resource, passing the
        load profile associated with that resource to the SundialResource.calc_cost routine associated with the given
        resource.
        self.cost = cost of this node only
        self.total_cost = cost of this node + children
        FIXME: this returns total cost and also sets self.total_cost.  One or the other may be
        FIXME: unnecessary, but don't want to change without checking.
        :return:
        """
        self.cost  = 0.0
        total_cost = 0.0
        for virtual_plant in self.virtual_plants:
            total_cost += virtual_plant.calc_cost()

        self.cost = self.sundial_resources.calc_cost(self.state_vars)

        total_cost += self.cost
        self.total_cost = total_cost
        return total_cost


##############################################################################
class SundialResource():
    """
    SundialResource defines an object model for defining the underlying physical parameters, current state, and cost
    function(s) associated with one or more associated DERs.
    A SundialResource instance is implemented as a tree.  Each node inherits state characteristics and physical
    characteristics from its children (e.g., the power output and nameplate capacity of a parent is defined as the sum
    of the power output / nameplate of its children), but cost functions specifically apply to the current node.
    Example:
        - Sundial system consists of 1 solar node, 1 ESS node, 1 pool of aggregated load, 1 pool of flexible load.  The
          solar+ESS are aggregated into an intermediate node, so the tree looks like this:
                                                    system
                                      ess+solar             load   flexLoad
                                essPlant    solarPlant
        - The "system" would have power, storage capacity, etc reflective of the sum of each of its children.  It's cost
          functions would apply to "system" loads
        - The "ess+solar" node has power, storage, etc reflecting the sum of the individual ESS & solar resources.  It's
          cost functions would apply to the combination of these resources.
        - The bottom nodes (essPlant, solarPlant, load, and flexLoad) reflect the state and the cost functions
          associated with the specific resources

    Instance variables:
    (1) self.resource_type - identifier for the SundialResource type.  Currently recognized types are "ESSCtrlNode",
                         "PVCtrlNode", "LoadShiftCtrlNode", "Load", and "System"
    (2) self.resource_id - unique identifier for the SundialResource
    (3) self.obj_fcns - list of references to methods that represent the objective functions associated with this resource
    (5) self.virtual_plants - list of children SundialResources associated with this resource.
    (6) self.update_required - this is a flag that tells the optimizer whether the profile of this resource has changed
        and needs to be updated.  Sort of a temporary fix to speed execution, but there may be better ways to do this.
    (7) ...
    (8) self.state_vars - stores information about the state of the resource.  Has the following keys:
    FIXME - data types have not been checked are and are likely inconsistent
        (a) ["MaxSOE_kWh"] - float.  Maximum allowable state of energy of the SundialResource, in kWh
        (b) ["MinSOE_kWh"] - float.  Maximum allowable state of energy of the SundialResource, in kWh
        (c) ["SOE_kWh"] - float.  Current state of energy of the SundialResource, in kWh
        (d) ["Pwr_kW"] - float.  Current power output of the SundialResource in kW
        (e) ["Nameplate"] - int.  nameplate of the device.  FIXME - nameplate is an over simplification esp for battery
        (f) ["DemandForecast_kW"] - numpy array of demand forecast values, length is given by SSA_PTS_PER_SCHEDULE.
            Generation is negative, Consumption is positive.  Data points are aligned to SSA time.
        (g) ["EnergyAvailableForecast_kWh"] - numpy array of forecast energy storage values, length is given by
            SSA_PTS_PER_SCHEDULE.  Data points are aligned to SSA time.
        (h) ["DemandForecast_t"]- timestamps, as datetime, associated with forecast data points, length is given by
            SSA_PTS_PER_SCHEDULE.
        (i) ["OrigDemandForecast_kW"] - list of demand forecast values provided by the end point resource.  Time stamps
            aligned to the native forecast time.
        (j) ["OrigDemandForecast_t_str"] - timestamps, as datetime string, associated with OrigDemandForecast data
            point.  Length is given by SSA_PTS_PER_SCHEDULE.  Timestamps reflect the resource's native context.
    (9) self.schedule_vars - stores *scheduled* state for the SundialResource.  (schedule_vars reflects the directive
        issued by the latest optimization pass.)  This is copied from the least_cost SundialResourceProfile
        (a) ["DemandForecast_kW"] - list of floats.  Represents a proposed time-series demand forecast, in kW for the
            associated DER.  By convention, generation is negative, consumption is positive.
        (b) ["EnergyAvailableForecast_kWh"] - list of floats.  Estimates stored energy available for the resource in
            question if the given DemandForecast_kW is executed.  In kWh
        (c) ["DeltaEnergy_kWh"] - list of floats.  Estimates the change in stored energy of the DER at each time
            step.  For non-storage devices, this is unused.  For storage devices, it is the alculated based on the
            power in DemandForecast_kW, adjusted by the efficiency of the ESS.
        (d) ["timestamp"] - list of timestamps.
    (10) end_pt_update_list - a list of keys to map from device end points (DERDevice instances) to SundialResource
         keys in state_vars
    (12) self.sim_offset - for simulated scenarios, stores the time delta between the SIM_START_TIME (i.e., the starting
         time of the stored data set), and the gs_start_time.  Used to synchronize retrieval of objective function data
         to gs time.
    (13) self.pt_per_schedule - # of data points stored in a schedule


    """
    ##############################################################################
    def __init__(self, resource_cfg, gs_start_time):
        """
        Initializes a generic SundialResource object based on parameters set in the resource_cfg data structure
        :param resource_cfg: json object representing sundial resource tree class structure
        """

        _log.info ("Resource is "+resource_cfg["ID"]+" of type "+resource_cfg["ResourceType"])

        self.resource_type = resource_cfg["ResourceType"]
        self.resource_id   = resource_cfg["ID"]
        self.update_required      = 0 # Flag that indicates if the resource profile needs to be updated between SSA iterations
                                      # Set to one for any resource types whose schedule is affected by changes to control signal

        self.obj_fcns     = []  # constructor for any applicable objectibve functions

        # initialize dictionaries for mapping from DERDevice keys to SundialResource keys.
        self.end_pt_update_list    = ["Pwr_kW",
                                      "AvgPwr_kW"]
        self.forecast_update_list = ["OrigDemandForecast_kW",
                                     "OrigDemandForecast_t_str"]

        if USE_SIM == 1:
            # set a time offset that matches gs start time to the desired sim start time
            self.sim_offset = SIM_START_TIME - datetime.strptime(gs_start_time,"%Y-%m-%dT%H:%M:%S")
        else:
            self.sim_offset = timedelta(0)

        self.pts_per_schedule = SSA_PTS_PER_SCHEDULE
        self.state_vars    = self.init_state_vars()
        self.schedule_vars = self.init_schedule_vars(gs_start_time)
        self.state_vars.update(self.init_forecast_vars(gs_start_time))

        # instantiate children based on resource_cfg instructions
        self.virtual_plants   = []
        # todo: consider replacing with an eval command?
        for virtual_plant in resource_cfg["VirtualPlantList"]:
            if virtual_plant["Use"] == "Y":
                print(virtual_plant["ResourceType"] + " " + virtual_plant["ID"])
                if virtual_plant["ResourceType"] == 'ESSCtrlNode':
                    self.virtual_plants.append(
                        ESSResource(virtual_plant, gs_start_time))
                elif virtual_plant["ResourceType"] == 'PVCtrlNode':
                    self.virtual_plants.append(
                        PVResource(virtual_plant, gs_start_time))
                elif (virtual_plant["ResourceType"] == "LoadShiftCtrlNode"):
                    self.virtual_plants.append(
                        LoadShiftResource(virtual_plant, gs_start_time))
                elif virtual_plant["ResourceType"] == "Load":
                    self.virtual_plants.append(
                        BaselineLoadResource(virtual_plant, gs_start_time))
                else:
                    self.virtual_plants.append(
                        SundialResource(virtual_plant, gs_start_time))
            else:
                _log.info("Skipping - "+virtual_plant["ID"])

    ##############################################################################
    def find_resource(self, resource_id):
        """
         This function traverses the SundialResource tree to find the object matching resource_id and returns the
         matching SundialResource instance (or None if not found).
         """

        if self.resource_id == resource_id:
            return self
        else:
            for virtual_plant in self.virtual_plants:
                child = virtual_plant.find_resource(resource_id)
                if child != None:
                    return child
            return None


    ##############################################################################
    def find_resource_type(self, resource_type):
        """
         This function traverses the SundialResource tree to find all the objects matching resource_type and
         returns in a flat list
        """
        resources = []
        for virtual_plant in self.virtual_plants:
            resources.extend(virtual_plant.find_resource_type(resource_type))
        if resource_type == self.resource_type:
            resources.append(self)
        return resources

    ##############################################################################
    def init_state_vars(self):
        """
        intializes the state_vars data structure
        :return: None
        """
        state_vars = {"MaxSOE_kWh": 0.0,
                      "MinSOE_kWh": 0.0,
                      "SOE_kWh": 0.0,
                      "Pwr_kW": 0.0,
                      "AvgPwr_kW": 0.0,
                      "Nameplate": 0.0}
        return state_vars

    ##############################################################################
    def init_forecast_vars(self, gs_start_time):
        """
        initializes time-series forecast data structures in the state_vars data structure
        :param gs_start_time: time stamp for initialization
        :return: dictionary of lists of demand forecast, energy forecast, and associated timestamps
        """
        init_forecast = [0.0] * self.pts_per_schedule
        init_timestamps = [datetime.strptime(gs_start_time, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=pytz.UTC) +
                           timedelta(minutes=t) for t in range(0,
                                                               SSA_SCHEDULE_DURATION * MINUTES_PER_HR,
                                                               SSA_SCHEDULE_RESOLUTION)]

        return {"DemandForecast_kW": numpy.array(init_forecast),
                "DemandForecast_t": init_timestamps,
                "OrigDemandForecast_kW": init_forecast,
                "OrigDemandForecast_t_str": [t.strftime("%Y-%m-%dT%H:%M:%S") for t in init_timestamps],
                "OrigEnergyAvailableForecast_kWh": init_forecast,
                "EnergyAvailableForecast_kWh": numpy.array(init_forecast)}


    ##############################################################################
    def init_schedule_vars(self, gs_start_time):
        """
        initializes the schedule_vars data structure
        :return:
        """
        schedule_vars = {"DemandForecast_kW": numpy.array([0.0] * self.pts_per_schedule),
                         "EnergyAvailableForecast_kWh": numpy.array([0.0] * self.pts_per_schedule),
                         "DeltaEnergy_kWh": numpy.array([0.0] * self.pts_per_schedule),
                         "timestamp": [datetime.strptime(gs_start_time,"%Y-%m-%dT%H:%M:%S").replace(tzinfo=pytz.UTC) +
                                       timedelta(minutes=t) for t in range(0,
                                                                           SSA_SCHEDULE_DURATION * MINUTES_PER_HR,
                                                                           SSA_SCHEDULE_RESOLUTION)],
                         "total_cost": 0.0}
        return schedule_vars


    ##############################################################################
    def load_scenario(self, demand_forecast=[0.0]*SSA_PTS_PER_SCHEDULE, pk_capacity=0.0, t= None):
        """
        loads scenario data into the state vars.  Used for intializing the SundialResource instance with specific data
        :param demand_forecast: time series list of demand forecast
        :param pk_capacity: nameplate capacity of the resource
        :param t: timestamps associated with the demand_forecast, stored as a datetime string
        :return: None
        """
        self.state_vars["OrigDemandForecast_kW"] = demand_forecast
        self.state_vars["DemandForecast_kW"]     = numpy.array(demand_forecast)
        self.state_vars["OrigDemandForecast_t_str"]  = t
        self.state_vars["DemandForecast_t"]          = [datetime.strptime(ts,
                                                                          "%Y-%m-%dT%H:%M:%S").replace(tzinfo=pytz.UTC)
                                                        for ts in t]
        self.state_vars["Nameplate"] = pk_capacity

    ##############################################################################
    def update_sundial_resource(self):
        """
        propagates data from children to non-terminal parent nodes in the SundialResource tree
        :return: None
        """

        if self.virtual_plants != []: # not a terminal node
            # initialize all state_vars
            self.state_vars.update(self.init_state_vars())

            for virtual_plant in self.virtual_plants:
                # retrieve data from child nodes and sum
                virtual_plant.update_sundial_resource()
                for k,v in self.state_vars.items():
                    if k not in forecast_keys:
                        self.state_vars[k] += virtual_plant.state_vars[k]


    ##############################################################################
    def cfg_cost(self, schedule_timestamps, tariffs):
        """
        configures cost information for all applicable cost functions in preparation for an optimization pass
        :param schedule_timestamps: list of timestamps (lengh = SSA_PTS_PER_SCHEDULE) for which to retrieve objective
               function configuration information
        :return: None
        """
        for virtual_plant in self.virtual_plants:
            virtual_plant.cfg_cost(schedule_timestamps, tariffs)
        for obj_fcn in self.obj_fcns:
            obj_fcn.obj_fcn_cfg(schedule_timestamps=schedule_timestamps,
                                tariffs=tariffs,
                                sim_offset=self.sim_offset,
                                forecast = self.state_vars)



    ##############################################################################
    def interpolate_forecast(self, schedule_timestamps):
        """
        interpolates a forecast to generate forecast data starting from time = now
        It traverses the sundial resource tree.
         - If it's a terminal node - interpolate.
         - If it's a non-terminal node, sum up the children
        :param schedule_timestamps: list of timestamps (length = SSA_PTS_PER_SCHEDULE)
        :return:
        """

        self.state_vars["DemandForecast_t"] = schedule_timestamps

        if self.virtual_plants == []: # terminal node
            ## do interpolation
            _log.debug(str(self.state_vars["OrigDemandForecast_kW"]))
            self.state_vars["DemandForecast_kW"]           = self.interpolate_values(schedule_timestamps,
                                                                                     self.state_vars["OrigDemandForecast_kW"])
            self.state_vars["EnergyAvailableForecast_kWh"] = self.interpolate_values(schedule_timestamps,
                                                                                     self.state_vars["OrigEnergyAvailableForecast_kWh"])

            try:
                self.state_vars["LoadShiftOptions_kW"] = self.interpolate_loadshift_options(schedule_timestamps,
                                                                                            self.state_vars["OrigLoadShiftOptions_kW"])
                self.state_vars["LoadShiftOptions_t"] = schedule_timestamps
            except KeyError: # not a load shift resource
                pass

        else:
            self.state_vars["DemandForecast_kW"] = numpy.array([0.0] * self.pts_per_schedule)
            self.state_vars["EnergyAvailableForecast_kWh"] = numpy.array([0.0] * self.pts_per_schedule)
            self.state_vars["LoadShiftOptions_kW"] =  numpy.array([[0.0] * self.pts_per_schedule]*20)

            #FIXME - hard coded max = 20 ls options.

            len_load_options = 0
            for virtual_plant in self.virtual_plants:
                # retrieve data from child nodes and sum
                _log.debug(self.resource_id)
                _log.debug(virtual_plant.resource_id)
                virtual_plant.interpolate_forecast(schedule_timestamps)
                self.state_vars["DemandForecast_kW"]           += virtual_plant.state_vars["DemandForecast_kW"]
                self.state_vars["EnergyAvailableForecast_kWh"] += virtual_plant.state_vars["EnergyAvailableForecast_kWh"]

                try:
                    self.state_vars["LoadShiftOptions_kW"][0:len(virtual_plant.state_vars["LoadShiftOptions_kW"])] \
                        += virtual_plant.state_vars["LoadShiftOptions_kW"]
                    len_load_options = len(virtual_plant.state_vars["LoadShiftOptions_kW"])
                except KeyError:
                    pass

                self.state_vars["LoadShiftOptions_kW"] += [virtual_plant.state_vars["DemandForecast_kW"] for ii in range(0,20)]

            self.state_vars["LoadShiftOptions_kW"] = self.state_vars["LoadShiftOptions_kW"][0:len_load_options]
            _log.debug(str(self.state_vars["DemandForecast_kW"]))
            _log.debug(str(self.state_vars["EnergyAvailableForecast_kWh"]))
            _log.debug(str(self.state_vars["LoadShiftOptions_kW"]))

    ##############################################################################
    def interpolate_loadshift_options(self, schedule_timestamps, init_demand):
        """

        :param schedule_start_time: start time for schedule, in GS frame of reference
        :return:
        """
        ind = 1  # index into timestamp list -- 1 = forecast at t+1, 0 = forecast at t-1

        _log.debug(self.resource_id)
        _log.debug(str(self.state_vars["LoadShiftOptions_t_str"]))
        _log.debug("Timestamps are: "+str(schedule_timestamps))

        interpolated_demand = [[0.0] * SSA_PTS_PER_SCHEDULE] * len(init_demand)

        if self.state_vars["LoadShiftOptions_t_str"] != None:
            time_elapsed = float((schedule_timestamps[0] -
                                  datetime.strptime(self.state_vars["LoadShiftOptions_t_str"][0],
                                                    "%Y-%m-%dT%H:%M:%S").replace(tzinfo=pytz.UTC)).total_seconds())   # seconds since the first forecast ts
            _log.debug("time elapsed = "+str(time_elapsed))
            scale_factor = time_elapsed / float(SSA_SCHEDULE_RESOLUTION*SEC_PER_MIN)
            _log.debug("scale factor= "+str(scale_factor))
            _log.debug("demand forecast orig = "+str(init_demand))

            for jj in range(0,len(init_demand)):
                interpolated_demand[jj] = [init_demand[jj][ii-1] +
                                   (init_demand[jj][ii] -
                                    init_demand[jj][ii-1]) * scale_factor
                                   for ii in range(1,SSA_PTS_PER_SCHEDULE)]

                interpolated_demand[jj].append(init_demand[jj][SSA_PTS_PER_SCHEDULE-1]) # FIXME - tmp fix to pad last element

        _log.debug(self.resource_id+": demand forecast is "+str(interpolated_demand))

        return numpy.array(interpolated_demand)


    ##############################################################################
    def interpolate_values(self, schedule_timestamps, init_demand):
        """

        :param schedule_start_time: start time for schedule, in GS frame of reference
        :return:
        """
        ind = 1  # index into timestamp list -- 1 = forecast at t+1, 0 = forecast at t-1
        SEC_PER_MIN = 60.0

        _log.debug(self.resource_id)
        _log.debug(str(self.state_vars["OrigDemandForecast_t_str"]))
        _log.debug("Timestamps are: "+str(schedule_timestamps))


        if self.state_vars["OrigDemandForecast_t_str"] != None:

            #FIXME - temporary!!! need to fix types of demand forecast
            time_elapsed = float((schedule_timestamps[0] -
                                  datetime.strptime(self.state_vars["OrigDemandForecast_t_str"][0],
                                                    "%Y-%m-%dT%H:%M:%S").replace(tzinfo=pytz.UTC)).total_seconds())   # seconds since the first forecast ts

            _log.debug("time elapsed = "+str(time_elapsed))
            scale_factor = time_elapsed / float(SSA_SCHEDULE_RESOLUTION*SEC_PER_MIN)
            _log.debug("scale factor= "+str(scale_factor))
            _log.debug("demand forecast orig = "+str(init_demand))
            interpolated_demand = [init_demand[ii-1] +
                                   (init_demand[ii] -
                                    init_demand[ii-1]) * scale_factor
                                   for ii in range(1,SSA_PTS_PER_SCHEDULE)]

            interpolated_demand.append(init_demand[SSA_PTS_PER_SCHEDULE-1]) # FIXME - tmp fix to pad last element

        else:
            interpolated_demand = [0.0]*SSA_PTS_PER_SCHEDULE
        _log.debug(self.resource_id+": demand forecast is "+str(interpolated_demand))

        return numpy.array(interpolated_demand)


    ############################
    def calc_cost(self, profile_state_vars, linear_approx = False):
        """
        Loops through each of the SundialResource's objective functions, calculates cost for the given profile
        :param profile: profile is a time-series list of values
        :return:
        """

        cost = 0 #[]
        for obj_fcn in self.obj_fcns:
            if linear_approx == False:
                cost += obj_fcn.obj_fcn_cost(profile_state_vars) # cost.append(obj_fcn.obj_fcn_cost(profile))
            else:
                cost += obj_fcn.get_linear_approximation(profile_state_vars)  # cost.append(obj_fcn.obj_fcn_cost(profile))

        #cost = 0
        #for fcn in self.obj_fcns:
        #    cost += fcn()
        return cost

##############################################################################
class ESSResource(SundialResource):
    """
    Inherits from SundialResource.  Defines objective functions, state_vars, etc specific to ESSCtrlNodes
    Incorporates additional self.state_vars instances:
        (h) ["ChgEff"] - efficiency for charging.
        (i) ["DischgEff"] - efficiency for discharge.
        (j) ["MaxChargePwr_kW"] - Maximum
        (k) ["MaxDischargePwr_kW"] -
    Future rev could change these from single point values to a lookup table.

    """

    ##############################################################################
    def __init__(self, resource_cfg, gs_start_time):
        SundialResource.__init__(self, resource_cfg, gs_start_time)
        self.update_required = 1  # Temporary fix.  flag that indicates if the resource profile needs to be updated between SSA iterations

        # define a bunch of ESS-specific end points to update
        self.end_pt_update_list.extend(["MaxSOE_kWh",
                                        "MinSOE_kWh",
                                        "SOE_kWh",
                                        "ChgEff",
                                        "DischgEff",
                                        "MaxChargePwr_kW",
                                        "MaxDischargePwr_kW",
                                        "Nameplate"])

        # set up the specific set of objective functions to apply for the system
        self.obj_fcns = [StoredEnergyValueObjectiveFunction(desc="StorageValue")]

    ##############################################################################
    def init_state_vars(self):
        """
        intializes the state_vars data structure
        :param length: length of time series keys in the state_vars dictionary
        :return: None
        """
        state_vars = SundialResource.init_state_vars(self)
        state_vars.update({"ChgEff": 1.0, # temporarily set here
                           "DischgEff": 1.0,
                           "MaxChargePwr_kW": 0.0,
                           "MaxDischargePwr_kW": 0.0})
        return state_vars


    ##############################################################################
    def load_scenario(self, init_SOE=0.0, max_soe=0.0, min_soe=0.0, max_chg=0.0,
                      max_discharge=0.0, chg_eff=1.0, dischg_eff=1.0, demand_forecast=[0.0]*SSA_PTS_PER_SCHEDULE, t = None):
        self.state_vars["MaxSOE_kWh"] = max_soe
        self.state_vars["MinSOE_kWh"] = min_soe
        self.state_vars["SOE_kWh"]    = init_SOE
        self.state_vars["DemandForecast_kW"] = numpy.array(demand_forecast)
        self.state_vars["DemandForecast_t"]  = t
        self.state_vars["EnergyAvailableForecast_kWh"] = numpy.array([self.state_vars["SOE_kWh"]]*SSA_PTS_PER_SCHEDULE)
        self.state_vars["ChgEff"]    = chg_eff
        self.state_vars["DischgEff"] = dischg_eff
        self.state_vars["MaxChargePwr_kW"]    = max_chg
        self.state_vars["MaxDischargePwr_kW"] = max_discharge
        self.state_vars["Nameplate"] = max_chg # approximation

        #print("Resource "+self.resource_id)
        #for k, v in self.state_vars.items():
        #    print(k+": "+str(v))

    ##############################################################################
    def update_soe(self, pwr_request, current_soe):
        """
        Given a power request and current state of energy, it checks ess constraints and adjusts the command
        accordingly.
        returns power command and new soe that are within ess operating envelope
        :param pwr_request: power request, in kW
        :param current_soe: current state of energy, in kWh
        :return: pwr_cmd: power- and energy-limited power command
        :return: new_soe: battery state of energy at the next time step after executing pwr_cmd, accounting for ESS
                 losses
        """

        tResolution_hr = float(SSA_SCHEDULE_RESOLUTION)/60.0  # convert to hours (from minutes)

        if pwr_request > 0: # charge
            # maximum energy that can be input to the battery before reaching upper constraint
            max_energy = (self.state_vars["MaxSOE_kWh"] - current_soe) / self.state_vars["ChgEff"]
            pwr_cmd    = min(pwr_request, self.state_vars["MaxChargePwr_kW"])
            pwr_cmd    = min(max_energy/tResolution_hr, pwr_cmd)
            delta_energy = pwr_cmd * tResolution_hr * self.state_vars["ChgEff"]

        else: # discharge
            # maximum energy that can be output from the battery before reaching lower constraint
            max_energy = (current_soe - self.state_vars["MinSOE_kWh"]) * self.state_vars["DischgEff"]
            pwr_cmd    = max(pwr_request, -1*self.state_vars["MaxDischargePwr_kW"])
            pwr_cmd    = max(-1 * max_energy / tResolution_hr, pwr_cmd)
            delta_energy = pwr_cmd * tResolution_hr / self.state_vars["DischgEff"]

        new_soe = current_soe + delta_energy
        return new_soe, pwr_cmd, delta_energy


    ##############################################################################
    def check_constraints2(self, profile, ind):
        """
        This is currently unused.
        It ensures that the proposed ESS charge/discharge schedule does not violate the ESS's high or low SOE
        constraints.

        This is an alternate (and in theory more efficient) method to check constriants on proposed ESS profile.
        It relies on the fact that the SSA algorithm perturbs only a single point in the battery schedule, so one can do
        a closed loop calculation to determine if a constraint has been violated.

            check_constraint(schedule, start_ind, init_SOE)
                calculate SOE over the full time horizon for the given init_SOE, and schedule starting from start_ind
                if no constraint is found
                    return current schedule
                else
                    find the index of the first point that violates a constraint
                    modify power command so as to not violate constraint
                    call check_constraint(schedule(start_ind:end, soe(start_ind))


        :param profile: SundialResourceProfile.state_vars - a profile for which a constraint needs to be checked.
        :param ind: starting index that was perturbed
        :return: profile - modified SundialResourceProfile.state_vars that does not violate any constraints
        """
        ind = int(ind)

        if profile["DemandForecast_kW"][ind] >= 0.0: # charge
            eff_factor = self.state_vars["ChgEff"]
        else:
            eff_factor = 1.0/self.state_vars["DischgEff"]

        profile["DeltaEnergy_kWh"][ind] = profile["DemandForecast_kW"][ind] * eff_factor

        energy = numpy.cumsum(profile["DeltaEnergy_kWh"]) + [self.state_vars["SOE_kWh"]] * len(
            profile["DeltaEnergy_kWh"])

        cnt = 0
        if max(energy) > float(self.state_vars["MaxSOE_kWh"])+0.001: # new command has violated an upper constraint
            # adjust power command downward by an amount equivalent to the SOE violation, after correcting for losses
            test_val = profile["DemandForecast_kW"][ind]-(max(energy) - self.state_vars["MaxSOE_kWh"])/eff_factor
            if (profile["DemandForecast_kW"][ind] > 0.0) & (test_val < 0.0):
                # implies modified command will go from chg to discharge, so we need to update the impact on
                # efficiency
                test_val   = test_val*(eff_factor**2.0)
                eff_factor = 1.0 / self.state_vars["DischgEff"]
            profile["DemandForecast_kW"][ind] = test_val
            profile["DeltaEnergy_kWh"][ind] = profile["DemandForecast_kW"][ind] * eff_factor
            energy = numpy.cumsum(profile["DeltaEnergy_kWh"]) + [self.state_vars["SOE_kWh"]] * len(profile["DeltaEnergy_kWh"])
            cnt += 1
        elif min(energy) < float(self.state_vars["MinSOE_kWh"])-0.001: # new command has violated a lower constraint
            # adjust power command upward by amount equivalent to SOE violation, after correcting for losses
            test_val = profile["DemandForecast_kW"][ind] + (self.state_vars["MinSOE_kWh"]-min(energy))/eff_factor
            if (profile["DemandForecast_kW"][ind] < 0.0) & (test_val > 0.0):
                # implies modified command will go from dicharge to charge
                test_val   = test_val*(eff_factor**2.0)
                eff_factor = self.state_vars["ChgEff"]
            profile["DemandForecast_kW"][ind] = test_val
            profile["DeltaEnergy_kWh"][ind] = profile["DemandForecast_kW"][ind] * eff_factor
            energy = numpy.cumsum(profile["DeltaEnergy_kWh"]) + [self.state_vars["SOE_kWh"]] * len(profile["DeltaEnergy_kWh"])
            cnt += 1

        if cnt == 2:
            _log.info("What the hey??")  # should never happen!

        #if (self.state_vars["Nameplate"]) != 0.0:
        #    profile["Weight"][ind] = profile["DemandForecast_kW"][ind]/float(self.state_vars["Nameplate"])
        #else:
        #    profile["Weight"][ind] = 1.0
        profile["EnergyAvailableForecast_kWh"] = energy
        return profile

    ##############################################################################
    def check_constraints(self, profile, ind):
        """
        Checks constraints on proposed ESS profile.  Calculates energy at each point in in time and modifies the
        power profile if the proposed ESS profile exceeds a limit condition (e.g., > MasSOE, <MinSOE)

        Empirically, this seems to work better than check_constraints2.  I think what's going on is that
        check_constraints2 routine only modifies the pwr cmd at the initial point of perturbation, but this
        routine will modify power at the point where a constraint is found.  Introduces additional noise to the system.

        :param profile: SundialResourceProfile.state_vars - a profile for which a constraint needs to be checked.
        :return: profile - modified SundialResourceProfile.state_vars that does not violate any constraints
        """

        if profile["DemandForecast_kW"][ind] >= 0.0: # charge
            eff_factor = self.state_vars["ChgEff"]
        else:
            eff_factor = 1.0/self.state_vars["DischgEff"]

        profile["DeltaEnergy_kWh"][ind] = profile["DemandForecast_kW"][ind] * eff_factor

        energy = numpy.cumsum(profile["DeltaEnergy_kWh"]) + [self.state_vars["SOE_kWh"]] * len(
            profile["DeltaEnergy_kWh"])

        #energy = numpy.cumsum(profile["DemandForecast_kW"])+[self.state_vars["SOE_kWh"]]*len(profile["DemandForecast_kW"])

        if (max(energy) > self.state_vars["MaxSOE_kWh"]) | (min(energy)<self.state_vars["MinSOE_kWh"]):
            for ii in range(len(profile["DemandForecast_kW"])):
                if ii == 0:
                    prev_soe = self.state_vars["SOE_kWh"]
                else:
                    prev_soe = profile["EnergyAvailableForecast_kWh"][ii - 1]
                profile["EnergyAvailableForecast_kWh"][ii],\
                profile["DemandForecast_kW"][ii], \
                profile["DeltaEnergy_kWh"][ii]    = self.update_soe(profile["DemandForecast_kW"][ii],prev_soe)
        else:
            profile["EnergyAvailableForecast_kWh"] = energy

        return profile #schedule




##############################################################################
class PVResource(SundialResource):
    """
    Inherits from SundialResource.  Defines objective functions, state_vars, etc specific to PVCtrlNodes
    """

##############################################################################
class LoadShiftResource(SundialResource):
    """
    Inherits from SundialResource.  Defines objective functions, state_vars, etc specific to LoadShiftCtrlNodes
    """

    ##############################################################################
    def __init__(self, resource_cfg, gs_start_time):
        SundialResource.__init__(self, resource_cfg, gs_start_time)

        # define a bunch of LoadShift-specific end points to update
        self.forecast_update_list.extend(["LoadShiftOptions_kW",
                                          "LoadShiftOptions_t_str"])

    ##############################################################################
    def init_forecast_vars(self, gs_start_time):
        """
        intializes forecast variables in the state_vars data structure
        :return: None
        """
        # FIXME - shape of load shift options is hardcoded
        forecast_vars = SundialResource.init_forecast_vars(self, gs_start_time)

        init_forecast = [[0.0] * self.pts_per_schedule]*10
        init_timestamps = [datetime.strptime(gs_start_time, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=pytz.UTC) +
                           timedelta(minutes=t) for t in range(0,
                                                               SSA_SCHEDULE_DURATION * MINUTES_PER_HR,
                                                               SSA_SCHEDULE_RESOLUTION)]

        forecast_vars.update({"LoadShiftOptions_kW": numpy.array(init_forecast),
                              "LoadShiftOptions_t": init_timestamps,
                              "OrigLoadShiftOptions_kW": init_forecast,
                              "LoadShiftOptions_t_str": [t.strftime("%Y-%m-%dT%H:%M:%S") for t in init_timestamps]})
        return forecast_vars

    ##############################################################################
    def load_scenario(self,
                      load_options = [[0.0]*SSA_PTS_PER_SCHEDULE]*10,
                      t = None):
        self.state_vars["LoadShiftOptions_kW"] = numpy.array(load_options)
        self.state_vars["LoadShiftOptions_kW"] = load_options
        self.state_vars["LoadShiftOptions_t_str"]  = t
        self.state_vars["LoadShiftOptions_t"]  = [datetime.strptime(ts,
                                                                    "%Y-%m-%dT%H:%M:%S").replace(tzinfo=pytz.UTC)
                                                  for ts in t]
        self.state_vars["DemandForecast_t"]    = [datetime.strptime(ts,
                                                                    "%Y-%m-%dT%H:%M:%S").replace(tzinfo=pytz.UTC)
                                                  for ts in t]


##############################################################################
class BaselineLoadResource(SundialResource):
    """
    Inherits from SundialResource.  Defines objective functions, state_vars, etc specific to Load resource_types
    """

##############################################################################
class SundialSystemResource(SundialResource):
    """
    Inherits from SundialResource.  Defines objective functions, state_vars, etc specific to "System" resource types
    """

    ##############################################################################
    def __init__(self, resource_cfg, gs_start_time):
        SundialResource.__init__(self, resource_cfg, gs_start_time)
        self.update_required = 1  # Temporary fix.  flag that indicates if the resource profile needs to be updated between SSA iterations

        # set up the specific set of objective functions to apply for the system
        self.obj_fcns = [EnergyCostObjectiveFunction(desc="EnergyPrice", fname="energy_price_data.xlsx"),
                         #LoadShapeObjectiveFunction(desc="LoadShape", fname="loadshape_data_load.xlsx"),
                         DemandChargeObjectiveFunction(desc="DemandCharge", cost_per_kW=10.0),
                         dkWObjectiveFunction(desc="dkW")]



        #self.obj_fcn_init = ['EnergyCostObjectiveFunction(desc="EnergyPrice", fname="energy_price_data.xlsx")',
        #                     #'LoadShapeObjectiveFunction("loadshape_data_load.xlsx", schedule_timestamps, self.sundial_resources.sim_offset, "LoadShape")']#,
        #                     #'LoadShapeObjectiveFunction(desc="LoadShape", fname="loadshape_data_load.xlsx")',
        #                     'DemandChargeObjectiveFunction(desc="DemandCharge", cost_per_kW=10.0, threshold=self.tariffs["demand_charge_threshold"])',
        #                     'dkWObjectiveFunction(desc="dkW")']
        #self.obj_fcns = []

        # instantiate objective functions -
        # this should load any data files, etc.
        # , schedule_timestamps, self.sundial_resources.sim_offset


    ############################
    def load_scenario(self):
        """
        Used to populate with some known values for testing.
        This (1) intializes data structures, setting to zero; (2) recursively calls the init_test_values routine in
        children nodes; and then (3) sums data initialized from children into the parent node
        :param length: length of a schedule
        :return: None
        """
        self.update_sundial_resource()

##############################################################################
class SundialResource_to_SiteManager_lookup_table():
    """
    Maps from SiteManager / DERDevice data models to SundialResource data models
    """

    def __init__(self, sundial_resource, device_list, sitemgr_list = [], use_volttron=0):
        """
        This acts like a record.  One field is a sundial_resoource.  The other field is a list of associated
        end point devices.  Provides a method to map to each other.
        :param sundial_resource:
        :param device_list:
        :param sitemgr_list:
        :param use_volttron:
        """
        self.sundial_resource = sundial_resource
        self.device_list      = device_list

        if use_volttron == 1:
            _log.info("SDR: Setting up agents")
            for device in self.device_list:
                device.update({"isAvailable": 0})

                if device["Use"] == "Y":
                    for site in sitemgr_list:
                        if site["identity"] == device["AgentID"]:
                            _log.info("SunDial Resource: Agent " + device["AgentID"] + " configured successfully")
                            device["isAvailable"] = 1
                            break

                    if site["identity"] != device["AgentID"]:
                        # error trapping - make sure that the agent & associated device are valid entries
                        _log.info("SunDial Resource: Warning - Agent " + device["AgentID"] + " not found.  Skipping...")
                else:
                    _log.info("SunDial Resource: Agent " + device["AgentID"] + " set to ignore.  Skipping...")

##############################################################################
def build_SundialResource_to_SiteManager_lookup_table(sundial_resource_cfg,
                                                      sundial_resources,
                                                      SDR_to_SM_table=[],
                                                      sitemgr_list = [],
                                                      use_volttron=0):
    """
    Initializes a SundialResource_to_SiteManager_lookup_table - which maps devices to SundialResources
    Recursively traverses the SundialResource tree.  At each node, if the SundialResource has associated end point
    devices, it creates a new entry in SDR_to_SM_table that maps the SundialResource to DERDevices
    :return: SDR_to_SM_table - of type SundialResource_to_SiteManager_lookup_table()
    """
    _log.info("In BuildSundialResource lookup - Use Volttron="+str(use_volttron))
    for virtual_plant in sundial_resource_cfg["VirtualPlantList"]:
        if virtual_plant["Use"] == "Y":
            build_SundialResource_to_SiteManager_lookup_table(virtual_plant,
                                                              sundial_resources,
                                                              SDR_to_SM_table,
                                                              sitemgr_list,
                                                              use_volttron)

    if sundial_resource_cfg["DeviceList"] != []:  # does this SundialResource have associated end point devices?
        # i.e., is this a terminal node in the resource tree?
        # then set up a record that stores SundialResources and DERDevice references
        resource_match = SundialResource.find_resource(sundial_resources, sundial_resource_cfg["ID"])
        tmp_val = SundialResource_to_SiteManager_lookup_table(resource_match, sundial_resource_cfg["DeviceList"], sitemgr_list, use_volttron)
        _log.info(tmp_val.sundial_resource.resource_id + ":" + str(tmp_val.device_list))
        SDR_to_SM_table.extend([tmp_val])

    return SDR_to_SM_table




##############################################################################
def export_schedule(profile, timestamps):
    """
    This routine copies a profile from a SundialResourceProfile data structure to the SundialResource data structure
    It is called at the completion of optimization, once the least_cost_soln has been found.  The least_cost_soln then
    becomes the sundial_resource's active schedule
    :param profile:
    :return:
    """
    #for virtual_plant in self.virtual_plants:
    #    self.virtual_plants.append(SundialResourceProfile(virtual_plant))

    for virtual_plant in profile.virtual_plants:
        export_schedule(virtual_plant, timestamps)

    profile.sundial_resources.schedule_vars["DemandForecast_kW"] = profile.state_vars["DemandForecast_kW"]
    profile.sundial_resources.schedule_vars["EnergyAvailableForecast_kWh"] = profile.state_vars["EnergyAvailableForecast_kWh"]
    profile.sundial_resources.schedule_vars["DeltaEnergy_kWh"] = profile.state_vars["DeltaEnergy_kWh"]
    profile.sundial_resources.schedule_vars["timestamp"] = copy.deepcopy(timestamps)
    profile.sundial_resources.schedule_vars["total_cost"] = profile.total_cost

    for obj_fcn in profile.sundial_resources.obj_fcns:
        profile.sundial_resources.schedule_vars[obj_fcn.desc] = obj_fcn.get_obj_fcn_data()

    pandas.options.display.float_format = '{:,.1f}'.format

    demand_df = pandas.DataFrame(data=[profile.sundial_resources.schedule_vars["DemandForecast_kW"],
                                       profile.sundial_resources.schedule_vars["EnergyAvailableForecast_kWh"]]).transpose()
    demand_df.columns = ["Demand-"+profile.sundial_resources.resource_id, "Energy-"+profile.sundial_resources.resource_id]
    demand_df.index = pandas.Series(profile.sundial_resources.schedule_vars["timestamp"])

    print(demand_df)

    pass

if __name__ == "__main__":

    # Unused.
    print(dir())
