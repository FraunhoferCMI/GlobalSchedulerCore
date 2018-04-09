import numpy
import pandas
import os
from datetime import datetime, timedelta
import csv


##############################################################################
class ObjectiveFunction():

    ##############################################################################
    def __init__(self, fname, schedule_timestamps, sim_offset=timedelta(0)):
        """
        loads a file of dates / values.  retrieves a pandas data frame of for the specified time window.
        1. load data file
        2. retrieve data corresponding to time window
        3. resample if necessary
        :param self:
        :return:
        """
        #### Read data from a file into a data structure that stores the complete time series.
        obj_fcn_data = pandas.read_excel(fname, header=0, index_col=0)
        offset_ts = [t +sim_offset for t in schedule_timestamps]   #todo - revist for non sim case
        #### Find the time window corresponding to the current set of timestamps:
        self.cur_cost = obj_fcn_data.loc[offset_ts].interpolate(method='linear')
        #return cur_data


##############################################################################
class EnergyCostObjectiveFunction(ObjectiveFunction):

    ##############################################################################
    def obj_fcn_cost(self, profile):
        demand = numpy.array(profile)
        cost = sum(self.cur_cost["Cost"] * demand)
        return cost


##############################################################################
class DemandChargeObjectiveFunction():

    ##############################################################################
    def __init__(self, cost_per_kW, threshold):
        # fname, schedule_timestamps, sim_offset=timedelta(0)
        self.threshold   = threshold
        self.cost_per_kW = cost_per_kW


    ##############################################################################
    def obj_fcn_cost(self, profile):
        """
        placeholder for a function that calculates a demand charge for a given net demand profile
        :return: cost of executing the profile, in $
        """
        #demand = numpy.array(profile)

        max_demand = max(profile)
        if max_demand > self.threshold:
            cost = self.cost_per_kW * (max_demand - self.threshold)
        else:
            cost = 0.0
        return cost


##############################################################################
class LoadShapeObjectiveFunction(ObjectiveFunction):

    ##############################################################################
    def obj_fcn_cost(self, profile):
        """
        imposes a cost for deviations from a target load shape.
        cost is calculated as square of the error relative to the target load shape.
        :return: cost of executing proposed profile, in $
        """
        price = 10.0  # sort of arbitrary.    objfcn_params.loadshape.weight;
        demand = numpy.array(profile)

        err = (demand - self.cur_cost["Load"]) ** 2
        cost = sum(err) * price
        return cost


##############################################################################
def cfg_fcns():
    """
    sample script for testing
    (1) Set demand equal to a demand profile - interpreted as demand as a fcn of time, in kW
    (2) Set obj_fcn_cfgs equal to a list of constructors for objective functions that you wish to apply
    :return: cost - the total cost of implementing the target profile
             obj_fcns - list of instances of target objective functions

    """
    schedule_timestamps = [datetime(year=2018, month=1, day=1, hour=10, minute=0, second=0) +
                           timedelta(hours=t) for t in range(0, 8)]

    demand = [100, 200, 300, 400, 500, 600, 500, 400]
    #obj_fcn_cfg
    obj_fcn_cfgs = ['EnergyCostObjectiveFunction("energy_price_data.xlsx", schedule_timestamps)',
                    'EnergyCostObjectiveFunction("cpp_data.xlsx", schedule_timestamps)',
                    'LoadShapeObjectiveFunction("loadshape_data.xlsx", schedule_timestamps)',
                    'DemandChargeObjectiveFunction(10.0, 200.0)']

    obj_fcns = []
    for obj_fcn in obj_fcn_cfgs:
        obj_fcns.append(eval(obj_fcn))

    cost = []
    for obj_fcn in obj_fcns:
        cost.append(obj_fcn.obj_fcn_cost(demand))


    return obj_fcns, cost

##############################################################################
def obj_fcn_min_backfeed(self):
    """
    placeholder for a function that calculates a demand charge for a given net demand profile
    :return: cost of executing the profile, in $
    """
    max_bf = min(self.profile)

    # tier at 200, 100, 10
    cost = 0.0
    for p in self.profile:
        cost += max(-1 * p - 300.0, 0) * 100.0
        cost += max(-1 * p - 250.0, 0) * 50.0
        cost += max(-1 * p - 200.0, 0) * 25.0
        cost += max(-1 * p - 150.0, 0) * 10.0
        cost += max(-1 * p - 100.0, 0) * 10.0
        cost += max(-1 * p - 50.0, 0) * 10.0
        cost += max(-1 * p, 0.0) * 10.0

    # if max_bf < 0: #self.demand_threshold:
    #    cost = self.demand_cost_per_kW*(-1*max_bf)
    # else:
    #    cost = 0
    return cost


##############################################################################
def obj_linear_energy_cost(self):
    """
    placeholder for a function that calculates a demand charge for a given net demand profile
    :return: cost of executing the profile, in $
    """
    max_bf = min(self.profile)

    # tier at 200, 100, 10
    cost = 0.0

    pass

    return cost
