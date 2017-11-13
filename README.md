# Global-Scheduler-Core
This is the top-level repository for the core Global Scheduler code.  It is is intended to be installed in the services/contrib directory of a valid volttron instance.  

Detailed information about the code base can be found in the Software Design Document. 

Overview of GlobalSchedulerCore Repository - 

	cfg / Modbus -- Modbus device and registry configuration files 
	cfg / SiteCfg -- SiteConfiguration json files
	cfg / DataMap -- Data Map file repository
	cfg / SystemCfg -- SystemConfiguration repository
	build - location for some automatic recompile scripts
	Executive/ - Executive Agent
	SiteManager/ - SiteManager Agent
	UI/ - UI Agent
	ForecastSim/ - Forecast Simulation Agent
	ISONE_API/ - ISONE API Agent
	lib/ - holds shared libraries for the GS code


INSTRUCTIONS for BUILDING & USING

1.	Configure linux environment per instructions on VOLTTRON website.  
2.	Set up appropriate credentials with the CSE GitHub account
3.	Clone a valid VOLTTRON fork from git
4.	Set up VOLTTRON development environment by running bootstrap from the newly created volttron/ directory
                             python2.7 bootstrap.py
5.	Change to the “contrib” agent directory
                           cd $HOME_DIR/volttron/services/contrib
6.	Clone GlobalSchedulerCore Repository

7.	mkdir  ~/.volttron/gs_cfg


IF ~/.volttron is not a valid path, modify the above gs_cfg location accordingly.  Also it is necessary to modify build scripts to point to the right location for .volttron
 (This is where SiteConfiguration, SystemConfiguration, and DataMap files get copied)

8.	Start volttron
                        volttron -v -l <logfile location>&

9.	Build / package agents.
The build process is not currently automated, and do not have paths, etc properly set up.
Some of the build scripts copy files to a known location - 
-	Various configuration files are copied to ~/.volttron/gs_cfg 
-	Some shared modules from the lib directory are copied to volttron/env/lib/python/site-packages


a.	package SiteManager - build script located @ GlobalSchedulerCore/build/pkg_SiteManager.sh
(SiteManager gets installed when Executive starts up)
b.	configure / build MasterDriver - build script @ GlobalSchedulerCore/build/build_modbus.sh
will build with a valid, internally consistent registry.  Need to set the slave target IP address and port in demo_site_devicefile

review build script for guidance about how to specify different device or registry config files.

c.	Build Actuator
build script @ GlobalSchedulerCore/build/build_actuator.sh

d.	Build Executive - run recompile.sh in Executive/
e.	Build UI - run recompile.sh in UI/
f.	Build ForecastSim
The irradiance data file it reads requires pandas version 0.19.2  (data files using an older version of pickle)
			(pip install pandas==0.19.2)
	
	Then run recompile.sh in ForecastSim/


10.	Start agents running (exec starts automatically as part of the recompile script)
                    volttron-ctl start --tag mb act ui cpr

11.	Check status
                  volttron-ctl status
hopefully all agents should be listed and running

12.	Check log file for feedback from system
13.	To do something useful:
a.	Start a modbus slave emulator communicating w/MasterDriver at the specified IP address.

A variety of command scripts (For use with the UI agent) are available at:
https://github.com/FraunhoferCSE/CmdScripts.git
	These enable user to change mode, start application control mode, and issue ESS commands.

14.	If volttron shuts down improperly, you will need to manually remove any SiteManager agents (this is an unhandled exception)
volttron-ctl remove <agentID>
