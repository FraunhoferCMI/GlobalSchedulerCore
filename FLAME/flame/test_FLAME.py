"Tests the functionality of FLAME.py components"
from datetime import datetime, timedelta

import websocket
from websocket import create_connection
import json
import pandas as pd
import os
import logging
import ipdb

from FLAME import *
# if __name__ == '__main__':

websocket.setdefaulttimeout(10) # set timeout quicker for testing purposes, normally 60
ws = create_connection("ws://flame.ipkeys.com:8888/socket/msg")

# Baseline
def test_Baseline():
    print("running Baseline")
    start =  '2018-03-01T00:00:00'
    granularity = 24
    # granularity =  'PT1H'
    duration = 'PT24H'
    bl = Baseline(start, granularity, duration, ws)
    print("processing Baseline")
    bl.process()
    print("Here's the Baseline forecast:\n", bl.forecast)
    print("done processing Baseline")
    return bl

# bl = test_Baseline()
##
def test_LoadShift():
    print("running LoadShift")
    # LoadShift
    ls = LoadShift(ws)
    ls.process()
    print("Here's the LoadShift forecast:\n", ls.forecast)
    print("done processing LoadShift")
    return ls
# ls = test_LoadShift()
##
def test_LoadSelect():
    print("running LoadSelect")
    lsel = LoadSelect(ws, 1)
    lsel.process()
    # print("Here's the LoadSelect response:\n", lsel.response)
    print("Here's the LoadSelect status:\n", lsel.status)
    print("done processing LoadSelect")
    return lsel
# lsel = test_LoadSelect()
##
def test_LoadReport():
    print("running LoadReport")
    loadReport_kwargs = {
        "dstart": "2018-01-01T00:00:00",        #start time for report
        "sampleInterval": "PT1H",            #sample interval
        "duration": "PT24H"            # duration of request
    }
    lr = LoadReport(ws, **loadReport_kwargs)
    lr.process()
    # print("Here's the LoadReport response:\n", lr.response)
    print("Here's the LoadReport loadSchedule:\n", lr.loadSchedule)
    print("done processing LoadReport")
    return lr
# lr = test_LoadReport()
##

def test_Status():
    print("running Status")
    status = Status(ws)
    status.process()
    # print("Here's the Status response:\n", status.response)
    print("Here's the Status alertStatus:\n", status.alertStatus)
    print("Here's the Status currentProfile:\n", status.currentProfile)
    print("done processing Status")
    return status
# status = test_Status()
##
