from ..ElsevierAPI.ResnetAPI.ResnetAPISession import BIBLIO_PROPERTIES
from ..ElsevierAPI.ResnetAPI.ResnetGraph import ResnetGraph,PS_CITATION_INDEX, PSRelation, PSObject,df,EFFECT
from ..ElsevierAPI.ETM_API.references import Reference,PUBYEAR,JOURNAL
from ..ElsevierAPI.utils import execution_time
import matplotlib.pyplot as plt
from datetime import datetime
import time
from collections import defaultdict
from ..ElsevierAPI.NCBI.pubmed import NCBIeutils

DRUGTARGET_RELATIONS = ['DirectRegulation','Regulation','Expression','MolTransport']
pct = '%'
MAX_OA_COUNT = 3

CHEMID4MAP = ['PubChem CID','ChEBI ID','InChIKey','HMDB ID']
DRUGPROPS = ['Name','PharmaPendium ID'] + CHEMID4MAP
DRUGTARGETRELPROPS = ['URN',EFFECT,'pX','Source']
ROBOKOP_ID = 'Robokop ID'

#cache_dir = 'D:/Python/ENTELLECT_API/ElsevierAPI/ResnetAPI/__pscache__/'
robokop_drugids = 'D:/Customers/EveryCure/Robokop/ROBOKOP_AllChemicalEntities_EqIDs.csv'
robokop_diseaseids = 'D:/Customers/EveryCure/Robokop/ROBOKOP_AllDiseases_EqIDs.csv'

parameters = {
            'what2retrieve' : BIBLIO_PROPERTIES,
            'rel_props' : ['TextRef'], # additional relation props to fetch from database
            'make_simple': False, # if True makes simple graph from database graph
            'ranks4simplifying' : [], # parameter for making simple graph
            'refprop2rel':dict(), # {reference_propname:relation_propname} - moves refprops to relprops using PSRelation._refprop2rel()
            'refprop_minmax':0, # parameter for PSRelation._refprop2rel(refprop2rel,refprop_minmax)
            #if min_max < 0 assigns single value to relprop that is the minimum of all ref_prop values
            #if min_max > 0 assigns single value to relprop that is the maximum of all ref_prop values
            #min_max works only if ref_prop values are numerical
            'predict_effect4' : [], # [_4enttypes:list,_4reltypes:list] - parameters for ResnetGraph.predict_effect4()
            'no_id_version': True,
            'max_threads' : 5,
            'connect2server' : True
            }


def in_oa(ref:Reference,oa_pmids:set):
    if ref.identifier('PMID') in oa_pmids:
        return True
    elif ref.is_from_abstract():
        return True
    else:
        return 'NCT ID' in ref.Identifiers.keys()
    

def read_oa_ncbi_pmids():
    oa_pmids = set()
    with open('D:/Customers/EveryCure/OAvsCA/oa_file_list (5,659,487).txt','r', encoding='utf-8') as f:
        line = f.readline()
        while line:
            line = f.readline()
            if line:
                columns = line.strip().split('\t')
                pmid = columns[3]
                pmid = pmid[5:]
                if pmid:
                    oa_pmids.add(pmid)

    print(f'Loaded {len(oa_pmids)} PMIDs from open access articles')
    return oa_pmids


def read_eu_pmids():
    oa_pmids = set()
    eu_pmids_file = 'D:/Customers/EveryCure/OAvsCA/PMID_PMCID_DOI.csv'
    with open(eu_pmids_file, 'r',encoding='utf-8') as f:
        line = f.readline()
        while line:
            line = f.readline()
            if line:
                columns = line.strip().split(',')
                pmid = columns[0]
                pmcid = columns[1]
                if pmcid and pmid:
                    oa_pmids.add(pmid)

    print(f'Read {len(oa_pmids)} EU PMC pmids')
    return oa_pmids


