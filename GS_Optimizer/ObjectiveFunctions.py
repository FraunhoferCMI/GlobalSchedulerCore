import numpy
import pandas
import os
import pytz
from datetime import datetime, timedelta
import isodate
import copy
import csv
from gs_identities import *
from gs_utilities import get_gs_path

USE_LOCAL_TIME = True

##############################################################################
class ObjectiveFunction():

    ##############################################################################
    def __init__(self, desc="", init_params=None, **kwargs): #fname, schedule_timestamps, sim_offset=timedelta(0), desc=""):
        """
        loads a file of dates / values.  retrieves a pandas data frame of for the specified time window.
        1. load data file
        2. retrieve data corresponding to time window
        3. resample if necessary
        :param self:
        :return:
        """
        print(desc)
        print(kwargs)
        self.desc   = desc
        self.init_params = {'tariff_key': None}

        for k, v in init_params.iteritems():
            try:
                self.init_params.update({k: kwargs[k]})
            except:
                print("Warning in ObjectiveFunction.py " + self.desc + "  __init__: '" + k + "' undefined - using default value")
                self.init_params.update({k: init_params[k]})


    ##############################################################################
    def obj_fcn_cfg(self, **kwargs):
        pass

    ##############################################################################
    def load_data_file(self, fname):
        """
        Loads time-series cost data from an excel file
        column 1 = datetime
        column 2-n = cost information
        row 1 = column headers
        :param fname: filename
        :return: self.obj_fcn_data --> dataframe of time series cost data
        """
        # fname_fullpath = get_gs_path("", fname)
        fname_fullpath = get_gs_path("GS_Optimizer/", fname)

        df = pandas.read_excel(fname_fullpath, header=0, index_col=0)
        #tst = numpy.array([pandas.Timestamp(t).replace(tzinfo=pytz.UTC).to_pydatetime() for t in df.index])
        new_df = df.resample(str(SSA_SCHEDULE_RESOLUTION) + 'T').bfill()

        if USE_LOCAL_TIME == True:
            new_df.index = [pandas.Timestamp(t).replace(tzinfo=pytz.timezone('US/Eastern')).to_pydatetime() for t in new_df.index]
            new_df.index = new_df.index.tz_convert(pytz.timezone('UTC'))
        else:
            new_df.index = [pandas.Timestamp(t).replace(tzinfo=pytz.UTC).to_pydatetime() for t in new_df.index]
        return new_df

    ##############################################################################
    def lookup_data(self, schedule_timestamps, sim_offset=timedelta(0)):
        """
        looks up cost data from a time-series dataframe for a time window defined by schedule_timestamps
        :param schedule_timestamps:
        :param sim_offset:
        :return:
        """
        print("sim_offset = "+str(sim_offset))

        #### Find the time window corresponding to the current set of timestamps:
        # slow!~ could be optimized.

        # FOR each element of the database
        # for each timestamp value
        # find the difference between all db elements and the timestamp
        # assign the closest one to that timestamp
        # this is very inefficient
        # instead...
        # 1. I get a timestamp
        # 2. I round down to the nearest time step


        ### what am I having problems with?
        # options -
        start_ind = numpy.argmin(numpy.abs(self.obj_fcn_data.index - (schedule_timestamps[0] + sim_offset)))
        if self.obj_fcn_data.index[start_ind] > schedule_timestamps[0]:
            start_ind -= 1


        cur_data = self.obj_fcn_data.iloc[start_ind:start_ind + len(schedule_timestamps)]
        print(cur_data)
        print(schedule_timestamps)
        cur_data.index = schedule_timestamps
        #cur_data['Cost'] = [0.05, 0.05, 0.05, 0.05, 0.05, 0.05,
        #                    0.05, 0.05, 0.05, 0.05, 0.05, 0.05,
        #                    0.05, 0.05, 0.25, 0.25, 0.25, 0.25,
        #                    0.80, 0.80, 0.80, 0.80, 0.80, 0.05]

        #indices = [numpy.argmin(
        #    numpy.abs(
        #        numpy.array([pandas.Timestamp(t).replace(tzinfo=pytz.UTC).to_pydatetime() for t in self.obj_fcn_data.index]) -
        #        (ts.replace(minute=0, second=0, microsecond=0) + sim_offset))) for ts in schedule_timestamps]
        pandas.options.display.float_format = '{:,.2f}'.format
        print(cur_data)

        return numpy.array(cur_data.transpose())
        #numpy.array(self.obj_fcn_data.iloc[indices].transpose())  #obj_fcn_data.loc[offset_ts].interpolate(method='linear')


    ##############################################################################
    def obj_fcn_cost(self, profile):
        return 0.0

    ##############################################################################
    def get_linear_approximation(self, profile):
        return self.obj_fcn_cost(profile)

    ##############################################################################
    def get_obj_fcn_data(self):
        return self.init_params["cur_cost"]

    ##############################################################################
    def get_objfcn_weights(self, schedule_timestamps):
        weights = numpy.array([0.0]*SSA_PTS_PER_SCHEDULE) #pandas.DataFrame(data=[0.0]*SSA_PTS_PER_SCHEDULE, index = schedule_timestamps)
        return weights

    ##############################################################################
    def obj_fcn_weighted_avg_cost(self, profile):

        baseline = profile['DemandForecast_kW']
        demand_high = baseline*1.25
        demand_low = baseline*0.75
        cost_bl   = self.obj_fcn_cost(profile)
        profile['DemandForecast_kW'] = demand_high
        cost_high =  self.obj_fcn_cost(profile)
        profile['DemandForecast_kW'] = demand_low
        cost_low  =  self.obj_fcn_cost(profile)
        profile['DemandForecast_kW'] = baseline

        return cost_bl*0.6+cost_high*0.2+cost_low*0.2
        pass


