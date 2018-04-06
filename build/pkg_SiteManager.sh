cp ../cfg/SiteCfg/SiteConfiguration-1site.json ~/.volttron/gs_cfg/SiteConfiguration.json
#cp ../cfg/SiteCfg/SiteConfiguration-1siteAndDemand.json ~/.volttron/gs_cfg/SiteConfiguration.json
#cp ../cfg/SiteCfg/SiteConfiguration-Demand.json ~/.volttron/gs_cfg/SiteConfiguration.json
cp ../cfg/SystemCfg/SundialSystemConfiguration.json ~/.volttron/gs_cfg/SundialSystemConfiguration.json
cp ../cfg/DataMap/ShirleySouth-Forecast-data-map.csv ~/.volttron/gs_cfg/
cp ../cfg/DataMap/ShirleySouth-Modbus-data-map.csv ~/.volttron/gs_cfg/
cp ../cfg/DataMap/FLAME-Forecast-data-map.csv ~/.volttron/gs_cfg/

cp ../lib/DERDevice.py ../../../../env/lib/python2.7/site-packages/
cp ../lib/gs_identities.py ../../../../env/lib/python2.7/site-packages/
cp ../lib/gs_utilities.py ../../../../env/lib/python2.7/site-packages/
cp ../lib/HistorianTools.py ../../../../env/lib/python2.7/site-packages/
volttron-pkg package ../SiteManager
