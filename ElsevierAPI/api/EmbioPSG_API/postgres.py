import psycopg2,ast
from psycopg2.sql import SQL,Identifier,Literal
from psycopg2.extras import Json
from collections import defaultdict
from time import sleep
from ..ResnetAPI.NetworkxObjects import PSRelation,RELATIONID, PSObject
from ...utils.utils import ThreadPoolExecutor,time,as_completed,load_api_config,print_error_info,execution_time,deterministic_hash64,unpack
from ...utils.pandas.panda_tricks import df,pd
from ..ResnetAPI.references import AUTHORS,JOURNAL,MEDLINETA,SENTENCE,PUBYEAR,TITLE,Reference, ARTICLE_ID_TYPES,REFERENCE_POSTGRES_COLS
import numpy as np

#  !!!!!!!!!!!!!!!!!RELATIONID != RELATION_ID !!!!!!!!!!!!!!!!
SNIPPET_ID = 'unique_id'
RELATION_ID = 'id'
REFID2ATTR = {'doi':'DOI','pmid':'PMID','embase':'EMBASE','pii':'PII', 'pui':'PUI','nct_id':'NCT ID','title':TITLE}#,'clinvar_rcv_id':'Clinvar RCV ID'}
#DB_SCHEMA = 'resnet18'
DB_SCHEMA = 'resnetcustomnov'

SENTENCE_PROPS = {'msrc':SENTENCE,'organism':'Organism','source':'Source','textmods':'TextMods','organ':'Organ','tissue':'Tissue',
  'biomarkertype':'BiomarkerType', 'celllinename':'CellLineName','celltype':'CellType', 'px':'pX','quantitativetype':'QuantitativeType',
  'changetype':'ChangeType','collaborator':'Collaborator','company':'Company','condition':'Condition',
  'experimental_system':'Experimental System','intervention':'Intervention','percent':'Percent',
  'phase':'Phase','start':'Start', 'studytype':'StudyType','trialstatus':'TrialStatus','url':'URL'}

COLUMN2ATTR = {'authors':AUTHORS,'title':TITLE,'pubyear':PUBYEAR,'journal':JOURNAL,'medlineta':MEDLINETA,
               'issn':'ISSN','essn':'ESSN','id':'Postgres ID'}

SCOPUS_DATA = {'citation_type':'Article type', 'citation_count':'Citations', 'fwci':'FWCI', 
'fwci_perc':f'FWCI %ile', 'citation_count_ns':'Non-self citations', 'fwci_ns':'Non-self FWCI', 
'fwci_perc_ns':f'Non-self FWCI %ile', 'citescore2024':'CiteScore2024', 
'min_asjc_citescore_percentile_raw':f'CiteScore %ile', 'patent_citation_count':'Patent citations', 
'corporate':'Corporate', 'num_refs':'References', 'independent_ref_count':'Independent References', 
'document_score':'Document score', 'relation_score':'Relation score'}

IDENTIFIER_COLUMNS = {attr:column for column,attr in REFID2ATTR.items()}


#reference table columns:
#column_name	data_type	character_maximum_length	is_nullable
#unique_id	bigint		NO
#authors	text		YES
#biomarkertype	text		YES
#celllinename	text		YES
#cellobject	text		YES
#celltype	text		YES
#changetype	text		YES
#collaborator	text		YES
#company	text		YES
#condition	text		YES
#doi	text		YES
#embase	text		YES
#c	text		YES
#essn	text		YES
#experimental_system	text		YES
#intervention	text		YES
#issn	text		YES
#journal	text		YES
#medlineta	text		YES
#mode_of_action	text		YES
#mref	text		YES
#msrc	text		YES
#nct_id	text		YES
#organ	text		YES
#organism	text		YES
#percent	text		YES
#phase	text		YES
#phenotype	text		YES
#pii	text		YES
#pmid	text		YES
#pubversion	text		YES
#pubyear	integer		YES
#pui	text		YES
#px	double precision		YES
#quantitativetype	text		YES
#source	text		YES
#start	text		YES
#studytype	text		YES
#textmods	text		YES
#textref	text		YES
#tissue	text		YES
#title	text		YES
#trialstatus	text		YES
#url	text		YES
#id	bigint		YES
#unique_ref	text		YES