##############################################################################
class EnergyCostObjectiveFunction(ObjectiveFunction):

    ##############################################################################
    def __init__(self, desc="", init_params=None, **kwargs):

        init_params = {'fname': None}

        # duration --> 'time_step': isodate.parse_duration('PT60M')


        ObjectiveFunction.__init__(self, desc=desc, init_params=init_params, **kwargs)
        #fname = kwargs["fname"]
        #schedule_timestamps = kwargs["schedule_timestamps"]
        self.obj_fcn_data = self.load_data_file(self.init_params["fname"]) #, self.init_params["schedule_timestamps"])
        #"schedule_timestamps=schedule_timestamps, sim_offset=self.sim_offset"

    ##############################################################################
    def obj_fcn_cfg(self, **kwargs):
        self.init_params["cur_cost"] = self.lookup_data(kwargs["schedule_timestamps"],
                                                        kwargs["sim_offset"])

    ##############################################################################
    def obj_fcn_cost(self, profile):
        cost = sum(self.init_params["cur_cost"][0] * profile["DemandForecast_kW"])
        return cost

    ##############################################################################
    def get_obj_fcn_data(self):
        return self.init_params["cur_cost"][0].tolist()


##############################################################################
class EnergyCostObjectiveFunction_Dynamic(EnergyCostObjectiveFunction):

    ##############################################################################
    def __init__(self, desc="", init_params=None, **kwargs):

        init_params = {'fname': None,
                       'is_timestamped': False}
        # duration --> 'time_step': isodate.parse_duration('PT60M')


        ObjectiveFunction.__init__(self, desc=desc, init_params=init_params, **kwargs)

    ##############################################################################
    def obj_fcn_cfg(self, **kwargs):
        """
        retrieve data from a file that represents hrs and prices, starting at hour = 0, through hour 23 (UTC)
        shifts time to line up with current schedule
        :param kwargs:
        :return:
        """

        if self.init_params['is_timestamped'] == False:
            prices = pandas.read_csv(self.init_params['fname'], header=None)/100.0  # 0 - 23
        else:
            pass # not currently suppored

        timestamps = [v + kwargs['sim_offset'] for v in kwargs['schedule_timestamps']]

        shifted_prices = pandas.DataFrame([0.0]*24, index=timestamps)
        for ii in range(0,len(timestamps)):
            shifted_prices[0][timestamps[ii]] = prices[0][timestamps[ii].hour]
        print(shifted_prices)

        self.init_params["cur_cost"] = numpy.array(shifted_prices.transpose())



