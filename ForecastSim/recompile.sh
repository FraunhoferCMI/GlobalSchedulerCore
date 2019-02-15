#cp SAM_PVPwr_nyc.csv  ~/.volttron/gs_cfg/SAM_PVPwr_nyc.csv
cp SAM_PVPwr_nyc_avg.csv ~/.volttron/gs_cfg/SAM_PVPwr_nyc.csv
#cp NYC_demand.csv  ~/.volttron/gs_cfg/NYC_demand.csv
cp NYC_demand_avg.csv  ~/.volttron/gs_cfg/NYC_demand.csv
cp NYC_demand_interpolated.csv  ~/.volttron/gs_cfg/NYC_demand_interpolated.csv
cp NYC_forecast_interpolated.csv  ~/.volttron/gs_cfg/NYC_forecast_interpolated.csv
cp irr_1min.csv  ~/.volttron/gs_cfg/irr_1min.csv
cp solar_forecast_matrix.csv  ~/.volttron/gs_cfg/
cp solar_forecast_ts_matrix.csv ~/.volttron/gs_cfg/

volttron-ctl remove  --tag cpr
volttron-pkg package .
cp forecast_sim/cpr_ghi.pkl ~/.volttron/gs_cfg/cpr_ghi.pkl
volttron-ctl install ~/.volttron/packaged/forecast_simagent-0.1-py2-none-any.whl --tag cpr
#volttron-ctl start --tag cpr
