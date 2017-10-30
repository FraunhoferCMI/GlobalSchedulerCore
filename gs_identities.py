
# Site Operating Modes
SITE_IDLE    = 0
SITE_RUNNING = 1

# Site System Control Modes
AUTO = 0
INTERACTIVE = 1

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

EXECUTIVE_CLKTIME = 5 # period, in seconds, at which the executive polls system state
GS_SCHEDULE = 300 # time, in seconds, for GS to run

#FIXME - Placeholder!
SCRAPE_TIMEOUT = 30 # timeout period in seconds for modbus device to post on the IEB bus