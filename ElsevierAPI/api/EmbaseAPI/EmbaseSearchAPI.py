
#C:Windows> py -m pip install entrezpy --user

import urllib.request, urllib.parse, json
from ..ResnetAPI.references import Reference,TITLE,PUBYEAR,JOURNAL,AUTHORS
from textblob import TextBlob
import urllib.error as http_error
from requests.exceptions import InvalidURL
from time import sleep
from urllib.parse import quote


class EmbaseAPI:
    baseURL = 'https://api.elsevier.com/content/embase/article/'
    PageSize = 100 #controls number of records downloaded in one get request

    def __init__(self,APIconfig:dict,add_param=dict()):
        self.headers = {'X-ELS-APIKey':APIconfig['ELSapikey'],'X-ELS-Insttoken':APIconfig['insttoken']}
        self.params = {'count':self.PageSize}
        self.params.update(add_param)
        self.url = self.baseURL

    def _get_param_str(self):
        return urllib.parse.urlencode(self.params,doseq=True)

    def _url_request(self):
        return self.baseURL+self._get_param_str()
    
    def _add_param(self,to_add:dict={}):
        self.params.update(to_add)
    
    def _get_results(self):
        try:
            req = urllib.request.Request(url=self._url_request(),data=self._get_param_str(), headers=self.headers)
            response = urllib.request.urlopen(req)
        except http_error.HTTPError:
            sleep(30)
            try:
                req = urllib.request.Request(url=self._url_request(),data=self._get_param_str(), headers=self.headers)
                response = urllib.request.urlopen(req)
            except http_error.HTTPError as error:
                raise error
            
        result = json.loads(response.read().decode('utf-8'))
        sleep(0.34)
        return result


    def get_results(self):
        result = self._get_results()
        result_count = result['header']['hits']

        articles = list()
        print('Will download %d articles' % result_count)
        for page in range(0,result_count,self.PageSize):
            #params = {'query': embase_search_query, 'count':PageSize, 'start':page}
            data = urllib.parse.urlencode(self.params).encode('ascii')
            req = urllib.request.Request(self.baseURL, data, self.headers)
            response = urllib.request.urlopen(req)
            result = json.loads(response.read().decode('utf-8'))
            articles = articles + [article for article in result['results']]
        return articles
    

    def lui2doc(self,embase_id:str):
        requrl = quote(self.baseURL+'lui/L'+embase_id,safe="/:")
        req = urllib.request.Request(requrl, headers=self.headers)
        for attempt in range(0,10):
            try:
                response = urllib.request.urlopen(req)
                response_str = response.read().decode('utf-8')
                try:
                    result = json.loads(response_str)
                    return dict(result['results'][0])
                except json.JSONDecodeError: 
                    sleep(0.34)
                    continue # Embase server may reespond with garbage if overwhelmed with requests
            except (http_error.HTTPError,InvalidURL) as error:
                raise error
        return dict()

        

    def pmid2doc(self,pmid:str):
        requrl = quote(self.baseURL+'pubmed_id/'+pmid, safe="/:")
        req = urllib.request.Request(requrl, headers=self.headers)
        for attempt in range(0,10):
            try:
                response = urllib.request.urlopen(req)
                response_str = response.read().decode('utf-8')
                try:
                    result = json.loads(response_str)
                    return dict(result['results'][0])
                except json.JSONDecodeError:
                    sleep(0.34)
                    continue # Embase server may reespond with garbage if overwhelmed with requests
            except (http_error.HTTPError,InvalidURL) as error:
                raise error
        return dict()
    

    @staticmethod
    def article2ref(article:dict):
        doi = str()
        pui= str()
        pmid = str()
        lui = str()
        my_ref = None
        try:
            pmid = article['itemInfo']['itemIdList']['medl']
            my_ref = Reference('PMID',pmid)
        except KeyError: pass

        try:
            doi = article['itemInfo']['itemIdList']['doi']
            if my_ref is None:
                my_ref = Reference('DOI',doi)
            else:
                my_ref.Identifiers['DOI'] = doi
        except KeyError: pass

        try:
            pui = article['itemInfo']['itemIdList']['pui']
            if my_ref is None:
                my_ref = Reference('PUI',pui)
            else:
                my_ref.Identifiers['PUI'] = pui
        except KeyError: pass

        try:
            lui = article['itemInfo']['itemIdList']['lui']
            if my_ref is None:
                my_ref = Reference('EMBASE',lui)
            else:
                my_ref.Identifiers['EMBASE'] = lui
        except KeyError: pass

        if isinstance(my_ref,Reference):
            my_ref[TITLE] = [str(article['head']['citationTitle']['titleText'][0]['ttltext'])]
            my_ref[PUBYEAR] = [article['head']['source']['publicationYear']]
            try:
                my_ref[JOURNAL] = [article['head']['source']['sourceTitle'][0]]
            except KeyError:  
                    try:                  
                        my_ref[JOURNAL] = [article['head']['source']['sourceTitleAbbrev'][0]]
                    except KeyError:
                        pass
                    
            author_str = str()
            try:
                authors = list(article['head']['authorList']['authors'])
                if authors:
                    for auth in authors:
                        initials = ''
                        try:
                            initials = str(auth['initials'])
                            initials = initials.replace('.','')
                        except KeyError:
                            pass

                        author_str += auth['surname']
                        if initials:
                           author_str +=' '+ initials +';'
                        else:
                            author_str += ';'
            except KeyError: pass

            if author_str:
                my_ref[AUTHORS] = [author_str[:-1]]

        return my_ref
        
        

