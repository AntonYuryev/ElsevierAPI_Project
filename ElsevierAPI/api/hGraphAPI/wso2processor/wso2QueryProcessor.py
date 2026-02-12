import json
import re
import requests
import os
import time


class WSO2QueryProcessor():
    '''
    This rudimentary class provides a way to query any API that is exposed via the WSO2 platform
    As a user, you will have to create an application and subscribe to these APIs using WSO2
    Once you have done that, you can get a Base 64 Production Consumer Key/Secret string which can be saved in a file called WSO2_APPLICATION_ID.
    In the future we will improve on this to also provide functionality to have the application ID as a environment variable
    '''

    def __init__(self,license_file:str):
        with open(license_file) as s:
            self.application_id = s.read().strip()
        self.WSO2_URL = "https://api.healthcare.elsevier.com"
        self.WSO2_TOKEN_URL = self.WSO2_URL + "/token"
        self.get_current_token()
        # set a caution threshold for token validity, can be set to 0
        self.CAUTION_THRESHOLD = 5

    def check_token_validity(self):
        '''
        Checks whether current token has expired or not
        If yes, then get a new token
        A caution threshold can be used to query intermittently before actual expiration
        @TODO: Optionally you can check some 'healthcheck' endpoint using threading at regular intervals
        (e.g., might help in rare cases where WSO2 has failed for a brief second and tokens need to be regenerated fresh)
        '''
        if (time.time() - self.token_gen_time) > (self.expire_time - self.CAUTION_THRESHOLD):
            self.get_current_token()

    def get_current_token(self):
        '''
        Get the current token from WSO2
        Tokens generally expire every 1 hour, but the time can be custom as determined by the expires_in
        set the current time as the token generation time
        '''
        try:
            r = requests.post(self.WSO2_TOKEN_URL,
                              data={'grant_type': 'client_credentials'},
                              headers={'Authorization': 'Basic ' + self.application_id})
            resp = r.json()
            self.token = resp['access_token']
            self.expire_time = resp['expires_in']
            self.token_gen_time = time.time()
        except Exception as e:
            print(e)
            print('Error initializing token generator')

    def query_api_url(self, base_path, extra_path="", query_params={}):
        '''
        Query an API through WSO2 (checks whether token is valid or not)
        ------------
        Parameters:
        base_path = Base path for the API to which the application is subscribed to (e.g. /h/knowledge/graph/)
        extra_path = Extra path for specific endpoint in the API (e.g. concept/search)
        query_params = A dictionary of all query parameters (e.g., {'query': 'aspirin', 'limit': 10})
        '''
        try:
            self.check_token_validity()
            q_param_string = '&'.join(['{}={}'.format(k, v)
                                       for k, v in query_params.items()])
            url = self.WSO2_URL + base_path + extra_path + '?' + q_param_string
            r = requests.get(url, headers={'Authorization': 'Bearer ' + self.token,
                                           'Accept': 'application/json'})
            return r.json()
        except Exception as e:
            print(e)
            print('Error Querying API with base_path' + base_path)


if __name__ == "__main__":
    print("Testing WSO2 Query Processor")
    queryProcessor = WSO2QueryProcessor()
    resp = queryProcessor.query_api_url(
        '/h/knowledge/graph/', 'concept/search', {'query': 'aspirin', 'limit': 10})
    print(resp)