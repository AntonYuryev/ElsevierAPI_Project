import logging
import os
from subprocess import check_output

import psycopg2 as psql

from .credentials import dbase, host, password, user

#
# create the file credentials.py with these variables:
# this lets the github allow you to add your own credentials without
# editing the file from git.
#
# host = 'localhost'
# user = 'rmc'
# password = ''
# dbase = 'rmc'


def getConnection():
    conn = psql.connect(dbname=dbase, user=user, password=password, host=host)
    return conn


def psql_cmd(command):
    env = dict(os.environ, PGPASSWORD=password)
    out = check_output(
        ["psql", "-h", host, "-U", user, "-d", dbase, "-c", command], env=env
    )
    logging.info(f"output: {out.decode('utf8')}")
