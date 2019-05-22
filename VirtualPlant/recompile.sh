### sample script to build and run flame agent
## 1. copy directory structure from another agent, (see e.g., the Executive directory)
##      In GlobalSchedulerCore, make a FLAME directory --> should have setup.py, this file (recompile.sh), and a subdirectory called "flame"
##      FLAME/flame should have __init__.py and agent.py
##      __init__.py and setup.py can be copied from elsewhere
##
## 2. Start volttron -- volttron -v -l volttron.log&
## 3. Runt this script from within the flame directory with volttron running
volttron-ctl remove  --tag vp
volttron-pkg package .
volttron-ctl install ~/.volttron/packaged/vpagent-1.0-py2-none-any.whl --tag vp
volttron-ctl start --tag vp
