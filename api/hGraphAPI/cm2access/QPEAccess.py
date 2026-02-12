#!/usr/bin/env python

# ### Access to the QPE query parser
#
# This code defines one public function:
# ```
# annotateString(s, url='http://emmet-qpe.clinicalkey.com:8080/qpe/api')
#     Pass string s to an EMMeT QPE service at the given url. Return
#     a list of Concepts that the QPE parsed from the string, or []
#     if none found or if there was a connection or parsing error.
#     url defaults to URL defined thus:
#     scheme = 'http'
#     host = 'emmet-qpe.clinicalkey.com'
#     port = '8080'
#     endpoint = 'qpe/api'
#     URL = '{}://{}:{}/{}'.format(scheme, host, port, endpoint)
# ```
# Concept is a named tuple with these fields:
# ```
#     cfn              # string
#     conceptID        # string
#     medicalName      # string
#     className        # string
#     styCodes         # list of string
#     isHealthRelated  # boolean
#     synonyms         # list of string
#
# ```

import sys
from collections import namedtuple
import requests  # pip install Requests  for this module

#DEFAULT_QPE_URL = 'https://qpe.graph.hmelsevier.com/api'
#DEFAULT_QPE_URL = 'http://api.healthcare.elsevier.com:443/h/qpe/nonprod/v1/1.0.0'
DEFAULT_QPE_URL = 'http://api.healthcare.elsevier.com:80/h/qpe/nonprod/v1/'

LANG_TO_QPE_LANG_PARAM = {
    'English': 'en',
    'French': 'fr',
    'Spanish': 'es',
    'German': 'de',
    'Portuguese': 'pt',
}

DEFAULT_QPE_LANG = 'English'

# Concept is immutable tuple with named fields
Concept_orig = namedtuple('Concept',
                     ['cfn', # string
                      'conceptID', # string
                      'medicalName', # string
                      'className', # string
                      'styCodes', # list of string
                      'queryToken', # string
                      'isHealthRelated', # boolean
                      'synonyms']) # list of string


# Concept is immutable tuple with named fields
Concept = namedtuple('Concept',
                     ['cfn', # string
                      'conceptID', # string
                      'medicalName', # string
                      'className', # string
                      'styCodes', # list of string
                      'queryToken', # string
                      'synonyms', # list of string
                      ])


def _createConcept_orig(jsonResponseMap):
    styCodesStr = jsonResponseMap.get('sty_codes', '')
    styCodes = [] if styCodesStr == '' else styCodesStr.split('|')
    synCodesStr = jsonResponseMap.get('synonyms', '')
    synonyms = [] if synCodesStr == '' else synCodesStr.split('|')
    return Concept_orig(
        jsonResponseMap.get('cfn', ''),
        jsonResponseMap.get('ConceptId', ''),
        jsonResponseMap.get('MedicalName', ''),
        jsonResponseMap.get('ClassName', ''),
        styCodes,
        jsonResponseMap.get('Query', 'notoken'),
        jsonResponseMap.get('isHealthRelated', ''),
        synonyms
    )


def _createConcept(jsonResponseMap):
    sty_info = jsonResponseMap.get('sty_info', [])
    # primary sort to get preferred stys at front
    # secondary sort on name to ensure deterministic order
    sty_info = sorted(sorted(sty_info, key=lambda r: r['name']),
                       key=lambda r: r['preferred'], reverse=True)

    sty_codes = [c['code'] for c in sty_info]
    preferred_stys = [c for c in sty_info if c.get('preferred')]
    # len(preferred_stys) should be 1, but not guaranteed
    if len(preferred_stys) >= 1:
        class_name = preferred_stys[0].get('class_name', '')
    else:
        class_name = ''
    synCodesStr = jsonResponseMap.get('synonyms', '')
    synonyms = [] if synCodesStr == '' else synCodesStr.split('|')
    return Concept(
        jsonResponseMap.get('cfn', ''),
        jsonResponseMap.get('ConceptId', ''),
        jsonResponseMap.get('MedicalName', ''),
        class_name,
        sty_codes,
        jsonResponseMap.get('Query', 'notoken'),
        synonyms,
    )