def add2counter(counter:dict[str,tuple[int,int]],ref:Reference,propname:str):
    '''
    Input
    -----
    ref must be annotated with PS_CITATION_INDEX (by ResnetGraph:citation_index()) 
    propname = PUBYEAR, JOURNAL

    Return
    ------
    counter = dict[ref[propname]] : (refcount,cumulative_citation_index)
    '''
    try:
        propvalue = ref[propname][0]
    except KeyError:
        return

    try:
        citation_freq = counter[propvalue]
        new_tuple = (citation_freq[0] + 1, citation_freq[1] + ref[PS_CITATION_INDEX][0])
        counter[propvalue] = new_tuple
    except KeyError:
        counter[propvalue] = (1,ref[PS_CITATION_INDEX][0])


def count_refs_by(propname:str, using_counter:dict, refs:list[Reference]):
    [add2counter(using_counter,r,propname) for r in refs]


def get_timeline(graph:ResnetGraph,oa_pmids:set):
    timeline_oa = dict() # {PUBYEAR:OAcount}
    timeline = dict() # {PUBYEAR:TotalCount}
    journal_oa_counter = dict()
    journal_counter = dict()

    citation_index = graph.citation_index()
    for id_type,ref in citation_index.items():
        add2counter(timeline,ref,PUBYEAR)
        add2counter(journal_counter,ref,JOURNAL)
        if in_oa(ref,oa_pmids):
            add2counter(timeline_oa,ref,PUBYEAR)
            add2counter(journal_oa_counter,ref,JOURNAL)
    
    return timeline_oa, timeline, journal_oa_counter, journal_counter


def print_timeline(timeline_oa:dict, timeline:dict,cache_name:str):
    timeline = dict(sorted(timeline.items()))
    timeline_ratio = dict()
    rows = list()
    excel_fname = f'OA contribution timeline4{cache_name}.xslx'
    header = ['PubYear','OA refcount','Total refcount','OA relcount','Total relcount','OA%',f'{pct}relations in OA']
    with open(excel_fname, 'w', encoding='utf-8') as t:
        header_str = '\t'.join(header)
        t.write(header_str+'\n')
        for pubyear,counts in timeline.items():
            oa_counts = timeline_oa.get(pubyear,(0,0))
            oa_fraction = round(float(oa_counts[0]/counts[0]),2)
            oa_citation_fraction = round(float(oa_counts[1]/counts[1]),2)
            timeline_ratio[pubyear] = (oa_fraction,oa_citation_fraction)
            t.write(f'{pubyear}\t{oa_counts[0]}\t{counts[0]}\t{oa_counts[1]}\t{counts[1]}\t{oa_fraction}\t{oa_citation_fraction}\n')
            row = [ pubyear,oa_counts[0],counts[0],oa_counts[1],counts[1],oa_fraction,oa_citation_fraction]
            rows.append(row)

    all_years = list(timeline_ratio.keys())
    [timeline_ratio.pop(year,0) for year in all_years if int(year) < 1980 or int(year) > datetime.now().year]
    # remove refs with no publication year


    categories = list(timeline_ratio.keys())
    values1 = [t[0] for t in timeline_ratio.values()]
    values2 = [t[1] for t in timeline_ratio.values()] 

    # Creating a bar chart
    plt.bar(categories, values1,label='OA%')
    plt.bar(categories, values2, label=f'{pct}relations in OA', alpha=0.5)

    # Adding labels and title
    plt.xlabel('Pubyear')
    plt.ylabel('OA contribution')
    plt.title('OA contribution timeline')
    plt.legend(loc='upper left')
    plt.xticks(rotation='vertical')

    # Save the plot as a PNG file
    plt.savefig(f'OA timeline4{cache_name}.png')

    return df.from_rows(rows, header)

    # Displaying the plot
    #plt.show()


