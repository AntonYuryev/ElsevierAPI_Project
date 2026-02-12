#!/usr/bin/env python
# coding: utf-8

# ### Importing modules and Setting up cache, etc.
# ---

# In[1]:


from email.quoprimime import quote
from os import sep
import pandas as pd
from wso2processor.hgraphAPIQueryProcessor import HGraphAPIQueryProcessor
from cm2access import QPEAccess
from concurrent.futures import ThreadPoolExecutor
import time
import json
import requests
#from urllib3 .connection.HTTPSConnection


# In[2]:


IMUI_CACHE_CON = {}
IMUI_CACHE_QPE = {}
IMUI_INFO = {}
RELATIONS_OF_INTEREST = ['has diagnostic procedure', 'has clinical finding']
FOLDER_NAME = "data/"


# ### The different functions we will use throughout
# ---

# In[3]:


# Establish an H-GraphAPIProcessor object

hgraphApiProcessor = HGraphAPIQueryProcessor()


# In[4]:


def get_concept_id_hgraph(qstring):
    '''
    First approach to convert strings to IMUIs is using 
    the H-Graph REST API Concept Search Endpoint.
    Using a Cache to avoid repeated querying
    '''
    if qstring in IMUI_CACHE_CON:
        return IMUI_CACHE_CON[qstring]
    resp = hgraphApiProcessor.concept_search(qstring)
    result = resp['result']
    if len(result) > 0:
        concept = [{'imui': result[0]['imui'], 'label': result[0]['label'], 
                   'groupLabel': result[0]['groupLabel']}]
    else:
        concept = [{}]
    IMUI_CACHE_CON[qstring] = concept
    return concept

def get_concept_id_qpe(qstring):
    '''
    Second approach to convert strings to IMUIs is using 
    the H-Graph QPE API.
    Using a Cache to avoid repeated querying
    '''
    if qstring in IMUI_CACHE_QPE:
        return IMUI_CACHE_QPE[qstring]
    tags = QPEAccess.annotateString(qstring)
    concepts = []
    for k in tags:
        concepts.append({"imui": int(k.conceptID), "label": k.medicalName})
    IMUI_CACHE_QPE[qstring] = concepts
    return concepts

def get_concept_info(concept_imui):
    '''
    Get the concept information for selected concept
    Using a Cache to avoid repeated querying
    '''
    if concept_imui in IMUI_INFO:
        concept_info = IMUI_INFO[concept_imui]
    else:
        try:
            concept_info = hgraphApiProcessor.concept_info(concept_imui)
            IMUI_INFO[concept_imui] = concept_info
        except:
            concept_info = {}
    return concept_info

def get_subject_select_relations(concept_imui):
    '''
    This function only retrieves the "object" concept of relations in H-Graph, where 
    the relation type is selected under RELATIONS_OF_INTEREST
    '''
    concept_info = get_concept_info(concept_imui)
    relations = {}
    for k in RELATIONS_OF_INTEREST:
        relations[k] = []
        if 'subjectOfRelation' in concept_info:
            for m in concept_info['subjectOfRelation']:
                if m['label'] == k:
                    relations[k].append({'imui': m['object']['imui'], 'label': m['object']['label']})
    return relations
    
def process_execute_thread(argument):
    '''
    Method to use for each thread
    '''
    try:
        (query_list, b, f) = argument 
        resp = f(query_list[b])
    except:
        resp = []
    return resp

def process_parallel(query_list, threads=3, f=get_concept_id_hgraph):
    '''
    Function to query any APIs in parallel
    '''
    start_time = time.time()
    print("Started at time", start_time)
    ex = ThreadPoolExecutor(max_workers=threads)
    args = ((query_list, b, f) for b in range(len(query_list)))
    results = ex.map(process_execute_thread, args)
    real_results = list(results)
    print("Time taken", time.time() - start_time)
    return real_results

def get_field(x, stype, field):
    try:
        return concept_matches[x][stype][0][field]
    except:
        return ''


# ### Evaluating the different functions
# ---

# In[5]:


# Get the Concept ID given the String using H-Graph REST API Concept Search Endpoint
#concept_ids = get_concept_id_hgraph('hereditary breast and ovarian cancer syndrome')


# In[6]:


# Get the Concept ID given the String using H-Graph QPE API
#concept_ids = get_concept_id_qpe('hereditary breast and ovarian cancer syndrome')


# In[7]:


# Get the Selected relations from H-Graph for selected concept
#get_subject_select_relations(8128750)


# ### Process the Input file and Get the IMUIs using different approaches
# ---

# In[8]:


# Read the diseases input file
disease_names_file = 'Uterine Neoplasms from PS.txt'
diseases = pd.read_csv(FOLDER_NAME + '/'+disease_names_file, keep_default_na=False, sep='\t')
diseases.head()


# In[9]:

concept_matches = {}
alias2name = dict()
for i in diseases.index:
    disease_name = diseases.at[i,'Name']
    disease_aliases = str(diseases.at[i,'Alias']).split(';')
    disease_aliases.append(disease_name)
    all_names = list(set(disease_aliases))
    alias2name.update({a:disease_name for a in all_names})


