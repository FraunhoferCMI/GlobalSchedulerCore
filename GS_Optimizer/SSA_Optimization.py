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

from math import floor, exp
import copy
import json
import csv
import sys
import pytz
import numpy
import pandas
from random import *
from SunDialResource import SundialSystemResource, SundialResource, SundialResourceProfile, export_schedule
from datetime import datetime, timedelta
import logging
from gs_identities import *
from gs_utilities import get_schedule

_log = logging.getLogger("SSA")

MINUTES_PER_HR = 60

############################
class SimulatedAnnealer():

    def __init__(self):
        # SSA configuration parameters:
        self.init_run    = 1            # number of runs to estimate initial temperature and weight
        self.nIterations = 100000           # Number of iterations
        self.temp_decrease_pd = 1500 # Number of iterations betweeen temperature decrease
        self.jump_decrease_pd = 30 # Number of iterations betweeen jump size decrease
        self.init_jump        = 1.0 #0.5 # initial maximum jump
        self.fract_jump       = 0.95 # amount by which jump is decreased every jump_decrease_pd steps
        self.fract_T          = 0.85
        self.O2T              = 0.5 #05  # Conversion of objective function into initial T


        self.display_pd = 5000; # update output for printing m and drawning

        self.tResolution_min          = SSA_SCHEDULE_RESOLUTION # time resolution of SSA optimizer control signals, in minutes
        self.optimizationPd_hr        = SSA_SCHEDULE_DURATION # period of the SSA time horizon, in hrs
        self.nOptimizationPtsPerPd    = SSA_PTS_PER_SCHEDULE

        self.persist_lowest_cost = 0 # flag to indicate whether to use keep previous solution if cost was lower.

    ############################
    def scale_battery_weights(self, max_ess_energy, weight_disch, tResolution_hr):
        """
        NOT CURRENTLY USED
        Normalizes battery charge / discharge commands to the size of the energy
        storage system.

        As currently implemented, the function limit checks that ESS value at
        the end of the optimization period is less than capacity, and greater
        than zero.  This is a little bit of a shortcut - it does not check if
        battery exceeds limits DURING the optimization period (a separate
        limit check is performed when power commands are generated).  This may
        be (a) inefficient; and (b) introduce a bias in the weight maps that
        get generated.  Future mod should also parameterize upper and lower
        limits on ESS targets (i.e., rather than implicitly defining SOC range as 0-100%).

        :return:
        """

        discharge_weight_factor = min(1, max_ess_energy/abs(sum(weight_disch*tResolution_hr)))
        return weight_disch * discharge_weight_factor

    ############################
    def calc_jump(self, x, jump, lb, ub):
        """
        Returns a new value for an SSA weight by perturbing the current weight x by a random amount between +/- jump.
        The new weight is subject to upper and lower bounds set by ub and lb, respectively
        :return:
        """
        y2 = (random() - .5) * 2.0 * jump
        y3 = x + y2
        #y4 = z - y2
        return max(min(y3,ub), lb)   #, max(min(y4,ub), lb)

    ############################
    def get_resource(self, sundial_profiles, resource_type):
        """
        searches a SundialProfile tree for instances whose resource_types that matches SundialProfile.resource_type
        :param sundial_profiles: an instance of SundialProfile class
        :param resource_type: resource type (e.g., ESSCtrlNode, PVCtrlNode, LoadShiftCtrlNode, Load, or System)
        :return: returns a list of SundialProfile class instances matching resource_type
        """
        resources = [] #None

        for virtual_plant in sundial_profiles.virtual_plants:
            resources.extend(self.get_resource(virtual_plant, resource_type))

        if resource_type == sundial_profiles.sundial_resources.resource_type:
            _log.info(sundial_profiles.sundial_resources.resource_id+" is a "+sundial_profiles.sundial_resources.resource_type)
            resources.append(sundial_profiles)
        return resources



    ############################
    def copy_profile(self, source, target):
        """
        does a deep copy of a SundialProfile instance from source to target by recursively traversing
        nodes.  Source and target must have the same tree topology
        :param source: SunDialProfile instance
        :param target: SunDialProfile instance
        :return: target - SundialProfile instance
        """
        for (source_child, target_child) in zip(source.virtual_plants, target.virtual_plants):
            target_child = self.copy_profile(source_child, target_child)

        if target.sundial_resources.update_required == 1:
            target.copy_profile(source)

        return target



    ############################
    def run_ssa_optimization(self, sundial_resources, timestamps):

        """
        Executes simulated Annealing optimization algorithm.

        Inputs:
        - sundial_resources is a SundialResource data object that acts as a container for information about the system
          we are trying to optimize.  Each node in the sundial_resources tree represents an aggregation of DERs whose behavior is driven by a
          common set of objective functions.  A sundial_resource node needs to be populated with:
           - in state_vars - a baseline forecast for the resource's net demand over the optimization period defined by
             SSA_SCHEDULE_DURATION, at time resolution of SSA_SCHEDULE_RESOLUTION
           - in state_vars - information about the resource's current state (E.g., battery SOE) and resource information
           - a list of one or more objective functions and/or constraints that equate the resource's behavior to cost,
             and associated cost parameters
        - timestamps - used to provide a time reference for schedules that get generated.

        Outputs:
        The primary output of run_ssa_optimization is schedule information for each resource in the Sundial system that
        reflects a global least-cost solution for the given combination of forecasts, objective functions, and starting
        conditions.  On completion, run_ssa_optimization
        (1) dumps the orgiinal and new schedule profiles to a csv file - each row is a different profile,
            columns represent time
        (2) copies least_cost_soln to the schedule_vars data structure to each resource in the sundial_resources tree.
            schedule_vars is used to determine set points in the Global Scheduler

        Overview of run_ssa_optimization:

        For each resource in the sundial_resources tree, run_ssa_optimization instantiates three different
        SundialResourceProfile instances - "init_soln", "least_cost_soln", and "current_soln"
        A SundialResourceProfile is a class that holds information about a proposed load shape.
        - init_soln - corresponds to the initial values for the optimization pass
        - current_soln - corresponds to proposed load profile for the current test case
        - least_cost_soln - corresponds to the least cost load profile that has been found during this optimization pass

        The simulated annealing algorithm references the following parameters:
        - self.nIterations - Number of iterations to
        - self.temp_decrease_pd - Number of iterations betweeen temperature decrease
        - self.jump_decrease_pd - Number of iterations betweeen jump size decrease
        - self.init_jump - initial maximum jump
        - self.fract_jump - amount by which jump is decreased every jump_decrease_pd iterations
        - self.fract_T - amount by which temperature is decreased every temp_decrease_pd iterations
        - self.O2T  - Conversion of objective function cost into initial T

        Execution of the Simulated Annealing algorithm is as follows:
        1. Initialize init_soln, current_soln, and least_cost_soln to a set of common baseline profiles
        2. calculate cost of the initial solution.  This is used to establish T0 - the initial temperature of the system
        3. Iteratively seek a least-cost solution (based on self.nIterations)
           - periodically decrease temperature and jump size, based on configured parameters to "cool" the system
           - select a controllable resource. NOTE - current implementation assumes a single ESS
           - perturb a single point in the resource's current_soln profile by a random amount, constrained by jump
           - check to make sure that this change has not violated a constraint (e.g., exceed upper or lower bound on
             SOE).  modify profile if necessary
           - update other resource profiles, as necessary
           - calculate cost of the current_soln.
           - compare to cost of the least_cost_soln: if the proposed solution (current_soln) is least_cost, adopt this
             as the new least cost solution.  If cost is higher, adopt as the new least_cost_soln with a probability
             dictated by the system's temperature

        The current implementation implicitly assumes that the only controllable resource is a single ESS.  This is a
        a shortcut towards getting a minimum version running.  Modest changes would support multiple controllable
        resources.


        TODO - check relationship between delta and self.O2T - does delta need to be convereted to T??

        :param sundial_resources: A SundialResource instance - referencing to the top of the SundialResource tree for
        the system in question.
        :param timestamps: list of timestamps, length of SSA_PTS_PER_SCHEDULE, that correpond to the time at which
        schedule_var data points are valid
        :return: None
        """
        run_optimization = True
        use_recursive    = False

        # get an initial set of commands to seed the ssa process
        # then, set least_cost_soln AND current_soln to initiate the SSA
        init_soln = SundialResourceProfile(sundial_resources, timestamps)
        current_soln = SundialResourceProfile(sundial_resources, timestamps)
        least_cost_soln = SundialResourceProfile(sundial_resources, timestamps)
        final_soln      = SundialResourceProfile(sundial_resources, timestamps)

        # For convenience - this extracts specific resource types from the Sundial tree structure and puts them
        # in a flat list, grouped by resource type.  Just simplifies data handling, speeds execution, particularly
        # for simple system topology
        # Currently, we are only handling a single SundialResource per resource_type.
        try:
            self.load       = self.get_resource(current_soln, "Load")[0]
        except:
            self.load       = []
        try:
            self.load_shift = self.get_resource(current_soln, "LoadShiftCtrlNode")[0]
        except:
            self.load_shift = []
        self.pv         = self.get_resource(current_soln, "PVCtrlNode")[0]
        self.ess        = self.get_resource(current_soln, "ESSCtrlNode")[0]
        self.system     = self.get_resource(current_soln, "System")[0]

        self.ess_least_cost = self.get_resource(least_cost_soln, "ESSCtrlNode")[0]


        #### what I'm thinking is that you put in a for loop right here.
        ## it needs to change current solution to
        ## ESS - init solution
        ## system resources - next load shift option
        ## load - init solution
        ## pv - init solution
        ## load shift - next load shift option


        ## in the nIterations for loop - we are setting current solution to least cost solution
        ## but....

        ## need to have least_cost_soln - global, and least_cost_soln - for the current load shift profile

        if run_optimization == True:
            # set initial temperature
            T0   = abs(self.O2T*init_soln.cost)
            T    = T0;

            _log.info("Jump is: "+str(self.init_jump))
            _log.info("T is: "+str(T))
            _log.info("Init Least Cost Solution is: "+str(least_cost_soln.total_cost))

            copy_time   = 0.0
            constraint_time = 0.0
            cost_time = 0.0
            loop_time = 0.0

            rand_time = 0.0
            essupdate_time = 0.0
            sysupdate_time = 0.0


            t0 = datetime.now()

            jump = self.init_jump
            dirty_flag = True

            system_net_demand_baseline = self.system.state_vars["DemandForecast_kW"]

            # From the initial solution, follow the simulated annealing logic: disturb
            # 1 point and check if there is improvement.
            for ii in range(self.nIterations):

                if (ii % self.display_pd == 0): # for debug - periodically publish results
                    _log.info("Iteration "+str(ii)+": T="+str(T)+"; Least Cost Soln = "+str(least_cost_soln.total_cost))

                if ((ii+1) % self.jump_decrease_pd) == 0: # check if it's time to decrease jump size.
                    # decrease jump size
                    jump = jump*self.fract_jump
                    #print("ii = "+str(ii)+"; Jump decrease - jump = " + str(jump))

                if ((ii+1) % self.temp_decrease_pd) == 0: # check if it's time to decrease temperature
                    # decrease temperature, reset jump to the starting value from the last jump decrease
                    T         = self.fract_T*T
                    n         = floor(self.temp_decrease_pd/self.jump_decrease_pd)
                    jump = jump/(self.fract_jump**n)
                    #print("ii = "+str(ii)+"; Temp decrease - "+str(T)+"; jump = "+str(jump))
                    #print("ESS Weight is: " + str(self.ess.current_soln.weight))

                # FIXME - Much of the following is taking advantage of a simple system topology by directly referencing
                # FIXME - into system nodes.  The universal version should do much of the following by recursively
                # FIXME - traversing the SundialResource tree.

                # set the current test profile to the current least-cost solution
                if dirty_flag == True:  # copy only if the last solution was not accepted
                    current_soln = self.copy_profile(least_cost_soln, current_soln) # set current soln to least cost soln

                # Randomly perturb a single point by a random value dictated by the size of the jump parameter
                # FIXME: currently this just deals with battery charge / discharge instructions - not other resources
                # FIXME: e.g., PV curtailment
                ind = int(floor(random()*self.nOptimizationPtsPerPd))
                self.ess.state_vars["DemandForecast_kW"][ind] = self.calc_jump(self.ess.state_vars["DemandForecast_kW"][ind],
                                                                               jump*(self.ess.sundial_resources.state_vars["MaxDischargePwr_kW"]+self.ess.sundial_resources.state_vars["MaxChargePwr_kW"])/2,
                                                                               -1*self.ess.sundial_resources.state_vars["MaxDischargePwr_kW"],
                                                                               self.ess.sundial_resources.state_vars["MaxChargePwr_kW"])

                # Then: check for constraints.
                # TODO - right now, just checking for battery limit violations.  Eventually put in ability to include
                # TODO - additional constraints
                self.ess.state_vars    = self.ess.sundial_resources.check_constraints(self.ess.state_vars, ind)

                # then: update resources.
                if use_recursive == True:
                    # slower but generic solution
                    self.system.update_sundial_resource()
                else:
                    # faster but not generalized
                    # This is a shortcut
                    # update overall "system" with new ESS profile -subtract old ESS profile.  then add new profile
                    self.system.state_vars["DemandForecast_kW"] = system_net_demand_baseline + \
                                                                  self.ess.state_vars["DemandForecast_kW"]
                    self.system.state_vars["EnergyAvailableForecast_kWh"] = self.ess.state_vars["EnergyAvailableForecast_kWh"][:]

                if (0):
                    # removed for speed up
                    # Sanity check to make sure that constraint check is working.  probably unnecessary at this pont.
                    if max(self.ess.state_vars["EnergyAvailableForecast_kWh"])>(self.ess.sundial_resources.state_vars["MaxSOE_kWh"])+0.001:
                        _log.info("ii= "+str(ii)+": Max Constraint Error!!  "+str(max(self.ess.state_vars["EnergyAvailableForecast_kWh"])))

                    if min(self.ess.state_vars["EnergyAvailableForecast_kWh"])<(self.ess.sundial_resources.state_vars["MinSOE_kWh"])-0.001:
                        _log.info("ii= "+str(ii)+": Min Constraint Error!! - "+str(min(self.ess.state_vars["EnergyAvailableForecast_kWh"])))

                # Now calculate cost of the current solution and get timing for cumulative time on doing cost calcs.
                total_cost = current_soln.calc_cost()

                # Calculate delta cost between this test value and the current least cost solution
                delta = total_cost - least_cost_soln.total_cost

                dirty_flag = True
                if delta < 0.0:
                    # Current test value is a new least-cost solution.  Use this!
                    least_cost_soln = self.copy_profile(current_soln, least_cost_soln)  # set least cost soln to current soln
                    dirty_flag = False

                elif delta > 0.0:
                    # Current test value is worse than current least-cost solution
                    # Adopt the current test value along a probabilistic
                    # distribution according to SSA parameters
                    # NOTE -- T must be greater than zero!!!  Need to watch out for this depending on obj fcn calcs.
                    th = exp(-delta / T)
                    r  = random()
                    if r < th:
                        #print("non best solution adopted.  r="+str(r)+"; Th = "+str(th)+"; T="+str(T)+"; delta = "+str(delta))
                        least_cost_soln = self.copy_profile(current_soln, least_cost_soln)  # set least cost soln to current soln
                        dirty_flag = False

                # end of main loop (nIterations)

            t8 = datetime.now()
            deltaT = t8 - t0
            total_time = deltaT.total_seconds()

            _log.info("least cost soln is "+str(least_cost_soln.total_cost))
            _log.info("total time: "+str(total_time))

        # dump some data to a csv file
        filename =  os.path.join(GS_ROOT_DIR, "ssa_results.csv")
        if not os.path.exists(filename):
            my_file = open(filename, 'w+')

        csv_name = (filename)

        with open(csv_name, 'wb') as csvfile:
            results_writer = csv.writer(csvfile)
            results_writer.writerow([t.strftime("%Y-%m-%dT%H:%M:%S") for t in timestamps])
            results_writer.writerow(least_cost_soln.state_vars["DemandForecast_kW"])
            results_writer.writerow(init_soln.state_vars["DemandForecast_kW"])
            results_writer.writerow(self.ess_least_cost.state_vars["DemandForecast_kW"])
            results_writer.writerow(self.ess_least_cost.state_vars["EnergyAvailableForecast_kWh"])
            results_writer.writerow(self.pv.state_vars["DemandForecast_kW"])

            if self.load != []:
                results_writer.writerow(self.load.state_vars["DemandForecast_kW"])
            #results_writer.writerow(self.pv.init_solution.schedule)
            #results_writer.writerow(self.demand.least_cost_soln.schedule)

        return least_cost_soln

    ############################
    def search_single_option(self, sundial_resources, timestamps):
        """
        searches a single load shape to find a least cost solution.
        It is assumed that load shift options are not available
        :param sundial_resources: sundial resource tree, with system as a top node, of type SundialSystemResource
        :param timestamps: schedule time stamps
        :return: None
        """
        least_cost_soln = self.run_ssa_optimization(sundial_resources, timestamps)
        # exports least_cost_soln to sundial_resources.schedule_vars
        if (self.persist_lowest_cost == 0):
            _log.info("SSA: New set of timestamps - generating new solution")
            export_schedule(least_cost_soln, timestamps)
        elif least_cost_soln.total_cost<sundial_resources.schedule_vars["total_cost"]:
            _log.info("SSA: Lower Cost Solution found - using new solution")
            _log.info("new soln is"+str(least_cost_soln.total_cost)+"; old soln = "+str(sundial_resources.schedule_vars["total_cost"]))
            export_schedule(least_cost_soln, timestamps)
        else:
            _log.info("SSA: Lower cost solution not found - using previous solution (cost ="+str(sundial_resources.schedule_vars["total_cost"])+")")
            export_schedule(least_cost_soln, timestamps, update=False)


    ############################
    def search_load_shift_options(self, sundial_resources, loadshift_resources, timestamps):
        """
        searches multiple load shift options to find a least cost solution.
        It is assumed that load shift options are available and enabled
        :param sundial_resources: sundial resource tree, with system as a top node, of type SundialSystemResource
        :param loadshift_resources: reference to the load shift resource node of type LoadShiftResource Class
        :param timestamps: schedule time stamps
        :return: None
        """

        least_cost_soln_list      = []
        least_cost_soln_cost_list = []


        for ii in range(0, len(loadshift_resources.state_vars["LoadShiftOptions_kW"])):
            _log.info("*************** Searching Load Shift Option "+str(ii+1)+" of "+
                      str(len(loadshift_resources.state_vars["LoadShiftOptions_kW"]))+"***************************")
            loadshift_resources.state_vars["DemandForecast_kW"] = loadshift_resources.state_vars["LoadShiftOptions_kW"][ii]
            sundial_resources.state_vars["DemandForecast_kW"]   = sundial_resources.state_vars["LoadShiftOptions_kW"][ii]
        #    sundial_resources.interpolate_forecast(schedule_timestamps)
            least_cost_soln = self.run_ssa_optimization(sundial_resources,timestamps)
            least_cost_soln_list.append(least_cost_soln)
            least_cost_soln_cost_list.append(least_cost_soln.total_cost)

            _log.info("*************** Finished Searching Load Shift Option " + str(ii+1) + " of " +
                      str(len(loadshift_resources.state_vars[
                                  "LoadShiftOptions_kW"])) + ", results are: ***************************")
            export_schedule(least_cost_soln, timestamps)
            # now copy the least cost solution for this load shift option to the lcs list
            # once all load shift options have been searched, we will choose the global least cost
            #least_cost_soln_list.append(self.copy_profile(least_cost_soln, final_soln))
            #
            # end of main loop (n load shift options)

        # now find global least cost solution
        lcs_ind         = least_cost_soln_cost_list.index(min(least_cost_soln_cost_list))
        least_cost_soln = least_cost_soln_list[lcs_ind]

        _log.info("ind is "+str(lcs_ind))
        #_log.info("")
        _log.info("LCS is "+str(least_cost_soln_cost_list[lcs_ind]))

        # exports least_cost_soln to sundial_resources.schedule_vars
        if (self.persist_lowest_cost == 0):
            _log.info("SSA: New set of timestamps - generating new solution")
            export_schedule(least_cost_soln, timestamps)
        elif least_cost_soln.total_cost<sundial_resources.schedule_vars["total_cost"]:
            _log.info("SSA: Lower Cost Solution found - using new solution")
            _log.info("new soln is"+str(least_cost_soln)+"; old soln = "+str(sundial_resources.schedule_vars["total_cost"]))
            export_schedule(least_cost_soln, timestamps)
        else:
            _log.info("SSA: Lower cost solution not found - using previous solution")


        loadshift_resources.schedule_vars["SelectedProfile"] = loadshift_resources.state_vars["IDList"][lcs_ind]


