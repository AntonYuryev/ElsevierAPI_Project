import sys,os,time
from pathlib import Path as path
from collections import defaultdict

root_dir = path(__file__).resolve().parent.parent
sys.path.append(str(root_dir))
from ElsevierAPI_Project.ElsevierAPI.utils.utils import execution_time,plot_distribution, dir2flist,Tee
from ElsevierAPI_Project.ElsevierAPI.api.EmbioPSG_API.PSnx2Neo4j import neo4j_nx,OBJECT_TYPE,CONNECTIVITY
from ElsevierAPI_Project.ElsevierAPI.api.ResnetAPI.ResnetGraph import ResnetGraph,PSObject
from ElsevierAPI_Project.ElsevierAPI.api.ResnetAPI.NetworkxObjects import RESNET_NODE_TYPES, RESNET_REL_TYPES, PROTEIN_TYPES
from ElsevierAPI_Project.ElsevierAPI.api.ResnetAPI.SNEA import df


neo4j = neo4j_nx()
WORK_DIR = 'D:/Python/ENTELLECT_API_SCRIPTS/Cypher/CitationVsRefcount'


STAT_HEADER = [
  'Regulator', 'rType', 'rURN', 'rCitationCount', 'rConnectivity','rLocalRefCount', 'rLocalConnectivity',
  'Target', 'tType', 'tURN', 'tCitationCount', 'tConnectivity','tLocalRefCount', 'tLocalConnectivity',
  'RelType', 'RelationID', 'RefCount', 'DBrefEnrichment', 'LocalrefEnrichment'
]

def neighborhood_refcount(G:ResnetGraph):
  urn2refcount = dict()
  for n in G._get_nodes():
    neighborhood = G.neighborhood({n})
    neighborhood_rels = neighborhood._psrels()
    refcount = sum([rel.count_refs() for rel in neighborhood_rels])
    urn2refcount[n.urn()] = refcount
  return urn2refcount


def path4stats(regulatortype:str,reltype:str,targettype:str,extension='tsv'):
  nodes = sorted((regulatortype, targettype))
  out_fname = f"{nodes[0]}_{reltype}_{nodes[1]}.{extension}"
  out_path = os.path.join(WORK_DIR,out_fname)
  return out_path


def stats(urn2nodes:dict[str,PSObject]={},_4nodetypes=RESNET_NODE_TYPES,_4reltypes=RESNET_REL_TYPES):
  start = time.time()
  triples_counter = 0
  relation_counter = 0
  nodes = list(urn2nodes.values())
  number_of_nodes = len(nodes)
  if number_of_nodes == 0:
    print(f"No nodes of type {regulatortype} connected to {targettype} via {reltype}")

  for i in range(0, len(_4nodetypes)):
    regulatortype = _4nodetypes[i]
    for j in range(i, len(_4nodetypes)):
      targettype = _4nodetypes[j]
      for reltype in _4reltypes:  
        regulators = [n for n in nodes if n.objtype() == regulatortype]
        number_of_regulators = len(regulators)
        targets = [n for n in nodes if n.objtype() == targettype]
        number_of_targets = len(targets)
        print(f'Connecting {number_of_regulators} {regulatortype}s to {number_of_targets} {targettype}s via {reltype}')
  
        connectionsG = neo4j.connect_objs(regulators,targets,
                                      by_relProps={OBJECT_TYPE:[f'{reltype}'],'Source':['Medscan']},
                                      dir = False, # direction is determined by reltype and regulator-target types
                                      with_references=False,edge_duplication=False)      
        number_of_edges = connectionsG.number_of_edges()
        if number_of_edges> 0:
          urn2localrefcount = neighborhood_refcount(connectionsG)
          path2tsv = path4stats(regulatortype,reltype,targettype)
          with open(path2tsv,'w', encoding='utf-8') as out_f:
            out_f.write('\t'.join(STAT_HEADER) + '\n')
                                              
            for r,t,rel in connectionsG.iterate():
              refcount = rel.count_refs()
              reltype = rel.objtype()
              r_urn = r.urn()
              if r_urn not in urn2nodes: continue
              else: rr = urn2nodes[r_urn]
              t_urn = t.urn()
              if t_urn not in urn2nodes: continue
              else: tt = urn2nodes[t_urn]

              r_dbcit = rr.get_prop('CitationCount', if_missing_return=0)
              r_dbdegree = rr.get_prop(CONNECTIVITY, if_missing_return=0)
              r_local_cit = urn2localrefcount.get(r_urn,0)
              r_localdegree = connectionsG.degree(r.uid())

              t_dbcit = tt.get_prop('CitationCount', if_missing_return=0)
              t_dbdegree = tt.get_prop(CONNECTIVITY, if_missing_return=0)
              t_local_cit = urn2localrefcount.get(t_urn,0)
              t_localdegree = connectionsG.degree(t.uid())

              db_refEnrichment = 2 * refcount / (r_dbcit/r_dbdegree + t_dbcit/t_dbdegree)
              local_refEnrichment = 2 * refcount / (r_local_cit/r_localdegree + t_local_cit/t_localdegree)
              relationid = rel.get_prop('RelationID')

              row = [r.name(), r.objtype(), r_urn, r_dbcit, r_dbdegree, r_local_cit, r_localdegree,
                     t.name(), t.objtype(), t_urn, t_dbcit, t_dbdegree, t_local_cit, t_localdegree,
                     reltype, relationid, refcount, round(db_refEnrichment, 5), round(local_refEnrichment, 5)]

              out_f.write('\t'.join(map(str, row)) + '\n')
            triples_counter += 1
            relation_counter += number_of_edges
            print(f"Found/Processed {number_of_edges} relations in {execution_time(start)}")
  
  print(f"Analyzed entire database in {execution_time(start)}")
  print(f"Total number of triples analyzed: {triples_counter}")
  print(f"Total number of relations with RefEnrichment calculated: {relation_counter}")