class ISONECostObjectiveFunction(EnergyCostObjectiveFunction):

    ##############################################################################
    def __init__(self, desc="", init_params=None, **kwargs):
        init_params = {'fname': None}
        EnergyCostObjectiveFunction.__init__(self, desc=desc, init_params=init_params, **kwargs)
        self.init_params = {'fname': None,
                            'isone': [0.0]*SSA_PTS_PER_SCHEDULE,
                       'tariff_key': 'tariffs'}

    ##############################################################################
    def obj_fcn_cfg(self, **kwargs):

        for k, v in self.init_params.iteritems():
            try:
                self.init_params.update({k: kwargs['tariffs'][k]})
                # print(str(k)+": "+str(kwargs[self.init_params['tariff_key'][k]]))
            except:
                pass

        self.init_params["cur_cost"] = kwargs[self.init_params['tariff_key']]["isone"]

    ##############################################################################
    def obj_fcn_cost(self, profile):
        cost = self.init_params["cur_cost"][-1]
        # cost = numpy.array(self.init_params["cur_cost"].to_records(index=False))

        return cost

##############################################################################
class PeakerPlantObjectiveFunction(ObjectiveFunction):
    def __init__(self, desc="", init_params=None, **kwargs):
        init_params = {'threshold': 100,
                       'cost_per_kW': 10,
                       'safety_buffer': 0.0,
                       'peaker_start': 19,
                       'peaker_end': 22,
                       'hrs': [],
                       'hrs_index': [],
                       'tariff_key': 'peaker_tariff',
                       'hrs_index_by_day': [[] for ii in range(0,7)],
                       'daily_threshold': [0 for ii in range(0, 7)],
                       'day_index': [],
                       'use_daily_threshold': True}

        init_params = self.update_hrs_list(init_params)
        ObjectiveFunction.__init__(self, desc=desc, init_params=init_params, **kwargs)

    ##############################################################################
    def update_hrs_list(self,init_params):
        init_params.update({'hrs': [v for v in range(init_params['peaker_start'],
                                                     init_params['peaker_end']+1)]}),  # [17,18,19,20],   # [18,19,20,21,22], [19,20,21,22]
        return init_params

    ##############################################################################
    def obj_fcn_cfg(self, **kwargs):
        print('*******In Peaker Plant Config!!!@*******')
        for k, v in self.init_params.iteritems():
            try:
                self.init_params.update({k: kwargs['tariffs'][k]})
                print("Peaker Plant Config: "+str(k)+": "+str(kwargs['tariffs'][k]))
            except:
                pass
        self.init_params = self.update_hrs_list(self.init_params)

        # list of time stamps
        # need to generate the indices that are associated with the given hours
        self.init_params["hrs_index"] = []
        self.init_params["hrs_index_by_day"] = [[] for ii in range(0,7)]


        #print(kwargs['schedule_timestamps'])
        timestamps = [v + kwargs['sim_offset'] for v in kwargs['schedule_timestamps']]
        #print(self.init_params['hrs'])
        #print(timestamps)
        for ii in range(0,len(timestamps)):
            if timestamps[ii].hour in self.init_params['hrs']:
                self.init_params['hrs_index'].append(ii)
                self.init_params['hrs_index_by_day'][timestamps[ii].weekday()].append(ii)
            self.init_params['day_index'].append(timestamps[ii].weekday())


        #print('hr index: ')
        #print(self.init_params['hrs_index'])
        #print(self.init_params['hrs_index_by_day'])
        #print(self.init_params['day_index'])


    ##############################################################################
    def obj_fcn_cost(self, profile):
        """
        placeholder for a function that calculates a demand charge for a given net demand profile
        :return: cost of executing the profile, in $
        """
        #demand = numpy.array(profile)


        if self.init_params['use_daily_threshold'] == False:
            max_demand = max(profile["DemandForecast_kW"][self.init_params['hrs_index']])
            threshold  = self.init_params["threshold"]*(1-self.init_params["safety_buffer"])
            if max_demand > threshold: #self.threshold:
                cost = self.init_params["cost_per_kW"] * (max_demand - threshold)
            else:
                cost = 0.0
        else:
            cost = 0.0
            for ii in range(0,len(self.init_params['hrs_index_by_day'])):
                if len(self.init_params['hrs_index_by_day'][ii]) != 0:
                    max_demand = max(profile["DemandForecast_kW"][self.init_params['hrs_index_by_day'][ii]])
                    threshold  = self.init_params["daily_threshold"][ii]*(1-self.init_params["safety_buffer"])
                    if max_demand > threshold: #self.threshold:
                        cost += self.init_params["cost_per_kW"] * (max_demand - threshold)


        return cost


    ##############################################################################
    def get_obj_fcn_data(self):
        return self.init_params["threshold"]

    ##############################################################################
    def get_objfcn_weights(self, schedule_timestamps):
        weights = numpy.array([0.0] * SSA_PTS_PER_SCHEDULE)  #pandas.DataFrame(data=[0.0]*SSA_PTS_PER_SCHEDULE, index = schedule_timestamps)
        weights[self.init_params['hrs_index']] = 10.0
        return weights


