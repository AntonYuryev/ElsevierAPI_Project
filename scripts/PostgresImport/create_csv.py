import argparse
import csv
import gzip
import logging
import os

from src.deduplicate import dedup
from src.logging import start_logging

# common definitions
tables = ["node", "control", "pathway", "attr"]
pdir = os.path.dirname(os.path.realpath(__file__))  # dir of this program

# column names and data types
table_column_dict = {
    "node": {
        "id": "bigint",
        "urn": "text",
        "name": "text",
        "nodetype": "text",
        "attributes": "ARRAY",
    },
    "control": {
        "id": "bigint",
        "inkey": "ARRAY",
        "inoutkey": "ARRAY",
        "outkey": "ARRAY",
        "controltype": "text",
        "ontology": "text",
        "relationship": "text",
        "effect": "text",
        "mechanism": "text",
        "attributes": "bigint",
    },
    "pathway": {
        "id": "bigint",
        "name": "text",
        "type": "text",
        "urn": "text",
        "attributes": "ARRAY",
        "controls": "ARRAY",
    },
    "reference": {
        "unique_id": "bigint",
        "authors": "text",
        "biomarkertype": "text",
        "celllinename": "text",
        "cellobject": "text",
        "celltype": "text",
        "changetype": "text",
        "collaborator": "text",
        "company": "text",
        "condition": "text",
        "doi": "text",
        "embase": "text",
        "c": "text",
        "essn": "text",
        "experimental_system": "text",
        "intervention": "text",
        "issn": "text",
        "journal": "text",
        "medlineta": "text",
        "mode_of_action": "text",
        "mref": "text",
        "msrc": "text",
        "nct_id": "text",
        "organ": "text",
        "organism": "text",
        "percent": "text",
        "phase": "text",
        "phenotype": "text",
        "pii": "text",
        "pmid": "text",
        "pubversion": "text",
        "pubyear": "integer",
        "pui": "text",
        "px": "double precision",
        "quantitativetype": "text",
        "source": "text",
        "start": "text",
        "studytype": "text",
        "textmods": "text",
        "textref": "text",
        "tissue": "text",
        "title": "text",
        "trialstatus": "text",
        "url": "text",
        "id": "bigint",
        "unique_ref": "text",
    },
    "attr": {"id": "bigint", "name": "text", "value": "text"},
}


def parse_arg():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--no-dedup", action="store_true", help="Disable data deduplication"
    )
    args = parser.parse_args()
    return args


def convert_to_csv(
    input_file: str, output_file: str, delimiter: str, log_interval: float = 5.0
):
    total_size = os.path.getsize(input_file)
    bytes_read = 0
    last_logged_progress = 0

    with open(input_file, "r", encoding="utf-8") as infile, gzip.open(
        output_file, "wt", newline="", encoding="utf-8"
    ) as outfile:
        writer = csv.writer(outfile)
        # write column names
        logging.info("Writing column names.")
        writer.writerow(list(table_column_dict[input_file.split(".")[0]].keys()))
        for key, value in table_column_dict[input_file.split(".")[0]].items():
            logging.info(f"  column name: {key}  -  data type: {value}")

        logging.info("Writing data.")
        for line in infile:
            # Remove quotes if present
            line = line.replace("\x01", "")
            # Split line by delimiter and write to CSV
            row = line.strip().split(delimiter)
            writer.writerow(row)

            # Update bytes read
            bytes_read += len(line.encode("utf-8"))
            # Calculate progress
            progress = bytes_read / total_size * 100
            # Log progress at intervals
            if progress - last_logged_progress >= log_interval:
                logging.info(f"  Progress: {progress:.1f}%")
                last_logged_progress = progress
    logging.info("  Progress: 100%")


def main():
    args = parse_arg()
    start_logging(folder=".", file="create_csv")
    logging.info("Starting conversion of temporary tables to CSV.")

    # deduplicate tables
    if not args.no_dedup:
        for t in tables:
            dedup(f"{t}.table")
    else:
        logging.info("Skipping data deduplication.")

    # convert to csv
    for t in tables:
        logging.info(f"Converting table {t} to CSV.")
        convert_to_csv(
            input_file=f"{t}.table.dedup", output_file=f"{t}.csv.gz", delimiter="\x07"
        )
    # reference table too large for deduplication
    # deduplication usually done in PostgreSQL rather than on disk
    for t in ["reference"]:
        logging.info(f"Converting table {t} to CSV.")
        convert_to_csv(
            input_file=f"{t}.table", output_file=f"{t}.csv.gz", delimiter="\x07"
        )
    logging.info("CSV files created.")
    logging.info("Finishing.")
    logging.shutdown()


if __name__ == "__main__":
    main()
