"""
Utilities for logging.
"""

import logging
import os
from datetime import date


# General logging function
def start_logging(folder: str, file: str) -> None:
    """
    General logging handler.

    Input:
        folder (str): Log output folder
        file (str): Log file name --> will be appended to
        current date automatically
    """
    if not os.path.isdir(os.path.abspath(folder)):
        os.makedirs(os.path.abspath(folder))

    today = date.today().strftime("%Y%m%d")
    file = f"{today}_{file}.txt"
    print(f"Writing log file to {os.path.join(folder, file)}.")
    logging.basicConfig(
        filename=os.path.join(folder, file),
        encoding="utf-8",
        level=logging.INFO,
        filemode="w",
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
