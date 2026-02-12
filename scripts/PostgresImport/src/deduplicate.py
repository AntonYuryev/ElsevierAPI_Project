import logging
import subprocess

dedupcmd = "sort -T `pwd` --field-separator=$'\\x07' --key=1,1 -u {fname}_temp > {fname}.dedup; rm {fname}_temp"
reversecmd = "tac {fname} > {fname}_temp"


def run_command(command: str) -> None:
    result = subprocess.run(
        command, shell=True, executable="/bin/bash", capture_output=True, text=True
    )
    if result.stdout:
        logging.info(result.stdout)
    if result.stderr:
        logging.error(result.stderr)
    if result.returncode != 0:
        logging.error(
            f"Command '{command}' failed with return code {result.returncode}."
        )


def dedup(fname: str) -> None:
    logging.info(f"deduplicating {fname}")
    lcmd = dedupcmd.format(fname=fname)
    rev = reversecmd.format(fname=fname)
    run_command(rev)
    run_command(lcmd)
