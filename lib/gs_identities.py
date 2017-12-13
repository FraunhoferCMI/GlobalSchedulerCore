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


# GS Internal Operating Modes
IDLE = 0
USER_CONTROL = 1
APPLICATION_CONTROL = 2
EXEC_STARTING = 3

EXECUTIVE_CLKTIME = 5 # period, in seconds, at which the executive polls system state
GS_SCHEDULE       = 5  # period, in seconds, at which the GS optimizer runs
STATUS_MSG_PD     = 20 # update rate for various status messages
UI_CMD_POLLING_FREQUENCY = 5 # period, in seconds, at which the UI agent polls UI_cmd.json for a new msg

#FIXME - Placeholder!
SCRAPE_TIMEOUT = 30 # timeout period in seconds for modbus device to post on the IEB bus