def OpenFile(fname):
    open(fname, "w", encoding='utf-8').close()
    return open(fname, "a", encoding='utf-8')

def make_json_dump_name(search_name):
    return search_name + '.embase.json'

def download_json(search_name:str, embase_search_query:str, api_config_file:str):
    file_result_name = make_json_dump_name(search_name)
    file_result = OpenFile(file_result_name)

    print('Beginning EMBASE response download with urllib...')
    config = json.load(open(api_config_file))
    EMBASEapiKey = config['ELSapikey']#Obtain from https://dev.elsevier.com
    token = config['insttoken'] #Obtain from mailto:integrationsupport@elsevier.com 

    PageSize = 100 #controls number of records downloaded in one get request 
    params = {'query': embase_search_query, 'count':PageSize, 'start':1}
    data = urllib.parse.urlencode(params).encode('ascii')
    headers = {'X-ELS-APIKey':EMBASEapiKey,'X-ELS-Insttoken':token}

    luiCounter = set()
    baseURL = 'https://api.elsevier.com/content/embase/article/'

    req = urllib.request.Request(baseURL, data, headers)
    HitCount = 0
    #finding restult size
    with urllib.request.urlopen(req) as response:
        the_page = response.read()
        result = json.loads(the_page.decode('utf-8'))
        HitCount = result['header']['hits']

    articles = list()
    print('Will download %d articles' % HitCount)
    for page in range(1,HitCount,PageSize):
        params = {'query': embase_search_query, 'count':PageSize, 'start':page}
        data = urllib.parse.urlencode(params).encode('ascii')
        req = urllib.request.Request(baseURL, data, headers)
        response = urllib.request.urlopen(req)
        result = json.loads(response.read().decode('utf-8'))
        articles = articles + [article for article in result['results']]
        
        ls = [x for x in [article['itemInfo']['itemIdList']['lui'] for article in result['results']]] #extracts lui identifiers
        luiCounter.update(ls)
        print('Downloaded %d EMBASE records out of %d search results with %d iterations' % (len(luiCounter),HitCount, page/PageSize))

    file_result.write(json.dumps(articles,indent=1))
    file_result.close()
    print('Finished downloading %d EMBASE records!' % len(luiCounter))
    return luiCounter, file_result_name


