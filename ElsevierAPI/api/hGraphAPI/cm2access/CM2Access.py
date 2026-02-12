#!/usr/bin/env python

# ### Access to the CM2 query parser
#
# This file defines one public function:
# ```
# annotateString(s, url='http://emmet-cm2.clinicalkey.com/cm2api')
#     Pass string s to a  CM2 service at the given url. Return
#     a list of Concepts (for now only populated with classNames)
#     that CM2 parsed from the string, or []
#     if none found or if there was a connection or parsing error.
#     url defaults to http://emmet-cm2.clinicalkey.com/cm2api
# ```
# Concept is a named tuple with these fields:
# ```
#     cfn              # string (unused)
#     conceptID        # string (unused)
#     medicalName      # string (unused)
#     className        # string
#     styCodes         # list of string  (unused)
#     isHealthRelated  # boolean (unused)
#     synonyms         # list of string (unused)
#
# ```

import sys
import re
from collections import namedtuple
import requests  # pip install Requests  for this module

DEFAULT_CM2_URL = 'https://cm2-hgraph.graph.hmelsevier.com/cm2api'

LANG_TO_CM2_LANG_PARAM = {
    'English': 'en',
    'French': 'fr',
    'Spanish': 'es',
    'German': 'de',
    'Portuguese': 'pt',
}
DEFAULT_CM2_LANG = 'English'

# scheme = 'http'
# host = 'emmet-cm2.clinicalkey.com'
# port = '80'
# endpoint = 'cm2api'
# URL = '{}://{}:{}/{}'.format(scheme, host, port, endpoint)

Concept_orig = namedtuple('Concept',
                     ['cfn', # string
                      'conceptID', # string
                      'medicalName', # string
                      'className', # string
                      'styCodes', # list of string
                      'maprelevancy', # float
                      'queryToken', # string
                      #'isHealthRelated', # boolean-- missing from CM2 response
                      #'synonyms'  # list of string-- missing from CM2 response
                     ])


# Concept is immutable tuple with named fields
Concept = namedtuple('Concept',
                     ['cfn', # string
                      'conceptID', # string
                      'medicalName', # string
                      'className', # string
                      'styCodes', # list of string
                      'maprelevancy', # float
                      'queryToken', # string
                      ])


def _createConcept_orig(imuid, jsonResponseMap, idMap):
    styCodesText = jsonResponseMap.get('semanticCodes', '')
    queryToken = idMap.get(imuid, 'notoken')
    return Concept_orig(
        jsonResponseMap.get('cfn', ''),
        imuid,
        jsonResponseMap.get('mn', ''),
        jsonResponseMap.get('semanticGroup', ''),
        re.findall(r'[A-Z]\d{3}', styCodesText), # capital letter + 3 digits
        jsonResponseMap.get('maprelevancy', ''),
        queryToken
    )


def _createConcept(imuid, jsonResponseMap, idMap):
    sty_info = jsonResponseMap.get('sty_info', [])
    # primary sort to get preferred stys at front
    # secondary sort on name to ensure deterministic order
    sty_info = sorted(sorted(sty_info, key=lambda r: r['name']),
                       key=lambda r: r['preferred'], reverse=True)

    sty_codes = [c['code'] for c in sty_info]
    preferred_stys = [c for c in sty_info if c.get('preferred')]
    queryToken = idMap.get(imuid, 'notoken')
    # len(preferred_stys) should be 1, but not guaranteed
    if len(preferred_stys) >= 1:
        class_name = preferred_stys[0].get('class_name', '')
    else:
        class_name = ''
    return Concept(
        jsonResponseMap.get('cfn', ''),
        imuid,
        jsonResponseMap.get('mn', ''),
        class_name,
        sty_codes,
        jsonResponseMap.get('maprelevancy', ''),
        queryToken
    )


def err_msg(s, level='Error'):
    sys.stderr.write('{}: {}\n'.format(level, s))


# Note: this method is only used for the pre-202 API (api_rev==1) 
def _bodyCpToIdMap(s):
    """Parse out a map from emuid->query term from body_cp element of response
    'case 5304448$diagnos 2791947$5047367$peacrnm 1998 8815274$cost' ->
    {'5304448': 'diagnos', '2791947':'peacrnm', '5047367': 'peacrnm'}
    """
    tokenWithCodes = [a.split('$') for a in s.split()]
    retVal = {}
    for tokenWithCode in tokenWithCodes:
        if len(tokenWithCode) < 2:
            # like 'case' or '1998' above, no associated codes
            continue
        for code in tokenWithCode[:-1]:
            retVal[str(code)] = tokenWithCode[-1]
    return retVal


def annotateString(s, url=DEFAULT_CM2_URL, api_rev='1',
                   lang=DEFAULT_CM2_LANG, method=None, 
                   timeout=None):
    """Pass string s to an EMMeT CM2 service at the given url. Return
    a list of Concepts that CM2 parsed from the string, or []
    if none found or if there was a connection or parsing error.
    url defaults to http://emmet-cm2.clinicalkey.com/cm2api.
    Concept is namedtuple('Concept',
                     ['cfn', # string
                      'conceptID', # string
                      'medicalName', # string
                      'className', # string
                      'styCodes', # list of string
                      'maprelevancy', # float
                     ])
    api_rev == '1': pre-2020 api, no sty_info element
    api_rev == '2': Jan 2020 api, has sty_info element
    method is currently unused, added now to keep
    the interface parallel with QPEAccess.annotateString.
    timeout: Time (in seconds) after which the get request 
    is terminated and an empty array is returned 
    """
    try:
        lang = LANG_TO_CM2_LANG_PARAM[lang]
    except KeyError:
        err_msg(f'Bad language parameter to CM2Access.annotateString(). '
                f'Got {lang}; expected '
                f'[{"|".join(LANG_TO_CM2_LANG_PARAM.keys())}]')
        return []
    payload = {'text': s, 'lang': lang}
    # placeholder logic til auth is passed in:
    httpUser = None
    httpPass = None
    if httpUser is not None and httpPass is not None:
        auth = (httpUser, httpPass)
    else:
        auth = None
    try:
        if timeout:
            response = requests.get(url, params=payload, auth=auth, timeout=timeout)
        else:
            response = requests.get(url, params=payload, auth=auth) # POST failed
        if response.status_code != 200:
            err_msg('request returned http status {}. '
                    'Request url:{}. Params:{}'
                    .format(response.status_code, url, str(payload)))
            return []
        json_response = response.json()
    except requests.ConnectionError as e:
        err_msg(str(e))
        return []
    except (TimeoutError, requests.exceptions.ReadTimeout) as e:
        err_msg(str(e))
        return []
    except ValueError as e:
        err_msg('error ({}) parsing json in response for query {}'
                .format(str(e), s))
        return []
    try:
        imuids = json_response['imuids'].items()
    except (KeyError, AttributeError):
        return []

    try:
        parsedBody = json_response['body_cp']
    except (KeyError, AttributeError):
        return []
    if parsedBody is None:
        return []
    id_map = _bodyCpToIdMap(parsedBody)
    if api_rev == '1':
        ret_val = [_createConcept_orig(k, v, id_map) for (k, v) in imuids]
    elif api_rev == '2':
        ret_val = [_createConcept(k, v, id_map) for (k, v) in imuids]
    else:
        err_msg('bad api_rev, must be in ["1", "2"]')
        sys.exit(1)
    return ret_val


if __name__ == "__main__":
    # execute only if run as a script
    sys.stderr.write('Use run_annotation.py to run this module.\n')
