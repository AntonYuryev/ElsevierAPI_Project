import atexit
import csv
import neo4j, time
from ..ResnetAPI.ResnetGraph import ResnetGraph, PSObject, PSRelation, RELATIONID
from ...utils.utils import execution_time, load_api_config, ThreadPoolExecutor, unpack,as_completed,np
from ..ResnetAPI.NetworkxObjects import OBJECT_TYPE,CHILDS,CONNECTIVITY,DBID, NONDIRECTIONAL
from neo4j import GraphDatabase, NotificationSeverity
from neo4j import ManagedTransaction as tx
from .cypher import Cypher, ENTPROP_NEO4J
from .postgres import PostgreSQL,pd

NODECOLUMN2ATTR = {'id':DBID,'urn':'URN'}
nondirectional_reltype = list(map(str.upper,NONDIRECTIONAL))

class neo4j_nx(GraphDatabase):
  def __init__(self, APIconfig:dict={},**kwargs):
    '''
    required kwargs: uriNeo4j, userNeo4j, password, database
    '''
    if not APIconfig:
      APIconfig = load_api_config()

    self.NODE_REGISTRY = set()
    self.uri = APIconfig['neo4juri']
    self.database = APIconfig['neo4jdb']
    self.user =  APIconfig['neo4juser']
    self.password = APIconfig['neo4jpswd']
    verbosity = kwargs.get('notifications_min_severity',NotificationSeverity.WARNING)
    self._closed = False
    self.__driver__ = super().driver(self.uri, 
                                     auth=(self.user, self.password),
                                     notifications_min_severity=verbosity
                                     )
    self.postgres = PostgreSQL(APIconfig)
    atexit.register(self.close)


  def __enter__(self):
    return self


  def __exit__(self, exc_type, exc, tb):
    self.close()
    return False
  

  def session(self,**kwargs):
    return self.__driver__.session(database=self.database, **kwargs)
  

  def run_cypher(self,cypher:str,parameters:dict={},request_name=''):
    '''
    output:
      (result,request_name) where result is the list of records returned by Neo4j for the query
    '''
    with self.session() as session:
      result = list(session.run(cypher,parameters))
      if request_name:
        print(f'Cypher query "{request_name}" returned {len(result)} records')
      return result,request_name
 

  def _unwind_(self,cypher:str,parameters:dict={}):
    '''
      Cypher query must contain UNWIND $batch AS row and use row.{item} to refer to items in the list\n
      request_name can be in parameters for messaging purposes, but is not used in the cypher query itself
      output:
        yields tuples of (result,request_name) for each batch processed, where result is the list of records returned by Neo4j for the batch
    '''
    batch_size = 10000
    request_name = parameters.pop('request_name','')
    print(f'Multithreading cypher "{request_name}" for {len(parameters["batch"])} input list. Batch size: {batch_size}')
    with ThreadPoolExecutor() as ex:
      futures = []
      for i in range(0, len(parameters['batch']), batch_size):
        batch = parameters['batch'][i:i+batch_size]
        params = parameters.copy()
        params['batch'] = batch
        futures.append(ex.submit(self.run_cypher,cypher,params))

      for future in as_completed(futures):
        yield future.result()


  def DBrelTypes(self):
    cypher = 'CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType'
    with self.session() as session:
      result = list(session.run(cypher))
      return sorted([record['relationshipType'] for record in result])
    

  def DBnodeLabels(self):
    cypher = 'CALL db.labels() YIELD label RETURN label'
    with self.session() as session:
      result = list(session.run(cypher))
      return sorted([record['label'] for record in result])


  def close(self):
    # Close once; avoid late-shutdown exceptions from driver finalization.
    if self._closed:
      return
    self._closed = True
    try:
      self.__driver__.close()
    except Exception:
      # Interpreter shutdown can tear down logging before driver finalizers run.
      pass


  @staticmethod
  def __record2psobj(node_record:neo4j.Record)->PSObject:
    psobj = PSObject({NODECOLUMN2ATTR.get(k,k):[v] for k,v in node_record._properties.items() if v not in ['_','']})
    psobj[OBJECT_TYPE] =  list(node_record.labels)
    return psobj


  def _triple2psrel(self, triple:neo4j.Record,add_reldbid=False)->PSRelation:
      '''
        triple: regulator-relation-target
      '''
      assert(len(triple) == 3), 'Only triples Regulator-relationship-target are considered'
      regulator = PSObject({k:[v] for k,v in triple[0].items() if v not in ['_','']})
      regulator[OBJECT_TYPE] =  list(triple[0].labels)
      regulator['URN'] =  regulator.pop('urn',regulator['URN'])
      target = PSObject({k:[v] for k,v in triple[2].items() if v not in ['_','']})
      target[OBJECT_TYPE] =  list(triple[2].labels)
      target['URN'] =  target.pop('urn',target['URN'])
      reldict = dict()
      for k,v in triple[1].items():
        if isinstance(v,list):
          v_clean = [x for x in v if x != '_'] # to support merged relations
          if v_clean:
            reldict[k] = v_clean
        elif v not in ['_','']:
          reldict[k] = [v]
      reldict[OBJECT_TYPE] = [triple[1].type]
      if add_reldbid:
        reldict[DBID] = [triple[1].element_id]
      is_directional = reldict[OBJECT_TYPE][0] not in nondirectional_reltype
      rel_obj = PSRelation.make_rel(regulator,target,reldict,[],is_directional)
      return rel_obj
  

  def triple2dics(self,triple:neo4j.Record)->tuple[dict,dict,dict]:
    '''
      support graph visualisation in yFiles.
      output: (regulator-relation-target)
    '''
    reg_record = triple[0]
    reg_props = {k:[v] for k,v in reg_record.items() if v not in ['_','']}
    reg_urn = reg_props['URN'][0]
    regulator = { "id": reg_urn,
                  "properties": reg_props,
                  "labels": list(reg_record.labels)
                }
    
    target_record = triple[2]
    target_props = {k:[v] for k,v in target_record.items() if v not in ['_','']}
    tar_urn = target_props['URN'][0]
    target = { "id": tar_urn,
                "properties": target_props,
                "labels": list(target_record.labels)
              }
    
    rel_record = triple[1]
    rel_props = {k:[v] for k,v in rel_record.items() if v not in ['_','']}
    rel = {
        "id": rel_record.element_id,
        "start": reg_urn,
        "end": tar_urn,
        "properties": rel_props,
        "label": rel_record.type
    }
    return regulator, rel, target


  def fetch_graph(self,cypher:str,parameters:dict={},request_name='')->ResnetGraph:
    '''
    input:
      cypher must RETURN (regulator)-[relation]->(target) 
      parameters["with_references"] is optional and is True by default
      parameters["edge_duplication"] is optional and is True by default
    '''
    edge_duplication = parameters.pop('edge_duplication',True)
    with self.session() as session:
      psrels = []
      try:
        start = time.time()
        neo4j_result = list(session.run(cypher,parameters))
        print(f'Cypher query "{request_name}" fetched {len(neo4j_result)} triples in {execution_time(start)}')
        psrels = [self._triple2psrel(record) for record in neo4j_result]
        if psrels:
          if parameters.pop('with_references',True):
            # must use set() here: relations with the same RELATIONID can be duplicated
            relation_ids = unpack([n[RELATIONID] for n in psrels])
            self.postgres.submit_refs(list(relation_ids))

          to_return = ResnetGraph.from_rels(psrels,edge_duplication)
          if request_name:
            print(f"loaded network with {len(to_return)} nodes and {to_return.number_of_edges()} edges")
          return to_return
        else:
          if request_name:
            print(f'Cypher query "{request_name}" did not fetch any data')
          return ResnetGraph()
      except Exception as e:
        print(f"Error during network retrival: {e}")
        raise

  
  def _connect_(self,regulator_objtypes:list[str], regulator_props:list[str],regulator_propName:str,
                target_objtypes:list[str], target_props:list[str],target_propName:str,
                by_relProps:dict[str,list[str|int|float]]={}, dir=False, request_name='Connect nodes',
                with_references=True,edge_duplication=True):
    '''
    input:
      if not dir connects regulators, targets in BOTH directions, otherwise connects regulator->target
      by_relProps = {reltype:[propValue1,propValue2,...]},
    '''
    cypher, params = Cypher.connect(regulator_objtypes, regulator_props,regulator_propName,
                                      target_objtypes, target_props,target_propName,by_relProps,dir)
    params['with_references'] = with_references
    params['edge_duplication'] = edge_duplication
    return self.fetch_graph(cypher, params, request_name=request_name)




  def connect_objs(self,regulators:set[PSObject],targets:set[PSObject],
                   by_relProps:dict[str,list[str|int|float]]={}, dir=False,
                   with_references=True,edge_duplication=True)->ResnetGraph:
    request_name = f'Connect {len(regulators)} regulators and {len(targets)} targets'
    cypher,params = Cypher.connect_objs(regulators,targets,by_relProps,dir)
    params['with_references'] = with_references
    params['edge_duplication'] = edge_duplication
    return self.fetch_graph(cypher, params, request_name=request_name)
  
  
  def get_ppi(self,interactors:set[PSObject], minref=2,with_references=True)->ResnetGraph:
    cypher, params = Cypher.ppi(list(interactors), minref=minref)
    params.update({'with_references':with_references})
    return self.fetch_graph(cypher, params)
  

  def _neighborhood_(self,seedProps:list[str],propType='Name',_2targettypes:list[str]=[],
                    by_relProps:dict[str,list[str|int|float]]={},dir='',with_references=True)->ResnetGraph:
    '''
    input:
      by_relProps = {reltype:[propValue1,propValue2,...]},
      use OBJECT_TYPE string to specify filtering by relation type
      dir: '', 'upstream', 'downstream'
      with_references: whether to fetch references for the relations
    '''
    cypher,param = Cypher.expand(seedProps,propType,_2targettypes,by_relProps,dir)        
    param['with_references'] = with_references
    return self.fetch_graph(cypher,param)
  

  def add_connectivity(self,to_nodes:list[PSObject]):
     cypher,params = Cypher.node_connectivity(to_nodes)
     with self.session() as session:
      result = list(session.run(cypher,params))
      urn2connectivity = dict()
      for record in result:
        urn = record['urn']
        connectivity = record[CONNECTIVITY]
        urn2connectivity[urn] = connectivity

      for n in to_nodes:
        n[CONNECTIVITY] = [urn2connectivity[n.urn()]]
      return to_nodes


  def retrieve_childs(self,parent:PSObject,max_childs:int=None,with_connectivity = False)->list[PSObject]:
    '''
    output:
      if max_childs is None or zero loads all children,
      otherwise loads children only for parents with number of children less than max_childs
      parents with number of children exceeding max_childs are annotated with 
      parent[CHILDS] = [PSObject()]*count
    '''
    if CHILDS in parent:
      return parent
    children = []
    with self.session() as session:
      cypher,params = Cypher.get_childs(parent, max_childs)
      record = session.run(cypher,params).single()
      if record:
        count = record['count']
        children_records = record['childs']
        if count > 0:
          if not max_childs or count <= max_childs:
            children = [self.__record2psobj(record) for record in children_records]
            if with_connectivity:
              children = self.add_connectivity(children)
          else:
            children = [PSObject()]*count
    parent[CHILDS] = children
    return parent
  

  def _load_children_(self,parents:list[PSObject],max_childs=None)->list[PSObject]:
    '''
    output:
      list of parent annotated with CHILDS attributed
      if max_childs is None or zero loads all children,
      otherwise loads children only for parents with number of children less than max_childs
      parents with number of children exceeding max_childs are annotated with 
      parent[CHILDS] = [PSObject()]*count
    '''
    def process_single(parent:PSObject):
      return self.retrieve_childs(parent,max_childs)
    
    results = []
    with ThreadPoolExecutor(max_workers=20) as executor:
      futures = executor.map(process_single,parents)
      for res in futures:
        results.append(res)
    return results
    

  def count_nodes(self, objtype:str,propName='',propVals=[])->int:
    cypher = f'MATCH (n:{objtype})\n'
    if propName:
      cypher += f' WHERE n.{propName} IN $propVals\n'
      params = {'propVals':propVals}
    else:
      params = {}
    cypher += 'RETURN COUNT(n) AS count'

    with self.session() as session:
      result = session.run(cypher,params)
      record = result.single()
      if record:
        return record['count']
      else:
        return 0


  def get_nodes(self,objtype:str,propName:str,propVals:list[str],
                with_childs=False,with_connectivity=False)->list[PSObject]:
    """
    input:
      objtype (label) can be empty, but the query will be slower
    """
    cypher,params = Cypher.get_nodes(objtype,propName,propVals,with_connectivity)
    with self.session() as session:
      result = list(session.run(cypher,params))
      if with_connectivity:
        nodes = []
        for record in result:
          node = self.__record2psobj(record[0])
          node.update_with_value(CONNECTIVITY,record[1])
          nodes.append(node)
      else:
        nodes = [self.__record2psobj(record[0]) for record in result]

      if with_childs:
        childs = []
        for node in nodes:
          self.retrieve_childs(node,with_connectivity=with_connectivity)
          childs += node[CHILDS]
        nodes += childs
      return set(nodes)
    

  def select_drugs(self,only_from:list[PSObject]=[]):
    cypher,params = Cypher.select_drugs(only_from)
    with self.session() as session:
      result = list(session.run(cypher,params))
      return [self.__record2psobj(record[0]) for record in result]
    

  def mine_sentences(self, with_keywords:list[str])->ResnetGraph:
    rel2refs = self.postgres.snippets_with(with_keywords)
    rel_ids = list(map(str,rel2refs.keys()))
    cypher = 'MATCH (u)-[r]->(t) WHERE r.RelationID IN $rel_ids RETURN u,r,t'
    params = {'rel_ids':rel_ids}
    my_graph = self.fetch_graph(cypher,params,request_name='Sentence mining')
    [rel.refs(relid2refs=rel2refs) for _, _, rel in my_graph.edges.data('relation')]
    return my_graph
  

  
  def __quintuple2psrel(self, quintuple:neo4j.Record)->PSRelation:
    '''
    used by fetch_common_neighbors(). Input:
      quintuple: (n1)-[r1]-(common)-[r2]-(n2)
    '''
    assert(len(quintuple) == 5), 'Only quintuples (n1)-[r1]-(common)-[r2]-(n2) are considered'
    n1 = quintuple['n1']
    node1 = PSObject({k:[v] for k,v in n1._properties.items() if v not in ['_','']})
    node1[OBJECT_TYPE] =  list(n1.labels)
    node1['URN'] =  node1.pop('urn',node1['URN'])

    n2 = quintuple['n2']
    node2 = PSObject({k:[v] for k,v in n2._properties.items() if v not in ['_','']})
    node2[OBJECT_TYPE] =  list(n2.labels)
    node2['URN'] =  node2.pop('urn',node2['URN'])

    common = quintuple['common']
    common_node = PSObject({k:[v] for k,v in common._properties.items() if v not in ['_','']})
    common_node[OBJECT_TYPE] =  list(common.labels)
    common_node['URN'] =  common_node.pop('urn',common_node['URN'])

    r1 = quintuple['r1']
    reldict = {k:[v] for k,v in r1._properties.items() if v not in ['_','']}
    reldict[OBJECT_TYPE] = [r1.type]
    is_directional = reldict[OBJECT_TYPE][0] not in nondirectional_reltype

    if n1 == r1.start_node:
      r1obj = PSRelation.make_rel(node1,common_node,reldict,[],is_directional)
    else:
      r1obj = PSRelation.make_rel(common_node,node1,reldict,[],is_directional)

    r2 = quintuple['r2']
    reldict = {k:[v] for k,v in r2._properties.items() if v not in ['_','']}
    reldict[OBJECT_TYPE] = [r2.type]
    is_directional = reldict[OBJECT_TYPE][0] not in nondirectional_reltype
    if n2 == r2.start_node:
      r2obj = PSRelation.make_rel(node2,common_node,reldict,[],is_directional)  
    else:
      r2obj = PSRelation.make_rel(common_node,node2,reldict,[],is_directional)
      
    return [r1obj,r2obj]


  def fetch_common_neighbors(self,cypher:str,parameters=dict(),request_name='')->ResnetGraph:
    '''
    input:
      cypher must MATCH (n1)-[r1]-(common)-[r2]-(n2) WHERE .....
      parameters["with_references"] is optional and is True by default, if True, references for all relations between common neighbor and nodes1 and nodes2 are fetched from Postgres and added to relation objects as refs attribute
    '''
    if request_name:
      print(f'Fetching common neighbors with query "{request_name}"')
    else:
      print(f'Fetching common neighbors with between {len(parameters['urnList1'])} and {len(parameters['urnList2'])} nodes')

    edge_duplication = parameters.pop('edge_duplication',True)
    with self.session() as session:
      psrels = []
      try:
        neo4j_result = list(session.run(cypher,parameters))
        psrels = set()
        [psrels.update(self.__quintuple2psrel(record)) for record in neo4j_result]
        if psrels:
          if parameters.pop('with_references',True):
            relation_ids = unpack([n[RELATIONID] for n in psrels])
            self.postgres.submit_refs(relation_ids)

          to_return = ResnetGraph.from_rels(psrels,edge_duplication)
          if request_name:
            print(f'Cypher query "{request_name}" found data:')
          print(f"Loaded network with {len(to_return)} nodes and {to_return.number_of_edges()} edges")
          return to_return
        else:
          if request_name:
            print(f'Cypher query "{request_name}" did not fetch any data')
          return ResnetGraph()
      except Exception as e:
        print(f"Error during network retrival: {e}")
        raise


  def export_relation_properties(self,fout:str, relProps:dict[str,bool],_4reltypes=[]):
    '''
    input:
      relProps: {relation_property_name: cannot_have_null_values}, if cannot_have_null_values is True, rows with null values for this property will be skipped in the output
      _4reltypes: if specified, export only for these relation types, otherwise export all relation types in the database
    '''
    prop_names = list(relProps.keys())
    reltypes = _4reltypes if _4reltypes else self.DBrelTypes()
    reltypes = '|'.join(reltypes)
    match = f"MATCH ()-[r:{reltypes}]->()"
    start = time.time()
    
    where_clauses = []
    for prop in prop_names:
      if relProps[prop]:
         quoted_name = Cypher.quoted_prop(prop)
         where_clauses.append(f'r.{quoted_name} IS NOT NULL AND r.{quoted_name} <> ["", "_"]')
    if where_clauses:
      match += ' WHERE ' + ' AND '.join(where_clauses)
    
    cypher2count = match + ' RETURN COUNT(r) AS count'
    clean_props = [prop.translate(str.maketrans(' ()%', '____')) for prop in prop_names]
    #clean_props = [c.strip('_') for c in clean_props]
    cypher4export = match + ' RETURN ' + ', '.join([f'r.{Cypher.quoted_prop(prop)} AS {clean_prop}' 
                                                for prop, clean_prop in zip(prop_names, clean_props)])

    
    count_rels = self.run_cypher(cypher2count,request_name='Count relations for export')[0][0]['count']
    print(f'Exporting {count_rels} relations with properties {list(relProps.keys())}')
    
    counter = 0
    with self.session(fetch_size=10000) as session:
      result = session.run(cypher4export)
      with open(fout, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(prop_names) # header
        for record in result:
          row_values = [record[prop] for prop in clean_props]      
          writer.writerow(row_values)
          counter += 1
          percent = (counter / count_rels) * 100
          if percent % 10 == 0:
            print(f'Exported {counter} ({percent:.2f}%) of {count_rels} relations... in {execution_time(start)}')

    print('Export of relation properties finished in', execution_time(start))
         
#################################################################################################


    
################ LOAD INTO NEO4J ####################### LOAD INTO NEO4J ########################
  def update_rels(self, with_prop:str, from_rels:list[PSRelation]):
    reltypes = '|'.join(set(rel.objtype() for rel in from_rels))
    regulators = set()
    targets = set()
    for rel in from_rels:
      regulators.update(rel.regulators())
      targets.update(rel.targets())
    regulator_nodetypes = '|'.join(set(n.objtype() for n in regulators))
    target_nodetypes = '|'.join(set(n.objtype() for n in targets))
    return self._update_rels_(with_prop, from_rels, regulator_nodetypes, reltypes, target_nodetypes)


  def _update_rels_(self, with_prop:str, from_rels:list[PSRelation],regulatorType:str,relType:str,targetType:str)->int:
    '''
    from_rels must be list of PSRelation with the same regulatorType, relType and targetType
    output:
      (number of updated relations, number of input relations, match used to select relations in Neo4j)
    '''
    dir = '-' if relType in NONDIRECTIONAL  else '->'
    match = f'(a:{regulatorType} {{URN:row.rURN}})-[r:{relType}]{dir}(b:{targetType} {{URN:row.tURN}})'
    print(f'updating {len(from_rels)} relations matched by {match}')

    cypher = f"""UNWIND $batch AS row 
          MATCH {match}
          WHERE r.Effect = row.effect OR (r.Effect IS NULL AND row.effect = '')
          AND r.Mechanism = row.mechanism OR (r.Mechanism IS NULL AND row.mechanism = '')
          SET r.`{with_prop}` = row.propValue
          RETURN COUNT(r) AS updatedCount
          """

    batch = []
    for rel in from_rels:
      if with_prop in rel:
        prop_values = rel.get_props(with_prop)
        prop_value = rel[with_prop] if len(prop_values) > 1 else rel[with_prop][0]
        regulators = rel.regulators()
        targets = rel.targets()
        rel_effect = rel.effect(unknown='_')
        rel_mechanism = rel.mechanism(if_missing_return='_')
        for r in regulators:
          for t in targets:
            batch.append({'rURN': r.urn(),
                          'tURN': t.urn(),
                          'effect': rel_effect,
                          'mechanism': rel_mechanism,
                          'propValue': prop_value})
    
    total_updated = 0
    #start = time.time()
    for result,request_name in self._unwind_(cypher,{'batch': batch, 'request_name':f'Update relation with {with_prop}'}):
      batch_updated = result[0]['updatedCount'] if result else 0
      total_updated += batch_updated
    
    #match = f'(a:{regulatorType})-[r:{relType}]{dir}(b:{targetType})'
    #print(f'update finished in {execution_time(start)}')
    return total_updated, len(from_rels), match


  def create_group(self,group_name:str,link_type:str,members:list[PSObject]):
    '''
    if link_type = "part_of" , creates Group with members
    if link_type = "is_a" creates ontology concept with label equal to label of the first member with members linked by "is_a"
    '''
    memberUrns = ResnetGraph.urns(members)
    if link_type == "part_of":
      cypher,params = Cypher.create_group(group_name,memberUrns)
    else:
      label = members[0].objtype()
      cypher,params = Cypher.create_ontology_group(group_name,label,memberUrns)
      
    with self.session() as session:
      result = session.run(cypher,params)
      record = result.single()
      if record:
        p_name = record["p"]["Name"]
        linked_count = len(record["LinkedUrns"])
        print(f"✅ Success! Merged '{p_name}' and linked {linked_count} new compounds.")
        print(f"Linked URNs: {record['LinkedUrns']}")
      else:
        print("⚠️ Query ran, but no group was created.")


  def add2group(self,group_name:str,link_type:str,nodeProps:dict[str,list[str|int|float]],with_childs=False):
    '''
    if link_type = "part_of" , adds members to Group
    if link_type = "is_a" adds members to ontology concept with label equal to label of the first member with members linked by "is_a"
    nodeProps = {propName:[propValue1,propValue2,...]}, use OBJECT_TYPE string to speed up node selection
    '''
    objtype = nodeProps.pop(OBJECT_TYPE,[])[0]
    members = set()
    for propName, propList in nodeProps.items():
      members.update(self.get_nodes(objtype,propName,propList,with_childs=with_childs))
    members = list(members)
    memberUrns = ResnetGraph.urns(members)

    if link_type == "part_of":
      cypher,params = Cypher.create_group(group_name,memberUrns)
    else:
      label = objtype if objtype else members[0].objtype()
      cypher,params = Cypher.create_ontology_group(group_name,label,memberUrns)
      
    with self.session() as session:
      result = session.run(cypher,params)
      record = result.single()
      if record:
        p_name = record["p"]["Name"]
        linked_urns = set(memberUrns).intersection(record["LinkedUrns"])
        print(f"✅ Success! Added '{len(linked_urns)}' to {p_name}.")
        print(f"Linked URNs: {linked_urns}")
      else:
        print("⚠️ Query ran, but no group was updated.")


  @staticmethod
  def __get_node_labels(node: PSObject):
      lbls = ','.join([k + ':\"' + v[0] + '\"' for k, v in node.items() if k in ENTPROP_NEO4J])
      return lbls


  @staticmethod
  def _find_and_return_node(tx:tx, node:PSObject):
      query = (
          'MATCH (n:{type}) WHERE n.URN = \"{urn}\"'
          'RETURN n.Name AS Name, n.URN as urn, labels(n) as ObjTypeName'
          # labels(n) returns list
      )
      query = query.format(type=node.objtype(), urn=node.urn())
      neo4j_result = tx.run(query)
      return {(record["Name"], record["urn"], record['ObjTypeName'][0]) for record in neo4j_result}
  
  """
  def __create_node(self, tx:tx, n: PSObject):
      node_found = self._find_and_return_node(tx, n)
      if len(node_found) > 0:
          return {(node[0], node[1], node[2][0]) for node in node_found}
      else:
          node_type = n['ObjTypeName'][0]
          query = ('CREATE (n:' + node_type + '{' + self.__get_node_labels(n) + '})'
                                                                                'RETURN n.Name as Name, n.URN as urn, labels(n) as ObjTypeName'
                    )  # labels(n) returns list
          neo4j_result = tx.run(query)
          try:
              return {(record["Name"], record["urn"], record['ObjTypeName'][0]) for record in neo4j_result}
          # Capture any errors along with the query and data for traceability
          except ServiceUnavailable as exception:
              logging.error(f"{query} raised an error:\n{exception}")
              raise


  def load_nodes_1by1(self, resnet:ResnetGraph):
      nodes = resnet.nodes(data=True)
      with self.session() as session:
          # Write transactions allow the driver to handle retries and transient errors
          for i, d in nodes:
              neo4j_result = session.execute_write(self.__create_node, d)
              for record in neo4j_result:
                  print(f'Neo4j got node: \"{record[0]}\" of type {record[2]} with URN={record[1]}')
  """
  
  def __create_nodes(self, tx:tx, nodes:list):
      create_node_count = 0
      for n in nodes:
          node_found = self._find_and_return_node(tx, n)
          if len(node_found) > 0:
              continue
          else:
              node_type = n['ObjTypeName'][0]
              query = ('CREATE (n:' + node_type + '{' + self.__get_node_labels(n) + '})'
                          'RETURN n.Name as Name, n.URN as urn, labels(n) as ObjTypeName'
                      )  # labels(n) returns list
              tx.run(query)
              create_node_count += 1
      return create_node_count

  
  def load_node_list(self, nodes:list):
      with self.driver.session() as session:
          # Write transactions allow the driver to handle retries and transient errors
          create_node_count = session.execute_write(self.__create_nodes, nodes)
      return create_node_count


  def load_nodes(self,resnet:ResnetGraph,max_wokers=5):
      start = time.time()
      nodes = resnet._get_nodes()
      with ThreadPoolExecutor(max_workers=max_wokers, thread_name_prefix='loading nodes') as executor:
          chunk_len = int(len(nodes)/max_wokers)
          chunks = [nodes[x:x+chunk_len] for x in range(0, len(nodes), chunk_len)]
          futures = list()
          for chunk in chunks:
              futures.append(executor.submit(self.load_node_list,chunk))
          
          create_node_count = 0
          for f in futures:
              create_node_count += f.result()

      print('%d nodes were loaded in %s' % (create_node_count,execution_time(start)))
      print('%d nodes were found in database' % (len(nodes) - int(create_node_count)))

  """
  @staticmethod
  def __get_rel_labels(rel:PSRelation):
      labls = ','.join([k.replace(':', ' ') + ':\"' + v[0] + '\"' for k, v in rel.items() if k in RELPROP_NEO4J])
      labls = labls + f',{REFCOUNT}:' + str(rel.count_refs()) 
      labls = labls + f',{SNIPPET_COUNT}:' + str(rel.count_refs(count_abstracts=True))
      return labls


  def __create_rel_query(self, node1:PSObject, node2:PSObject, relation:PSRelation):
    relationType = relation.objtype()
    node1urn = node1.urn()
    node2urn = node2.urn()
    node1type = node1.objtype()
    node2type = node2.objtype()

    return ('MATCH'
            '(a:' + node1type + '),'
            '(b:' + node2type + ')'
            'WHERE a.URN = \"' + node1urn + '\" AND b.URN = \"' + node2urn + '\"'
            'CREATE (a)-[r:' + relationType + ' {' + self.__get_rel_labels(relation) + '}]->(b)'
            'RETURN a.Name as rName, b.Name as tName, type(r) as rel_type'
            )
  

  def __create_relations(self, rels:list[PSRelation]):
    '''
    input:
      rel_tuples = [(node1_id, node2_id, PSRelation)]
    '''
    create_rel_count = 0
    with self.session() as session:
      for rel in rels:
        query, params = self.__create_relation(rel)
        session.run(query, params)
        create_rel_count += 1
    return create_rel_count
  
  def load_relation_list(self, edge_tuples:list,resnet:ResnetGraph):
      '''
      input:
        edge_tuples = [(node1_id, node2_id, PSRelation)]
      '''
      with self.session() as session:
        created_relation_count = session.execute_write(self.__create_relations,edge_tuples,resnet)
      return int(created_relation_count)
          

  def load_relations_multithread(self,resnet:ResnetGraph, max_workers=100):
      start = time.time()
      max_edge_in_split = int(resnet.number_of_edges()/max_workers)
      multithreads = resnet.split(max_edge_in_split)

      create_relation_count = 0
      for multithread in multithreads:
          with ThreadPoolExecutor(max_workers=len(multithread), thread_name_prefix='loading relations') as executor:
              futures = list()
              for thread in multithread:
                  tread_edges = thread.edges()
                  futures.append(executor.submit(self.load_relation_list,tread_edges,resnet))
              
              for f in futures:
                  create_relation_count += f.result()

      print('%d relation were loaded in %s' % (create_relation_count,execution_time(start)))

  """
  
  def __create_relation(self, relation:PSRelation):
    cypher, params = Cypher.create_rels(relation)
    with self.session() as session:
      try:
        session.run(cypher, params)
        return len(params['pairs'])
      except Exception as e:
        print(f"Error during network retrival: {e}")
        raise


  def import_relations(self, rels:list[PSRelation], max_workers=None):
    start = time.time()
    relcount = 0
    with self.session() as session:
      for cypher, params in Cypher.create_rels2(rels):
        try:
          relcount += session.run(cypher, params)
        except Exception as e:
          print(f"Error during network retrival: {e}")
          raise

      print(f'{relcount} relations were loaded in {execution_time(start)}')
    return relcount


  def load_relations_1by1(self, resnet:ResnetGraph):
    with self.session() as session:
      rel_counter = 0
      for _, _, rel in resnet.edges.data('relation'):
        neo4j_result = session.execute_write(self.__create_relation, rel)
        for record in neo4j_result:
          print(f"Created {record[1]}: {record[0]} -> {record[2]} relation")
          rel_counter += 1
          if rel_counter%10000 == 0:
            print(f'\n\nImported {rel_counter} relations\n\n')

  
  def load_graph2neo4j(self, resnet:ResnetGraph):
      resnet_size = resnet.number_of_edges()
      print('Importing Resnet with %d edges into local Neo4j' % resnet_size)
      import_start = time.time()
      resnet.load_references()
      for cypher, params in Cypher.create_nodes(resnet._get_nodes()):
        with self.session() as session:
          session.run(cypher, params)
        
      if resnet_size > 50000:
        self.import_relations(resnet._psrels())
      else:
        self.load_relations_1by1(resnet)

      print("Graph with %d nodes and %d edges was imported into Neo4j in %s ---" % 
          (resnet.number_of_nodes(), resnet_size, execution_time(import_start)))

  from concurrent.futures import ThreadPoolExecutor

  @staticmethod
  def __update(tx, update_cypher:str, batch:list):
    """
    This function represents the work done inside a single transaction.
    The 'tx' object is provided by the driver's execute_write method.
    """
    result = tx.run(update_cypher, batch=batch)
    return list(result)

  def process_update(self, update_cypher:str, chunk:list):
    """
    Each thread runs this: opens a session and calls execute_write.
    """
    with self.session() as session:
      return session.execute_write(self.__update, update_cypher, chunk)


  def _unwind_tx_(self, update_cypher:str, full_list:list, 
               chunk_size=10000,request_name='',multithread=True):
    '''
      Cypher query must contain UNWIND $batch AS row and use row.{item} to refer to items in the list
    '''
    if request_name:
      print(f'Multithread update with query "{request_name}" with chunks {chunk_size} and total input {len(full_list)}')
    
    if multithread:
      with ThreadPoolExecutor() as ex:
        futures = [
          ex.submit(self.process_update, update_cypher, chunk) 
          for chunk in [full_list[i:i + chunk_size] for i in range(0, len(full_list), chunk_size)]
        ]
      for future in as_completed(futures):
        try:
          yield future.result()
        except Exception as e:
          print(f"A batch failed: {e}")
    else:
      for chunk in [full_list[i:i + chunk_size] for i in range(0, len(full_list), chunk_size)]:
        yield self.process_update(update_cypher, chunk)

  ########################### CURATION METHODS ########################### CURATION METHODS ###########################
  def delete_rels_with(self, values:list[str], in_propName:str):
    cypher = f'UNWIND $relIds AS idToDelete MATCH ()-[r]->() WHERE r.{in_propName} = idToDelete DELETE r'
    with self.session() as session:
      session.run(cypher, {'relIds': values})
      print(f"Deleted {len(values)} relations with {in_propName}: {values}")


  def node_citation_count(self,seedtype='',reltype='', neighbortype='', source='Medscan') -> dict[str, PSObject]:
    '''
    Calculates citation count and relation count for each node based on relations from the specified source in all directions.
    Returns a dictionary mapping node URNs to PSObjects updated with 'CitationCount' and 'Connectivity'.
    input:
      seedtype: filter for seed node type (label), if empty retreives data for all node types
      reltype: filter for relation type, if empty retreives data for all relation types linked to each seed node,
      neighbortype: filter for neighbor node type (label), if retreives data for any neighbor type linked to each seed node,
      set neighbortype to empty to calculate citation count for non-directional relations connecting nodes of the same type, e.g. protein-protein interactions
    '''
    print('Collecting reference density and connectivity for nodes in Neo4j...')
    s = f's:{seedtype}' if seedtype else 's'
    r = f'r:{reltype}' if reltype else 'r'
    n = f'n:{neighbortype}' if neighbortype else '' #if neighbortype is empty will match any neighbor node
    
    cypher = f"MATCH ({s})-[{r}]-({n}) WHERE r.Source = '{source}' RETURN count(DISTINCT s) AS ConnectedNodeCount, count(r) AS TotalRelCount"
    if neighbortype:
      cypher += f', count(DISTINCT n) AS NeighborNodeCount'
    result = self.session().run(cypher)
    record = result.single()
    nodeCount = record['ConnectedNodeCount']
    relCount = record['TotalRelCount']
    if neighbortype:
      neighborCount = record['NeighborNodeCount']
    s_type = seedtype if seedtype else 'any type of node'
    n_type = neighbortype if neighbortype else 'any type of neighbor node'
    rel_type = reltype if reltype else 'any type of relation'
    if neighbortype:
      print(f'{nodeCount} {s_type}s are connected via {rel_type} to {neighborCount} {n_type}s in database with {relCount} relations')
    else:
      print(f'{nodeCount} {s_type}s are connected via {rel_type} in database with {relCount} relations')
    if nodeCount == 0:
      return dict()
    
    # match in both directions to calculate citationCount for both regulators and targets
    # RelationNumberOfReferences is list in merged relations. 
    # "reduce" is used to accomodate both single value and multivalue RelationNumberOfReferences. 
    # and sum() sums up RelationNumberOfReferences across all matched relations to calculate total citation count for a node
    seed_cypher = f"""
      MATCH ({s})
      WHERE EXISTS {{({s})-[]-()}}
      MATCH ({s})-[{r}]-({n})
      WHERE r.Source = '{source}'
      RETURN s as seed, count(r) AS relCount, 
      sum(reduce(total = 0, x IN apoc.convert.toList(r.RelationNumberOfReferences) | total + x)) AS citationCount
    """
    start = time.time()
    node_dict = dict()
    with self.session() as session:
      result = session.run(seed_cypher)
      for record in result:
        node = self.__record2psobj(record['seed'])
        citation_count = record['citationCount']
        rel_count = record['relCount']
        if citation_count > 0 :
          node.update_with_value('CitationCount',citation_count)
          node.update_with_value(CONNECTIVITY,rel_count)
          node_dict[node.urn()] = node

      if neighbortype:
        target_cypher = f"""
          MATCH ({s})-[{r}]-({n})
          WHERE r.Source = '{source}'
          RETURN n as target, count(r) AS relCount, 
          sum(reduce(total = 0, x IN apoc.convert.toList(r.RelationNumberOfReferences) | total + x)) AS citationCount
        """
        result = session.run(target_cypher)
        for record in result:
          return_node = self.__record2psobj(record['target'])
          citation_count = record['citationCount']
          rel_count = record['relCount']

          return_urn = return_node.urn()
          if return_urn in node_dict:
            my_node = node_dict[return_urn]
            my_node['CitationCount'][0] += citation_count
            my_node[CONNECTIVITY][0] += rel_count
          else:
            return_node.update_with_value('CitationCount',citation_count)
            return_node.update_with_value(CONNECTIVITY,rel_count)
            node_dict[return_node.urn()] = return_node
      
      print(f'Total collected {len(node_dict)} nodes in {execution_time(start)}')
    return node_dict
  

  def snippets_df(self,relids: list[str], only_reltypes=[]):
    '''
    pd.Dataframe with columns:\n['Regulators','Targets','msrc','Effect','Confidence (%)','Citation score','RelType,ID','journal','title','doi','pmid']
    '''
    r = f"r:{'|'.join(only_reltypes)}" if only_reltypes else "r"
    cypher = f"""
    MATCH (a)-[{r}]->(b) 
    WHERE r.RelationID IN $id_list
    RETURN a, r, b
    """
    requeste_name = f"Fetch snippets for {len(relids)} relations"
    params = {'id_list': relids}
    graph2display = self.fetch_graph(cypher, parameters=params, request_name=requeste_name)

    relid2attrs = {}
    for rel in graph2display._psrels():
      raw_ids = rel.get('RelationID')
      if isinstance(raw_ids, str):
        raw_ids = [raw_ids]

      regulators = ','.join([n.name() for n in rel.regulators()])
      targets = ','.join([n.name() for n in rel.targets()])
      confidence = rel['Confidence (%)'][0] if 'Confidence (%)' in rel else np.nan
      citation_score = rel['Citation score'][0] if 'Citation score' in rel else np.nan
      rel_attrs = (regulators, targets, rel.objtype(), rel.effect(), confidence, citation_score)

      for raw_id in raw_ids:
        relid2attrs[raw_id] = rel_attrs

    rel_props = self.postgres.get_refs(set(relid2attrs.keys()))
    rel_props['id'] = rel_props['id'].astype(str)

    default_attrs = ('', '', '', '', 0, 0)
    mapped_attrs = rel_props['id'].map(lambda rid: relid2attrs.get(rid, default_attrs))
    rel_props[['Regulators', 'Targets', 'RelType', 'Effect', 'Confidence (%)', 'Citation score']] = pd.DataFrame(
      mapped_attrs.tolist(), index=rel_props.index)

    rel_props['RelType,ID'] = rel_props['RelType']+": "+rel_props['id']

    # deduplicating rows
    def sentences_key(row):
      return row['Regulators']+'_'+row['Targets']+'_'+row['msrc'][0:30]+row['RelType']+' '+row['Effect']
    
    rel_props = rel_props.sort_values(by='msrc', key=lambda x: x.str.len(), ascending=False)
    rel_props['sentence_key'] = rel_props.apply(sentences_key, axis=1)
    rel_props = rel_props.drop_duplicates(subset='sentence_key', keep='first')

    col2display = ['Regulators','Targets','msrc','Effect','Confidence (%)','Citation score','RelType,ID','journal','title','doi','pmid']
    snippets_df = rel_props[col2display]
    snippets_df = snippets_df.drop_duplicates(subset=['Regulators','Targets','msrc','Effect','RelType,ID'], keep='first')
    return snippets_df