def load_medscan_dic(dic_fname:str, id_ranges:list=[]):
    to_return = dict()
    f = open(dic_fname, 'r', encoding='utf-8')
    line = f.readline()
    
    if id_ranges:
        for id_range in id_ranges:
            id_range_max = id_range + 999999
            while line:
                dic_row = line.split('\t')
                msid = dic_row[0]
                if int(msid) >= id_range and int(msid) <= id_range_max:
                    flag = dic_row[2]
                    alias = dic_row[1] if flag[0] == 'l' else dic_row[1].lower()
                    to_return[alias] = msid
                line = f.readline()
    else:
        while line:
            dic_row = line.split('\t')
            msid = dic_row[0]
            flag = dic_row[2]
            alias = dic_row[1] if flag[0] == 'l' else dic_row[1].lower()
            to_return[alias] = msid
            line = f.readline()

    return to_return


def count_tuple(counter:dict, t:tuple):
    t_str = ' '.join(list(t))
    try:
        current_count = counter[t_str]
        counter[t_str] = current_count +1
    except KeyError:
        counter[t_str] = 1


def count_tuples(counter:dict, ngrams:list):
    for n in ngrams:
        count_tuple(counter, tuple(n))


def has_substring(ngram:list, keywords_subs:set):
    ngram_lower = map(lambda x: x.lower(),list(ngram))
    if any(substring in word for word in ngram_lower for substring in keywords_subs): 
        return True
    return False


def has_dic_word(ngram:list, medscan_dic:dict):
    ngram_lower = list(map(lambda x: x.lower(),list(ngram)))
  #  for n in ngram_lower:
   #     if n in medscan_dic.keys(): 
    #        return True
    #return False
    return {alias:msid for alias,msid in medscan_dic.items() if alias in ngram_lower}


def merge_ngrams(ngramlist:list):
    phrase = list()
    for ngram in ngramlist:
        phrase.append(ngram[0])
    
    return ' '.join(phrase)


def mention_substrings (ngramlist:list, keywords_subs:set):
    annotation_ngrams = [n for n in ngramlist if has_substring(n,keywords_subs)]
    return merge_ngrams(annotation_ngrams)


def mention_dic_word(ngramlist:list, medscan_dic:dict):
    dic_words = set()
    for n in ngramlist:
        found_dic_word = has_dic_word(n,medscan_dic)
        if found_dic_word:
            dic_words.update(found_dic_word)
    return ','.join(dic_words)