def journal_stats(journal_oa_counter:dict, journal_counter:dict):
    print('Analyzing journal statistics')
    journal2publisher_df = df.read('D:/Customers/EveryCure/OAvsCA/Journal2Publisher.txt',header=0)
    journal2publisher_dic = journal2publisher_df.to_dict('Journal','Publisher')

    rows = list()
    header = ['Journal','OA refcount','Total refcount','OA relcount','Total relcount','OA%',f'{pct}relations in OA']
    number_of_journals = len(journal_counter)
    start = time.time()
    for journal,counts in journal_counter.items():
      oa_counts = journal_oa_counter.get(journal,(0,0))
      oa_fraction = round(float(oa_counts[0]/counts[0]),2)
      oa_citation_fraction = round(float(oa_counts[1]/counts[1]),2)
      row = [journal,oa_counts[0],counts[0],oa_counts[1],counts[1],oa_fraction,oa_citation_fraction]
      rows.append(row)
      iteration = len(rows)
      if iteration % 500 == 0:
        print(f'Analyzed {iteration} journals out of {number_of_journals} in {execution_time(start)}')

    journ_stats = df.from_rows(rows,header)
    journ_stats = journ_stats.merge_dict(journal2publisher_dic,'Publisher','Journal')
    journ_stats = journ_stats.dfcopy(only_columns=['Journal','Publisher']+header[1:])
    journ_stats_sorted = journ_stats.sortrows(by=['Total refcount'],ascending=[False])
    return journ_stats_sorted


def count_oa(rels:list[PSRelation], oa_pmids:set,max_oa_count=MAX_OA_COUNT):
    '''
    Return
    ------
    [OA1,OA2,OA3] - OA counts when relation has 1 OA ref, 2 OA refs, 3 OA refs
    '''
    def count_oa_refs(rel:PSRelation):
   #     if rel.objtype() == 'ClinicalTrial':
   #         print('')
        oa_refcount = 0
        for ref in rel.refs():
            if in_oa(ref,oa_pmids):
                oa_refcount += 1
            if oa_refcount >= max_oa_count:
                return oa_refcount
        return oa_refcount

    oa_relcounts = [0] * max_oa_count
    for rel in rels:
        oa_refcount = count_oa_refs(rel)
        for count in range(0,oa_refcount):
            oa_relcounts[count] += 1

    return oa_relcounts


def node_stats(cache_graph:ResnetGraph,objects:list[PSObject],
               id_columns:list[str],reltypes4stat:list,oa_pmids:set):
    '''
    id_columns[0] - ObjectTypeNAme. Column will contain object.name()
    '''
    print(f'Analyzing {len(objects)} {id_columns[0]}s')
    ids = id_columns[1:]
    front_columns = ['Total OA1 relations','Total OA2 relations','Total OA3 relations','Total relations']

    reltype_stat_columns = list()
    for rtype in reltypes4stat:
        reltype_stat_columns += ['OA '+rtype,rtype]

    header = list(id_columns)
    header += reltype_stat_columns
    header += front_columns

    rows = list()
    start = time.time()
    for i, psobj in enumerate(objects):
        uid = psobj.uid()
        raw_rels = [rel for r,t,rel in cache_graph.edges(uid,data='relation')]
        raw_rels += ([rel for r,t,rel in cache_graph.edges(data='relation') if t == uid])

        row_rels = set(raw_rels)
        # set operation removes duplicates of non-directional realtions
        row = [psobj.name()] + [psobj.get_prop(id,0) for id in ids]

        oa_relcounts = [0] * MAX_OA_COUNT
        for rtype in reltypes4stat:
            rtype_rels = [r for r in row_rels if r.objtype() == rtype]
            oa_reltypecounts = count_oa(rtype_rels,oa_pmids)
            oa_relcounts = [x + y for x, y in zip(oa_relcounts, oa_reltypecounts)]         
            # writing only OA1 oa_reltypecounts here
            row += [oa_reltypecounts[0],len(rtype_rels)]

        row += [oa_relcounts[0],oa_relcounts[1],oa_relcounts[2],len(row_rels)]
        rows.append(row)
        if i and i % 500 == 0:
            print(f'Analyzed {i} out of {len(objects)} {id_columns[0]}s in {execution_time(start)}')
            print(f'Message time: {datetime.now()}')

    # making last row with stats for all relations in cache_graph
    last_row = [f'All {id_columns[0]}s']+['']*(len(id_columns)-1)
    last_row_rels = cache_graph.psrels_with()
    oa_relcounts = [0] * MAX_OA_COUNT
    for rtype in reltypes4stat:
        rtype_rels = [r for r in last_row_rels if r.objtype() == rtype]
        oa_reltypecounts = count_oa(rtype_rels,oa_pmids)
        oa_relcounts = [x + y for x, y in zip(oa_relcounts, oa_reltypecounts)]         
        # writing only OA1 oa_reltypecounts here
        last_row += [oa_reltypecounts[0],len(rtype_rels)]

    rel_count = len(last_row_rels)
    last_row += [oa_relcounts[0],oa_relcounts[1],oa_relcounts[2],rel_count]
    rows.append(last_row)

    stats_df = df.from_rows(rows,header)
    stats_df['%OA1'] = 100*stats_df['Total OA1 relations']/stats_df['Total relations']
    stats_df['%OA2'] = 100*stats_df['Total OA2 relations']/stats_df['Total relations']
    stats_df['%OA3'] = 100*stats_df['Total OA3 relations']/stats_df['Total relations']
    front_columns = ['Total OA1 relations','%OA1','Total OA2 relations','%OA2','Total OA3 relations','%OA3','Total relations']
    stats_df = stats_df.reorder(id_columns+front_columns+reltype_stat_columns)
    stats_df = stats_df.sort_values('Total relations')
    return df.from_pd(stats_df)


