### sample script to build and run flame agent
## 1. copy directory structure from another agent, (see e.g., the Executive directory)
##      In GlobalSchedulerCore, make a FLAME directory --> should have setup.py, this file (recompile.sh), and a subdirectory called "flame"
##      FLAME/flame should have __init__.py and agent.py
##      __init__.py and setup.py can be copied from elsewhere
##
## 2. Start volttron -- volttron -v -l volttron.log&
## 3. Runt this script from within the flame directory with volttron running
volttron-ctl remove  --tag flame
cp flame/IPKeys_Root.pem  ~/.volttron/gs_cfg/
volttron-pkg package .
volttron-ctl install ~/.volttron/packaged/flameagent-0.1-py2-none-any.whl --tag flame
volttron-ctl start --tag flame
