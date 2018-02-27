#cp SAM_PVPwr_nyc.csv  ~/.volttron/gs_cfg/SAM_PVPwr_nyc.csv
cp irr_1min.csv  ~/.volttron/gs_cfg/irr_1min.csv
volttron-ctl remove  --tag cpr
volttron-pkg package .
cp forecast_sim/cpr_ghi.pkl ~/.volttron/gs_cfg/cpr_ghi.pkl
volttron-ctl install ~/.volttron/packaged/forecast_simagent-0.1-py2-none-any.whl --tag cpr
#volttron-ctl start --tag cpr
