#!/bin/bash
volttron-ctl stop --tag iso
volttron-ctl remove --tag iso
volttron-pkg package .
volttron-ctl install --tag iso ~/.volttron/packaged/ISOAgentagent-0.1-py2-none-any.whl
#volttron-ctl config list   
volttron-ctl start --tag iso
volttron-ctl status
