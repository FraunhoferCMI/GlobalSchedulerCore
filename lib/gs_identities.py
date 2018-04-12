# Copyright (c) 2017, The Fraunhofer Center for Sustainable Energy
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in
#    the documentation and/or other materials provided with the
#    distribution.
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# This material was prepared as an account of work sponsored by an agency
# of the United States Government.  Neither the United States Government
# nor any agency thereof, nor Fraunhofer, nor any of their employees,
# makes any warranty, express or implied, or assumes any legal liability
# or responsibility for the accuracy, completeness, or usefulness of any
# information, apparatus, product, or process disclosed, or represents
# that its use would not infringe privately owned rights.
#
# Reference herein to any specific commercial product, process, or service
# by trade name, trademark, manufacturer, or otherwise does not necessarily
# constitute or imply its endorsement, recommendation, or favoring by the
# United States Government or any agency thereof, or Fraunhofer.  The
# views and opinions of authors expressed herein do not necessarily state
# or reflect those of the United States Government or any agency thereof.

from datetime import datetime, timedelta

# execution flags
USE_VOLTTRON = 1
USE_LABVIEW  = 1

# Site Operating Modes
SITE_IDLE    = 0
SITE_RUNNING = 1

# Site System Control Modes
AUTO        = 0
INTERACTIVE = 1
STARTING    = 2
READY       = 3

DISABLED = 0
ENABLED  = 1

# Site Timeout
PMC_HEARTBEAT_TIMEOUT = 100 # timeout, in seconds
PMC_HEARTBEAT_PD      = 10 # expected period, in seconds
PMC_HEARTBEAT_RESET   = 24 * 60 * 60 # heartbeat reset frequency, in seconds
PMC_WATCHDOG_PD       = 10 # expected heartbeat, in seconds
PMC_WATCHDOG_RESET    = 24 * 60 * 60 # watchdog reset frequency, in seconds
IGNORE_HEARTBEAT_ERRORS = 1

# GS Internal Operating Modes
IDLE = 0
USER_CONTROL = 1
APPLICATION_CONTROL = 2
EXEC_STARTING = 3

EXECUTIVE_CLKTIME = 1 # period, in seconds, at which the executive polls system state
GS_SCHEDULE       = 30  # period, in seconds, at which the GS optimizer runs
ESS_SCHEDULE      = 5
STATUS_MSG_PD     = 20 # update rate for various status messages
UI_CMD_POLLING_FREQUENCY = 5 # period, in seconds, at which the UI agent polls UI_cmd.json for a new msg
START_LATENCY = 0 # time in seconds, to delay execution

#FIXME - Placeholder!
MODBUS_SCRAPE_INTERVAL = 1 # period in seconds for modbus device to post on the IEB bus
MODBUS_AVERAGING_WINDOW = 60 # period in seconds over which to average instantaneous readings
MODBUS_PTS_PER_WINDOW = int(MODBUS_AVERAGING_WINDOW/MODBUS_SCRAPE_INTERVAL)
CPR_QUERY_INTERVAL = 5 # period in seconds for forecasts to arrive
MODBUS_WRITE_ATTEMPTS  = 5  # number of modbus reads before a write error is thrown

SSA_SCHEDULE_DURATION = 24 # Duration, in hours, over which SSA generates schedules
SSA_SCHEDULE_RESOLUTION   = 60 # Time resolution, in minutes, of SSA schedule
SSA_PTS_PER_SCHEDULE = SSA_SCHEDULE_DURATION * 60/SSA_SCHEDULE_RESOLUTION

REGULATE_ESS_OUTPUT = False

# For configuring w/simulated data
USE_SIM        = 1
USE_SOLAR_SIM  = 1
USE_DEMAND_SIM = 1
SIM_SCENARIO   = 1
SIM_HRS_PER_HR = 1 # used to set time acceleration.  1 = normal time.  60 = 60x acceleration
if SIM_SCENARIO == 1:
    PV_FORECAST_FILE = "SAM_PVPwr_nyc.csv"  # "irr_1min.csv"
    PV_FORECAST_FILE_TIME_RESOLUTION_MIN = 60  # 1
    SIM_START_DAY = 202  # day 106 #2  # day 202, Hr = 5 # 200, Hr = 7
    SIM_START_HR  = 5
else:
    PV_FORECAST_FILE = "irr_1min.csv"
    PV_FORECAST_FILE_TIME_RESOLUTION_MIN = 1
    SIM_START_DAY = 200  # day 106 #2  # day 202, Hr = 5 # 200, Hr = 7
    SIM_START_HR  = 7

DEMAND_FORECAST_FILE = "NYC_demand.csv"
DEMAND_FORECAST_FILE_TIME_RESOLUTION_MIN = 60
DEMAND_FORECAST_QUERY_INTERVAL = 10 # seconds
LOADSHIFT_QUERY_INTERVAL = 30 # seconds
DEMAND_REPORT_SCHEDULE = 10 # SECONDS

SIM_START_TIME = datetime(year=2018, month=1, day=1, hour=0, minute=0, second=0) + timedelta(hours=SIM_START_HR, days=SIM_START_DAY-1)