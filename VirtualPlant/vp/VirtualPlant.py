from datetime import datetime, timedelta
import time

class VirtualESS():
    ##############################################################################
    def __init__(self,
                 labels=None):
        self.maxSOE_kWh = 1000.0
        self.minSOE_kWh = 0.0
        self.maxCharge_kW = 500.0
        self.maxDischarge_kW = 500.0
        self.eff = 0.93 * 0.93
        self.SOE_kWh = 500.0
        self.pwr_kW = 0.0
        self.pwrCmd_kW = 0.0

        self.last_update = datetime.utcnow()

        if labels == None:
            self.labels = {"FullChargeEnergy_kWh": "FullChargeEnergy_kWh",
                           "MaxChargePwr": "MaxChargePwr",
                           "MaxDischargePwr": "MaxDischargePwr",
                           "SOE_kWh": "SOE_kWh",
                           "Pwr_kW": "Pwr_kW",
                           "PwrCmd_kW": "PwrCmd_kW"}
        else:
            self.labels = labels


    ##############################################################################
    def set_real_pwr(self, cmd):
        self.update_state()
        self.pwrCmd_kW = cmd


    ##############################################################################
    def update_state(self):
        """
        calculates current SOE of the battery
        :param last_update:
        :return:
        """
        now = datetime.utcnow()
        delta_t = (now - self.last_update).total_seconds()  # elapsed time since the last time SOE was updated

        if self.pwrCmd_kW < 0:  # discharge
            eff_factor = 1.0
        else:
            eff_factor = self.eff

        pwr = self.pwrCmd_kW
        pwr = max(-1 * self.maxDischarge_kW, pwr)
        pwr = min(self.maxCharge_kW, pwr)

        delta_energy_kWsec = pwr * delta_t * eff_factor  # in kW-sec
        delta_energy_kWh = delta_energy_kWsec / 3600

        SOE_kWh = max(self.SOE_kWh + delta_energy_kWh, self.minSOE_kWh)
        SOE_kWh = min(SOE_kWh, self.maxSOE_kWh)

        # set power to 0 if we are energy limited
        if (pwr > 0) & (SOE_kWh >= self.maxSOE_kWh):
            pwr = 0
        if (pwr < 0) & (SOE_kWh <= self.minSOE_kWh):
            pwr = 0

        # update state variables
        self.pwr_kW = pwr
        self.SOE_kWh = SOE_kWh
        self.last_update = now


    ##############################################################################
    def serialize(self):

        self.labels = {"FullChargeEnergy_kWh": "FullChargeEnergy_kWh",
                       "MaxChargePwr": "MaxChargePwr",
                       "MaxDischargePwr": "MaxDischargePwr",
                       "SOE_kWh": "SOE_kWh",
                       "Pwr_kW": "Pwr_kW",
                       "PwrCmd_kW": "PwrCmd_kW"}

        self.serialized_data = {self.labels["FullChargeEnergy_kWh"]: self.maxSOE_kWh,
                                self.labels["MaxChargePwr"]: self.maxCharge_kW,
                                self.labels["MaxDischargePwr"]: self.maxDischarge_kW,
                                self.labels["SOE_kWh"]: self.SOE_kWh,
                                self.labels["Pwr_kW"]: self.pwr_kW,
                                self.labels["PwrCmd_kW"]: self.pwrCmd_kW}
        self.serialized_meta_data = {self.labels["FullChargeEnergy_kWh"]: {"units": 'kWh', "type": 'float'},
                                     self.labels["MaxChargePwr"]: {"units": 'kW', "type": 'float'},
                                     self.labels["MaxDischargePwr"]: {"units": 'kW', "type": 'float'},
                                     self.labels["SOE_kWh"]: {"units": 'kWh', "type": 'float'},
                                     self.labels["Pwr_kW"]: {"units": 'kW', "type": 'float'},
                                     self.labels["PwrCmd_kW"]: {"units": 'kW', "type": 'float'}}


        self.serialized_msg = [self.serialized_data, self.serialized_meta_data]

        return self.serialized_msg




if __name__ == '__main__':
    ess = VirtualESS()

    delay = 1

    schedule = [500, -500, -300, -250, 100, -100, -1000, 1000, -50, 50, 0, 500]

    ind = 0
    delta_soe = 0

    use_realtime = True

    while (1):
        pwr_cmd = schedule[ind]

        print(str(ess.last_update)+': ESS Cmd = '+str(ess.pwrCmd_kW)+'; SOE='+str(ess.SOE_kWh)+'; Pwr='+str(ess.pwr_kW) + '; Delta SOE='+str(delta_soe))
        prev_soe = ess.SOE_kWh
        if use_realtime == False:
            ess.last_update = datetime.utcnow()-timedelta(minutes=30)
        ess.set_real_pwr(pwr_cmd)
        delta_soe = ess.SOE_kWh - prev_soe

        if ind == len(schedule)-1:
            ind = 0
        else:
            ind += 1
        time.sleep(delay)