def get_dispatch_schedule(gs_start_time, cfg_file, shift_to_start_of_day, tstep=45, nIterations=1):
    if shift_to_start_of_day == True:
        gs_start_time = gs_start_time.replace(hour=0, minute=0, second=0)
    gs_start_time_str = gs_start_time.strftime("%Y-%m-%dT%H:%M:%S")
    _log.info("Initializing SundialSystemResource with start time: {}".format(gs_start_time_str))

    resource_cfg_list = json.load(open(cfg_file, 'r'))
    sundial_resources = SundialSystemResource(resource_cfg_list, gs_start_time_str)
    load_scenarios(sundial_resources, gs_start_time)
    system_tariff = {"threshold": 500} #DEMAND_CHARGE_THRESHOLD}
    solarPlusStorage_tariff = {"threshold": 150}

    ##### This section replicates the periodic call of the optimizer ######
    # calls the actual optimizer.
    _log.info("Initializing optimizer")
    toffset = 0
    optimizer = SimulatedAnnealer()
    last_forecast_start = datetime(1900, 1, 1, tzinfo=pytz.UTC)


    _log.info("Starting optimization")
    for ii in range(0,nIterations):
        cur_time = gs_start_time.replace(tzinfo=pytz.UTC)+timedelta(minutes=toffset)
        if ALIGN_SCHEDULES == True:
            if sundial_resources.schedule_vars["schedule_kW"] == {}:
                schedule_start_time = cur_time.replace(minute=0, second=0)
            else:
                schedule_start_time = cur_time.replace(minute=0, second=0) + timedelta(hours=1)

        else:
            schedule_start_time = cur_time
        schedule_timestamps = [schedule_start_time +
                               timedelta(minutes=t) for t in range(0,
                                                                   SSA_SCHEDULE_DURATION * MINUTES_PER_HR,
                                                                   SSA_SCHEDULE_RESOLUTION)]
        print(schedule_timestamps)

        try:
            try:
                loadshift_resources = sundial_resources.find_resource_type("LoadShiftCtrlNode")[0]
            except:
                loadshift_resources = []

            print("load shift options")
            print(loadshift_resources.state_vars["LoadShiftOptions_kW"])
            print(loadshift_resources.state_vars["OrigLoadShiftOptions_t_str"])
        except:
            pass
        sundial_resources.interpolate_forecast(schedule_timestamps)
        sundial_resources.interpolate_soe(schedule_timestamps, cur_time)

        if sundial_resources.state_vars["DemandForecast_kW"][0] != None:
            if ALIGN_SCHEDULES == True:
                forecast_start = schedule_timestamps[0]
            else:
                pv_resources = sundial_resources.find_resource_type("PVCtrlNode")[0]
                forecast_start = datetime.strptime(pv_resources.state_vars["OrigDemandForecast_t_str"][0],
                                                   "%Y-%m-%dT%H:%M:%S").replace(tzinfo=pytz.UTC)

            if forecast_start == last_forecast_start:
                optimizer.persist_lowest_cost = 1
            else:
                optimizer.persist_lowest_cost = 0
            last_forecast_start = forecast_start

            sundial_resources.cfg_cost(schedule_timestamps,
                                       system_tariff = system_tariff,
                                       solarPlusStorage_tariff = solarPlusStorage_tariff)
            #optimizer.search_load_shift_options(sundial_resources, loadshift_resources, schedule_timestamps)
            optimizer.search_single_option(sundial_resources, schedule_timestamps)
        else:
            _log.info("No valid forecasts found - skipping")


        toffset += tstep

    return sundial_resources


