cp ../cfg/SiteCfg/SiteConfiguration-1site.json ~/.volttron/gs_cfg/SiteConfiguration.json
cp ../cfg/SystemCfg/SundialSystemConfiguration.json ~/.volttron/gs_cfg/SundialSystemConfiguration.json
cp ../cfg/DataMap/ShirleySouth-Forecast-data-map.csv ~/.volttron/gs_cfg/
#cp ../cfg/DataMap/ShirleySouth-Modbus-data-map.csv ~/.volttron/gs_cfg/
#cp ../cfg/DataMap/ShirleySouth-Core-Modbus-data-map.csv ~/.volttron/gs_cfg/ShirleySouth-Modbus-data-map.csv
cp ../cfg/DataMap/ShirleySouth-CtrlCore-Modbus-data-map.csv ~/.volttron/gs_cfg/ShirleySouth-Modbus-data-map.csv

cp ../lib/DERDevice.py ../../../../env/lib/python2.7/site-packages/
cp ../lib/gs_identities.py ../../../../env/lib/python2.7/site-packages/
cp ../lib/HistorianTools.py ../../../../env/lib/python2.7/site-packages/
volttron-pkg package ../SiteManager
