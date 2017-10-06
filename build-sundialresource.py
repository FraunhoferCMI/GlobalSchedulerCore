


class SunDialResource()
    def __init__(self, resource_type = "SunDial"):
    """
    
        1. Read a configuration file that tells what resources to include
        2. populate
    """

        self.resource_type     = resource_type
        self.der_member_list   = []
        # get der members from config file
        # parse config file - this should link to DERSite objects.  get site_id
        # curSite = find_site(site_id)
        # self.der_member_list.append(cur_site)

        # now I have a list of der member sites

        # now I need to figure out which cost functions to include.


        self.get_status()
        self.controllable      = "False"  # default to not controllable
        
        
        pass


    def get_health_status(self):
    """
        traverses the list of DER member resources to get status (e.g., online / offline)
    """
        pass


    def get_op_status(self):
        """
        traverses the list of DER member resources to get operataional state (e.g., current pwr)
        """
        pass

    def get_forecast(self):
        """
        retrieves forecast for all of the member resouces
        for each DERSite --> retrieve forcast, add to running tally of Resource forecast
        """


    def set_schedule(self):
        pass


    def execute(self):
        """
        Just a placeholder for describing how the mechnaics of this object would work
        """
        # for each SunDial Resource in SunDial-resource-file
        # initialize either to a "DERsite" or a "SunDial resource"
        # would parse some config files similar to what is done to build a site in the DERDevice class
        # THEN, you would do something like initiate a generate_dispatch() function call
        # For each SunDial resource, it would aggregate...

        # How would htis work?? How do we know what SunDial resources get passed to the optimizer?
        # you need to send it each of tge controllable resource classes, the baseline demand, and...
        # is the top level "SunDial" object - mostly a list of objective functionst to use that are based
        # on....net_demand of the system.

        # Maybe you can assume a fairly flat structure for this whole thing...
        # .... what else? 
