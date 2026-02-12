import time,numpy, pandas
from ElsevierAPI.utils.utils import ThreadPoolExecutor,run_tasks,execution_time,unpack
from ..ResnetAPI.TargetIndications import Indications4targets,OQL,df,ResnetGraph,PSObject
from ..ResnetAPI.TargetIndications import RAWDF4ANTAGONISTS,RAWDF4AGONISTS,SNIPPET_PROPERTIES
from ..ResnetAPI.SemanticSearch import RANK,TOTAL_REFCOUNT,REFCOUNT_COLUMN,INPUT_WOKSHEET,CHILDREN_COUNT

AGGRANK = 'Aggregate Rank'

CELLPROCESS_WORDS = ['activation','proliferation','differentiation','migration','infiltration','population','expansion','survival','phenotype','count','interaction',
                    'recognition','homeostasis','adhesion','mediated immunity','viability','growth','formation','homing','priming','localization','polarity',
                    'division','motility','selection','function','motion','renewal','distribution','fate commitment','cell-mediated cytotoxicity','lifespan']

# KLRG1+ cell ontology:
CELL_ONTOLOGY = {
          'KLRG1+cells':['KLRG1','KLRG1+T cells',"KLRG1+cells","TemRA",'Early Effector Cell','resident memory T-cell',"T-cell aging",'KLRG1 overexpresssion','antigen specific cytotoxic T-cell','KLRG1+cells cell-mediated cytotoxicity'],
          'KLRG1+CD8+':["KLRG1+CD8+TEX",'CD8+TemRA','KLRG1+CD8+ cells',"KLRG1+CD8+ MAIT cells", "KLRG1+CD8+TCMs",
          'KLRG1+CD8+TCMs','KLRG1+TRMs','short-lived effector cells','exhausted CD8+T-cell','senescent CD8+ T-cell'],               
          'KLRG1+CD4+':['CD4+Temra','KLRG1+ CD4+ cells',"exhausted CD4+T-cell",'CD4+ cytotoxic T-cell',"senescent CD4+ T-cell"],
          'CD8+':["CD8+ T-cell","effector memory CD8+ T-cell","activated CD8+ T-cell",'CD8+TRMs','large granular lymphocyte','CD8+ memory T-cell'],
          'CD4+':["helper T-cell",'Th1 cell','CD4+TRMs','CD4+ memory T-cell',"activated CD4+ T-cell"],
          'KLRG1+gammadelta':['TEMRA Vd2pos','TEMRA Vd1','TEMRA gd'],
          'gammadelta':['gammadelta T-cell','Vg9/Vd2 T-cell'],
          'KLRG1+NKTs':['KLRG1',"KLRG1+cells",'KLRG1+T cells',"KLRG1+ NKTs","KLRG1+iNKTs",'CD8+ NKT-like cell','NKT-like cell'],
            'NKTs':['natural killer T-cell','CD8+ NK T-cell','activated CD8+ NK T-cell', 
          'activated NKT-like cell','CD56+ T-cell','NKTfh'], #'invariant natural killer T-cell','CD4+ NK T-cell',
          'KLRG1+NKs':['KLRG1',"KLRG1+cells","KLRG1+ NKs"],
          'NKs':['CD56+CD8+TEMs',"natural killer cell","CD56+ natural killer cell","activated natural killer cell","CD57+ natural killer cell","killer cell","memory-like natural killer cell","natural killer cell precursor"], #"CD56hi natural killer cell",
          'KLRG1+ILCs':["KLRG1+ ICL2",'KLRG1',"KLRG1+cells"],
          'ILC2s':["group 2 innate lymphoid cell"],
          'ILCs':["innate lymphoid cell"],
           'Teff':["activated T-cell",'cytotoxic T-cell',"effector memory T-cell","effector T-cell","exhausted T-cell"],
          'T-cells':["senescent T-cell","naive T-cell","memory T-cell","central memory T-cell","alphabeta T-cell","T-cell"],
          'Leukocytes':["immunocompetent cell","mononuclear cell","spleen cell","myeloid cell","PBMC","peripheral lymphocyte","lymphocyte","cytotoxic lymphocyte","effector cell","memory cell","immunosenescence"],
          'KLRG1+Tregs':["KLRG1+ Tregs", 'KLRG1+ Tfh'],
          'Tregs': ["highly suppressive regulatory T-cell","inducible CD4+CD25+ regulatory T-cell",
                    "regulatory T-cell",'CD8+ regulatory T-cell','CCR3+ CD8+ regulatory T-cell',
                    'CD122+ CD8+ regulatory T-cell','CD25+ CD8+ regulatory T-cell','CD28- CD8+ regulatory T-cell',
                    'suppressor-inducer T-cell','effector/activated regulatory T-cell','extralymphoid regulatory T-cell',
                    'Qa-1 restricted regulatory T-cell','CD4+ CD25- FOXP3+ T-cell','memory regulatory T-cell',
                    'naive regulatory T-cell','CD4+ CD25+ regulatory T-cell','Tr1 cell'] 
          #'Monocytes':["monocyte","dendritic cell",'macrophage']
          }

