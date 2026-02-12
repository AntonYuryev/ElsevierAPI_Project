import urllib.request,urllib.parse, base64
import json
import urllib.error as http_error
import time
import requests


class hGraphAPI:
    #url = 'https://kong.cert.platform.healthcare.elsevier.com/h/knowledge/graph/'
    #url = 'https://kong.cert.platform.healthcare.elsevier.com/h/knowledge/graph/concept/search'
    url = 'https://apigw.healthcare.elsevier.com/h/knowledge/graph/'
    api = 'concept/search?'
    
    def __init__(self,APIconfig:dict,add_param=dict()): 
        self.APIconfig = APIconfig
        token = self.get_auth_token() 
        self.header = {'Authorization':'Bearer '+token}
        self.header.update({'Accept':'*/*'})
        self.params = dict()
        self.params.update(add_param)


    def get_auth_token(self):
        """
        get an auth token
        """
        #make_token_url = "https://jwt-creator.access-controls.dev.platform.healthcare.elsevier.com/token"
        #make_token_url = 'https://jwt-creator.access-controls.cert.platform.healthcare.elsevier.com/token'
        make_token_url = 'https://jwt-creator.access-controls.prod.platform.healthcare.elsevier.com/token'
        req = urllib.request.Request(make_token_url, method='POST')
        #us_pas = '{}:{}'.format(self.APIconfig['KongUsername'],self.APIconfig['KongPassword'])
        us_pas = '{}:{}'.format(self.APIconfig['h_graph_prod_key'],self.APIconfig['h_graph_prod_secret'])
        us_pas_e = us_pas.encode()
        base64string = base64.b64encode(us_pas_e)
        req.add_header("Authorization", "Basic %s" % base64string.decode())
        response = urllib.request.urlopen(req)
        body = json.loads(response.read())
        token = body['access_token']
        #print (token)
        self.token_retreive_time = time.time()
        return token


    def _get_param_str(self):
        return urllib.parse.urlencode(self.params,doseq=True)

    def _url_request(self):
        return self.url+self.api+self._get_param_str()
    
    def _add_param(self,to_add:dict()):
        self.params.update(to_add)
        
    def _get_results(self):
        try:
            url_req = self._url_request()
            response = requests.get(url_req, headers = self.header)
            #req = urllib.request.Request(url=url_req, headers=self.header, method='GET')
            #response = urllib.request.urlopen(req)
            #print('request success')
        except http_error.HTTPError:
            raise http_error.HTTPError
        concepts = response.json()
        #result = json.loads(pp_view.decode('utf-8'))
        return concepts['result']






