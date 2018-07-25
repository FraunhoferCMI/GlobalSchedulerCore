from gs_identities import *

def Scale(val, scale_factor):
    return val * scale_factor

def ScaleEnergy(val, scale_factor):
    return Scale(val, scale_factor)*SIM_HRS_PER_HR

def PctToUnits(val,nameplate):
    return float(val)/100.0 * nameplate

def UnitsToPct(val, nameplate):
    return int(float(val)*100.0 / float(nameplate))

def SunSpecScale(keyval, data_dict, to_unit_scale, to_unit_units):
    base_name = keyval[:len(keyval) - to_unit_units]  # assume this has a unit on the end of the name
    return (data_dict[keyval] * 10.0 ** data_dict[base_name + "SF"]) / to_unit_scale

def ScaleNegPctToUnits(val,nameplate):
    return -1*PctToUnits(val, nameplate)

def Scale103(val):
    return float(val)*1000.0

def Scale10neg3(val):
    return float(val)*0.001

def Scale101(val):
    return float(val)*10.0

def Scale10neg1(val):
    return float(val)*0.001

def Scale102(val):
    return float(val)*100.0

def Scale10neg2(val):
    return float(val)*0.01

def ScaleSolectriaV():
    pass

def ScaleNeg103(val):
    return -1 * Scale103(val)

def ScaleNeg10neg3(val):
    return -1 * Scale10neg3(val)

