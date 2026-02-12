#!/usr/bin/env python3
"""Use a SoDA service, expected to be running, to add offsets
a list of concepts that annotate a text."""

import json
from collections import namedtuple
import requests  # pip install Requests  for this module


class SodaMatcher():
    def __init__(self, soda_url):
        """soda_url is like 'http://localhost:8080/soda',
        pointing to a running soda server"""
        self.soda_annot_url = soda_url + "/annot.json"

    def test_enum(d):
        # for testing only, to generate namedtuple Concepts
        # in place of dict concepts
        return (
            namedtuple(
                'Concept',
                ['cfn', # string
                 'conceptID', # string
                 'medicalName', # string
                 'className', # string
                 'styCodes', # list of string
                 'maprelevancy', # float
                 'queryToken',
                 'begin',
                 'end',
                 ])(
                     d.get('cfn'),
                     d.get('conceptID'),
                     d.get('medicalName'),
                     d.get('className'),
                     d.get('styCodes'),
                     d.get('maprelevancy'),
                     d.get('queryToken'),
                     d.get('begin'),
                     d.get('end'),
                 ))

    def soda_annotate(self, lexicon, text, matching):
        body = json.dumps({
            "lexicon": lexicon,
            "text": text,
            "matching": matching
        })
        resp = requests.post(self.soda_annot_url, data=body)
        annot_resp = json.loads(resp.text)
        return annot_resp

    def concept_list_with_offsets(self, clist,
                                  lexicon, text, matching):
        """clist is a list of concepts as returned by CM2/QPE.
        return a list of dicts representing the concepts, with
        offsets added if we can find them with a call to
        self.soda_annotate() if soda server is not running, don't try
        to add offsets.
        """
        c_dict_list = [c._asdict() for c in clist]
        try:
            soda_annot_resp = self.soda_annotate(lexicon, text, matching)
        except requests.exceptions.ConnectionError:
            return c_dict_list
        soda_annotations = soda_annot_resp.get('annotations', [])
        soda_annotation_dict = {a['id']: a for a in soda_annotations[::-1]}

        for c in c_dict_list:
            soda_annotation = soda_annotation_dict.get(c['conceptID'])
            if soda_annotation is not None:
                c['begin'] = soda_annotation['begin']
                c['end'] = soda_annotation['end']
        # for testing:
        # return [SodaMatcher.test_enum(d) for d in c_dict_list]
        return c_dict_list


if __name__ == "__main__":
    # execute only if run as a script
    # ./SodaMatch.py 'Ebola in humans.'
    # should return
    # {
    # "annotations": [
    #     {
    #         "begin": 0,
    #         "confidence": 1.0,
    #         "coveredText": "Ebola",
    #         "end": 5,
    #         "id": "2796192",
    #         "lexicon": "emmet"
    #     }
    # ],
    # "status": "ok"
    # }

    import sys
    import CM2Access # from this directory
    soda_url = 'http://localhost:8080/soda'
    sm = SodaMatcher(soda_url)
    text = sys.argv[1]
    try:
        res = sm.soda_annotate('emmet', text, 'stem2')
        res = json.dumps(res, sort_keys=True, indent=4)
        sys.stdout.write(f'{res}\n')
    except requests.exceptions.ConnectionError:
        print(f'No soda server available at {soda_url}')

    sys.stdout.write(f'\n=======\n\n')
    cm2_url = 'http://ec2-54-224-174-139.compute-1.amazonaws.com/cm2api'
    clist = CM2Access.annotateString(text, cm2_url, api_rev='2')
    w_offsets = sm.concept_list_with_offsets(clist, 'emmet', text, 'stem2')
    res = json.dumps(w_offsets, sort_keys=True, indent=4)
    sys.stdout.write(f'{res}\n')