##############################################################################
class StoredEnergyValueObjectiveFunction(ObjectiveFunction):
    """
    assigns a cost to change in power (dPwr/dt)
    """
    def __init__(self, desc="", init_params=None, **kwargs):
        ObjectiveFunction.__init__(self, desc=desc, init_params={}, **kwargs)
        self.init_params["value_per_kWh"] = -0.15

    def obj_fcn_cost(self, profile):
        end_ind = len(profile["EnergyAvailableForecast_kWh"])-1
        # print( "CURRENT FORECAST")
        # print( profile["EnergyAvailableForecast_kWh"])
        # print( type(profile["EnergyAvailableForecast_kWh"]))
        cost = self.init_params["value_per_kWh"] * profile["EnergyAvailableForecast_kWh"][end_ind]
        return cost

    def get_obj_fcn_data(self):
        return self.init_params["value_per_kWh"]


##############################################################################
class EnergyTargetObjectiveFunction(ObjectiveFunction):
    """
    assigns a cost to variance from a targeted ESS SOE
    """
    def __init__(self, desc="", init_params=None, **kwargs):
        ObjectiveFunction.__init__(self, desc=desc, init_params={}, **kwargs)
        self.init_params["value_per_kWh"] = -1.0
        self.init_params['TargetHr'] = 18
        #self.init_params['']
        self.init_params['use_multiple_tgts'] = True
        self.init_params['Target'] = {0: (300, -0.3),
                                      1: (300, -0.3),
                                      2: (300, -0.3),
                                      3: (300, -0.3),
                                      4: (300, -0.3),
                                      5: (300, -0.3),
                                      6: (300, -0.3),
                                      7: (300, -0.3),
                                      8: (300, -0.3),
                                      9: (300, -0.3),
                                      10: (300, -0.3),
                                      11: (300, -0.3),
                                      12: (300, -0.3),
                                      13: (300, -0.3),
                                      18: (930, -3.0)}

    def obj_fcn_cfg(self, **kwargs):
        print('*******In Energy Target Config!!!@*******')

        # list of time stamps
        # need to generate the indices that are associated with the given hours
        self.init_params["hrs_index"] = {}


        #print(kwargs['schedule_timestamps'])
        timestamps = [v + kwargs['sim_offset'] for v in kwargs['schedule_timestamps']]
        #print(self.init_params['hrs'])
        #print(timestamps)

        if self.init_params['use_multiple_tgts'] == True:
            inds = []
            for ii, v in self.init_params['Target'].iteritems():
                inds.append(ii)
        else:
            inds = [self.init_params['TargetHr']]

        for ii in range(0,len(timestamps)):
            if timestamps[ii].hour in inds:
                self.init_params['hrs_index'].update({timestamps[ii].hour: ii})

    def obj_fcn_cost(self, profile):
        if self.init_params['use_multiple_tgts'] == False:
            end_ind = self.init_params['TargetHr']
            cur_hr = self.init_params['hrs_index'][end_ind]
            cost = self.init_params["value_per_kWh"] * profile["EnergyAvailableForecast_kWh"][cur_hr]
        else:
            cost = 0
            for cur_ind, v in self.init_params['Target'].iteritems():
                cur_hr = self.init_params['hrs_index'][cur_ind]
                cost += -1*v[1] * abs(profile["EnergyAvailableForecast_kWh"][cur_hr] - v[0])
        return cost

    def get_obj_fcn_data(self):
        return self.init_params["value_per_kWh"]




