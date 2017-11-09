#!/usr/bin/python
import csv
import pymonetdb
import sys
import datetime
import argparse



def main(args):
    """
Load one of the ISONE historical CSVs into Monetdb
    """
    C = pymonetdb.connect("voc")
    table="lmp_5min"
    # todo:
    # open the CSV. Skip the right rows.
    # do an insert.
    c=C.cursor()
    W = csv.reader(open(args[1]))
    fdate = None
    for row in W:
        if ( row[0] == "C" and
             row[1].startswith("Report for: ")):
             fdate = datetime.datetime.strptime(
                 row[1][:24],
                 "Report for: %m/%d/%Y -").date()
        if row[0] == "D":
            row[2] = pymonetdb.sql.monetize.convert(
                datetime.datetime.combine(
                    fdate,
                    pymonetdb.py_time(row[2])).isoformat())            
            query = "insert into %s values (%s);"%(
                table,
                ','.join(row[1:]))
            print C.execute(query)
    C.commit()
                
if __name__ == "__main__":
    main(sys.argv)

        
    
