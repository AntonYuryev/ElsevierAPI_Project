#!/usr/bin/env python
"""Annotate tab-separated file with concepts from CM2. Multiple fields
are separately annotated, e.g.: --fieldNum 6 7 to annotate fields 6 and 7.
Output file is same as input file, with the addition of one tab-separated
field for each fieldNum, the value of which is a json string representing
the list of concepts detected by CM2 in that field.
Example invocation to get concepts in fields 8, 19, 20:
CM2Annotate.py --inputDir sample-EurekaTSV2 --outputDir annotated --fieldNum 8 19 20
"""
import sys
import os
import argparse
import json
from CM2Access import annotateString # from this directory

parser = argparse.ArgumentParser(
    # don't want to reformat the description message, use file's doc_string
    formatter_class=argparse.RawDescriptionHelpFormatter,
    description=__doc__
)
parser.add_argument('--inputDir', dest='inputDir', default='.',
                    help='Input directory. All files here and '
                    'recursively underneath will be annotated. Default=.')
parser.add_argument('--outputDir', dest='outputDir', default='out',
                    help='Output directory. All output is written under here '
                    'in files (not paths) named in INPUTDIR. Default=.')
parser.add_argument('--fieldNum', dest='fieldNum',
                    default=[1], type=int, nargs='*',
                    help='field numbers to annotate,counting from 1. '
                         'Default=1')
args = parser.parse_args()

inputDir = args.inputDir
outputDir = args.outputDir
fieldNums = args.fieldNum


def getFileList(inDir):
    """Return list of all files in or under inDir."""
    matches = []
    for root, dirnames, filenames in os.walk(inDir):
        for filename in filenames:
            matches.append(os.path.join(root, filename))
    return matches


def err_msg(s, level='Error'):
    sys.stderr.write('{}: {}\n'.format(level, s))


def processFile(inFile, inFileName):
    ofName = os.path.join(outputDir, inFileName)
    os.makedirs(outputDir, exist_ok=True)
    with open(inFile) as in_f:
        with open(ofName, 'w') as out_f:
            for line in in_f:
                lineArray = line.strip('\n').split('\t')
                if max(fieldNums) > len(lineArray):
                    msg = 'Expected >= {} tab-separated fields in {}. Got {}'
                    err_msg(msg.format(fieldNums, inFile, line))
                    continue
                for fieldNum in fieldNums:
                    concepts = annotateString(lineArray[fieldNum - 1])
                    cDicts = [c._asdict() for c in concepts]
                    lineArray.append(json.dumps(cDicts, separators=(',', ':')))
                out_f.write('{}\n'.format('\t'.join(lineArray)))


if __name__ == "__main__":
    for inFile in getFileList(inputDir):
        inFileName = os.path.basename(inFile)
        print(inFileName)
        processFile(inFile, inFileName)
