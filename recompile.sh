volttron-ctl remove  --tag cpr
volttron-pkg package .
volttron-ctl install /home/volttron/.volttron/packaged/cpragentagent-0.1-py2-none-any.whl --tag cpr
volttron-ctl start --tag cpr