RANKED_CELL_ONTOLOGY = {'KLRG1+cells':0,'KLRG1+CD8+':0,'KLRG1+CD4+':0,'CD8+':1,'CD4+':1,'Teff':2,'T-cells':3} # T-cell ontology


def rank_cells(cell_ontology:list[str]|dict[str,int])->dict[tuple[str,int],list[str]]:
  '''
  output:
    {(cell_group,rank):[cell_type_names from CELL_ONTOLOGY]}
  '''
  if isinstance(cell_ontology,dict):
    return {(co, rank):list(CELL_ONTOLOGY[co]) for co,rank in cell_ontology.items() if co in CELL_ONTOLOGY}
  else:
    return {(co, rank):list(CELL_ONTOLOGY[co]) for rank,co in enumerate(cell_ontology) if co in CELL_ONTOLOGY}



class Indications4cells (Indications4targets):
  def __init__(self, *args, **kwargs):
    self.grouprank2concepts = dict() ##{(group,rank):list[PSObject]}
    self.indication2dbids = dict() # {indication_name:[dbids]}
    self.indication_reports = dict() #{(group,rank):df}
    self.coocIndications = set()
    self.ranked_cell_ontology = kwargs.pop('ranked_cell_ontology',dict())
    super().__init__(*args,**kwargs)


  def clear(self):
    self.grouprank2concepts.clear()
    self.clear_indications()
    self.report_pandas.clear()
    self.raw_data.clear()


  def __loadCoocG(self) -> bool:
    """
    Determines whether co-occurrence graph needs to be loaded.
    
    Returns:
        True if graph should be loaded, False otherwise
    """
    needs_cooc = (self.params.get('add_sentcooccur') or 
                  self.params.get('include_cooc_indications4'))
    
    if needs_cooc:
      # Load only if not already loaded
      return not (hasattr(self, '__coocG__') and self.__coocG__)
    else:
      return False
    

  def _set_targets(self,group:str,targets:list[str]|dict[str:int]):
    if self.__loadCoocG():
      cooc_fut = ThreadPoolExecutor().submit(ResnetGraph.fromRNEFdir,self.params['add_sentcooccur'])
    self.add_ent_props(['Class','Alias'])
    input_target_names = list(targets.values()) if isinstance(targets,dict) else list(targets)
    target_names = input_target_names + ['activated '+ t for t in input_target_names]
    extension = [t+' '+cp for t in target_names for cp in CELLPROCESS_WORDS]
    target_names_ext = target_names + extension
    oql = 'SELECT Entity WHERE Name = ({props})'
    targetsG = self.iterate_oql(oql,target_names_ext,request_name=f'Load "{group}" group cells')
    self.entProps.remove('Class')
    self.__targets__ = set(targetsG._get_nodes())
    self.__input_targets__ = {x for x in self.__targets__ if x.name() in input_target_names}

    self.entProps.remove('Alias')
    if  isinstance(targets,dict):
      self.targets_have_weights = True
      for t in self.__targets__:
        t_weight = targets[t.name()]
        t['regulator weight'] = [t_weight]
        t['target weight'] = [t_weight]
    
    if self.__loadCoocG():
      self.__coocG__ = cooc_fut.result()
      print(f'loaded {self.__coocG__.number_of_nodes()} nodes from {self.params["add_sentcooccur"]} co-occurence graph')
    return


  def target_names_str(self):
    '''
    output:
      group name from self.params['target_names']
    '''
    targets_group = list(self.params['target_names'].keys())
    for group_rank in targets_group:
      return group_rank[0]


  def report_path(self,extension='.xlsx'):
    return super().report_path(extension)


  def input_target_names_str(self):
    return self.target_names_str()
  

  def target_names(self):
    return list(self.params['target_names'].values())
  

  def _indications4targets(self): 
    super()._indications4targets()
    cellproc_targets = [t for t in self.__targets__ if t.objtype() == 'CellProcess']
    if cellproc_targets:
      t_oql = OQL.get_objects(ResnetGraph.dbids(cellproc_targets))
      i_oql,_ = self.oql4indications()
      REQUEST_NAME = f'Find indications FunctionalAssociated with {len(cellproc_targets)} CellProcess: {ResnetGraph.names(cellproc_targets)}'
      OQLquery = f'SELECT Relation WHERE objectType = FunctionalAssociation  AND NeighborOf({t_oql}) AND NeighborOf ({i_oql})' 
      CellProcDiseaseAssociation = self.process_oql(OQLquery,REQUEST_NAME)
      if isinstance(CellProcDiseaseAssociation,ResnetGraph):
        indications = set(CellProcDiseaseAssociation.psobjs_with(only_with_values=self.params['indication_types']))
        self.__indications4antagonists__.update(indications)

    if self.params.get("include_cooc_indications4",False):
      if not self.coocIndications:
        top_ontogroups = [n for n,r in self.ranked_cell_ontology.items() if r == 0]
        klrg_cellnames = unpack([v for k,v in CELL_ONTOLOGY.items() if k in top_ontogroups])
        klrg_cells = self.__coocG__.psobjs_with(['Name'],klrg_cellnames)
        cooc_indications = self.__coocG__.get_neighbors(klrg_cells)
        cooc_indications = [i for i in cooc_indications if i.objtype() == 'Disease' and i not in self.__indications4antagonists__]
        self.coocIndications,_ = self.load_dbids4(cooc_indications)
      self.__indications4antagonists__.update(self.coocIndications)
      print(f'Added {len(self.coocIndications)} indications from co-occurence data')


  def indications4targets(self,group:str,targets:list[str]|dict[str:int]):
    '''
    input:
      target names must be in self.params['target_names']
      moa in [ANTAGONIST, AGONIST, ANY_MOA]
    '''
    start_time = time.time()
    self._set_targets(group,targets)
    self._indications4targets()
    self._resolve_conflict_indications()
    print(f"{len(self._my_indications())} indications for {self.target_names_str()} were found in {execution_time(start_time)}")
    return 
  

  def add_sentcooc(self,_2df:df)->dict[str,int]:
    dis2cooc = dict()
    if self.__coocG__ and self.params.get('add_sentcooccur',''):
      dis2cooc = dict()
      my_indications = self.__indications4antagonists__ if _2df._name_  == RAWDF4ANTAGONISTS else self.__indications4agonists__
      cooc_counter = 0
      for i in my_indications:
        t_coocG = self.__coocG__.neighborhood([i],only_neighbors=self.__targets__,only_reltypes=['UnknownRelation'])
        cooc_refs = t_coocG.load_references()
        dis2cooc[i.name()] = len(cooc_refs) 
        if cooc_refs:
          cooc_counter += 1

      if cooc_counter: # to avoid adding column with all zeros
        _2df['SentCooccur'] = _2df['Name'].map(dis2cooc)
        _2df['SentCooccur'] = _2df['SentCooccur'].fillna(0)
        _2df.set_rank('SentCooccur')
        non_zero_count = int((_2df['SentCooccur'] != 0).sum())
        print(f'Added {non_zero_count} coocurences to column "SentCooccur" to worksheet {_2df._name_} with {len(_2df)} rows')
        return dis2cooc
      else:
        print(f'No sentence co-occurences found for {_2df._name_} with {len(_2df)} rows')
        return dict() # dis2cooc can have all zeros


  def add_abstract_cooc(self,_2df:df)->tuple[dict[str, int], dict[str, float]]:
    '''
    output:
      name2abscooc, name2relevance
    '''
    if self.params.get('add_abstcooccur',False) and self.params.get('init_refstat',True):
      print('Will attept to add abstract co-occurences from SBS')
      multithread = not self.debug()
      concept_names = ResnetGraph.names(self.__input_targets__)
      concept_names = ['"KLRG1"' if item == 'KLRG1' else item for item in concept_names]
      return self.RefStats.abs_cooc(_2df,'Name',concept_names,multithread=multithread)
    else:
      return dict(),dict()


  def perform_semantic_search(self):
    start = time.time()
    ind2abscooc = dict()
    ind2relevance = dict()
    if RAWDF4ANTAGONISTS in self.raw_data:
      if self.debug():
        self.raw_data[RAWDF4ANTAGONISTS] = self.semscore4(self.__targets__,'positive',self.__partners__,self.raw_data[RAWDF4ANTAGONISTS])
        ind2sentcooc = self.add_sentcooc(self.raw_data[RAWDF4ANTAGONISTS]) # SentCooc must have higher rank than AbsCooccur
        ind2abscooc, ind2relevance = self.add_abstract_cooc(self.raw_data[RAWDF4ANTAGONISTS])
      else:
        tasks = [(self.semscore4,(self.__targets__,'positive',self.__partners__,self.raw_data[RAWDF4ANTAGONISTS]))]
        tasks.append((self.add_abstract_cooc,(self.raw_data[RAWDF4ANTAGONISTS],)))
        results = run_tasks(tasks)
        self.raw_data[RAWDF4ANTAGONISTS] = results['semscore4']
        ind2sentcooc = self.add_sentcooc(self.raw_data[RAWDF4ANTAGONISTS]) # SentCooc must have higher rank than AbsCooccur
        ind2abscooc, ind2relevance = results['add_abstract_cooc']

      if ind2relevance:
        self.raw_data[RAWDF4ANTAGONISTS]['AbsCooccur'] = self.raw_data[RAWDF4ANTAGONISTS]['Name'].map(ind2relevance)
        self.raw_data[RAWDF4ANTAGONISTS]['AbsCooccur'] = self.raw_data[RAWDF4ANTAGONISTS]['AbsCooccur'].fillna(0)
        non_zero_count = int((self.raw_data[RAWDF4ANTAGONISTS]['AbsCooccur'] != 0).sum())
        print(f'Added column "AbsCooccur" with {non_zero_count} non-empty rows to worksheet with {len(self.raw_data[RAWDF4ANTAGONISTS])} entities')
        self.raw_data[RAWDF4ANTAGONISTS].set_rank('AbsCooccur')
      
    if RAWDF4AGONISTS in self.raw_data:
      self.raw_data[RAWDF4AGONISTS] = self.semscore4(self.__targets__,'negative',self.__partners__,self.raw_data[RAWDF4AGONISTS])
      tox2sentcooc = self.add_sentcooc(self.raw_data[RAWDF4AGONISTS])
    
    self.raw2report()

    # reverting coocurences to counts for report
    def _2int(d:df, col:str, int_dict:dict,_1st_row = 1):
      if int_dict and col in d.columns:
        d.loc[_1st_row:,col] = d.loc[_1st_row:,'Name'].map(int_dict)
        d.loc[_1st_row:,col] = pandas.to_numeric(d.loc[_1st_row:,col], errors='coerce').fillna(0).astype(int)

    ws_ind,ws_tox = self.ws_names()
    if ws_ind in self.report_pandas:
      _2int(self.report_pandas[ws_ind],'SentCooccur',ind2sentcooc)
      _2int(self.report_pandas[ws_ind],'AbsCooccur',ind2abscooc)
    if ws_tox in self.report_pandas:
      _2int(self.report_pandas[ws_tox],'SentCooccur',tox2sentcooc)
    
    self.add_target_columns()
    self.write_report()
    print(f'TargetIndications semantic search is finished in {execution_time(start)}')
    return


  def make_report4(self,group:str,of_cells:list[str]|dict[str,int])->tuple[df,list]:
    '''
    output:
      worksheets in self.report_pandas: ws_ind,ws_tox
    '''
    self.indications4targets(group,of_cells)
    if self.init_semantic_search():
      self.perform_semantic_search()
      self.add_graph_bibliography()

    ws_ind, ws_tox = self.ws_names()
    raw_df = self.raw_data.get(ws_ind,df())
    if not raw_df.empty:
    # indications do not have children in __indications4antagonists__
      indication2dbids = dict(zip(raw_df['Name'], raw_df[self.__temp_id_col__]))
      self.indication2dbids.update(indication2dbids)

    group_concepts = list(self.__targets__) + list(self.__GVs__) + list(self.__partners__)
    return self.report_pandas.get(ws_ind,df()), group_concepts


  def make_reports(self,max_rank=0):
    max_rank =  max_rank if max_rank else len(self.ranked_cell_ontology)
    grouprank2cells = rank_cells(self.ranked_cell_ontology)
    for (group,rank), cells in grouprank2cells.items():
      if rank <= max_rank:
        self.params['target_names'] = {(group,rank):cells}
        self.ws_prefix = group
        report, group_concepts = self.make_report4(group,cells)
        self.indication_reports[(group,rank)] = report
        self.grouprank2concepts[(group,rank)] = group_concepts
        self.clear_indications()
      

  def add_true_refcount(self,_2df:df):
    klrg1refs_future = ThreadPoolExecutor().submit(self.RefStats.search_docs,'"KLRG1"')
    rank_df = _2df.dfcopy()
    how2connect = self.set_how2connect()
    cols2remove = set()
    all_cells = set()
    rename_refcount = dict()
    for (group,rank),cells in self.grouprank2concepts.items():
      concept2 = group+'-all'
      all_cells.update(cells)
      _,rank_df = self.link2concept(concept2,cells,rank_df,how2connect)
      refcount_name = self._refcount_colname(concept2)
      rename_refcount.update({refcount_name:f'Semantic refcount to {group}'})
      weighted_name = self._weighted_refcount_colname(concept2)
      linked_colname = self._linkedconcepts_colname(concept2)
      size_column = self._concept_size_colname(concept2)
      cols2remove.update([self.__temp_id_col__,weighted_name,linked_colname,size_column])

    cols = rank_df.columns.to_list()
    cols =  [c for c in cols if c not in cols2remove]
    rank_df = rank_df.dfcopy(cols,rename_refcount)

    indication_dbids = set(unpack(_2df['entity_IDs'].to_list())) # this list also includes all children of indications
    all_indications = self.Graph.psobj_with_ids(indication_dbids)

    filteredCoocG = self.__coocG__.copy()
    if hasattr(self,'mustbe_toxicities'):
        filteredCoocG.remove_nodes_from(ResnetGraph.uids(self.mustbe_toxicities))
    if hasattr(self,'mustnotbe'):
        filteredCoocG.remove_nodes_from(ResnetGraph.uids(self.mustnotbe))
    self.Graph = self.Graph.compose(filteredCoocG) #updated self.Graph is neeeded for snippets4df
    cells2indications = self.Graph.get_subgraph(list(all_cells),list(all_indications))
    biblio_df = cells2indications.bibliography('Refs4Ind.')
    snippets_df = self.snippets4df(rank_df,cells2indications,'Snippets')

    # adding KLRG1 rank column to snippets_df:
    klrg1_refs = klrg1refs_future.result()
    pmid2rank = {ref.pubmed_link():rank for rank,ref in enumerate(klrg1_refs) if ref.pmid() and ref.pubmed_link() in snippets_df['PMID'].values}
    rank_colname = 'KLRG1 article rank'
    snippets_df[rank_colname] = snippets_df['PMID'].map(pmid2rank)
    print(f'{snippets_df[rank_colname].count()} rows were mapped by PMID in {rank_colname} column')
    doi2rank = {ref.doi_link():rank for rank,ref in enumerate(klrg1_refs) if ref.doi() and ref.doi_link() in snippets_df['DOI'].values}
    norank_rows_mask = snippets_df[rank_colname].isnull()
    snippets_df.loc[norank_rows_mask, rank_colname] = snippets_df.loc[norank_rows_mask, 'DOI'].map(doi2rank)
    print(f'{snippets_df[rank_colname].count()} rows out of {len(snippets_df)} were mapped by PMID and DOI in {rank_colname} column')

    sentence_colindex = int(snippets_df.columns.get_loc('Sentence'))
    snippets_df = snippets_df.move_cols({rank_colname:sentence_colindex})
    snippets_df = snippets_df.sortrows(by=[rank_colname,'Indication','Target'],ascending=[True,True,True])
    
    name2childcount = {i.name():i.number_of_children()+1 for i in all_indications}
    rank_df[CHILDREN_COUNT] = rank_df['Name'].map(name2childcount)
    rank_df = rank_df.move_cols({CHILDREN_COUNT:1})
    return rank_df, biblio_df, snippets_df


  def add_input2df(self):
    rows4inputdf = []
    for (group,rank), concepts in self.grouprank2concepts.items():
      for concept in concepts:
        assert(isinstance(concept,PSObject))
        cell_aliases = set(concept.get_props('Alias'))
        cell_aliases.add(concept.name())
        cell_aliases = ','.join(cell_aliases)
        rows4inputdf.append([group,rank+1,concept.name(),cell_aliases])
    param_df = df.from_rows(rows4inputdf,['Concept','Rank','Cell','Aliases'])
    param_df = param_df.sortrows(by=['Rank','Concept','Cell'],ascending=[True,False,False])
    param_df._name_ = INPUT_WOKSHEET
    param_df.tab_format['tab_color'] = 'yellow'
    self.add2report(param_df)
    return param_df
  

  def _combine_ranks(self,in_df:df):
    weight_row = {'Name':'WEIGHTS:'}
    weight_row.update(self.rank2weight(in_df.col2rank))
    weights_df = df([weight_row])

    rank_cols = list(in_df.col2rank.keys())
    weights = weights_df.loc[0,rank_cols].values.tolist()
    my_df = in_df.dfcopy()
    for i in my_df.index:
      row_scores = my_df.loc[i,rank_cols].values.tolist()
      assert(len(weights) == len(row_scores))
      weighted_sum = numpy.nan_to_num(sum(s*w for s,w in zip(row_scores, weights)))
      my_df.loc[i,AGGRANK] = weighted_sum


    my_df = my_df.sortrows(by=[AGGRANK]+rank_cols)
    weights_df = df.from_pd(weights_df.map(lambda x: f'{x:,.4f}' if isinstance(x,float) else x))
    new_colorder = ['Name'] + rank_cols + [AGGRANK]
    other_cols = [x for x in my_df.columns.to_list() if x not in new_colorder]
    new_colorder += other_cols
    my_df = my_df.dfcopy(new_colorder)
    my_df = weights_df.append_df(my_df)
    my_df = my_df.move_cols({AGGRANK:1})
    my_df._name_ = in_df._name_
    my_df.make_header_vertical()
    return my_df
  

  def make_combine_report(self)->df:
    combined_report = df.from_dict2(self.indication2dbids,'Name',self.__temp_id_col__)
    for (group,rank),report in self.indication_reports.items():
      if report.empty: continue
      no_weightdf = df.from_pd(report[report['Name'] != 'WEIGHT:'])
      no_weightdf.copy_format(report)
      combined_report = combined_report.merge_df(no_weightdf,on='Name',how='left',columns=[RANK,TOTAL_REFCOUNT])
      combined_report[RANK] = combined_report[RANK].fillna(0)
      new_rankcolname = f'{group} {RANK}'
      new_refcountcolname = f'RefCount to {group}'
      combined_report = combined_report.dfcopy(rename2={RANK:new_rankcolname,TOTAL_REFCOUNT:new_refcountcolname})
      combined_report.col2rank[new_rankcolname] = rank

    combined_report.col2rank = {k:v for k,v in combined_report.col2rank.items() if k in combined_report.columns}
    # combined_report['p-value'] = combined_report.calculate_pvalues(combined_report[AGGRANK],skip1strow=True)
    # combined_report['expopvalue'] = combined_report.calculate_expo_pvalues(combined_report[AGGRANK],skip1strow=True)
    combined_report._name_ = 'aggregate_report'
    combined_report.tab_format['tab_color'] = 'green'
    return combined_report


  def refs2combined_report(self,_2df:df,name2refs:dict,col_name:str):
    if name2refs:
      _2df[col_name] = _2df['Name'].map(name2refs)
      _2df[col_name] = _2df[col_name].fillna('')
      print(f'Hyperlinked references for {len(name2refs)} rows in aggregate report column "{col_name}"')
      report_column_order = ['Name',AGGRANK,col_name]
    else:
      report_column_order = ['Name',AGGRANK]

    [report_column_order.append(c) for c in _2df.columns.to_list() if c not in report_column_order and not c.startswith('RefCount to')]
    _2df.add_column_format(col_name,'align','center')
    _2df.set_hyperlink_color([col_name])
    return _2df.dfcopy(report_column_order)

  
  def reflinks(self,_df:df,search_concepts:list[str],add2query=[],expand=True)->dict[str,str]:
    if self.params["add_bibliography"]:
      print(f'\nWill find best references for {len(_df)} rows in {_df._name_} using query {search_concepts}')
      multithread = False if self.debug() else True
      return self.RefStats.reflinks(_df,'Name',search_concepts,add2query,multithread,expand)
    else:
      return dict()

