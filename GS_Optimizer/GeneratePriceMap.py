from math import floor, exp
import copy
import json
import csv
import sys
import pytz
import numpy
import pandas
from random import random
# from random import *
from SunDialResource import SundialSystemResource, SundialResource, SundialResourceProfile, export_schedule
from datetime import datetime, timedelta
import logging
from gs_identities import *
from gs_utilities import get_schedule

_log = logging.getLogger("PriceMap")

import pandas as pd


##############################################################################
def generate_cost_map(sundial_resources, pv_resources, n_time_steps = 24, search_resolution = 25):
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
    total_cost = 0
    epsilon    = 0.1 # minimum price difference required to differentiate a new price tier

    # TODO - only deals with system level costs
    # TODO - adjust for solar forecast

    # pprint(self.sundial_resources.state_vars["DemandForecast_kW"])

    lb = min(sundial_resources.state_vars["DemandForecast_kW"])
    ub = max(sundial_resources.state_vars["DemandForecast_kW"])

    # adjust upper and lower bound limits to extend past forecast
    if lb <0:
        lb *= 1.2
    else:
        lb *= 0.8
    if ub <0:
        ub *= 0.8
    else:
        ub *= 1.2

    # _log.info("UB = "+str(ub)+"; LB = "+str(lb))

    if (lb + 4* search_resolution > ub):  # indicates that no forecast is available, or demand lies over a narrow range
        # use a default value
        lb = -2000
        ub = 4000
    else:  # set ub and lb to the nearest search resolution
        lb = int(lb - (lb % search_resolution))
        ub = int(ub - (ub % search_resolution) + search_resolution)

    n_demand_steps = int((ub - lb) / search_resolution + 1)

    cost_map = pandas.DataFrame([[0.0] * n_demand_steps] * n_time_steps)
    test_profile = numpy.array([[0.0] * n_time_steps] * n_time_steps)
    for ii in range(0, n_time_steps):
        for jj in range(0, n_demand_steps):
            test_profile[ii][ii] = lb + jj * search_resolution
            # print(test_profile)
            sv = {}
            sv.update({"DemandForecast_kW": test_profile[ii]})
            #print(test_profile[ii])
            cost_map.iloc[ii][jj] = sundial_resources.calc_cost(sv, linear_approx=True)

    v = cost_map.diff(axis=1)
    v.columns = range(lb, ub + search_resolution, search_resolution)
    _log.debug(v)
    tiers = []
    for ii in range(0, n_time_steps):
        jj=max(0.0, lb+2*search_resolution)
        cnt = 0
        cur_generation = -1*pv_resources.state_vars["DemandForecast_kW"][ii]
        _log.info(cur_generation)
        tiers.append([{"LB": 0.0}])

        tiers[ii][cnt].update({"price": round(v.iloc[ii][jj - search_resolution] / search_resolution, 3)})
        while jj <= ub:
            same_tier = True
            while same_tier == True:
                if jj == ub:
                    same_tier = False
                    tiers[ii][cnt].update({"UB": jj+cur_generation})
                elif ((v.iloc[ii][jj] > v.iloc[ii][jj - search_resolution] + epsilon) or
                      (v.iloc[ii][jj] < v.iloc[ii][jj - search_resolution] - epsilon)):
                    if (jj - search_resolution+cur_generation) != tiers[ii][cnt]["LB"]:
                        tiers[ii][cnt].update({"UB": jj - search_resolution+cur_generation})
                        cnt += 1
                        tiers[ii].append({"LB": jj - search_resolution+cur_generation})
                    tiers[ii][cnt].update({"price": round(v.iloc[ii][jj] / search_resolution, 3)})
                    same_tier = False
                jj += search_resolution
    return tiers