def load_scenarios(cur_resource, gs_start_time):
    ess_resources = cur_resource.find_resource_type("ESSCtrlNode")[0]
    pv_resources = cur_resource.find_resource_type("PVCtrlNode")[0]

    try:
        solarPlusStorage_resources = cur_resource.find_resource_type("SolarPlusStorageCtrlNode")[0]
    except:
        solarPlusStorage_resources = []

    system_resources = cur_resource.find_resource_type("System")[0]
    try:
        loadshift_resources = cur_resource.find_resource_type("LoadShiftCtrlNode")[0]
    except:
        loadshift_resources = []
    try:
        load_resources = cur_resource.find_resource_type("Load")[0]
    except:
        load_resources = []

    ALIGN_SCHEDULES = True
    _log.info("initializing variables")
    forecast_timestamps = [(gs_start_time.replace(minute=0, second=0) +
                            timedelta(minutes=t)).strftime("%Y-%m-%dT%H:%M:%S") for t in range(0,
                                                                                               SSA_SCHEDULE_DURATION * MINUTES_PER_HR,
                                                                                               SSA_SCHEDULE_RESOLUTION)]

    #### Just load with example values - ######
    ess_forecast = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                    0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                    0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                    0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

    ess_resources.load_scenario(init_SOE=500.0,
                                max_soe=1000.0 * ESS_MAX,
                                min_soe=1000.0 * ESS_MIN,
                                max_chg=500.0,
                                max_discharge=500.0,
                                chg_eff=0.93,
                                dischg_eff=0.93,
                                demand_forecast=ess_forecast,
                                t=forecast_timestamps)

    # forecast, indexed to 00:00
    # pv_forecast_base = [0,0,0,0,0,0,0,0,-5.25, -19.585, -95.39, -169.4, -224,-255, -276, -278, -211, -124, -94, -61, -15, -0.45, 0,0]
    scale = 1.0
    pv_forecast_base = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, -2.49, -11.39, -7.21, -12.04, -21.49, -29.84, -29.07, -18.27,
                        -7.69, -2.71, -0.37, 0, 0, 0]
    pv_forecast_base = [scale * v for v in pv_forecast_base]


    # demand_forecast_base = [142.4973, 142.4973, 142.4973, 145.9894,
    #                        160.094, 289.5996, 339.7752, 572.17,
    #                        658.6025, 647.2883, 650.1958, 639.7053,
    #                        658.044, 661.158, 660.3772, 673.1098,
    #                        640.9227, 523.3306, 542.7008, 499.3727,
    #                        357.9398, 160.0936, 145.9894, 142.4973]

    demand_forecast_base = [467, 436, 450, 341, 326, 321,
                            317, 319, 391, 487, 551, 574,
                            579, 584, 580, 551, 535, 535,
                            513, 486, 454, 445, 446, 393]
    # demand_forecast_base = [0.0]*24
    demand_forecast_base = [scale * v for v in demand_forecast_base]

    if shift_to_start_of_day == False:
        # shift starting point to match up to current hour
        forecast_start_hour = datetime.strptime(forecast_timestamps[0], "%Y-%m-%dT%H:%M:%S").hour
        pv_forecast = pv_forecast_base[forecast_start_hour:len(pv_forecast_base)]
        pv_forecast.extend(pv_forecast_base[0:forecast_start_hour])

        demand_forecast = demand_forecast_base[forecast_start_hour:len(demand_forecast_base)]
        demand_forecast.extend(demand_forecast_base[0:forecast_start_hour])

    else:  # start sim at start of day.
        pv_forecast = pv_forecast_base
        demand_forecast = demand_forecast_base

    _log.info("Load scenarios")
    scale = 1.1
    pv_resources.load_scenario(demand_forecast=pv_forecast,
                               pk_capacity=500.0,
                               t=forecast_timestamps)
    print(pv_forecast)

    if load_resources != []:
        load_resources.load_scenario(demand_forecast=demand_forecast,
                                     pk_capacity=1000.0,
                                     t=forecast_timestamps)

    try:
        if loadshift_resources != []:
            ls = pandas.read_excel("loadshift_example.xlsx", header=None)
            print(ls)
            load_shift_options = [ls[ii].tolist() for ii in range(0, 13)]
            loadshift_resources.load_scenario(load_options=load_shift_options,
                                              t=forecast_timestamps)
    except:
        pass

    # if solarPlusStorage_resources != []:
    #    solarPlusStorage_resources.load_scenario()

    system_resources.load_scenario()

    #########