def hist4df(stats_df:df,out_dir=WORK_DIR,_2subdir='Distributions'):
  '''
  Creates 'Distributions' subdirectory in out_dir and plots distributions of DBrefEnrichment and LocalrefEnrichment for the given stats_df if it contains more than 1000 relations.
  The distributions are winsorized at 1.0 to handle outliers and plotted with 100 bins, showing percentiles at 1,2,3,4,5,10 and a reference line at 1.0. The plot is saved in the 'Distributions' subdirectory with the name of the stats_df.
  '''
  size_limit = 1000
  # Create Distributions subdirectory in out_dir
  distributions_dir = os.path.join(out_dir, _2subdir)
  os.makedirs(distributions_dir, exist_ok=True)
  if len(stats_df) > size_limit:
      db_winsorized = [x if x <= 1.0 else 1.0 for x in stats_df['DBrefEnrichment'].tolist()]
      local_winsorized = [x if x <= 1.0 else 1.0 for x in stats_df['LocalrefEnrichment'].tolist()]
      distributions = [{'DBnorm': db_winsorized},
                       {'LocalNorm' : local_winsorized}]
      kwargs = {'number_of_bins': 100,
                'outdir': distributions_dir,
                'percentiles':[1,2,3,4,5,10],
                'percentile4score': [1.0],
                'legend_loc':'upper center',
                'title':stats_df._name_
                }
      plot_distribution(distributions,**kwargs)
      print(f"Plotted distributions for {stats_df._name_} with {len(stats_df)} relations")
      return True
  else:
    print(f"Skipped plotting for {stats_df._name_} with only {len(stats_df)} relations (<= {size_limit})")
  return False


def hist4dir(stat_dir=WORK_DIR,file_ext='tsv',join_plot_name=''):
  stat_files = dir2flist(stat_dir,file_ext=file_ext,include_subdirs=False)
  if join_plot_name:
      join_df = df(name = join_plot_name)
  
  counter = 0
  for stat_file in stat_files:
    basename = os.path.basename(stat_file).split('.')[0]
    stat_df = df.read(stat_file,header=0,encoding='utf-8', encoding_errors='replace')
    if join_plot_name:
      join_df = join_df.append_df(stat_df)
    else:
      stat_df._name_ = basename
      if hist4df(stat_df):
        counter +=1
        
  if join_plot_name:
    hist4df(join_df)
    print(f"Plotted distribution combined from {join_plot_name} for {join_plot_name} with {len(join_df)} relations")
    counter +=1

  print(f"Plotted {counter} distributions with relations out of {len(stat_files)} triple stats")
  return



def plot_group_name(stat_file:str):
  basename = os.path.basename(stat_file).split('.')[0]
  RType, RelType, TType = basename.split('_')
  if RType in PROTEIN_TYPES:
    RType = 'Protein'
  if TType in PROTEIN_TYPES:
    TType = 'Protein'
  nodes = sorted((RType, TType))
  return (nodes[0], RelType, nodes[1])


def group_stats_by_triple(stat_dir=WORK_DIR,file_ext='tsv'):
  '''
    Combines stats for protein type nodes: Protein,FunctionalClass,Complex
  '''
  stat_files = dir2flist(stat_dir,file_ext=file_ext,include_subdirs=False)
  triple2stats = defaultdict(list)
  for stat_file in stat_files:
    group_name = plot_group_name(stat_file)
    triple2stats[group_name].append(stat_file)
  return dict(triple2stats)


def make_plots(input_dir = WORK_DIR):
  with Tee(os.path.join(WORK_DIR,'Plotting.log')):
    triple2stats = group_stats_by_triple(input_dir)
    for triple, stat_files in triple2stats.items():
      plot_name = '_'.join(triple)
      plot_df = df.read(stat_files[0],header=0,encoding='utf-8', encoding_errors='replace')
      plot_df._name_ = plot_name
      if len(stat_files) > 1:
        for i in range(1, len(stat_files)):
          stat_df = df.read(stat_files[i],header=0,encoding='utf-8', encoding_errors='replace')
          plot_df = plot_df.append_df(stat_df)

      if hist4df(plot_df):
        print(f"Plotted distribution combined from {plot_name} from {len(stat_files)} files with {len(plot_df)} relations")
  