class PostgreSQL:
  def __init__(self, APIconfig:dict={}):
    if not APIconfig:
      APIconfig = load_api_config()
    self.schema = APIconfig.get('postgreSQschema', DB_SCHEMA)
    self.rel2refDict = dict() # {int(relid):[Reference]}
    self.executor = ThreadPoolExecutor(thread_name_prefix='postgres')
    self.futures = [] # futures of reference retrieval
    
    try:
      self.db = psycopg2.connect(
          database = APIconfig['postgreSQLdb'],
          host = APIconfig['postgreSQLhost'],
          user = APIconfig['postgreSQLuser'],
          password = APIconfig['postgreSQLpswd'],
          port = APIconfig['postgreSQLport']
        )
      print('Connected to Postgres')
    except Exception as e:
      self.db = None
      print("Error connecting to PostgreSQL:", e)

  def close(self):
    """
    Closes the connection to PostgreSQL.
    """
    if self.db:
      self.db.close()
      print('Postgres connection closed')


  def full_table_name(self,table:str):
    return f'{self.schema}.{table}'


  def get_relprops(self,relations_id:list[str]):
    relid_str = ','.join(map(str, relations_id))
    sql = f"SELECT * FROM {self.schema}.control WHERE {self.schema}.control.id IN ({relid_str})"

    with self.db.cursor() as cur:
        cur.execute(sql)
        data = cur.fetchall()
        colnames = [desc[0] for desc in cur.description]

    return df.from_rows(data, columns=colnames)
  

  def get_stats(self,table:str, columns:list[str],filter:dict[str:tuple[str,int]]=dict()):
    '''
    input:
      filter = {columns_name:(sign,value)}
    '''
    count_str = ','.join([f'count({c})' for c in columns])
    count_str += ',count(*)'
    sql = f'SELECT {count_str} from {self.schema}.{table}'
    if filter:    
      clauses = [f'{colname} {value[0]} {value[1]}' for colname,value in filter.items()]
      sql += ' WHERE '+ ' AND '.join(clauses)
    with self.db.cursor() as cur:
      cur.execute(sql)
      data = cur.fetchall()
      counts = list(data[0])
      row_count = counts[-1]
      result_str = f'"{table}" table has {row_count} rows\n'
      for i,count in enumerate(counts[:-1]):
        result_str += f'{columns[i]}: {count}\n'
      print('Counts:\n'+result_str)
      return
    

  def averages(self,table:str, columns:list[str],min_values:dict[str:tuple[str,int]]=dict()):
    '''
    input:
      filter = {columns_name:(sign,value)}
    '''
    count_str = ','.join([f'AVG({c})' for c in columns])
    sql = f'SELECT {count_str} from {self.schema}.{table}'
    if min_values:    
      clauses = [f'{colname} {value[0]} {value[1]}' for colname,value in min_values.items()]
      sql += ' WHERE '+ ' AND '.join(clauses)
    with self.db.cursor() as cur:
      cur.execute(sql)
      data = cur.fetchall()
      averages = list(data[0])
      result_str = ''
      for i,average in enumerate(averages):
        result_str += f'Average of {columns[i]}: {average:.2f}\n'
      print(result_str)
      return averages
    
  
  def execute_sql(self, sql:str):
    with self.db.cursor() as cur:
      cur.execute(sql)
      data = cur.fetchall()
      return list(data)


  def plot_distribution(self,table:str,columns:list[str],outdir=''):
    my_df = df(columns=columns)
    for col in columns:
      sql = f'SELECT {col} FROM {self.schema}.{table}'
      with self.db.cursor() as cur:
        cur.execute(sql)
        rows = [list(r) for r in cur.fetchall()]
        my_df[col] = rows

    print(f'Will plot distribution for {columns} in {table} with {len(my_df)} rows')
    my_df.plot_distribution(columns,outdir=outdir)
    return
  

  def sql2df(self,sql:str):
    with self.db.cursor() as cur:
      cur.execute(sql)
      rows = cur.fetchall()
      colnames = [desc[0] for desc in cur.description]
      rows = [list(r) for r in rows]
      return df.from_rows(rows,columns=colnames)


  def get_refs(self,relations_id:set[str]):
    new_relids = set(map(int, relations_id))
    new_relids = new_relids.difference(self.rel2refDict)
    sql = f"SELECT * FROM {self.schema}.reference WHERE {self.schema}.reference.id = ANY(%s)"

    with self.db.cursor() as cur:
      for attempt in range(3):
        try:
          cur.execute(sql, (list(new_relids),))
          rows = cur.fetchall()
          colnames = [desc[0] for desc in cur.description]
          rows = [list(r) for r in rows]
          ref_pd = pd.DataFrame(rows,columns=colnames)
          return ref_pd
        except Exception as e:
          print(f'Fetching references from Postgres with SQL {sql[:255]} has finished with error:')
          print_error_info(e)
          self.db.rollback()
          sleep(2**attempt)
      print(f'Failed to fetch references from Postgres after 3 attempts with SQL {sql[:255]}')
      return pd.DataFrame()
    
    

  def submit_refs(self, relations_ids:set[str],batch_size=50000):
    """
      submits reference fetching job to ThreadPoolExecutor future that is added to self.futures
    """
    if relations_ids:
      if len(relations_ids) > batch_size:
        print(f'Submitting reference retrieval for {len(relations_ids)} relations to Postgres executor in batches of {batch_size}')
      
      relid_list = list(relations_ids)
      for i in range(0, len(relid_list), batch_size):
        batch = set(relid_list[i:i+batch_size])
        self.futures.append(self.executor.submit(self.get_refs,batch))


  def scopus_data(self, refids:list[int]):
    '''
      scopus_data.reference_id is joined with reference.unique_id
    '''
    refid_str = ','.join(map(str, refids))
    sql = f"SELECT * FROM {self.schema}.scopus_data WHERE {self.schema}.scopus_data.reference_id IN ({refid_str})"
    with self.db.cursor() as cur:
      try:
        cur.execute(sql)
        rows = cur.fetchall()
        colnames = [desc[0] for desc in cur.description]
      except Exception as e:
        if e.pgcode == '42P01':
          print('Postgres does not have Scopus data') #
        else:
          print(f'Fetching Scopus data from Postgres with SQL {sql[:255]} has finished with error:')
          print(e)
        self.db.rollback()
        return pd.DataFrame()
      
    rows = [list(r) for r in rows]
    scopus_pd = pd.DataFrame(rows,columns=colnames)
    #no_list_cols = [col for col in scopus_pd.columns if col != 'author_ids_masked']
    #scopus_pd = scopus_pd.drop_duplicates(subset = no_list_cols,ignore_index=True)
    scopus_pd = scopus_pd.set_index('reference_id')
    return scopus_pd
  

  def __rows2refs(self,ref_pd:pd.DataFrame,scopus_pd:pd.DataFrame)->dict[str,list[Reference]]:
    '''
    output:
      {relation_id:[Reference]}
      scopus_data.reference_id is joined with reference.unique_id
    '''
    relid2refs = defaultdict(list)
    ref_idtypes = list(REFID2ATTR.keys())
    for refpd_idx in ref_pd.index:
      relid = ref_pd.at[refpd_idx,RELATION_ID]
      textref = ref_pd.at[refpd_idx,'textref']
      ref = dict()     
      for idtype_idx, idtype in enumerate(ref_idtypes):
        refid = ref_pd.at[refpd_idx,idtype]
        if not pd.isna(refid):
          ref = Reference(REFID2ATTR[idtype],refid)
          for idt in ref_idtypes[idtype_idx+1:]:
            id = ref_pd.at[refpd_idx,idt]
            if not pd.isna(id):
              ref.Identifiers[REFID2ATTR[idt]] = id
          break

      if isinstance(ref,Reference):
        for col, attr in SENTENCE_PROPS.items():
          attr_val = ref_pd.at[refpd_idx,col]
          if not pd.isna(attr_val):
            ref.add_sentence_prop(textref,attr,attr_val)

        for col, attr in COLUMN2ATTR.items():
          attr_val = ref_pd.at[refpd_idx,col]
          if not pd.isna(attr_val):
            if attr in [PUBYEAR]:
              attr_val = int(attr_val)
            ref[attr] = [attr_val]

        snippet_id = int(ref_pd.at[refpd_idx,SNIPPET_ID])
        if snippet_id in scopus_pd.index:
        #  if snippet_id == -4265759418113288334:
        #    print()
          ref_scopus_data = scopus_pd.loc[[snippet_id]].iloc[0].to_dict() # in case of duplicates in scopus_pd, take the first one
          ref.update({SCOPUS_DATA[k]:[v] for k,v in ref_scopus_data.items() if k in SCOPUS_DATA})
        else:
          refid = ref.doi_or_id()
          if not refid.startswith('NCT') and not scopus_pd.empty:
            print(f'Reference {refid} has no Scopus data')
      
        ref.toAuthors()
        relid2refs[int(relid)].append(ref)

    return dict(relid2refs)


  def load_refs(self):
    """
    load self.rel2refDict
    output:
      self.rel2refDict = {embio_relation_id:[Reference]}
    """
    if self.futures:
      processed_futures = []
      print(f'Got {len(self.futures)} Postgres futures to process')
      for get_refs_future in as_completed(self.futures):
        ref_pd = get_refs_future.result()
        processed_futures.append(get_refs_future)
        scopus_pd = self.scopus_data(set(ref_pd[SNIPPET_ID].to_list()))
        self.rel2refDict.update(self.__rows2refs(ref_pd,scopus_pd))

      self.futures = [f for f in  self.futures if f not in processed_futures]
      print(f'Cached references for {len(self.rel2refDict)} relations from Postgres')
    return self.rel2refDict
  

  def add_refs(self,to_rels:set[PSRelation]):
    '''
    input:
      to_rels: list of PSRelation objects that need references to be added
    output:
      to_rels with added references
    '''
    self.load_refs()
    add_counter = 0
    for rel in to_rels:
      for relid in rel[RELATIONID]:
        irelid = int(relid)
        if irelid in self.rel2refDict:
          new_refs = self.rel2refDict.pop(irelid) # use pop here to keep memory use down, assuming that each relation has around 10 refs, this should free up memory after processing 100 relations
          [rel.references.append(ref) for ref in new_refs if ref not in rel.references]
          add_counter += 1
    print(f'Added references to {add_counter} out of {len(to_rels)} relations')
    return to_rels
  
  
  def snippets_with(self,keywords:list[str])->dict[int,list[Reference]]:
    '''
    output:
      {relation_id:[Reference]},
      relation IDs for references containing any of the keywords in their sentences
    '''
    start = time.time()
    vrsn = self.schema
    sql = f'''SELECT * FROM {vrsn}.reference
          WHERE {vrsn}.reference.msrc ILIKE ANY (ARRAY[{','.join([f"\'%{kw}%\'" for kw in keywords])}]);
      '''
    ref_pd = self.get_refs(sql)
    rel2refs = self.__rows2refs(ref_pd)
    print(f'Snippet search for keywords {keywords} found {len(rel2refs)} relations and {len(ref_pd)} snippets in {execution_time(start)}')
    return rel2refs
  

  def select_citation_score(self,rels:list[PSRelation]):
    relids = set()
    [relids.update(rel[RELATIONID]) for rel in rels if rel[RELATIONID]]
    #relid_str = ','.join([str(relid) for relid in relids])
  #  sql = f"""SELECT DISTINCT reference.id, relation_score
  #       FROM {self.schema}.reference, {self.schema}.scopus_data
  #        WHERE {self.schema}.reference.unique_id = {self.schema}.scopus_data.reference_id
  #        AND {self.schema}.reference.id IN ({relid_str})
  #        """
    sql = f"""SELECT DISTINCT control_attribute, relation_score
          FROM {self.schema}.control_attribute_summary
          WHERE control_attribute IN (%s)"""
    
    with self.db.cursor() as cur:
      try:
        cur.execute(sql, (tuple(relids),))
        rows = cur.fetchall()
        if rows:
          return {str(row[0]):row[1] for row in rows}
        else:
          return dict()
      except Exception as e:
        print(f'Error fetching citation score from Postgres for relation_ids {relids} with SQL {sql[:255]}:')
        print(e)
        self.db.rollback()
        return dict()


  def add_citation_score(self,rels:list[PSRelation]):
    relid2citation_score = self.select_citation_score(rels)
    rels_with_score = []
    for rel in rels:
      rel_ids = rel[RELATIONID]
      for rel_id in rel_ids:
        if rel_id in relid2citation_score:
          rel['Citation score'] = [round(relid2citation_score[rel_id], 4)]
          rels_with_score.append(rel)
          break # if one of the relation IDs has a citation score, add it to the relation and move on to the next relation
    print(f'\nAdded citation score to {len(rels_with_score)} out of {len(rels)} relations based on Scopus data from Postgres')
    return rels_with_score


  def add_column(self,_2df:df,using_sql:str, relid_col= RELATIONID, 
                 column_name='new_column', how2agg=None, new_col_dtype='string'):
    '''
    add a new column to the dataframe with a specified value for rows that have a relation ID, otherwise leave it as NA\n
    how2agg = min,max,avg.  Shows how to aggregate values for rows with list of relation IDs in string format (e.g. "[123,456,789]"),\n 
    if how2agg=None, will return a comma-separated list of values for the relation IDs in the list
    new_col_dtype = Int64, float, string, etc.  The dtype of the new column, used for proper NA handling and aggregation.  If how2agg is not None, new_col_dtype must be numeric.  If how2agg is None, new_col_dtype can be string to return comma-separated list of values.
    '''
    chunk_size = 10000
    number_of_batches = (len(_2df) // chunk_size) + 1
    print(f'Adding "{column_name}" to "{_2df._name_}" dataframe with {len(_2df)} rows using streaming cursor in batches of {chunk_size} for {number_of_batches} batches...')
    relid2prop = dict()
    with self.db.cursor(name=f'fetch{column_name.title()}') as srv_cur:
      srv_cur.itersize = chunk_size
      srv_cur.execute(using_sql)
      for row in srv_cur:
        relid2prop[row[0]] = row[1]

    print(f'Retreived {column_name} for {len(relid2prop)} relation IDs from Postgres, now mapping to dataframe...')
    
    relid_series = _2df[relid_col].astype(str).str.strip() # ensure that relation IDs are strings and strip any whitespace
    list_mask = relid_series.str.startswith('[') # mask for rows where relation ID is a list of relation IDs in string format (e.g. "[123,456,789]"), we will need to parse these and take the earliest publication year among the list of relation IDs
    scalar_relids = pd.to_numeric(relid_series[~list_mask], errors='coerce') # Vectorized fast path for scalar relation IDs.
    scalar_relids = scalar_relids.dropna().astype(int)
    my_dype = 'float' if how2agg == 'avg' else new_col_dtype
    default_val = '' if my_dype == 'string' else (np.nan if my_dype == 'float' else pd.NA)
    _2df[column_name] = pd.Series(default_val, index=_2df.index, dtype=my_dype) # nullable integer dtype to allow NA values
    _2df.loc[scalar_relids.index, column_name] = scalar_relids.map(relid2prop)
    mapped_count = _2df[column_name].notna().sum()
    print(f'Mapped {mapped_count} out of {len(_2df)} rows with scalar relation IDs, now processing list-like relation IDs...')

    # Parse list-like relation IDs and take the earliest mapped publication year.
    def list2list(relid_value:str):
      relid_list = list(map(int, ast.literal_eval(relid_value)))
      if how2agg is None or new_col_dtype == 'string':
        value_list = [str(relid2prop[relid]) for relid in relid_list if relid in relid2prop and relid2prop[relid] is not None]
        return f'{",".join(value_list)}'
      elif how2agg == 'min':
        values = [relid2prop[relid] for relid in relid_list if relid in relid2prop and relid2prop[relid] is not None]
        if values:
          return int(min(values)) if new_col_dtype == 'Int64' else float(min(values))
        return default_val
      elif how2agg == 'max':
        values = [relid2prop[relid] for relid in relid_list if relid in relid2prop and relid2prop[relid] is not None]
        if values:
          return int(max(values)) if new_col_dtype == 'Int64' else float(max(values))
        return default_val
      elif how2agg == 'avg':
        values = [relid2prop[relid] for relid in relid_list if relid in relid2prop and relid2prop[relid] is not None]
        if values:
          return float(sum(values)/len(values))
        return default_val
      else:
        raise ValueError(f'Unsupported aggregation method: {how2agg}')

    if list_mask.any():
      _2df.loc[list_mask, column_name] = relid_series[list_mask].apply(list2list)

    mapped_count = _2df[column_name].notna().sum()
    print(f"Finished mapping {column_name} for {_2df._name_} rows using streaming cursor")
    print(f'Mapped {mapped_count}' f' out of {len(_2df)} rows, {mapped_count/len(_2df)*100:.2f}% coverage')
    return _2df


  def add_1st_pubyear(self,_2df:df, relid_col= RELATIONID, pubyear_col='1stPubYear', stream=True):
    '''
    use stream to add 1st publication year to large number of RelationsIDs
    handles "relid_col" to be either a single relation ID or a list of relation IDs in string format (e.g. "[123,456,789]")
    '''
    chunk_size = 10000
    batch_counter = 0
    # ensure that relation IDs are strings and strip any whitespace
    number_of_batches = (len(_2df) // chunk_size) + 1
    if stream:
      sql = f'''SELECT id, MIN(pubyear) as first_pubyear
          FROM {self.schema}.reference
          WHERE {self.schema}.reference.pubyear IS NOT NULL
          GROUP BY id'''
      df_year = self.add_column(_2df, using_sql=sql, relid_col=relid_col, column_name=pubyear_col, how2agg='min', new_col_dtype='Int64')
    else: # batching without server-side cursor, not recommended for large number of relation IDs due to memory use, but can be faster for small number of relation IDs
      sql = f'''SELECT id::text AS id, MIN(pubyear) as first_pubyear
          FROM {self.schema}.reference
          WHERE {self.schema}.reference.id IN '''
      sql += '''(%s)
          GROUP BY id'''
      
      _2df[relid_col] = _2df[relid_col].astype(int).str.strip() 
      for idx in range(0, len(_2df), chunk_size):
        chunk = _2df.iloc[idx:idx+chunk_size][relid_col].to_list()
        #relid_str = ','.join([str(relid) for relid in set().union(*chunk[relid_col].to_list())])
        #sql = sql.format(relid_str=relid_str)
        # 'cursor_name' makes this a server-side cursor
        with self.db.cursor() as cur:
          try:
            cur.execute(sql, (tuple(set(chunk)),))
            rows = cur.fetchall()
            if rows:
              relid2pubyear = {row[0]: row[1] for row in rows}
              _2df[pubyear_col] = _2df[relid_col].map(relid2pubyear)
              batch_counter += 1
              print(f"Processed batch {batch_counter} of {number_of_batches}, {len(rows)} rows...")
          except Exception as e:
            print(f'Error fetching MIN PubYear from Postgres for relation_ids {chunk} with SQL {sql[:255]}:')
            print(e)
            self.db.rollback()
      df_year = _2df
      df_year[pubyear_col] = df_year[pubyear_col].astype('Int64')
    return df_year

  # node table columns:
  #column_name	data_type	character_maximum_length	is_nullable
  # id	bigint		NO
  # urn	text		YES
  # name	text		YES
  # nodetype	text		YES
  # attributes	ARRAY		YES
  
  # attr table columns:
  # column_name	data_type	character_maximum_length	is_nullable
  # id	bigint		NO
  # name	text		YES
  # value	text		YES
  def nodeid2prop(self,nodeids:list[str], prop:str)->dict[int,list[str]]:
    '''
    output:
      {nodeid:prop_value}
    '''
    id_str = ','.join([f"{nodeid}" for nodeid in nodeids])
    sql = f"""SELECT n.id::int AS id, a.value
              FROM {self.schema}.node as n
              JOIN {self.schema}.attr as a ON a.id = ANY(n.attributes)
              WHERE a.name = %s
              AND n.id = ANY(%s)"""
    
    node_ids = list(map(int, nodeids))
    with self.db.cursor() as cur:
      try:
        cur.execute(sql, (prop, node_ids))
        #colnames = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
        if rows:
          nodeid2values = defaultdict(list)       
          [nodeid2values[row[0]].append(row[1]) for row in rows]
          return dict(nodeid2values)
        else:
          return dict()
      except Exception as e:
        print(f'Error fetching {prop} from Postgres for URNs {id_str} with SQL {sql[:255]}:')
        print(e)
        self.db.rollback()
        return dict()


  def _insert_node_(self,node:PSObject):
    '''
    Inserts a node into the Postgres database.
    input:
      node: PSObject representing the node to be inserted
    '''
    node_attrs = []
    attr_ids = []
    for attr_name, attr_values in node.items():
      for val in attr_values:
        attr_id = deterministic_hash64(f"{attr_name}|{val}")
        attr_row = (attr_id, attr_name, val)
        node_attrs.append(attr_row)
        attr_ids.append(attr_id)

    sql = f"""INSERT INTO {self.schema}.node (id, urn, name, nodetype, attributes)
              VALUES (%s, %s, %s, %s, %s)"""
    with self.db.cursor() as cur:
      try:
        cur.execute(sql, (
          node['id'],
          node.get('urn'),
          node.get('name'),
          node.get('nodetype'),
          attr_ids
        ))
        self.db.commit()
      except Exception as e:
        print(f'Error inserting node {node["id"]} into Postgres:')
        print(e)
        self.db.rollback()

      if node_attrs:
        sql_attrs = f"""INSERT INTO {self.schema}.attr (id, name, value)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (id) DO NOTHING"""
        with self.db.cursor() as cur:
          try:
            cur.executemany(sql_attrs, node_attrs)
            self.db.commit()
          except Exception as e:
            print(f'Error inserting node attributes for node {node["id"]} into Postgres:')
            print(e)
            self.db.rollback()


  def _insert_nodes_(self,nodes:list[PSObject])->int:
    '''
    Insert nodes and their attributes using UNNEST in a single transaction.
    Return the inserted node count; roll back and propagate database errors.
    '''
    if not nodes:
      return 0

    node_rows = []
    attributes = {}
    for node in nodes:
      node_id = node.neo4j_NodeID()
      attr_ids = []
      for attr_name, attr_values in node.items():
        for val in attr_values:
          attr_id = deterministic_hash64(f"{attr_name}|{val}")
          attributes[attr_id] = (attr_id, attr_name, str(val))
          attr_ids.append(attr_id)
      # Text array literals allow different attribute counts for each node.
      attr_array = '{' + ','.join(map(str, attr_ids)) + '}'
      node_rows.append((node_id, node.urn(), node.name(), node.objtype(), attr_array))

    node_sql = SQL(
      'INSERT INTO {}.{} (id, urn, name, nodetype, attributes) '
      'SELECT id, urn, name, nodetype, attributes::bigint[] '
      'FROM UNNEST(%s::bigint[], %s::text[], %s::text[], %s::text[], %s::text[]) '
      'AS incoming(id, urn, name, nodetype, attributes)'
      'ON CONFLICT (id) DO NOTHING'
    ).format(Identifier(self.schema), Identifier('node'))

    attr_sql = SQL(
      'INSERT INTO {}.{} (id, name, value) '
      'SELECT id, name, value FROM UNNEST(%s::bigint[], %s::text[], %s::text[]) '
      'AS incoming(id, name, value) ON CONFLICT (id) DO NOTHING'
    ).format(Identifier(self.schema), Identifier('attr'))

    with self.db:
      with self.db.cursor() as cur:
        if attributes:
          cur.execute(attr_sql, [list(values) for values in zip(*attributes.values())])
        cur.execute(node_sql, [list(values) for values in zip(*node_rows)])
        inserted_count = cur.rowcount
        print(f'Inserted {inserted_count} out of {len(node_rows)} nodes into Postgres.')
    return len(node_rows)


  def refExists(self, ref:Reference, _4relid:int)->bool:
    matches = [
      (IDENTIFIER_COLUMNS[idtype], value)
      for idtype,value in ref.Identifiers.items()
      if idtype in IDENTIFIER_COLUMNS and value not in (None, '')
    ]
    if not matches:
      return False

    clauses = [SQL('{} = %s').format(Identifier(column)) for column,_ in matches]
    query = SQL(
      'SELECT EXISTS (SELECT 1 FROM {}.{} WHERE {} = %s AND ({}))'
    ).format(
      Identifier(self.schema), Identifier('reference'), Identifier(RELATION_ID),
      SQL(' OR ').join(clauses)
    )
    parameters = [_4relid] + [value for _,value in matches]
    with self.db.cursor() as cur:
      try:
        cur.execute(query, parameters)
        return bool(cur.fetchone()[0])
      except Exception:
        self.db.rollback()
        raise


  def refsNotExist(self, relid2refs:dict[int,list[Reference]])->dict[int,list[Reference]]:
    '''
    output:
      a list of identifiers containing the identifier value and relation ID that either empty or do not exist in the database
    '''
    refcount = sum(len(refs) for refs in relid2refs.values())
    print(f'Checking existence of {refcount} references for {len(relid2refs)} relations using all identifier types',flush=True)

    search4refs = []
    missing_positions = set()
    missing_refs = defaultdict(list)
  
    identifiers = [(ref.identifiers(ARTICLE_ID_TYPES), relid, ref) for relid,refs in relid2refs.items() for ref in refs]
    for position,(ids,relid,ref) in enumerate(identifiers):
      search4refs.append((position,ids,relid))
      
    if not search4refs:
      return dict(missing_refs)

    clauses = [
      SQL('(identifier_pair.value->>0 = {} AND reference_row.{} = identifier_pair.value->>1)').format(
        Literal(idtype), Identifier(column)
      )
      for idtype,column in IDENTIFIER_COLUMNS.items()
    ]
    query = SQL(
      'SELECT incoming.position '
      'FROM UNNEST(%s::integer[], %s::jsonb[], %s::bigint[]) '
      'AS incoming(position, ids, relid) '
      'WHERE NOT EXISTS (SELECT 1 FROM {}.{} AS reference_row '
      'CROSS JOIN LATERAL jsonb_array_elements(incoming.ids) AS identifier_pair(value) '
      'WHERE reference_row.{} = incoming.relid '
      'AND ({}))'
    ).format(
      Identifier(self.schema), Identifier('reference'),
      Identifier(RELATION_ID), SQL(' OR ').join(clauses)
    )
    positions,idtype2id,relids = zip(*search4refs)
    parameters = [list(positions), [Json(ids) for ids in idtype2id], list(relids)]
    with self.db.cursor() as cur:
      try:
        #sql_str = cur.mogrify(query, parameters).decode(self.db.encoding) # for debug only
        #sql_template = query.as_string(self.db) # for debug only
        cur.execute(query, parameters)
        missing_positions.update(row[0] for row in cur.fetchall())
      except Exception:
        self.db.rollback()
        raise

    for position in missing_positions:
      ids, relid, ref = identifiers[position]
      missing_refs[relid].append(ref) 

    missing_refcount = sum(len(refs) for refs in missing_refs.values())
    print(f'{missing_refcount} references out of {refcount} are not found in database', flush=True)
    return dict(missing_refs)


  def _insert_refs_(self, relid2refs:dict[int,list[Reference]])->int:
    '''
    Insert {relation_id: [missing references]} using one UNNEST statement and commit.
    Skip rows conflicting with unique or exclusion constraints and report inserted and skipped counts.
    Roll back and propagate other database errors.
    Return inserted row count.
    '''
    rows = []
    for relid, missing_refs in relid2refs.items():
      for ref in missing_refs:
        rows.extend(ref.postgres_refs(relid))

    if not rows:
      return 0

    columns = ['unique_id']+[column.lower().replace(' ', '_') for column in REFERENCE_POSTGRES_COLS]
    columns.extend([RELATION_ID, 'unique_ref'])
    if any(len(row) != len(columns) for row in rows):
      raise ValueError('Reference row length does not match the insert columns')

    numeric_types = {'unique_id':'bigint', RELATION_ID:'bigint', 'pubyear':'integer', 'px':'double precision'}
    expressions = [
      SQL("NULLIF(incoming.{}, '')::{}").format(Identifier(column), SQL(numeric_types[column]))
      if column in numeric_types else SQL('incoming.{}').format(Identifier(column))
      for column in columns
    ]
    column_names = SQL(', ').join(Identifier(column) for column in columns)
    query = SQL(
      'INSERT INTO {}.{} ({}) SELECT {} FROM UNNEST({}) AS incoming ({}) '
      'ON CONFLICT DO NOTHING'
    ).format(
      Identifier(self.schema), Identifier('reference'),
      column_names, SQL(', ').join(expressions),
      SQL(', ').join(SQL('%s::text[]') for column in columns), column_names
    )
    # Every column travels as ONE text[] array parameter, and PostgreSQL rejects any single
    # value above 1 GB ("invalid memory alloc request size ..."). A large RNEF <resnet> can
    # carry hundreds of thousands of relations, so the rows are sent in chunks. All chunks
    # run in the same transaction (the `with self.db` block), so the batch is still
    # all-or-nothing.
    INSERT_CHUNK_ROWS = 20000
    inserted_count = 0
    with self.db:
      with self.db.cursor() as cur:
        try:
          for start in range(0, len(rows), INSERT_CHUNK_ROWS):
            chunk = rows[start:start + INSERT_CHUNK_ROWS]
            parameters = [list(values) for values in zip(*chunk)]
            cur.execute(query, parameters)
            inserted_count += cur.rowcount
        except Exception as e:
          self.db.rollback()
          raise e
  
    print(f'Inserted {inserted_count} references; skipped {len(rows)-inserted_count} duplicate rows')
    return inserted_count


  def import_refs(self,fromExistRels:list[PSRelation], fromNewRels:list[PSRelation])->int:
    '''Returns count of newly inserted references'''
    newrefcount = 0

    if fromNewRels:
      new_refs = {r.neo4j_relationID(): r.refs() for r in fromNewRels}
      if len(new_refs) == 0:
        print("!!!! No new references to insert from new relations !!!!")
      else:
        newrefcount = self._insert_refs_(new_refs)
        print(f"Inserted {newrefcount} new references from new relations",flush=True)
    else:
      print('No new relations to insert references from',flush=True)

    if fromExistRels:
      existing_refs = {r.neo4j_relationID(): r.refs() for r in fromExistRels}
      missing_refs = self.refsNotExist(existing_refs)
      if missing_refs:
        insert_row_count = self._insert_refs_(missing_refs)
        if insert_row_count == 0:
          print(f"No missing references to insert for {len(fromExistRels)} existing relation(s)",flush=True)
        newrefcount += insert_row_count
        if insert_row_count > 0:
          print(f"Inserted {insert_row_count} missing references for {len(fromExistRels)} existing relations",flush=True)
        else:
          print(f"{len(fromExistRels)} existing relations have no new references",flush=True)
      else:
        print(f"No existing relations to insert references from",flush=True)
  
    return newrefcount


  
