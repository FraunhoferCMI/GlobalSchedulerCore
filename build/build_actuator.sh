volttron-ctl stop --tag act
volttron-ctl remove --tag act
volttron-pkg package ../../../core/ActuatorAgent/
volttron-ctl install --tag act ~/.volttron/packaged/actuatoragent-1.0-py2-none-any.whl 

