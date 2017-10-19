volttron-ctl stop --tag ui
volttron-pkg package . 
volttron-ctl remove --tag ui
volttron-ctl install --tag ui ~/.volttron/packaged/<namehere>.whl
volttron-ctl start --tag ui