def relation_stats(cache_graph:ResnetGraph,oa_pmids:set):
    '''
    output:
      RefCount	Relations count	OA1	OA2	OA3	%OA1	%OA2	%OA3
    '''
    graph_rels = cache_graph.psrels_with()
    refcount2rels = dict()
    
    for rel in graph_rels:
        refcount = rel.count_refs()
        try:
            refcount2rels[refcount].append(rel)
        except KeyError:
            refcount2rels[refcount] = [rel]

    oa_counts = [[]]*MAX_OA_COUNT
    refcounts = list()
    relcount = list()
    for refcount,rels in refcount2rels.items():
        oa_counts4refcount = count_oa(rels,oa_pmids)
        for c in range(0,MAX_OA_COUNT):
            c_oacounts = list(oa_counts[c])
            c_oacounts.append(int(oa_counts4refcount[c]))
            oa_counts[c] = c_oacounts
        relcount.append(len(rels))
        refcounts.append(refcount)

    df_columns = {'RefCount':refcounts,'Relations count':relcount}
    for c in range(0,MAX_OA_COUNT):
        df_columns.update({'OA'+str(c+1):oa_counts[c]})
    
    relstat_df = df.from_dict(df_columns)
    for c in range(0,MAX_OA_COUNT):
        relstat_df['%OA'+str(c+1)] = (relstat_df['OA'+str(c+1)]/relstat_df['Relations count']).apply(lambda x: round(x,2))
        #relstat_df['%OA'+str(c+1)] = relstat_df['%OA'+str(c+1)].apply(lambda x: round(x,2))

    relstat_df = df.from_pd(relstat_df.sort_values(by='RefCount'))
    return relstat_df


def load_robokop(robokop_mapfile:str):
    def parse_bracketed_values(s:str):
        return s[1:-1].split(",")

    map_dict = dict()
    id2name = dict()
    robokop_ids = df.read(robokop_mapfile,converters={'equivalent_ids':parse_bracketed_values})
    #robokop_ids['equivalent_ids'] = robokop_ids['equivalent_ids'].apply(eval)
    for i in robokop_ids.index:
        primary_id = robokop_ids.at[i,'primary_id']
        name = str(robokop_ids.at[i,'name'])
        map2ids = robokop_ids.at[i,'equivalent_ids']
        map_dict['name:'+name.lower()] = primary_id
        id2name[primary_id] = (name,map2ids)
        for id in map2ids:
            map_dict[str(id).lower()] = primary_id

    return map_dict,id2name