def _createConcept_tmp(json_response):
    synonyms = json_response.get('synonyms', [])
    return Concept(
        json_response.get('cfn', ''),
        json_response.get('ConceptId', '') or json_response.get('imuid', ''),
        json_response.get('MedicalName', '') or json_response.get('medicalName', ''),
        'diseases', # FIXME when endpoint returns sty_info
        json_response.get('semanticTypeCodes', []), # FIXME when endpoint returns sty_info
        'notoken', # query
        synonyms,
    )


def err_msg(s, level='Error'):
    sys.stderr.write('{}: {}\n'.format(level, s))


def annotateString(s, url=DEFAULT_QPE_URL, api_rev='1',
                   lang=DEFAULT_QPE_LANG, method='AnalyzeQuery'):
    """Pass string s to an EMMeT QPE service at the given url. Return
    a list of Concepts that the QPE parsed from the string, or []
    if none found or if there was a connection or parsing error.
    url example: http://emmet-qpe.clinicalkey.com:8080/qpe/api.
    api_rev == '1': pre-2020 api, no sty_info element
    api_rev == '2': Jan 2020 api, has sty_info element
    """
    lang_code = LANG_TO_QPE_LANG_PARAM[lang]
    payload = {
        # the methods available are:
        #    AnalyzeQuery AnalyzeQueryIndexing AnalyzeQueryIndexingSentences
        # they are undocumented as far as I know (WFD 7/29/2016)
        'method': method,
        # 'method': 'AnalyzeQueryIndexing',
        # 'method': 'AnalyzeQueryIndexingSentences',
        'lang': lang_code, # en = English
        'query': s}
    # placeholder logic til auth is passed in:
    httpUser = None
    httpPass = None
    if httpUser is not None and httpPass is not None:
        auth = (httpUser, httpPass)
    else:
        auth = None
    try:
        response = requests.post(url, params=payload, auth=auth)
        if response.status_code != 200:
            msg = 'request returned http status {}. Request url:{}. Params:{}'
            err_msg(msg.format(response.status_code, url, str(payload)))
            return []
        json_response = response.json()
    except requests.ConnectionError as e:
        err_msg(str(e))
        return []
    except ValueError as e:
        err_msg('error ({}) parsing json in response for query {}'
                .format(str(e), s))
        return []
    health_concepts = json_response.get('health_concepts')
    if health_concepts is None:
        err_msg('health_concepts missing from response for query {}'.format(s))
        return []
    if api_rev == '1':
        create_concept_fnc = _createConcept_orig
    elif api_rev == '2':
        create_concept_fnc = _createConcept
    else:
        err_msg('bad api_rev, must be in ["1", "2"]')
        sys.exit(1)
    return list(map(create_concept_fnc, health_concepts.values()))


def get_concept_by_imui(imui, url=DEFAULT_QPE_URL):
    """QPE Lookup: Pass imui to an EMMeT QPE service at the given url. Return
    Concept, or None if no concept has that IMUI.
    """
    url = f'{url}/concept/imuid/{imui}'
    payload = {
        # If lang is other than English then additional fields
        # may be returned.  For now, hard code this.
        'lang': 'en', # en = English
    }
    # placeholder logic til auth is passed in:
    httpUser = None
    httpPass = None
    if httpUser is not None and httpPass is not None:
        auth = (httpUser, httpPass)
    else:
        auth = None
    BAD_RET_VAL = None
    try:
        response = requests.get(url, params=payload, auth=auth)
        if response.status_code != 200:
            msg = 'request returned http status {}. Request url:{}. Params:{}'
            err_msg(msg.format(response.status_code, url, str(payload)))
            return BAD_RET_VAL
        json_response = response.json()
    except requests.ConnectionError as e:
        err_msg(str(e))
        return BAD_RET_VAL
    except ValueError as e:
        err_msg(f'error ({str(e)}) parsing json in response for query {imui}')
        return BAD_RET_VAL
    return [_createConcept_tmp(json_response)]


if __name__ == "__main__":
    # execute only if run as a script
    sys.stderr.write('Use run_annotation.py to run this module.\n')
