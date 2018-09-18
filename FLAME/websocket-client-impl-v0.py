from websocket import create_connection
import json

### BaselineRequest ###
payload_baseline = json.dumps({'type': 'BaselineRequest',
                                       'msg': {'dstart': '2018-01-01T00:00:00','granularity': 'PT1H','duration': 'PT24H'
                                               }})

ws = create_connection("ws://flame.ipkeys.com:8888/socket/msg",timeout=None)
print ("Sending Request")
ws.send(payload_baseline)
print("Send")
print("Receiving")
result_json = ws.recv()
print("received")
result = json.loads(result_json)


# parse BaselineRequest Response
forecast_values = dict()
Forecast =[]
Time = []

for loadSchedule, LSvalue in result['msg'].items():
            print(loadSchedule,"is",LSvalue)
            for i in range(len(LSvalue)):
                for data,value in LSvalue[i].items():

                    if data == 'value':
                        Forecast.append(value)
                    elif data == 'dstart':
                        Time.append(value)
                    elif data == 'units':
                        Units = value
                    elif data == 'duration':
                        Resolution = value

Duration = (len(LSvalue))

forecast_values = {"Forecast": Forecast, "Time":Time, "Duration": Duration, "Resolution": Resolution}

print(forecast_values)


### LoadRequest ###

payload_loadreq = json.dumps({"type":"LoadRequest","msg":{"nLoadOptions":"12","marginalCostCurve":[{"dstart":"2018-01-01T01:00:00","duration":"PT1H","priceMap":[{"LB":"-Infinity","UB":0,"price":0.05},{"LB":0,"UB":200,"price":0.1},{"LB":200,"UB":"Infinity","price":2.94}]},{"dstart":"2018-01-01T23:00:00","duration":"PT1H","priceMap":[{"LB":"-Infinity","UB":0,"price":0},{"LB":0,"UB":200,"price":0},{"LB":200,"UB":"Infinity","price":0}]}]}})

print('Sending LoadRequest')

ws.send(payload_loadreq)

print('Receiving LoadRequest response')

result1_json = ws.recv()
result1 = json.loads(result1_json)


### MAK comment - the below is not parsing the message correctly
### Instead of organizing as a list organized by field, it should be organized
### as a dict organized by profile.
### i.e., I think the native JSON response is already exactly how one would want to publish.

# parse response
OptionID = []
ImplementationCost = []
Load =[]
TimeLoad = []
Unit = []
Resolution =[]


for Options,Ovalue in result1['msg'].items():
  # print(Options,"* is *",Ovalue)
  print('length is',len(Ovalue))
  for i in range(len(Ovalue)):

    for k, v in Ovalue[i].items():
        # print(k,"** is **",v)
        if k == 'optionID':
            OptionID.append(v)
        elif k == 'implementationCost':
            ImplementationCost.append(v)
        elif k == 'loadSchedule':
            # print(k)
            for j in range(len(Ovalue[i][k])):
                for k1,v1 in Ovalue[i][k][j].items():
                    # print(k1,'***is***',v1)

                    if k1 == 'dstart':
                        TimeLoad.append(v1)
                    elif k1 == 'duration':
                        Resolution = v1
                    elif k1 == 'value':
                        Load.append(v1)
                    elif k1 == 'units':
                        Unit = v1

print(ImplementationCost)
print(OptionID)
print(TimeLoad)
print(Load)
print(Unit)
print(Resolution)

ws.close()