def add_robokop_id(to:PSObject,robokop:dict,idtype_map:dict):
    '''
    Input
    -----
    ids = [(Resnet_property_name,map2Robokop_IDtype)]
    For diseases: {"Orphanet ID":'orphanet','MeSH ID':'MESH','Name':'name'}
    For drugs: {'InChIKey':'INCHIKEY','HMDB ID':'HMDB','PubChem CID':'PUBCHEM.COMPOUND','ChEBI ID':CHEBI','Name':'name'}
    '''
    for resnet_propname,robokop_idtype in idtype_map.items():
        try:
            resnet_ids = to[resnet_propname]
            for id in resnet_ids:
                try:
                    robokop_primary_id = robokop[robokop_idtype+':'+str(id).lower()]
                    to.set_property(ROBOKOP_ID,robokop_primary_id)
                    return 
                except KeyError:
                    continue
        except KeyError:
            continue
        

def add_robokop_2graph(g:ResnetGraph,robokop:dict,idtype_map:dict):
    '''
    Input
    -----
    ids = [(Resnet_property_name,map2Robokop_IDtype)]
    For diseases: {"Orphanet ID":'orphanet','MeSH ID':'MESH','Name':'name'}
    For drugs: {'InChIKey':'INCHIKEY','HMDB ID':'HMDB','PubChem CID':'PUBCHEM.COMPOUND','ChEBI ID':CHEBI','Name':'name'}
    '''
    for uid,n in g.nodes.data(data=True):
      for resnet_propname,robokop_idtype in idtype_map.items():
        resnet_ids = n.get(resnet_propname,[])
        for id in resnet_ids:
          robokop_search_str = robokop_idtype+':'+str(id).lower()
          if robokop_search_str in robokop:
            g.set_node_attributes({uid:{resnet_propname:[robokop[robokop_search_str]]}})


def unmapped_robokop_ids(annotated_psobjs:list[PSObject],robokop_idmap:dict,robokop_id2name:dict):
    all_robokop_ids = set(robokop_idmap.values())
    mapped_robokop_ids = {o.get_prop(ROBOKOP_ID,0) for o in annotated_psobjs}
    mapped_robokop_ids.remove('')
    unmapped_robokop_ids = all_robokop_ids.difference(mapped_robokop_ids)
    unmapped_robokop_ids = {i:robokop_id2name[i] for i in unmapped_robokop_ids}

    df2return = df.from_dict2(unmapped_robokop_ids,ROBOKOP_ID,'Name+IDs')
    df2return['Name'], df2return['equivalent_ids'] = zip(*df2return['Name+IDs'])
    pd2return = df2return[['Name',ROBOKOP_ID,'equivalent_ids']]
    if len(pd2return) > 1000000:
        chunks = [pd2return[i:i+1000000] for i in range(0, len(pd2return), 1000000)]
    else:
        chunks = [pd2return]

    return [df.from_pd(pd) for pd in chunks]


def in_ca_dates(rel:PSRelation,oa_pmids:set):
    first_ref = rel._1st_ref()
    if first_ref:
        published_1st = first_ref.pubyear()
        if not in_oa(rel.references[-1],oa_pmids):
            for ref in reversed(rel.references):
                if in_oa(ref,oa_pmids):
                    oa_pubyear = ref.pubyear()
                    if oa_pubyear > 1812:
                        return published_1st, True, oa_pubyear    
            return published_1st, True, 0
        else:
            return published_1st, False, 0
    return 0, False, 0