if __name__ == '__main__':
    # Entry point for script

    ##### This section replicates the initialization of the system (done one time, when system starts up) ######

    # the following is a rough demo of how a system gets constructed.
    # this is a hard-coded version of what might happen in the executive
    # would eventually do all this via external configuration files, etc.

    _log.setLevel(logging.INFO)
    msgs = logging.StreamHandler(stream=sys.stdout)
    #msgs.setLevel(logging.INFO)
    #_log.addHandler(msgs)

    SundialCfgFile = "../cfg/SystemCfg/SundialSystemConfiguration.json"#"SundialSystemConfiguration2.json"
    sundial_resource_cfg_list = json.load(open(SundialCfgFile, 'r'))

    gs_start_time = datetime.utcnow().replace(microsecond=0)
    gs_start_time_str = gs_start_time.strftime("%Y-%m-%dT%H:%M:%S")
    sundial_resources = SundialSystemResource(sundial_resource_cfg_list, gs_start_time_str)

    ess_resources = sundial_resources.find_resource_type("ESSCtrlNode")[0]
    pv_resources = sundial_resources.find_resource_type("PVCtrlNode")[0]
    system_resources = sundial_resources.find_resource_type("System")[0]
    try:
        loadshift_resources = sundial_resources.find_resource_type("LoadShiftCtrlNode")[0]
    except:
        loadshift_resources = []
    try:
        load_resources = sundial_resources.find_resource_type("Load")[0]
    except:
        load_resources = []

    forecast_timestamps = [(gs_start_time +
                           timedelta(minutes=t)).strftime("%Y-%m-%dT%H:%M:%S") for t in range(0,
                                                                                              SSA_SCHEDULE_DURATION * MINUTES_PER_HR,
                                                                                              SSA_SCHEDULE_RESOLUTION)]


    #### Just load with example values - ######
    ess_forecast = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                    0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                    0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                    0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

    #ess_forecast = [-51.35175009, -51.37987963, -52.40495415, -55.7941499,
    #                -70.15320262, -193.91606361,   15.24561777, -13.75917004,
    #                63.47416001,  247.63232283, 350.72528327,  426.73011525,
    #                417.92689915,  357.44332889, 224.46714951, 16.86389897,
    #                0.0, 0.0, -136.28581942, -96.68917457,
    #                49.07769182, 97.72753814, 111.3388077, 0.0]

    ess_resources.load_scenario(init_SOE=1000.0,
                                max_soe=2000.0,
                                min_soe=0.0,
                                max_chg=500.0,
                                max_discharge=500.0,
                                chg_eff=0.95,
                                dischg_eff=0.95,
                                demand_forecast=ess_forecast,
                                t=forecast_timestamps)

    pv_forecast = [0.0, 0.0, 0.0, 0.0,
                   0.0, -5.769, -93.4666, -316.934,
                   -544.388, -716.663, -822.318, -888.916,
                   -898.478, -839.905, -706.972, -512.013,
                   -265.994, -74.6933, -2.0346, 0.0,
                   0.0, 0.0, 0.0, 0]

    #pv_forecast = [0.5 * v for v in [0.0, 0.0, 0.0, 0.0,
    #                                 0.0, -5.769, -93.4666, -316.934,
    #                                 -544.388, -716.663, -822.318, -888.916,
    #                                 -898.478, -839.905, -706.972, -512.013,
    #                                 -265.994, -74.6933, -2.0346, 0.0,
    #                                 0.0, 0.0, 0.0, 0]]

    demand_forecast = [142.4973, 142.4973, 142.4973, 145.9894,
                       160.094, 289.5996, 339.7752, 572.17,
                       658.6025, 647.2883, 650.1958, 639.7053,
                       658.044, 661.158, 660.3772, 673.1098,
                       640.9227, 523.3306, 542.7008, 499.3727,
                       357.9398, 160.0936, 145.9894, 142.4973]

    pv_resources.load_scenario(demand_forecast = pv_forecast,
                               pk_capacity = 1000.0,
                               t=forecast_timestamps)

    if load_resources != []:
        load_resources.load_scenario(demand_forecast = demand_forecast,
                                     pk_capacity = 1000.0,
                                     t=forecast_timestamps)

    try:
        ls = pandas.read_excel("loadshift_example.xlsx", header=None)
        print(ls)
        load_shift_options = [ls[ii].tolist() for ii in range(0,13)]
        loadshift_resources.load_scenario(load_options=load_shift_options,
                                          t=forecast_timestamps)
    except:
        pass

    system_resources.load_scenario()


    # tariffs = {"threshold": 500} #DEMAND_CHARGE_THRESHOLD}
    start_times = pd.date_range(datetime.now().date(),
                                periods=24,
                                freq='H')
    iso_data = pd.DataFrame([random() / 10 for i in range(24)],
                            index = start_times)

    tariffs = {"threshold": -100,
               "isone": iso_data
               }

    #########


    ##### This section replicates the periodic call of the optimizer ######
    # calls the actual optimizer.
    toffset = 0
    schedule_timestamps = [gs_start_time.replace(tzinfo=pytz.UTC) +
                           timedelta(minutes=t+toffset) for t in range(0,
                                                               SSA_SCHEDULE_DURATION * MINUTES_PER_HR * 2,
                                                               SSA_SCHEDULE_RESOLUTION)]
    sundial_resources.interpolate_forecast(schedule_timestamps)
    sundial_resources.cfg_cost(schedule_timestamps, tariffs=tariffs)


    tiers = generate_cost_map(sundial_resources, pv_resources)
    print(str(tiers))
    print(json.dumps(tiers, indent=4, sort_keys=True))