if __name__ == "__main__":
    #SearchQuery = '("acute generalized exanthematous pustulosis":ti,ab OR agep:ti,ab OR "generalized bullous fixed drug eruptions":ti,ab OR gbfde:ti,ab OR "stevens johnson syndrome":ti,ab OR sjs:ti,ab OR "stevens-johnson syndrome":ti,ab OR "toxic epidermal necrolysis":ti,ab OR "dress syndrome":ti,ab OR "drug reaction with eosinophilia and systemic symptoms":ti,ab OR "severe cutaneous adverse reactions":ti,ab OR "sjs-ten":ti,ab OR "sjs/ten":ti,ab) AND ([conference abstract]/lim OR [conference review]/lim)'
    SearchQuery = "'drug formulation' AND 'inhalation'"

    api_config = 'D:/Python/ENTELLECT_API/ElsevierAPI/APIconfig.json'
    search_name = 'Inhalation Formulations'
    file_result_name = make_json_dump_name(search_name)
    #luis, file_result_name = download_json(search_name, SearchQuery, api_config)

    formulation_roots = ['inhal', 'formulat', 'aerosol', 'microniz', 'powder', 'particle', 'nano', 'propel', 'lipo']

    disease_dic = load_medscan_dic('D:/MEDSCAN/DevStandard10.bin/DiseaseFX.bin/msdata/Mammal.cellDictionary.tab.e', [9000000, 15000000])
    disease_dic.update(load_medscan_dic('D:/MEDSCAN/DevStandard10.bin/DiseaseFX.bin/msdata/Mammal.ExactLiteral.tab.e', [9000000, 15000000]))
    disease_dic.update(load_medscan_dic('D:/MEDSCAN/DevStandard10.bin/DiseaseFX.bin/msdata/Mammal.curNames.tab.e', [9000000, 15000000]))

    chemical_dic = load_medscan_dic('D:/MEDSCAN/DevStandard10.bin/Standard.bin/msdata/Mammal.CASDictionary.tab.e')
    chemical_dic.update(load_medscan_dic('D:/MEDSCAN/DevStandard10.bin/Standard.bin/msdata/Mammal.ExactLiteral.tab.e', [1000000]))
    chemical_dic.update(load_medscan_dic('D:/MEDSCAN/DevStandard10.bin/Standard.bin/msdata/Mammal.curNames.tab.e', [1000000]))

    ngram_size = 3
    file_abstracts = OpenFile(search_name + '_report.txt')
    file_ngram_counter = OpenFile(search_name + '_ngarms'+ str(ngram_size)+'.txt')
    
    articles = json.load(open(file_result_name))
    ngram_counter = dict()
    for article in articles:
        head = article['head']
        itemIdList = dict(article['itemInfo'])['itemIdList']
        doi = str()
        pui= str()
        try:
            doi = itemIdList['doi']
        except KeyError:
            pui = itemIdList['pui']

        technology_anno = set()
        disease_anno = set()
        drug_anno = set()

        title = str(dict(head['citationTitle']['titleText'][0])['ttltext'])
        title_blob = TextBlob(title)
        title_ngrams = title_blob.ngrams(n=ngram_size)
        a = mention_substrings(title_ngrams,formulation_roots)
        if a: technology_anno.add(a)
        #a = mention_dic_word(title_ngrams, disease_dic)
        a = {w for w in title_blob.words if w in disease_dic.keys()}
        if a: 
            disease_anno.update(a)
        #a = mention_dic_word(title_ngrams, chemical_dic)
        a = {w for w in title_blob.words if w in chemical_dic.keys()}
        if a: 
            drug_anno.update(a)

        pub_year = head['source']['publicationYear']
        journal = head['source']['sourceTitle'][0]

        try:
            abstracts = dict(head['abstracts'])
            abstract = abstracts['abstracts'][0]['paras'][0]
            blob = TextBlob(abstract)
            for sentence in blob.sentences:
                sentence_ngrams = sentence.ngrams(n=ngram_size)
                a = mention_substrings(sentence_ngrams,formulation_roots)
                if a: technology_anno.add(a)
                a = {w for w in sentence.words if w in disease_dic.keys()}
                #a = mention_dic_word(sentence_ngrams, disease_dic)
                if a: 
                    disease_anno.update(a)
               # a = mention_dic_word(sentence_ngrams, chemical_dic)
                a = {w for w in sentence.words if w in chemical_dic.keys()}
                if a: 
                    drug_anno.update(a)
    
        except KeyError:
            abstract = ''

        try:
            authors = list(head['authorList']['authors'])
        except KeyError:
            authors = []

        try:
            correspondence = list(head['correspondence'])
        except KeyError: pass  

        author_str = str()
        if authors:
            for auth in authors:
                author_str = author_str + ' '.join(auth.values())

        docid = doi if doi else pui 
        file_abstracts.write('\n'+pub_year+': '+title+'. from '+ journal)
        file_abstracts.write("\ndoi:"+docid)
        if technology_anno:
            file_abstracts.write('\nTechnology:'+'; '.join(technology_anno))
        if disease_anno:
            file_abstracts.write('\nDiseases:'+'; '.join(disease_anno))
        if drug_anno:
            file_abstracts.write('\nDrugs:'+'; '.join(drug_anno)+'\n')
        file_abstracts.write('\nAbstract:\n'+abstract+'\n')
    
    sorted_counter = dict(sorted(ngram_counter.items(), key=lambda item: item[1],reverse=True))
    file_ngram_counter.write(json.dumps(sorted_counter,indent=1))
    file_abstracts.close()