def load_stat_file(stat_file:str):
  basename = os.path.basename(stat_file).split('.')[0]
  stat_df = df.read(stat_file,header=0,encoding='utf-8', encoding_errors='replace')

  my_df = stat_df[['rURN','rType','tURN','tType','RelType','RelationID', 'LocalrefEnrichment']].copy()
  _, distr_conf_col = my_df.calulate_confidence('LocalrefEnrichment')
  my_df = my_df.dfcopy(rename2={distr_conf_col:'Confidence (%)'})
  
  my_df.loc[my_df['LocalrefEnrichment'] > 0.001, 'LocalrefEnrichment'] = my_df.loc[
    my_df['LocalrefEnrichment'] > 0.001, 'LocalrefEnrichment'].round(3)
  print(f"Submitting {len(my_df)} rows with refEnrichment score to update {basename} relations")
  
  RType, RelType, TType = basename.split('_')
  mydf1 = my_df[(my_df['rType'] == RType) & (my_df['tType'] == TType)]
  print(f'First batch for {basename} with {len(mydf1)} rows')
  mydf2 = my_df[(my_df['tType'] == RType) & (my_df['rType'] == TType)]
  if not mydf2.empty:
    mydf2 = mydf2.rename(columns={'rURN':'tURN','rType':'tType','tURN':'rURN','tType':'rType'})
    print(f'Second batch for {basename} with {len(mydf2)} rows')
    
  updated_count = 0
  for _df in [mydf1, mydf2]:
    if _df.empty: continue

    batch4future = [
      {'rURN': str(r_urn), 'rType': str(r_type), 'tURN': str(t_urn), 'tType': str(t_type), 
      'reltype': str(rel_type), 'RelationID': str(rel_id), 
      'LocalrefEnrichment': float(ref_enrichment), 'Confidence (%)': float(conf)}

      for r_urn, r_type, t_urn, t_type, rel_type, rel_id, ref_enrichment, conf in 
      zip(_df['rURN'],_df['rType'], _df['tURN'], _df['tType'],
          _df['RelType'],_df['RelationID'], _df['LocalrefEnrichment'],_df['Confidence (%)'])
    ]
    
    cypher = f"""
              UNWIND $batch AS row
              MATCH (a:{RType} {{URN: row.rURN}})-[r:{RelType}]-(b:{TType} {{URN: row.tURN}})
              WHERE r.RelationID = row.RelationID OR row.RelationID IN r.RelationID
              SET r.refEnrichment = toFloat(row.LocalrefEnrichment)
              SET r.`Confidence (%)` = toFloat(row.`Confidence (%)`)
              SET r.refPVal = NULL
              RETURN count(r) AS updated_count
            """
    start = time.time()
    # alternative: for result in neo4j._update_(cypher, batch4future, request_name=f'{basename}',multithread=multithread):
    df_update_count = 0
    for result in neo4j._unwind_(cypher, {'batch': batch4future, 'request_name': f'{basename}'}):
      df_update_count += result[0][0][0]

    if df_update_count == 0:
      print(f"No relations updated for {basename} in this batch. Check if node types, relation types, and RelationID values in the stat file match those in the database.")
    else:
      updated_count += df_update_count
      print(f"Batch with {len(batch4future)} rows updated {df_update_count} relations for {basename} in {execution_time(start)}")

  if updated_count == 0:
    print(f"No relations updated for {basename} triple.\nCheck if RelationID values in the stat file match those in the database.")
  else:
    print(f"Updated total {updated_count} relations for {basename} triple in {execution_time(start)}")  
  return updated_count


def _loadRefEnrichment_(input_dir=WORK_DIR):
  stat_files = dir2flist(input_dir,file_ext='tsv',include_subdirs=True)
  start = time.time()
  total_count = 0
  with Tee(os.path.join(input_dir,'RefEnrichmentAnnotation.log')):
    for stat_file in stat_files:
      updated_count = load_stat_file(stat_file)
      total_count += updated_count
    print(f"Scrip finished and annotated {total_count} relations with RefEnrichment and COnfidence values from {len(stat_files)} stat files in {execution_time(start)}")
  return


def RetreiveStats(_4nodetypes=RESNET_NODE_TYPES,_4reltypes=RESNET_REL_TYPES):
  with Tee(os.path.join(WORK_DIR,'RefEnrichment.log')):
    urn2nodes = neo4j.node_citation_count()
    stats(urn2nodes,_4nodetypes,_4reltypes)
  return


if __name__ == "__main__":
  RetreiveStats() # retrieves relation RefCount and node neighborhood RefCount from Neo4j and calculates refEnrichment score
  make_plots() # optional make histograms of RefEnrichment score distributions for each triple type NodeType1-RelType-NodeType2
  _loadRefEnrichment_() # annotates relations in Neo4j with "refEnrichment" property calculated by RetreiveStats()
