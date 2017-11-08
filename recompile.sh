volttron-ctl stop --tag ui
volttron-pkg package . 
volttron-ctl remove --tag ui
volttron-ctl install --tag ui ~/.volttron/packaged/uiagent-1.0-py2-none-any.whl
volttron-ctl start --tag ui