def castay_year(g:ResnetGraph,oa_pmids:set)->tuple[df,ResnetGraph,ResnetGraph]:
    '''
    output:
      df['Year','# articles published in CA','# CA articles transitioned to OA','Average stay in CA','Average 2nd citation time','# rels with 1 ref']
      published_in_ca_graph
      oa_graph
    '''

    print(f'Analyzing CA stays for graph with {g.number_of_nodes()} nodes and {g.number_of_edges()} edges')
    rels = g.psrels_with()
    year2castays = defaultdict(list)
    year2_oa2ndcitation = defaultdict(list)
    year2citation_time = defaultdict(list)
    year2capubs = defaultdict(int)
    year2single_ref_rel = defaultdict(int)

    ca_rels = list()
    oa_rels = list()

    def align_years(in_dic:dict,by_dic:dict,default_val:int|list=0):
        my_years = list(in_dic.keys()) # cannot use year2capubs.keys() in list editing: dictionary changed size during iteration
        [in_dic.pop(y) for y in my_years if y not in by_dic.keys()]
        for y in by_dic.keys():
            if y not in in_dic.keys():
                in_dic[y] = default_val
        return dict(sorted(in_dic.items()))

    for rel in rels:
        _1stpubyear, published_in_ca, oa_pubyear = in_ca_dates(rel,oa_pmids)
        if published_in_ca:
            year2capubs[_1stpubyear] += 1

            if oa_pubyear:
                ca_stay = oa_pubyear - _1stpubyear
                year2castays[_1stpubyear].append(ca_stay)
                oa_rels.append(rel)
            else:
                ca_rels.append(rel)
        else:
            oa_rels.append(rel)
        
        if rel.count_refs()> 1:
            _2nd_citation_year = rel.references[1].pubyear()
            if _2nd_citation_year > 1812:
                citation_period = _2nd_citation_year - _1stpubyear
                year2citation_time[_1stpubyear].append(citation_period)
                if not published_in_ca:
                    year2_oa2ndcitation[_1stpubyear].append(citation_period)
        else:
            year2single_ref_rel[_1stpubyear] += 1
                    
    published_in_ca_graph = g.subgraph_by_rels(ca_rels)
    oa_graph = g.subgraph_by_rels(oa_rels)
    year2castays = dict(sorted(year2castays.items()))

    year2capubs = align_years(year2capubs,year2castays)
    year_ca2oacounts = [len(x) for x in year2castays.values()]
    year2averagestay = [round(sum(c)/len(c),2) for c in year2castays.values()]

    year2citation_time = align_years(year2citation_time,year2castays,default_val=[0])
    year2average_citation_time = [round(sum(c)/len(c),2) for c in year2citation_time.values()]

    year2_oa2ndcitation = align_years(year2_oa2ndcitation,year2castays,default_val=[0])
    year2average_oa2ndcitation = [round(sum(c)/len(c),2) for c in year2_oa2ndcitation.values()]

    year2single_ref_rel = align_years(year2single_ref_rel,year2castays)


    return df.from_dict({'Year':list(year2castays.keys()),
                         '# articles published in CA' : list(year2capubs.values()),
                         '# CA articles transitioned to OA' : year_ca2oacounts,
                         'Average stay in CA' : year2averagestay,
                         'Average 2nd citation time': year2average_citation_time,
                         'Average 2nd citation time for OA': year2average_oa2ndcitation,
                         '# rels with 1 ref': year2single_ref_rel.values()
                         }
                            ),published_in_ca_graph,oa_graph


def castay_journal(g:ResnetGraph,oa_pmids:set):
    rels = g.psrels_with()
    journal2castay = dict()
    for rel in rels:
        published_1st, in_ca, oa_pubyear = in_ca_dates(rel,oa_pmids)
        if in_ca and oa_pubyear:
            first_ref = rel._1st_ref()
            if isinstance(first_ref,Reference):
                ca_stay = oa_pubyear - published_1st
                rel_journal = first_ref.get_prop(JOURNAL)
               # if rel_journal == 'Ann N Y Acad Sci':
               #     print('')
                if rel_journal:
                    try:
                        journal2castay[rel_journal].append(ca_stay)
                    except KeyError:
                        journal2castay[rel_journal] = [ca_stay]

    journal2averagestay = {j:round(sum(c)/len(c),2) for j,c in journal2castay.items()}
    ca_article_count = [len(v) for v in journal2castay.values()]
    df2return = df.from_dict({'Journal':list(journal2castay.keys()),
                              'Average CA stay': list(journal2averagestay.values()),
                              'Number of CA articles' : ca_article_count
                              }
    )
        
    df2return = df.from_pd(df2return.sort_values(['Average CA stay'],ascending=False))
    return df2return

def count_retracted_in_oa(oa_pmids:set):
    ncbi = NCBIeutils('')
    retracted_pmids = ncbi.get_uids('retracted articles')
    retracted_pmids = set(map(str,retracted_pmids))
    return(retracted_pmids.difference(oa_pmids))
