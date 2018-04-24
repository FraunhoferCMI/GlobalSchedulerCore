import xml.etree.ElementTree as ET
from  xml.etree.ElementTree import tostring
from xml.dom import minidom

def create_xml_query(start, end):
    "Create xml query to CPR model"

    CreateSimulationRequest = ET.Element("CreateSimulationRequest",
                                         xmlns="http://service.solaranywhere.com/api/v2")
    EnergySites = ET.SubElement(CreateSimulationRequest, "EnergySites")
    EnergySite = ET.SubElement(EnergySites, "EnergySite",
                               Name="SHINES-Shirley, MA",
                               Description="Shirley site in MA, higher resolution")
    Location = ET.SubElement(EnergySite, "Location",
                             Latitude="42.5604788",
                             Longitude="-71.6331026")

    PvSystems = ET.SubElement(EnergySite, "PvSystems")
    PvSystem = ET.SubElement(PvSystems, "PvSystem",
                             Albedo_Percent="17",
                             GeneralDerate_Percent="85.00")
    Inverters = ET.SubElement(PvSystem, "Inverters")
    Inverter = ET.SubElement(Inverters, "Inverter",
                             Count="2",
                             MaxPowerOutputAC_kW="500.00000",
                             EfficiencyRating_Percent="98.000000")

    PvArrays = ET.SubElement(PvSystem, "PvArrays")
    PvArray = ET.SubElement(PvArrays, "PvArray")
    PvModules = ET.SubElement(PvArray, "PvModules")
    PvModule = ET.SubElement(PvModules, "PvModule",
                             Count="3222",
                             NameplateDCRating_kW="0.310000",
                             PtcRating_kW="0.284800",
                             PowerTemperatureCoefficient_PercentPerDegreeC="0.43",
                             NominalOArrayperatingCellTemperature_DegreesC="45")
    ArrayConfiguration = ET.SubElement(PvArray, "ArrayConfiguration",
                                       Azimuth_Degrees="232",
                                       Tilt_Degrees="20.000",
                                       Tracking="Fixed",
                                       TrackingRotationLimit_Degrees="90")

    SimulationOptions = ET.SubElement(CreateSimulationRequest, "SimulationOptions",
                                      PowerModel="CprPVForm",
                                      ShadingModel="ShadeSimulator",
                                      OutputFields=",".join(["StartTime",
                                                             "EndTime",
                                                             "PowerAC_kW",
                                                             "GlobalHorizontalIrradiance_WattsPerMeterSquared",
                                                             "AmbientTemperature_DegreesC"
                                                             ]))

    WeatherDataOptions = ET.SubElement(SimulationOptions, "WeatherDataOptions",
                                       WeatherDataSource="SolarAnywhere3_2",
                                       WeatherDataPreference = "Auto",
                                       PerformTimeShifting = "true",
                                       StartTime=start,
                                       EndTime=end,
                                       SpatialResolution_Degrees="0.01",
                                       TimeResolution_Minutes="60")

    xml_string = tostring(CreateSimulationRequest)
    # ppxml = xml.dom.minidom.parseString(xml_fname)
    # print(ppxml.toprettyxml())

    return xml_string


def parse_query(query):
    """ Function to parse XML response from API"""
    xmldoc = minidom.parseString(query)
    SimPd = xmldoc.getElementsByTagName('SimulationPeriod')
    results ={"results":[[sim.attributes['StartTime'].value,float(sim.attributes['PowerAC_kW'].value)]
                for sim in SimPd],
            "Units":"kWh",
            "tz": "UTC-5",
            "data_type":"float"
        }
    return results

if __name__ == "__main__":
    headers =  {'content-type': "text/xml; charset=utf-8",
                'content-length': "length",}
    url = "https://service.solaranywhere.com/api/v2/Simulation"
    userName = "schoudhary@cse.fraunhofer.org"
    password = "Shines2017"
    querystring = {"key":"FRHR3MXX7"}
    start = datetime.datetime.isoformat(datetime.datetime.now(tz=pytz.timezone('America/New_York')).replace(microsecond=0,second=0,minute=0)+timedelta(hours=1))
    end  = datetime.datetime.isoformat(datetime.datetime.now(tz=pytz.timezone('America/New_York')).replace(microsecond=0,second=0,minute=0)+timedelta(hours=6))

    ##
    print("Request model")
    complete_payload = payload.format(start, end)
    generated = create_xml_query(start, end)
    response = requests.post(url,
                             auth=HTTPBasicAuth(userName, password),
                             data=generated.decode(),
                             # data=complete_payload,
                             headers=headers,
                             params=querystring)

    ##
    print("Receive model request")
    url2 =  "https://service.solaranywhere.com/api/v2/SimulationResult/" + self.simulationId
    data = requests.get(url2,
                        auth = HTTPBasicAuth(userName, password)
                        )
    parsed_response = parse_query(data.content)
    ##
