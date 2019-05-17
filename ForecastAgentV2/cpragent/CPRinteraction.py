import xml.etree.ElementTree as ET
from  xml.etree.ElementTree import tostring
from xml.dom import minidom

from  datetime import timedelta, datetime
import pytz
import isodate
import requests
from requests.auth import HTTPBasicAuth
from gs_identities import *
import json


def create_xml_query(start, end, TimeResolution_Minutes, a):
    "Create xml query to CPR model"
    if TimeResolution_Minutes== 60:
       PerformTimeShifting = "true"
    else:
       PerformTimeShifting = "false"

    CreateSimulationRequest = ET.Element("CreateSimulationRequest",
                                         xmlns="http://service.solaranywhere.com/api/v2")
    EnergySites = ET.SubElement(CreateSimulationRequest, "EnergySites")
    for b in a['EnergySites']:
        EnergySite = ET.SubElement(EnergySites, "EnergySite",
                                   Name=b["Name"],
                                   Description=b["Description"])
        Location = ET.SubElement(EnergySite, "Location",
                                 Latitude=b["Location"]["Latitude"],
                                 Longitude=b["Location"]["Longitude"])
        PvSystems = ET.SubElement(EnergySite, "PvSystems")
        PvSystem = ET.SubElement(PvSystems, "PvSystem",
                                 Albedo_Percent=b["PVSystem"]["Albedo_Percent"],
                                 GeneralDerate_Percent=b["PVSystem"]["GeneralDerate_Percent"])
        Inverters = ET.SubElement(PvSystem, "Inverters")
        Inverter = ET.SubElement(Inverters, "Inverter",
                                 Count=b["PVSystem"]["Inverters"]["Count"],
                                 MaxPowerOutputAC_kW=b["PVSystem"]["Inverters"]["MaxPowerOutputAC_kW"],
                                 EfficiencyRating_Percent=b["PVSystem"]["Inverters"]["EfficiencyRating_Percent"])
        PvArrays = ET.SubElement(PvSystem, "PvArrays")
        PvArray = ET.SubElement(PvArrays, "PvArray")
        PvModules = ET.SubElement(PvArray, "PvModules")
        PvModule = ET.SubElement(PvModules, "PvModule",
                                 Count=b["PVSystem"]["PVArrays"]["PvModule"]["Count"],
                                 NameplateDCRating_kW=b["PVSystem"]["PVArrays"]["PvModule"]["NameplateDCRating_kW"],
                                 PtcRating_kW=b["PVSystem"]["PVArrays"]["PvModule"]["PtcRating_kW"],
                                 PowerTemperatureCoefficient_PercentPerDegreeC=b["PVSystem"]["PVArrays"]["PvModule"][
                                     "PowerTemperatureCoefficient_PercentPerDegreeC"],
                                 NominalArrayOperatingCellTemperature_DegreesC=b["PVSystem"]["PVArrays"]["PvModule"][
                                     "NominalArrayOperatingCellTemperature_DegreesC"])
        ArrayConfiguration = ET.SubElement(PvArray, "ArrayConfiguration",
                                           Azimuth_Degrees=b["PVSystem"]["PVArrays"]["ArrayConfiguration"][
                                               "Azimuth_Degrees"],
                                           Tilt_Degrees=b["PVSystem"]["PVArrays"]["ArrayConfiguration"]["Tilt_Degrees"],
                                           Tracking=b["PVSystem"]["PVArrays"]["ArrayConfiguration"]["Tracking"],
                                           TrackingRotationLimit_Degrees=
                                           b["PVSystem"]["PVArrays"]["ArrayConfiguration"][
                                               "TrackingRotationLimit_Degrees"])

    SimulationOptions = ET.SubElement(CreateSimulationRequest, "SimulationOptions",
                                      PowerModel="CprPVForm",
                                      ShadingModel="ShadeSimulator",
                                      OutputFields=",".join(["StartTime",
                                                             "EndTime",
                                                             "PowerAC_kW",
                                                             "EnergyAC_kWh",
                                                             "GlobalHorizontalIrradiance_WattsPerMeterSquared",
                                                             "DirectNormalIrradiance_WattsPerMeterSquared",
                                                             "DiffuseHorizontalIrradiance_WattsPerMeterSquared",
                                                             "IrradianceObservationType",
                                                             "AmbientTemperature_DegreesC"
                                                             ]))

    WeatherDataOptions = ET.SubElement(SimulationOptions, "WeatherDataOptions",
                                       WeatherDataSource="SolarAnywhere3_2",
                                       WeatherDataPreference = "Auto",
                                       PerformTimeShifting = PerformTimeShifting,
                                       StartTime=start,
                                       EndTime=end,
                                       SpatialResolution_Degrees="0.01",
                                       TimeResolution_Minutes=str(TimeResolution_Minutes))

    xml_string = tostring(CreateSimulationRequest)

    return xml_string

