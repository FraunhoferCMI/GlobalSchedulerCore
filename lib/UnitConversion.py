from gs_identities import *

def Scale(val, scale_factor):
    return val * scale_factor

def ScaleEnergy(val, scale_factor):
    return Scale(val, scale_factor)*SIM_HRS_PER_HR

def PctToUnits(val,nameplate):
    return float(val)/100.0 * nameplate

def UnitsToPct(val, nameplate):
    return round(float(val)*100.0 / float(nameplate))

def UnitsToFracPct(val, nameplate):
    return round(10*float(val)*100.0 / float(nameplate))/10


def SunSpecScale(keyval, cur_attribute, to_unit_scale, to_unit_units, val, incoming_msg=None):
    base_name = keyval[:len(keyval) - len(to_unit_units)]  # assume this has a unit on the end of the name
    if incoming_msg is None:
        if cur_attribute.data_dict[base_name + "SF"] is None:
            return 0.0
        else:
            return (val * 10.0 ** cur_attribute.data_dict[base_name + "SF"]) / to_unit_scale
    else:
        k = cur_attribute.map_int_to_ext_endpt[base_name + "SF"]
        if incoming_msg[k] is None:
            return 0.0
        else:
            return (val * 10.0 ** incoming_msg[k]) / to_unit_scale

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

