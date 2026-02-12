import requests,json
from ...utils.pandas.panda_tricks import df


class TigerGraph:
    baseUrl = "https://tigergraph-api.platinum-qa-01.shared1.nonprod.entellect.com/query/Entellect/"
    
    headers = {
        'Authorization': 'Bearer b9m1hu16m42jbatr869huj6vkcofjopj',  #{cfg["tigergraph"]["token"]}',
        'GSQL-TIMEOUT': '600000',
        'Response-Limit': '314572800'
        }


    def __init__(self,query:str,add_param=dict()):
        self.query = query
        self.data = dict()
        self.data.update(add_param)


    def _get_results(self):
        # run the request, return the json object and extract the results section
        interaction_response = requests.request("POST", f'{self.baseUrl}{self.query}', headers=self.headers, data=self.data)
        if interaction_response.ok:
            filename = self.query+'.json'
            interaction_response = interaction_response.json()["results"][0]["result"]
            with open(filename, "w") as f:
                f.write(json.dumps(interaction_response, indent=4, sort_keys=False))
        else: 
            with open(filename, "w") as f:
                f.write(interaction_response.text)

        response = df.from_dict(interaction_response)
        return response,filename