
import json
from datetime import datetime, timedelta
import pandas
import sys
import logging


_log = logging.getLogger("PriceMap")
log_file = "PriceMap.log"
logging.basicConfig(filename=log_file,
                    level=logging.INFO,
                    format='%(asctime)s %(message)s',
                    datefmt="%Y-%m-%dT%H:%M:%S")

CMD_LINE_OUTPUT = 0

def generate_price_map(price_file, start_time, duration, nLoadOptions):
    #start_time.replace(tzinfo=pytz.UTC)
    #start_time = datetime.utcnow().replace(minute=0, second=0, microsecond=0)

    price_data = pandas.read_excel(price_file, sheet_name="Sheet1", header=0, index_col=0)
    forecast_timestamps = [(start_time +
                            timedelta(minutes=t)).strftime("%Y-%m-%dT%H:%M:%S") for t in range(0,
                                                                                               duration * 60,
                                                                                               60)]
    lst = []
    for ii in range(0, len(price_data)):

        tmp = price_data[ii:ii + 1].to_dict(orient='records')
        if tmp[0]["UB"] == "infinity":
            tmp[0]["UB"] = "Infinity"
        if tmp[0]["LB"] == "-infinity":
            tmp[0]["LB"] = "-Infinity"

        tiers = [{"LB": tmp[0]["LB"],
                  "UB": tmp[0]["UB"],
                  "price": tmp[0]["price"]}]

        key_error = False
        cnt = 1
        while not(key_error):
            id="."+str(cnt)
            try:
                if tmp[0]["UB"+id] == "infinity":
                    tmp[0]["UB"+id] = "Infinity"
                if tmp[0]["LB"+id] == "-infinity":
                    tmp[0]["LB"+id] = "-Infinity"

                tiers.append({"LB": tmp[0]["LB"+id],
                              "UB": tmp[0]["UB"+id],
                              "price": tmp[0]["price"+id]})
                cnt +=1
            except KeyError:
                key_error = True

        lst.append(tiers)

    marginalCostCurve = []
    for ii in range(0, len(lst)):
        marginalCostCurve.append({"dstart": forecast_timestamps[ii], "duration": "PT1H", "priceMap": lst[ii]})

    load_shift_request = {"nLoadOptions": nLoadOptions,
                          "marginalCostCurve": marginalCostCurve}

    return load_shift_request


if __name__ == '__main__':
    # usage - python GeneratePriceMap.py <input xlsx file> <output json file> <start_time> <nLoadOptions><duration>


    #### Edit the below parameters to modify output
    #if len(sys.argv) == 2: # input from a file
    #    price_file = sys.argv[1]
        #with open(sys.argv[1], 'r') as f:
        #    sys.stdout.write(f.read())

    #else:   # input from command line
        #price_file = "/Users/mkromer/PycharmProjects/PriceMap/Example1.xlsx"

    try:
        price_file = sys.argv[1]
        print('Using '+price_file)
    except:
        price_file = "Example1.xlsx"
        print("Error - no input file given, using default "+price_file)

    if CMD_LINE_OUTPUT == 0:
        try:
            load_shift_request_file = sys.argv[2]
        except:
            print("Error - no output file given - writing to command line")
            CMD_LINE_OUTPUT = 1

    try:
        start_time_str = sys.argv[3]
        start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%S")
    except:
        start_time_str = "2018-07-25T00:00:00" # replace with desired start time.
        start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%S")
        print("No start time entered or formatted incorrectly (%Y-%m-%dT%H:%M:%S) - using default of "+start_time_str)

    try:
        nLoadOptions = sys.argv[4]
    except:
        nLoadOptions = 5  # use default
        print("No load options provided - using default "+ str(nLoadOptions))

    try:
        duration = int(sys.argv[5])
    except:
        duration = 24  # use default
        print("No duration provided - using default "+ str(duration))


    #####
    load_shift_request = generate_price_map(price_file, start_time, duration, nLoadOptions)

    if CMD_LINE_OUTPUT == 1:
        print(json.dumps(load_shift_request, indent=4, sort_keys=True))
        print("Load Shift Request written to cmd line")
    else:
        json.dump(load_shift_request, open(load_shift_request_file,'w'))
        print("Load Shift Request written to: "+load_shift_request_file)


