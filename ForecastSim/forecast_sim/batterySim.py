import logging

import sys
sys.path.insert(0, '../../GS_Optimizer/')
# from SundialResource import ESSResource
from SunDialResource import ESSResource
# from GS_Optimizer.SundialResource import ESSResource

_log = logging.getLogger(__name__)

class BatterySim(ESSResource):
    def __init__(self,
                 Pwr_kW,
                 SOE_kWh,
                 MaxSOE_kWh,
                 MinSOE_kWh,
                 ChgEff,
                 DischgEff,
                 MaxChargePwr_kW,
                 MaxDischargePwr_kW):

        # initial states
        self.Pwr_kW = Pwr_kW
        self.SOE_kWh = SOE_kWh

        # battery characteristics
        self.MaxSOE_kWh = MaxSOE_kWh
        self.MinSOE_kWh = MinSOE_kWh
        self.ChgEff = ChgEff
        self.DischgEff = DischgEff
        self.MaxChargePwr_kW = MaxChargePwr_kW
        self.MaxDischargePwr_kW = MaxDischargePwr_kW

        return None


    def __repr__(self):
        return "\n".join(["<BatterySim instance>",
                          "Current Power: " + str(self.Pwr_kW) + " kW",
                          "SOE : " + str(self.SOE_kWh) + " kWh",
                          "Max SOE : " + str(MaxSOE_kWh) + " kWh",
                          "Min SOE : " + str(MinSOE_kWh) + " kWh",
                          "Charge Efficiency: " + str(ChgEff),
                          "Discharge Efficiency: " + str(DischgEff),
                          "Max Charge Power: " + str(MaxChargePwr_kW) + " kW",
                          "Max Discharge Power: " + str(MaxDischargePwr_kW) + " kW"])

    def update_battery_state(self, power_request):
        '''
        Takes a requested percentage of capable charge/discharge in power_request,
        checks if there is enough capacity,
        calculates the accomodating adjustment to the request
        and changes the Pwr_kW to the requested/adjusted level.
        '''

        if (-1 <= power_request) & (power_request < 0):
            _log.info("DISCHARGING")
            # convert percent to kW
            kw_request = self.MaxDischargePwr_kW * power_request
            _log.info("Request of %s is %s kW",
                      str(power_request*100) + "%",
                      kw_request)
            soe_preliminary_request = self.SOE_kWh + kw_request / self.DischgEff
            # need to adjust kw_request to a level that won't exceed SOE constraint
            soe_request = max(soe_preliminary_request, self.MinSOE_kWh)
            if soe_request == self.MinSOE_kWh:
                _log.info("Insufficient capacity for discharge of: %s//%s",
                          power_request,
                          kw_request)
                soe_request = (self.MinSOE_kWh - soe_request) * self.DischgEff
        elif (0 <= power_request) & (power_request <= 1):
            _log.info("CHARGING")
            kw_request = self.MaxChargePwr_kW * power_request
            _log.info("Request of %s is %s kW",
                      str(power_request*100) + "%",
                      kw_request)
            soe_preliminary_request = self.SOE_kWh + kw_request * self.ChgEff
            # don't exceed max SOE
            soe_request = min(soe_preliminary_request, self.MaxSOE_kWh)
            # need to adjust pwr to a level that won't exceed SOE contraint
            if soe_request == self.MaxSOE_kWh:
                _log.info("Insufficient capacity for charge of: %s/%s kW",
                          str(power_request*100) + "%",
                          kw_request)
                soe_request = (self.MaxSOE_kWh - soe_request) / self.ChgEff
        else:
            _log.warn("Battery has been asked to (dis)charge with a higher power than is possible.")
            pwr = self.Pwr_kW

        _log.info("Power level changed from %s to %s", self.Pwr_kW, soe_request)
        self.Pwr_kW = soe_request

        return None


if __name__ == "__main__":

    Pwr_kW = 0
    SOE_kWh = 7
    MaxSOE_kWh = 10
    MinSOE_kWh = 1.2
    ChgEff = 0.65
    DischgEff = 0.67
    MaxChargePwr_kW = -1
    MaxDischargePwr_kW = 1.5

    percent_power_request = 0.75

    bat = BatterySim(
        Pwr_kW,
        SOE_kWh,
        MaxSOE_kWh,
        MinSOE_kWh,
        ChgEff,
        DischgEff,
        MaxChargePwr_kW,
        MaxDischargePwr_kW)
    bat.update_battery_state(0.5)

    # why are some efficiencies multiplied and some divided?
    # shouldn't time be associated with pwr to understand if the battery can accommodate the request? Is it assuming an hour of charge/discharge since that's the case this model will work?