##############################################################################
class dkWObjectiveFunction(ObjectiveFunction):
    """
    assigns a cost to change in power (dPwr/dt)
    """
    def __init__(self, desc="", init_params=None, **kwargs):
        ObjectiveFunction.__init__(self, desc=desc, init_params={}, **kwargs)
        self.init_params["cost_per_dkW"] = 0 #0.005**2

    def obj_fcn_cost(self, profile):
        return (sum(abs(numpy.ediff1d(profile["DemandForecast_kW"]))**2))*self.init_params["cost_per_dkW"]

    def get_obj_fcn_data(self):
        return self.init_params["cost_per_dkW"]

##############################################################################
class DemandChargeObjectiveFunction(ObjectiveFunction):

    ##############################################################################
    def __init__(self, desc="", init_params=None, **kwargs):
        init_params = {'threshold': 250,
                       'cost_per_kW': 10,
                       'safety_buffer': 0.0,
                       'tariff_key': 'tariffs'}

        ObjectiveFunction.__init__(self, desc=desc, init_params=init_params, **kwargs)

    ##############################################################################
    def obj_fcn_cfg(self, **kwargs):

        for k, v in self.init_params.iteritems():
            try:
                self.init_params.update({k: kwargs['tariffs'][k]})
                #print(str(k)+": "+str(kwargs[self.init_params['tariff_key'][k]]))
            except:
                pass

        # Generate a linear approximation of demand charge
        #v = kwargs["forecast"]["DemandForecast_kW"]-self.init_params["threshold"]
        #energy_above_threshold = v[numpy.where(v > 0)].sum()
        #cost = self.obj_fcn_cost(kwargs["forecast"])
        #if cost == 0:
        #    self.imputed_cost_per_kWh = 0
        #else:
        #    self.imputed_cost_per_kWh = energy_above_threshold / cost
        #print(self.imputed_cost_per_kWh)
        print(self.init_params)
        #self.init_params["threshold"] = kwargs["threshold"]
        #self.init_params["cost_per_kW"] = kwargs["cost_per_kW"]

    ##############################################################################
    def obj_fcn_cost(self, profile):
        """
        placeholder for a function that calculates a demand charge for a given net demand profile
        :return: cost of executing the profile, in $
        """
        #demand = numpy.array(profile)

        max_demand = max(profile["DemandForecast_kW"])
        threshold  = self.init_params["threshold"]*(1-self.init_params["safety_buffer"])
        if max_demand > threshold: #self.threshold:
            cost = self.init_params["cost_per_kW"] * (max_demand - threshold)
        else:
            cost = 0.0
        return cost

    ##############################################################################
    def get_linear_approximation(self, profile):
        """
        (1) calculate how much energy is expected to be consumed in excess of the threshold = sum(max(forecast-threshold,0))
        (2) calculate total cost = max(forecast) x cost
        (3) calculate imputed cost per kWh = energy / cost
        :param profile:
        :return:
        """
        v = profile["DemandForecast_kW"]-self.init_params["threshold"]
        energy_above_threshold = v[numpy.where(v > 0)].sum()
        cost = self.obj_fcn_cost(profile)
        if cost == 0:
            imputed_cost_per_kWh = 0
        else:
            imputed_cost_per_kWh = energy_above_threshold / cost

        return imputed_cost_per_kWh


    ##############################################################################
    def get_obj_fcn_data(self):
        return self.init_params["threshold"]

