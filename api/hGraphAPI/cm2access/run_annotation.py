#!/usr/bin/env python3
"""Run QPEAccess or CM2Access in a loop over a file of line inputs;
output written to stdout. Parameter service = [cm2|qpe] is required.

Example invocations:
echo headache | ./run_annotation.py --api-rev 1 cm2
echo headache | ./run_annotation.py --api-rev 1 qpe
echo headache | ./run_annotation.py --url https://cm2-hgraph-cert.np.graph.hmelsevier.com/cm2api cm2
./run_annotation.py --in infile --url https://qpe-dev.np.graph.hmelsevier.com/api qpe
"""

import argparse
import sys
import QPEAccess # from this directory
import CM2Access # from this directory

SERVICES = ['cm2', 'qpe', 'qpe-lookup']
API_REVS = ['1', '2']
DEFAULT_API_REV = '1'

LANGS = list(CM2Access.LANG_TO_CM2_LANG_PARAM.keys())

DEFAULT_LANG = 'English'


def parse_args():
    parser = argparse.ArgumentParser(
        # don't want to reformat the description message, use file's doc_string
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__
    )
    parser.add_argument('--ignore-first-col', action='store_true',
                        help='First tab-separated column is not passed to '
                        'CM2/QPE, but is prepended to the output.')
    parser.add_argument('--url', default=None, help=f'API url. '
                        f'Default for QPE is {QPEAccess.DEFAULT_QPE_URL}; '
                        f'Default for CM2 is {CM2Access.DEFAULT_CM2_URL}')
    parser.add_argument('--api-rev', choices=API_REVS, default=DEFAULT_API_REV,
                        help=f'api_rev == "1": pre-2020 api, no sty_info element; '
                        f'api_rev == "2": Jan 2020 api, has sty_info element; '
                        f'default = {DEFAULT_API_REV}')
    parser.add_argument('--input', default='-',
                        help='Input file name or - (default) '
                        'for standard input')
    parser.add_argument('--lang', default=DEFAULT_LANG,
                        choices=LANGS,
                        help=f'Language; default = {DEFAULT_LANG}')
    parser.add_argument('service', choices=SERVICES)
    args = parser.parse_args()
    return args


def get_annotator_input(line, args):
    if args.ignore_first_col:
        metadata, query = line.strip().split('\t', 2)
        query = query.replace('\t', ' ')
        return f'{metadata}\t{query}', query
    else:
        query = line.strip()
        return query, query


def process(args):
    lang = args.lang
    url = args.url
    if url is None:
        if args.service in ['qpe', 'qpe-lookup']:
            url = QPEAccess.DEFAULT_QPE_URL
        else:
            # args.service == 'cm2'
            url = CM2Access.DEFAULT_CM2_URL
    if args.service == 'qpe-lookup':
        def annotate(q):
            return QPEAccess.get_concept_by_imui(q, url)
    elif args.service == 'qpe':
        def annotate(q):
            return QPEAccess.annotateString(q, url, args.api_rev, lang, 'AnalyzeQuery')
    else:
        # args.service == 'cm2'
        def annotate(q):
            return CM2Access.annotateString(q, url, args.api_rev, lang)
    with sys.stdin if args.input == '-' else open(args.input) as in_f:
        for line in in_f:
            prefix, query = get_annotator_input(line, args)
            for c in annotate(query):
                print(f'{prefix}\t{c}')


if __name__ == "__main__":
    args = parse_args()
    process(args)