#print ("Disease Strings to retrieve IMUIs for:", len(qlist))
qlist = list(alias2name.keys())
concept_list = process_parallel(qlist)
concept_list_qpe = process_parallel(qlist, f=get_concept_id_qpe)

concept_matches = {}
name2imui = dict()
for i, k in enumerate(qlist):
    disease_name = alias2name[k]
    try:
        hgraph_result = concept_list[i]
        for r in hgraph_result:
            hgraph_id = r['imui']
            try:
                name2imui[disease_name].update(hgraph_id)
            except KeyError:
                name2imui[disease_name] = set([hgraph_id])
    except KeyError: pass
    try:
        hgraph_result = concept_list_qpe[i]
        for r in hgraph_result:
            hgraph_id = r['imui']
            try:
                name2imui[disease_name].update(hgraph_id)
            except KeyError:
                name2imui[disease_name] = set([hgraph_id])
    except KeyError: pass

    concept_matches[k] = {'hgraph': concept_list[i], 'qpe': concept_list_qpe[i]}


# In[11]:

concept_matches['hereditary breast and ovarian cancer syndrome']


# ### Determine where different H-Graph concepts parsed for the same disease string over the two approaches
# ---
# We are only going to proceed with diseases where the same H-Graph concept is parsed by both approaches. The file where different H-Graph concepts are tagged is saved for further analysis. <br>
# 
# **To note:** QPE can parse a string into multiple H-Graph concepts, if it does not get an exact match on a label. Similarly, H-Graph REST API Search Endpoint can retrieve multiple H-Graph concepts based on the match. 
# In the file, only the first concept retrieved from both approaches is saved but other concepts can be retrieved from `concept_matches`

# In[12]:


diseases_tagged = pd.concat([diseases, 
                             diseases['Name'].apply(lambda x: get_field(x, 'hgraph', 'imui')).to_frame(name='hgraph_imui'), 
                             diseases['Name'].apply(lambda x: get_field(x, 'hgraph', 'label')).to_frame(name='hgraph_label'), 
                             diseases['Name'].apply(lambda x: get_field(x, 'qpe', 'imui')).to_frame(name='qpe_imui'), 
                             diseases['Name'].apply(lambda x: get_field(x, 'qpe', 'label')).to_frame(name='qpe_label')], 
                            axis=1)


# In[13]:


diseases_diff = diseases_tagged[diseases_tagged[['hgraph_imui', 
                                                 'qpe_imui']].apply(lambda x: True if x[0] != x[1] or 
                                                                    len(str(x[0])) == 0 else False, 
                                                                       axis=1)]
print ("Disease Strings with different (or no) concepts parsed:", diseases_diff.shape[0])


# In[14]:


diseases_same = diseases_tagged[diseases_tagged[['hgraph_imui', 
                                                 'qpe_imui']].apply(lambda x: True if x[0] == x[1] and 
                                                                    len(str(x[0])) > 0 else False, 
                                                                       axis=1)]


# In[15]:


diseases_same.sample(10)


# In[16]:


# Save the diseases where different H-Graph concepts parsed for the same disease string over the two approaches, 
# we will ignore them going forward
diseases_diff.to_csv(FOLDER_NAME + "different_qpe_hgraphsearch.tsv", sep="\t", index=None)


# ### Get the Symptoms and Diagnostic Procedures for the Diseases in the `diseases_same` Data Frame

# In[17]:


all_concept_imuis = list(diseases_same['hgraph_imui'])


# In[18]:


all_concept_rels = process_parallel(all_concept_imuis, f=get_subject_select_relations)


# In[19]:


all_concept_info = {}
for i, k in enumerate(all_concept_imuis):
    all_concept_info[k] = all_concept_rels[i]


# In[20]:


diseases_dict = diseases_same.to_dict(orient='index')
diseases_output = {}
for k in diseases_dict:
    name = diseases_dict[k]['Name']
    imui = diseases_dict[k]['hgraph_imui']
    hgraph_label = diseases_dict[k]['hgraph_label']
    
    include_disease = False
    if imui in all_concept_info:
        for m in RELATIONS_OF_INTEREST:
            if len(all_concept_info[imui][m]) > 0:
                include_disease = True

    if include_disease:
        diseases_output[imui] = {'Name': name, 'HGraphIMUI': imui, 
                                 'MedScanID': diseases_dict[k]['MedScan ID'], 
                                 'URN': diseases_dict[k]['URN'], 'HGraphLabel': hgraph_label}
        for m in RELATIONS_OF_INTEREST:
            diseases_output[imui][m] = all_concept_info[imui][m]


# In[21]:


# Save the JSON in a file
with open(FOLDER_NAME + "diseases_hgraph_rels.json", 'w', encoding='utf-8') as f:
    json.dump(diseases_output, f, ensure_ascii=False, indent=4)


# In[22]:


print ("Diseases with H-Graph relations:", len(diseases_output))


# In[ ]:



