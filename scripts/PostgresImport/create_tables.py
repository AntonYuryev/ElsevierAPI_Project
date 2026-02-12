#!/bin/python3

import logging
import os
import re
import sys

from src.dbconnect import getConnection, psql_cmd
from src.deduplicate import dedup
from src.logging import start_logging

# common definitions
tables = ["node", "control", "pathway", "attr"]

pdir = os.path.dirname(os.path.realpath(__file__))  # dir of this program


def initdb(schema):
    """initialize db"""

    drop = "drop schema if exists " + schema + " cascade;"

    sql = """
    create schema xxxx;
    create table  xxxx.version(name text, value text);
    create table  xxxx.attr( id bigint, name text, value text);
    create table  xxxx.node( id bigint, urn text, name text, nodetype text, attributes bigint[]);

    create table  xxxx.control(id bigint, inkey bigint[], inoutkey bigint[], outkey bigint[], controltype text,
        ontology text, relationship text, effect text, mechanism text, attributes bigint);

    create table xxxx.pathway(id bigint, name text, type text, urn text, attributes bigint[], controls bigint[]);

    create table xxxx.reference ( unique_id bigint,
       Authors text, BiomarkerType text, CellLineName text, CellObject text,
       CellType text, ChangeType text, Collaborator text, Company text, Condition text,
       DOI text, EMBASE text, c text, ESSN text, Experimental_System text, Intervention text,
       ISSN text, Journal text, MedlineTA text, Mode_of_Action text,
       mref text, msrc text, NCT_ID text, Organ text, Organism text, Percent text,
       Phase text, Phenotype text, PII text, PMID text, PubVersion text, PubYear integer, PUI text,
       pX float, QuantitativeType text, Source text, Start text, StudyType text, TextMods text,
       TextRef text, Tissue text, Title text, TrialStatus text, URL text, id bigint, unique_ref text);
    """

    sql = re.sub("xxxx", schema, sql)
    conn = getConnection()

    logging.info("initializing schema")
    try:
        logging.info(f"execute {drop}")
        with conn.cursor() as cur:
            cur.execute(drop)
            conn.commit()
    except:
        logging.info("schema did not exist")
        conn.commit()

    with conn.cursor() as cur:
        for line in sql.split(";"):
            if line.strip() != "":
                logging.info(f"sql {line}")
                cur.execute(line)
                conn.commit()


def indexdb(schema):
    # create indices """
    with open(pdir + "/sql/resnet.sql", "r") as sf:
        lsql = sf.read()

    conn = getConnection()
    lsql = re.sub("xxxx", schema, lsql)

    with conn.cursor() as cur:
        statements = lsql.split(";")
        for statement in statements:
            if statement.strip() != "" and not statement.startswith("--"):
                logging.info(statement)
                cur.execute(statement)
                conn.commit()

    conn.commit()
    conn.close()


def combine_temp(schema):
    """combine temporary tables with main database"""
    logging.info("combining tables")
    conn = getConnection()
    tables = ["attr", "node", "control", "pathway", "reference"]

    lschema = re.sub("_temp", "", schema)

    # insert data
    for table in tables:
        sql = (
            "insert into "
            + lschema
            + "."
            + table
            + " select * from "
            + schema
            + "."
            + table
            + " on conflict do nothing "
        )
        logging.info(sql)
        with conn.cursor() as cur:
            cur.execute(sql)
            logging.info(f"{table} {cur.rowcount} rows inserted")

    # drop temp schema
    drop = "drop schema if exists " + schema + " cascade;"
    with conn.cursor() as cur:
        cur.execute(drop)

    conn.commit()
    conn.close()


def load(schema):
    """load tables.  the only feasible way for tables this large is to use the copy command"""

    copycmd1 = (
        "\copy "
        + schema
        + ".xxxx from 'xxxx.table.dedup' with (delimiter E'\x07' ,format csv, quote E'\x01')"
    )
    copycmd2 = (
        "\copy "
        + schema
        + ".xxxx from 'xxxx.table' with (delimiter E'\x07' ,format csv, quote E'\x01')"
    )

    initdb(schema)

    for t in tables:
        dedup(t + ".table")

    for t2 in tables:
        logging.info(f"loading table {t2}")
        cmd = re.sub("xxxx", t2, copycmd1)
        logging.info(psql_cmd(cmd))

    for t2 in ["reference", "version"]:
        if os.path.exists(t2 + ".table"):
            logging.info(f"loading table {t2}")
            cmd = re.sub("xxxx", t2, copycmd2)
            logging.info(cmd)
            logging.info(psql_cmd(cmd))

    logging.info("starting indexing")
    indexdb(schema)
    logging.info("finished indexing")

    # combine update with full tables
    if "_temp" in schema:
        logging.info("merging tables")
        combine_temp(schema)


#
# needs an argument to specify whether this is a load from the bulk file or
# a load from an update
#
def main():
    start_logging(folder=".", file="create_tables")
    if len(sys.argv) < 2:
        logging.warning(
            " need schema name resnet for full load or resnet_temp for update"
        )

    schema = sys.argv[1]
    load(schema)
    logging.info("done")


if __name__ == "__main__":
    copycmd1 = (
        "\copy "
        + "schema"
        + ".xxxx from 'xxxx.table.dedup' with (delimiter E'\x07' ,format csv, quote E'\x01')"
    )
    for t2 in tables:
        cmd = re.sub("xxxx", t2, copycmd1)
        continue
    main()