def parse_query(query):
    """ Function to parse XML response from API"""
    xmldoc = minidom.parseString(query)
    parsed_forecast_list = {}
    SimResult = xmldoc.getElementsByTagName('SimulationResult')
    for res in SimResult:
        curSite = res.attributes['EnergySiteName'].value
        print('Received forecast for...'+curSite)
        SimPd = res.getElementsByTagName('SimulationPeriod')

        time = []
        forecast = []
        ghi      = []
        for sim in SimPd:
            iso_datetime = isodate.parse_datetime(sim.attributes['StartTime'].value)
            time.append(iso_datetime.astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M:%S"))
            try:
                #print(sim.attributes['StartTime'].value + ": " + sim.attributes['PowerAC_kW'].value)
                forecast.append(-1.0*float(sim.attributes['PowerAC_kW'].value))
            except KeyError:
                #print(sim.attributes['StartTime'].value + ": " + "synthesized 0.0")
                forecast.append(0.0)

            try:
                ghi.append(float(sim.attributes["GlobalHorizontalIrradiance_WattsPerMeterSquared"].value))
            except KeyError:
                ghi.append(0.0)

        parsed_forecast = dict(
            forecast=forecast,
            ghi=ghi,
            time=time,
            units="kW",
            # tz = "UTC-5",
            datatype="float"
        )

        parsed_forecast_list.update({curSite: parsed_forecast})

    return parsed_forecast_list

def get_date(query_interval, duration):
    dt_now = datetime.now(tz=pytz.timezone('America/New_York')).replace(microsecond=0, second=0)

    if query_interval == 1:
        dt_strt = datetime.isoformat(dt_now + timedelta(minutes=5))
        dt_end  = datetime.isoformat(dt_now + timedelta(minutes=duration*60+5))
    else:
        dt_strt = datetime.isoformat(dt_now.replace(minute=0))  # align to top of the hour
        dt_end  = datetime.isoformat(dt_now.replace(minute=0) + timedelta(hours=duration))

    return dt_strt, dt_end

if __name__ == "__main__":
    headers =  {'content-type': "text/xml; charset=utf-8",
                'content-length': "length",}
    url = "https://service.solaranywhere.com/api/v2/Simulation"
    userName = "schoudhary@cse.fraunhofer.org"
    password = "Shines2017"
    querystring = {"key":"FRHR3MXX7"}
    TimeResolution_Minutes = 1
    duration = 5
    start, end = get_date(TimeResolution_Minutes, duration)

    ##
    print("Request model")
    # TimeResolution_Minutes = 60
    ForecastSiteCfgFile = os.path.join(GS_ROOT_DIR, "ForecastAgentV2/", "SiteConfig.json")
    site_config = json.load(open(ForecastSiteCfgFile, 'r'))  # self._conf['EnergySites']
    generated = create_xml_query(start, end, TimeResolution_Minutes, site_config)


    response = requests.post(url,
                             auth=HTTPBasicAuth(userName, password),
                             data=generated.decode(),
                             headers=headers,
                             params=querystring)

    simulationId = ET.fromstring(response.content).attrib.get("SimulationId")
    ##
    print("Receive model request")
    url2 =  "https://service.solaranywhere.com/api/v2/SimulationResult/" + simulationId
    data = requests.get(url2,
                        auth = HTTPBasicAuth(userName, password)
                        )
    parsed_response = parse_query(data.content)
    print(parsed_response)
    ##
    # review the generated
    import xml.dom.minidom
    parsed = xml.dom.minidom.parseString(generated)
    print("This is the submitted response: ")
    print(parsed.toprettyxml())
    ##
