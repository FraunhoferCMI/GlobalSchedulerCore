#!/bin/bash
volttron-ctl stop --tag sql
volttron-ctl remove --tag sql
volttron-pkg package ../../../core/SQLHistorian
volttron-pkg configure ~/.volttron/packaged/sqlhistorianagent-3.6.1-py2-none-any.whl ../cfg/Historian/config
volttron-ctl install --tag sql ~/.volttron/packaged/sqlhistorianagent-3.6.1-py2-none-any.whl --vip-identity platform.historian
volttron-ctl start --tag  sql
