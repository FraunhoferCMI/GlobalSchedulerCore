cp ../GS_Optimizer/SunDialResource.py ../../../../env/lib/python2.7/site-packages/
cp ../GS_Optimizer/SSA_Optimization.py ../../../../env/lib/python2.7/site-packages/
cp ../GS_Optimizer/loadshape_irronly.csv ~/.volttron/gs_cfg/loadshape.csv
cp ../GS_Optimizer/ObjectiveFunctions.py ../../../../env/lib/python2.7/site-packages/
cp ../GS_Optimizer/GeneratePriceMap.py ../../../../env/lib/python2.7/site-packages/

volttron-ctl stop --tag exec
sh ../build/pkg_SiteManager.sh
volttron-pkg package .
volttron-ctl remove --tag exec
volttron-ctl install --tag exec ~/.volttron/packaged/executiveagent-1.0-py2-none-any.whl 
volttron-ctl start --tag exec


