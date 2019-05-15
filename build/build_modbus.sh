#!/bin/bash
volttron-ctl stop --tag mb
volttron-ctl remove --tag mb
volttron-pkg package ../../../core/MasterDriverAgent
volttron-ctl install --tag mb ~/.volttron/packaged/master_driveragent-3.1.1-py2-none-any.whl
volttron-ctl config delete platform.driver --all
#volttron-ctl config store platform.driver config ../../../core/MasterDriverAgent/config

#volttron-ctl config store platform.driver devices/Site1 ../cfg/Modbus/demo_site_devicefile

volttron-ctl config store platform.driver config ../cfg/Modbus/config


volttron-ctl config store platform.driver devices/Site1low ../cfg/Modbus/demo_site_devicefilelow
volttron-ctl config store platform.driver devices/Site1mid ../cfg/Modbus/demo_site_devicefilemid
volttron-ctl config store platform.driver devices/Site1high ../cfg/Modbus/demo_site_devicefilehigh
volttron-ctl config store platform.driver devices/Site2 ../cfg/Modbus/north_site_devicefile

#volttron-ctl config store platform.driver registry_configs/site1_registry.csv ../cfg/Modbus/ShirleyCore.csv --csv
#volttron-ctl config store platform.driver registry_configs/site1_registry.csv ../cfg/Modbus/CtrlCore.csv --csv


#volttron-ctl config store platform.driver registry_configs/site1_registry.csv ../cfg/Modbus/ShirleyTest.csv --csv

volttron-ctl config store platform.driver registry_configs/site1low_registry.csv ../cfg/Modbus/ShirleyTestLow.csv --csv
volttron-ctl config store platform.driver registry_configs/site1mid_registry.csv ../cfg/Modbus/ShirleyTestMid.csv --csv
volttron-ctl config store platform.driver registry_configs/site1high_registry.csv ../cfg/Modbus/ShirleyTestHigh.csv --csv
volttron-ctl config store platform.driver registry_configs/site2_registry.csv ../cfg/Modbus/ShirleyNorth.csv --csv


#volttron-ctl config store platform.driver registry_configs/site1_registry.csv ../cfg/Modbus/DemoRegistry.csv --csv

#volttron-ctl config store platform.driver devices/Shirley-MA/South/PMC ./services/core/MasterDriverAgent/devices/shirley-ma-south-pmc
#volttron-ctl config store platform.driver registry_configs/SOUTH.csv ./services/core/MasterDriverAgent/registry_configs/SOUTH.csv --csv
#volttron-ctl config store platform.driver devices/Shirley-MA/North/PMC ./services/core/MasterDriverAgent/devices/shirley-ma-north-pmc
#volttron-ctl config store platform.driver registry_configs/NORTH.csv ./services/core/MasterDriverAgent/registry_configs/NORTH.csv --csv
volttron-ctl config list platform.driver
#volttron-ctl start --tag mb
#volttron-ctl restart --tag vcp
#volttron-ctl restart --tag vc
#volttron-ctl status