##############################################################################
class MinPeakBFObjectiveFunction(DemandChargeObjectiveFunction):

    ##############################################################################
    def obj_fcn_cost(self, profile):
        """
        placeholder for a function that calculates a demand charge for a given net demand profile
        :return: cost of executing the profile, in $
        """
        #demand = numpy.array(profile)

        max_neg_demand = min(profile["DemandForecast_kW"])
        threshold  = self.init_params["threshold"]*(1-self.init_params["safety_buffer"])
        if max_neg_demand < threshold: #self.threshold:
            cost = self.init_params["cost_per_kW"] * (threshold-max_neg_demand)
        else:
            cost = 0.0
        return cost


##############################################################################
class TieredEnergyObjectiveFunction():
    """
    placeholder for a function that calculates a demand charge for a given net demand profile
    :return: cost of executing the profile, in $
    """
    ##############################################################################
    def __init__(self, desc):
        # fname, schedule_timestamps, sim_offset=timedelta(0)
        pass


    ##############################################################################
    def obj_fcn_cost(self, profile):

        max_bf = max(profile["DemandForecast_kW"])

        # tier at 200, 100, 10
        cost = 0.0
        for p in profile["DemandForecast_kW"]:
            cost += max(p - 400.0, 0) * 100.0
            cost += max(p - 250.0, 0) * 50.0
            cost += max(p - 200.0, 0) * 25.0
            cost += max(p - 150.0, 0) * 10.0
            cost += max(p - 100.0, 0) * 5.0
            cost += max(p - 50.0, 0) * 3.0
            cost += max(p, 0.0) * 1.0

            #if p > 0:
            #    cost += p*p


        # if max_bf < 0: #self.demand_threshold:
        #    cost = self.demand_cost_per_kW*(-1*max_bf)
        # else:
        #    cost = 0
        return cost

##############################################################################
class LoadShapeObjectiveFunction(ObjectiveFunction):

    ##############################################################################
    def __init__(self, desc="", **kwargs): #fname, schedule_timestamps, sim_offset=timedelta(0), desc=""):
        init_params = {'fname': None,
                       'schedule_timestamps':[0],
                       'vble_price': False}
        ObjectiveFunction.__init__(self, desc=desc, init_params=init_params, **kwargs)

        self.obj_fcn_data = self.load_data_file(self.init_params["fname"])
        self.cfg_params   = "schedule_timestamps=schedule_timestamps, sim_offset=self.sim_offset"

        self.cost = 0.0
        self.err  = 0.0

    ##############################################################################
    def obj_fcn_cfg(self, **kwargs):
        self.init_params["cur_cost"] = self.lookup_data(kwargs["schedule_timestamps"],
                                                        kwargs["sim_offset"])

        print("Target Load Shape is:")
        print(self.init_params['cur_cost'])

    ##############################################################################
    def obj_fcn_cost(self, profile):
        """
        imposes a cost for deviations from a target load shape.
        cost is calculated as square of the error relative to the target load shape.
        :return: cost of executing proposed profile, in $
        """
        self.err = (profile["DemandForecast_kW"] - self.init_params["cur_cost"][0]) ** 2

        if self.init_params["vble_price"] == False:
            price = 10.0  # sort of arbitrary, just needs to be a number big enough to drive behavior in the desired direction.
            self.cost = (sum(self.err) * price**2)**0.5
        else:
            price = self.init_params["cur_cost"][1]  # sort of arbitrary, just needs to be a number big enough to drive behavior in the desired direction.
            self.cost = (sum(self.err * price**2))**0.5
        #demand = numpy.array(profile)

        return self.cost

    ##############################################################################
    def get_obj_fcn_data(self):
        return self.init_params["cur_cost"][0].tolist()


