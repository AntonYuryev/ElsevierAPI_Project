from .wso2QueryProcessor import WSO2QueryProcessor
import pprint

class HGraphAPIQueryProcessor():
    '''
    This rudimentary class provides a uniform way to query the set of two different H-Graph APIs - Rest and LD (Linked Data) 
    Currently this class provides the following methods:
    - Tag a blob of string with H-Graph concepts
    - Search for a H-Graph using a simple string
    - Get all information for a given Concept (i.e., children, mappings, etc.)
    - Get all information on relation between a pair of Concepts
    - Get the concept mapped in H-Graph for any term in the external vocabulary
    Rudimentary code is provided on how to use these different methods
    '''

    def __init__(self, license_file:str):
        self.queryProcessor = WSO2QueryProcessor(license_file)
        self.queryProcessor.check_token_validity()
        self.REST_BASE_PATH = '/h/knowledge/graph/'
        self.LD_BASE_PATH = '/h/knowledge/graph/ld/'

    def concept_tag(self, string, lang='en', additional_params={}):
        '''
        Use the Tag endpoint to tag a blob of string with H-Graph concept
        Parameters
        -----------
        string: the blob of string to tag
        lang: Default is en, current languages supported are fr, es, de, zh, pt
        '''
        query_params = {'query': string, 'lang': lang}
        for k in additional_params:
            query_params[k] = additional_params[k]
        resp = self.queryProcessor.query_api_url(self.REST_BASE_PATH,
                                                 'concept/tag',
                                                 query_params)
        return resp

    def concept_search(self, string, limit=10, additional_params={}):
        '''
        Use the Search endpoint to search for a concept using its label
        (Only English Language Labels are currently supported)
        Parameters
        -----------
        string: the label to search for
        limit: number of concepts to return
        additional_params: additional parameters to use
        '''
        query_params = {'query': string, 'limit': limit}
        for k in additional_params:
            query_params[k] = additional_params[k]
        resp = self.queryProcessor.query_api_url(self.REST_BASE_PATH,
                                                 'concept/search',
                                                 query_params)
        return resp

    def concept_info(self, identifier, lang='en', additional_params={}):
        '''
        Get all the concept information for a given concept in H-Graph
        You can use IMUI or UUID currently here
        Parameters
        -----------
        identifier: IMUI or UUID
        lang: Default is en, current languages supported are fr, es, de, zh, pt
        additional_params: additional parameters to use
        '''
        query_params = {'lang': lang}
        for k in additional_params:
            query_params[k] = additional_params[k]
        resp = self.queryProcessor.query_api_url(self.LD_BASE_PATH,
                                                 'concept/' + str(identifier),
                                                 query_params)
        return resp

    def relation_search(self, identifier_set, lang='en', additional_params={}):
        '''
        Get all the manually-curated relations from H-Graph between the set
        of identifiers (IMUIs or UUIDs) listed in the set
        Parameters
        ----------
        identifier_set: List consisting of at least 2 identifiers (IMUIs or UUIDs)
        lang: Default is en, current languages supported are fr, es, de, zh, pt
        additional_params: additional parameters to use
        '''
        if len(identifier_set) < 2:
            print("Provide at least 2 identifiers")
            return {}
        query_params = {'lang': lang, 'ids': ','.join(
            [str(k) for k in list(identifier_set)])}
        for k in additional_params:
            query_params[k] = additional_params[k]
        resp = self.queryProcessor.query_api_url(self.REST_BASE_PATH,
                                                 'relation/search',
                                                 query_params)
        return resp

    def mapping_info(self, mapping_vocab, mapping_vocab_term_id, additional_params={}):
        '''
        Get all the mappings for an external vocabulary term
        Parameters
        -----------
        mapping_vocab: Vocabulary for which the term is (e.g., SNOMED, ICD10-CM)
        mapping_vocab_term_id: Term ID to use to find mappings for
        additional_params: additional parameters to use
        '''
        query_params = {}
        for k in additional_params:
            query_params[k] = additional_params[k]
        resp = self.queryProcessor.query_api_url(self.LD_BASE_PATH,
                                                 'mapping/' +
                                                 mapping_vocab + '/' +
                                                 str(mapping_vocab_term_id),
                                                 query_params)
        return resp


if __name__ == "__main__":
    print("Testing H-Graph API Query Processor through WSO2")
    hgraphApiProcessor = HGraphAPIQueryProcessor()
    pp = pprint.PrettyPrinter(indent=4)

    print("Testing Concept Tag REST endpoint in French")
    print("-------------------------------")
    resp = hgraphApiProcessor.concept_tag(
        'le glioblastome multiforme peut être traité par témozolomide', 'fr')
    pp.pprint(resp)
    print("-------------------------------")

    print("Testing Concept Tag REST endpoint in English")
    print("-------------------------------")
    resp = hgraphApiProcessor.concept_tag(
        'glioblastoma multiforme can be treated by temozolomide')
    pp.pprint(resp)
    print("-------------------------------")

    print("Testing Concept Search REST endpoint in English")
    print("-------------------------------")
    resp = hgraphApiProcessor.concept_search('asthma')
    pp.pprint(resp)
    print("-------------------------------")

    print("Testing Relation Search REST endpoint in English")
    print("-------------------------------")
    resp = hgraphApiProcessor.relation_search(
        [4998026, 2800346, 'id-5c15a36d-b77d-3f91-87b2-981611ac084d'], lang='fr')
    pp.pprint(resp)
    print("-------------------------------")

    print("Testing Concept Info LD endpoint in English")
    print("-------------------------------")
    resp = hgraphApiProcessor.concept_info(3816105)
    pp.pprint(resp)
    print("-------------------------------")

    print("Testing Mapping Info LD endpoint in English")
    print("-------------------------------")
    resp = hgraphApiProcessor.mapping_info('UMLS', 'C0021083')
    pp.pprint(resp)
    print("-------------------------------")