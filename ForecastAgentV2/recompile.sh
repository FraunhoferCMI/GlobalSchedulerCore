volttron-ctl remove --tag real_cpr
volttron-pkg package .
volttron-pkg configure ~/.volttron/packaged/cpragentagent-0.1-py2-none-any.whl config
volttron-ctl install ~/.volttron/packaged/cpragentagent-0.1-py2-none-any.whl  --tag real_cpr
volttron-ctl start --tag real_cpr

