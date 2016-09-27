#!/usr/bin/python
import sys
import requests
import argparse
import json
import pprint
from optparse import OptionParser
usage = """
"""

USERNAME = "ocschwar@mit.edu"
PASSWORD = ""
PREFIX = "https://webservices.iso-ne.com/api/v1.1/"

def main(argv):
    parser = argparse.ArgumentParser(
        description = "Fetch data from ISONE")
    parser.add_argument(
        "--username",help="ISONE username",
        default=USERNAME,
        action="store"
    )
    parser.add_argument(
        "--password",
        default=PASSWORD
    )
    parser.add_argument(
        "--prefix",help="prefix for REST operations",
        default=PREFIX
    )
    opts,args = parser.parse_known_args(argv)
    auth = requests.auth.HTTPBasicAuth(opts.username,opts.password)
    for a in args[1:]:
        req = requests.get(opts.prefix+a,
                           headers={"Accept":"application/json"},
                           auth=(opts.username,opts.password))
        print (opts.prefix+a)
        print(req.status_code)
        print(req.text)
        pprint.pprint(req.json())
    
                
if __name__ == "__main__":
    main(sys.argv)