if __name__ == '__main__':
    # Entry point for script

    ##### This section replicates the initialization of the system (done one time, when system starts up) ######

    # the following is a rough demo of how a system gets constructed.
    # this is a hard-coded version of what might happen in the executive
    # would eventually do all this via external configuration files, etc.

    shift_to_start_of_day = False

    _log.setLevel(logging.INFO)
    msgs = logging.StreamHandler(stream=sys.stdout)
    #msgs.setLevel(logging.INFO)
    #_log.addHandler(msgs)


    gs_start_time = datetime.utcnow().replace(microsecond=0)
    if shift_to_start_of_day == True:
        gs_start_time = gs_start_time.replace(hour=0, minute=0, second=0)
    gs_start_time_str = gs_start_time.strftime("%Y-%m-%dT%H:%M:%S")

    day_ahead_resources = get_dispatch_schedule(gs_start_time,
                                                "../cfg/SystemCfg/DayAheadSundialSystemConfiguration.json",
                                                shift_to_start_of_day)

    inds = [v.hour for v in day_ahead_resources.schedule_vars['timestamp']]
    #pandas.DataFrame(data = day_ahead_resources.schedule_vars['DemandForecast_kW'], index = day_ahead_resources.schedule_vars['timestamp']).to_csv("myloadshape.csv")


    pandas.DataFrame(data={'0': day_ahead_resources.schedule_vars['DemandForecast_kW'],
                           '1': day_ahead_resources.schedule_vars['weights']},
                             index=day_ahead_resources.schedule_vars['timestamp']).to_csv('myloadshape.csv')

    sundial_resources   = get_dispatch_schedule(gs_start_time,
                                                "../cfg/SystemCfg/EmulatedSundialSystemConfiguration.json",
                                                shift_to_start_of_day)