##############################################################################
class DynamicLoadShapeObjectiveFunction(LoadShapeObjectiveFunction):

    def load_data_file(self, fname):
        return None

    ##############################################################################
    def lookup_data(self, schedule_timestamps, sim_offset=timedelta(0)):
        """
        looks up cost data from a time-series dataframe for a time window defined by schedule_timestamps
        :param schedule_timestamps:
        :param sim_offset:
        :return:
        """
        fname_fullpath = get_gs_path("GS_Optimizer/", self.init_params["fname"])
        self.obj_fcn_data = pandas.read_csv(fname_fullpath, header=0, index_col=0)
        self.obj_fcn_data.index = pandas.to_datetime(self.obj_fcn_data.index)
        pandas.options.display.float_format = '{:,.2f}'.format

        start_ind = schedule_timestamps[0].hour

        tmp = numpy.array([[0.0]*len(self.obj_fcn_data.columns)]*len(self.obj_fcn_data))
        for ii in range(0,len(schedule_timestamps)):
            for jj in range(0,len(self.obj_fcn_data.columns)):
                v = self.obj_fcn_data[str(jj)].loc[self.obj_fcn_data.index.hour == schedule_timestamps[ii].hour]
                try:
                    tmp[ii][jj] = v
                except:
                    pass

        #print(tmp)
        #print('Target Load Shape: ')
        #print(self.obj_fcn_data)

        return tmp.transpose() #numpy.array(self.obj_fcn_data.transpose())

##############################################################################
class BatteryLossModelObjectiveFunction(ObjectiveFunction):
    ## place holder that corrects for efficiency as a function of battery chg / discharge rate
    ## this might not make sense - it's more correct to address by actually calculating losses
    ## but might have a speed impact. Numbers are made up at this point.

    ##############################################################################
    def __init__(self, desc="", init_params=None, **kwargs):
        ObjectiveFunction.__init__(self, desc=desc, init_params={}, **kwargs)

    ##############################################################################
    def obj_fcn_cfg(self, **kwargs):
        pass

    ##############################################################################
    def obj_fcn_cost(self, profile):
        price = 0.02

        cost = (abs(profile['DemandForecast_kW']).sum())*price  # 8/20/2019 - charge per kWh throughput on ESS

        #cost = 0.10*profile['DemandForecast_kW'][profile['DemandForecast_kW']>0].sum()


        prices = [-0.05, -0.05, -0.05, -0.05, -0.05, -0.05,
                            -0.05, -0.05, -0.05, -0.05, -0.05, -0.05,
                            -0.05, -0.05, 0.0, 0.0, 0.0, 0.0,
                            0.0, 0.0, 0.0, 0.0, 0.0, -0.05]

        vals = (prices*profile['DemandForecast_kW'])

        #cost+=vals[vals>0].sum()

        if 0:
            for ii in (0,len(profile["DemandForecast_kW"])-1):
                if profile["DemandForecast_kW"][ii] > 0.0:
                    if profile["DemandForecast_kW"][ii] < 20.0:
                        cost += profile["DemandForecast_kW"][ii] * 0.1
                    elif profile["DemandForecast_kW"][ii] < 50.0:
                        cost += profile["DemandForecast_kW"][ii] * 0.05
                    elif profile["DemandForecast_kW"][ii] < 100.0:
                        cost += profile["DemandForecast_kW"][ii] * 0.025
                    elif profile["DemandForecast_kW"][ii] < 200.0:
                        cost += profile["DemandForecast_kW"][ii] * 0.015
                    elif profile["DemandForecast_kW"][ii] < 300.0:
                        cost += profile["DemandForecast_kW"][ii] * 0.01
                    elif profile["DemandForecast_kW"][ii] >= 300.0:
                        cost += profile["DemandForecast_kW"][ii] * 0.0
        return cost

    ##############################################################################
    def get_obj_fcn_data(self):
        pass
