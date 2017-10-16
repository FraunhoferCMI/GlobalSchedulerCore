volttron-ctl stop --tag sm
volttron-pkg package . 
volttron-ctl remove --tag sm
volttron-ctl install --tag sm ~/.volttron/packaged/site_manageragent-1.0-py2-none-any.whl
volttron-ctl start --tag sm


