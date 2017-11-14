volttron-ctl remove  --tag cpr
volttron-pkg package .
volttron-ctl install ~/.volttron/packaged/forecastagentagent-0.2-py2-none-any.whl --tag cpr
volttron-ctl start --tag cpr
