from ..ResnetAPI.NetworkxObjects import PSObject,PSRelation, PHYSICAL_INTERACTIONS, PROTEIN_TYPES
from ..ResnetAPI.NetworkxObjects import RESNET_REL_TYPES,OBJECT_TYPE,REFCOUNT,SNIPPET_COUNT,CONNECTIVITY,EFFECT
from ..ResnetAPI.ResnetGraph import RELATIONID
from ..ResnetAPI.references import ANATOMICAL_PROPS,REFERENCE_POSTGRES_COLS
from collections import defaultdict


ENTPROP_NEO4J = ['URN', 'Name', 'Description','Alias', 'CAS_ID','Localization',
                 'NodeID','Reaxys_ID','Pharmapendium_ID','Notes']
RELPROP_NEO4J = ['Name', 'Effect', 'Mechanism', 'Source',  RELATIONID,'BiomarkerType',
                  'ChangeType','NCT_ID','QuantitativeType','Phase']+ANATOMICAL_PROPS

ALL_NEOP4J_RELPROPS =  RELPROP_NEO4J + [OBJECT_TYPE, REFCOUNT, SNIPPET_COUNT]
DEAFAULT_DATABASE_RELPROPS = set(ALL_NEOP4J_RELPROPS + REFERENCE_POSTGRES_COLS + ['URN'])


class Cypher:
  @staticmethod
  def __urns(nodes:list[PSObject]):
    return [n.urn() for n in nodes]


  @staticmethod
  def quoted_prop(prop_name:str)->str:
    escaped = prop_name.replace('`', '``')
    return f'`{escaped}`' if any(ch.isspace() for ch in prop_name) else escaped

  @staticmethod
  def quoted_list(prop_names:list[str])->list[str]:
    return [Cypher.quoted_prop(name) for name in prop_names]

  @staticmethod
  def rel_types(reltypes:list|set=RESNET_REL_TYPES) -> str:
    '''
    output:
      "r:RelType1|RelType2|RelType3"
    '''
    return '|'.join(reltypes)

  @staticmethod
  def match_psobjs(objs:list[PSObject],letter='a'):
    list_name = f'{letter}_urnList'
    objtypes = {o.objtype() for o in objs}
    objtypes_str = '|'.join(objtypes)
    cypher = f"WITH ${list_name} AS urns\nUNWIND urns AS urn\nMATCH ({letter}:{objtypes_str}{{URN:urn}})\n"
    parameter = {f'{list_name}':[obj.urn() for obj in objs]}
    return cypher, parameter
  

  def match_nodes_byprop(propValues:list[str|int],propName:str,objtype:str,letter='a'):
    list_name = f'{letter}_propList'
    cypher = f"WITH ${list_name} AS props\nUNWIND props AS prop\nMATCH ({letter}:{objtype}{{{propName}:prop}})\n"
    parameter = {f'{list_name}':propValues}
    return cypher, parameter

  
  def match_node_by_names(names:list[str],objtype='',letter='a',with_connectivity=False):
    '''
     searches both Name and Alias properties for the names in the list
    '''
    node = letter + ':' + objtype if objtype else letter
    cypher = '\n'.join([
      "WITH $batch AS rows",
      'CALL (rows) {',
      "UNWIND rows AS row",
      f"MATCH ({node})",
      f"WHERE toLower({letter}.Name) = toLower(row) OR toLower(row) IN [x IN {letter}.Alias | toLower(x)]",
      f"RETURN {letter}",
      '} IN TRANSACTIONS OF 10000 ROWS',
      f"RETURN {letter}"
    ])
 
    if with_connectivity:
          cypher += f', COUNT{{({letter})-[]-()}} AS {CONNECTIVITY}'
    
    parameter = {'batch':names}
    return cypher, parameter


  @staticmethod
  def match_drugs(letter='d'):
    '''
    Needs MATCH and WHERE
    '''
    return f""" (
            ({letter})-[:is_a*]->(:SmallMol {{Name:'plant medicinal product'}}) 
            OR ({letter})-[:is_a*]->(:SemanticConcept {{Name:'drugs'}})
            )
            AND NOT ({letter})-[:is_a]->(:SmallMol {{Name:'PAINS compounds'}})
            """


  @staticmethod
  def select_drugs(only_from:list[PSObject]=[]):
    if only_from:
      cypher ="""WITH $drug_urnList AS urns
                UNWIND urns AS urn
                MATCH (d:SmallMol {URN:urn}) WHERE """
      cypher += Cypher.match_drugs()
      cypher += "RETURN d"
      return cypher, {'drug_urnList':Cypher.__urns(only_from)}
    else:
      cypher = 'MATCH (d:SmallMol) WHERE '
      cypher += Cypher.match_drugs()
      cypher += "RETURN d"
      return cypher, dict()
  

  @staticmethod
  def select_drug_targets(_4targets:list[PSObject],only_from:list[PSObject]=[],
                relProps:dict[str,list[str|int|float]]=[]) -> tuple[str,dict[str,list]]:
    '''
    input:
      only_from - list of drugs to limit the graph
    '''
    targettypes = {o.objtype() for o in _4targets}
    targettypes_str = ','.join([f"'{t}'" for t in targettypes])

    cypher, params = Cypher.select_drugs(only_from)
    cypher = cypher[:-8] # remove "RETURN d"
    cypher += f'MATCH (t) WHERE any(label IN labels(t) WHERE label IN [{targettypes_str}])\n'
    cypher += f'AND t.URN IN $targeturnList\n'
    cypher +=  'MATCH (d)-[r]->(t)'
    if relProps:
      cypher = Cypher.add_relProps(cypher,relProps)
    cypher += '\nRETURN d,r,t'

    params.update({'targeturnList':[o.urn() for o in _4targets]})
    return cypher, params


  @staticmethod
  def create_group(group_name:str, memberUrns:list[str]):
    """
      Cypher query requires {memberUrns:[urns]} as parameter for session.run(cypher,parameter)
    """
    return f"""
      MERGE (p:Group {{Name: '{group_name}'}})
      WITH p, $memberUrns AS memberUrnsList
      UNWIND memberUrnsList AS currentUrn
      OPTIONAL MATCH (c:SmallMol {{URN: currentUrn}})
      WITH p, c
      WHERE c IS NOT NULL
      MERGE (c)-[:part_of]->(p)
      WITH DISTINCT p
      OPTIONAL MATCH (linked_member:SmallMol)-[:part_of]->(p)
      RETURN p, collect(linked_member.URN) AS LinkedUrns
  """, {'memberUrns':memberUrns}


  @staticmethod
  def create_ontology_group(group_name:str, concept_type:str,memberUrns:list[str]):
    """
      Cypher query requires {memberUrns:[urns]} as parameter for session.run(cypher,parameter)
    """
    return f"""
      MERGE (p:{concept_type} {{Name: '{group_name}'}})
      WITH p, $memberUrns AS memberUrnsList
      UNWIND memberUrnsList AS currentUrn
      OPTIONAL MATCH (c:SmallMol {{URN: currentUrn}})
      WITH p, c
      WHERE c IS NOT NULL
      MERGE (c)-[:is_a]->(p)
      WITH DISTINCT p
      OPTIONAL MATCH (linked_member:SmallMol)-[:is_a]->(p)
      RETURN p, collect(linked_member.URN) AS LinkedUrns
  """, {'memberUrns':memberUrns}


  @staticmethod
  def get_nodes(objtype:str,propName:str,propVals:list[str],with_connectivity=False):
    """
    input:
      objtype can be empty

    output:
      cypher query, parameters from propVals for session.run(cypher,parameter)
      if with_connectivity = True, cypher query returns list of (node,connectivity) tuples
      otherwise returns list of nodes
    """
    cypher = f' MATCH (c:{objtype})' if objtype else ' MATCH (c)'
    cypher += f'\nWHERE c.{propName} IN $values\n'
    cypher +=  ' RETURN c AS node'
    if with_connectivity:
      cypher += f', COUNT{{(c)-[]-()}} AS {CONNECTIVITY}'
    return cypher, {'values':propVals}

  
  @staticmethod
  def match_childs(parent:PSObject,letter='c',max_childs=10):
    return f"""MATCH ({letter})
      WHERE ({letter})-[:is_a*..{max_childs}]->(:{parent.objtype()}{{{'URN'}:'{parent.urn()}'}})\n"""
  

  @staticmethod
  def get_childs(parent:PSObject,max_childs:int=None,depth=None):
    '''
      if max_childs is specified, only parents with less than max_childs childs are returned
      set max_childs to None to get all childs
    '''
    cypher = f"MATCH (p:{parent.objtype()} {{URN:$urn}})"
    if depth:
      cypher += f"OPTIONAL MATCH (child)-[:is_a*..{depth}]->(p)"
    else:
      cypher += f"OPTIONAL MATCH (child)-[:is_a*]->(p)\n"

    cypher += f"WITH p, collect(DISTINCT child) AS all_children"
    if max_childs:
      cypher += '\n'.join([
              "WITH size(all_children) AS count, all_children",
              f"RETURN count, CASE WHEN count > 0 AND count <= {max_childs} THEN all_children ELSE null, END AS childs"
      ])
    else:
      cypher += "\nRETURN size(all_children) AS count, all_children AS childs"

    return cypher, {'urn':parent.urn()} # urn is returned as parametert to overcome URNs with ' sign

  
  @staticmethod
  def get_parents(child:PSObject,depth=3):
    cypher = '\n'.join([
      f'MATCH (child:{child.objtype()} {{URN:$urn}})',
      f'OPTIONAL MATCH (parent)<-[:is_a*..{depth}]-(child)',
      'WITH child, collect(DISTINCT parent) AS parents',
      'RETURN parents AS parents'
    ])
    return cypher, {'urn':child.urn()} # urn is returned as parametert to overcome URNs with ' sign


  @staticmethod
  def node_connectivity(nodes:list[PSObject]):
    objtypes = {p.objtype() for p in nodes}
    objtypes_str = '|'.join(objtypes)
    cypher = '\n'.join([
      'WITH $urnList AS urns',
      'UNWIND urns AS urn',
      f'MATCH (n:{objtypes_str}{{URN:urn}})',
      'RETURN urn as urn, COUNT{(n)-[]-()} AS {CONNECTIVITY}'
    ])
    return cypher, {'urnList':[n.urn() for n in nodes]}


  @staticmethod ## TO DO 
  def _get_childs_(parents:list[PSObject],max_childs=10,letter='c'):
    objtypes = {p.objtype() for p in parents}
    objtypes_str = '|'.join(objtypes)
    cypher = '\n'.join([
      'WITH $urnList AS urns',
      'UNWIND urns AS urn',
      f'MATCH ({letter}) WHERE ({letter})-[:is_a* ..{max_childs}]->(:{objtypes_str}{{URN:urn}})',
      f'RETURN {letter}'
    ])
    return cypher, {'urnList':[p.urn() for p in parents]}
  

  @staticmethod
  def __list2str(values:list[str|int|float])->str:
    if isinstance(values[0], str):
      return ', '.join([f"'{v}'" for v in values])
    else:
      return ', '.join([str(v) for v in values])


  @staticmethod
  def add_relProps(cypher:str, relProps:dict[str,list[str|int|float]], letter='r',add_where=True) -> str:
    """
      Appends WHERE clauses to a Cypher query based on properties.
    """
    if not relProps:
      return cypher

    conditions = []
    for prop, values in relProps.items():
      if not values:
        continue
      if prop == OBJECT_TYPE:
          conditions.append(f"type({letter}) IN [{Cypher.__list2str(values)}]")
      elif prop == REFCOUNT:
          val = values[0] if isinstance(values, list) else values
          conditions.append(f"{letter}.{prop} {val}")
      elif prop == EFFECT:
        unknown_effect_requested = 'unknown' in values
        standard_effects = [v for v in values if v not in ('unknown')]

        effect_logic_parts = []
        if standard_effects:
          effect_logic_parts.append(f"{letter}.Effect IN [{Cypher.__list2str(standard_effects)}]")
        if unknown_effect_requested:
          effect_logic_parts.append(f"coalesce({letter}.Effect, '_') IN ['unknown', '_']")
        
        if effect_logic_parts:
          conditions.append(f"({' OR '.join(effect_logic_parts)})")
      else:
        conditions.append(f"{letter}.{prop} IN [{Cypher.__list2str(values)}]")

    if conditions:
        if add_where:
          return f"{cypher}\nWHERE {' AND '.join(conditions)}"
        else:
          return f"{cypher}\nAND {' AND '.join(conditions)}"
    
    return cypher


  @staticmethod
  def expand_upstream(seeds_with_values:list[str],in_prop='Name', 
                    _2neighbor_types:list[str]=[],by_relProps:dict[str,list[str|int|float]]={}):
    '''
      by_relProps = {reltype:[propValue1,propValue2,...]},
      use OBJECT_TYPE string to specify filtering by relation type
    '''
    if in_prop == OBJECT_TYPE:
      parameters = dict()
      seeds = '|'.join(seeds_with_values)
      if _2neighbor_types:
        neigbors = '|'.join(_2neighbor_types)
        cypher = f'MATCH (n:{neigbors})-[r]-(s:{seeds})\n'
      else:
        cypher = f'MATCH (n)-[r]-(s:{seeds})\n'
    else:
      cypher = f'WITH $propList AS props\nUNWIND props AS prop\nMATCH (s{{{in_prop}:prop}})'
      parameters = {'propList':seeds_with_values}
      if _2neighbor_types:
        neigbors = '|'.join(_2neighbor_types)
        cypher += f'MATCH (n:{neigbors})-[r]->(s)\n'
      else:
        cypher += 'MATCH (n)-[r]->(s)'

    cypher = Cypher.add_relProps(cypher, by_relProps)
    cypher += '\nRETURN n,r,s'
    return cypher,parameters
  

  @staticmethod
  def expand_downstream(seeds_with_values:list[str],in_prop='Name', 
                    _2neighbor_types:list[str]=[],by_relProps:dict[str,list[str|int|float]]={}):
    '''
      by_relProps = {reltype:[propValue1,propValue2,...]},
      use OBJECT_TYPE string to specify filtering by relation type
    '''
    if in_prop == OBJECT_TYPE:
      parameters = dict()
      seeds = '|'.join(seeds_with_values)
      if _2neighbor_types:
        neigbors = '|'.join(_2neighbor_types)
        cypher = f'MATCH (s:{seeds})-[r]->(n:{neigbors})\n'
      else:
        cypher = f'MATCH (s:{seeds})-[r]->(n)\n'
    else:
      cypher = f'WITH $propList AS props\nUNWIND props AS prop\nMATCH (s{{{in_prop}:prop}})'
      parameters = {'propList':seeds_with_values}
      if _2neighbor_types:
        neigbors = '|'.join(_2neighbor_types)
        cypher += f'MATCH (s)-[r]->(n:{neigbors})\n'
      else:
        cypher += 'MATCH (s)-[r]->(n)'

    cypher = Cypher.add_relProps(cypher, by_relProps)
    cypher += '\nRETURN s,r,n'
    return cypher,parameters
  

  @staticmethod
  def expand(seeds_with_values:list[str],in_prop='Name', 
            _2neighbor_types:list[str]=[],by_relProps:dict[str,list[str|int|float]]={},dir=''):
    '''
      by_relProps = {reltype:[propValue1,propValue2,...]},
      use OBJECT_TYPE as key in by_relProps to specify filtering by relation type
      dir: '', 'upstream', 'downstream'
    '''
    seeds = f's:{'|'.join(seeds_with_values)}' if in_prop == OBJECT_TYPE else 's'
    neigbors = f'n:{'|'.join(_2neighbor_types)}' if _2neighbor_types else 'n'
    parameters = dict()

    if dir == 'upstream':
      cypher = f'MATCH ({neigbors})-[r]->({seeds})\n'
    elif dir == 'downstream':
      cypher = f'MATCH ({seeds})-[r]->({neigbors})\n'
    else:
      cypher = f'MATCH ({neigbors})-[r]-({seeds})\n'

    if in_prop != OBJECT_TYPE:
      cypher += f'WHERE s.{in_prop} IN $propList\n'   
      parameters = {'propList':seeds_with_values}

    cypher = Cypher.add_relProps(cypher, by_relProps,add_where=False)
    cypher += '\nRETURN s,r,n'
    return cypher,parameters


  @staticmethod
  def expand_with_cutoff(seed_types:list[str], neighbor_types:list[str]=[],
                         rel_types:list[str]=[],dir='',min_neighbors=1,only_with_neighbors:dict={}):
    '''
      input:
        only_with_neighbors is dict {propName:[value1,value2,...]} to specify that seeds must have at least min_neighbors of specified neighbor_objtype connected by specified reltypes regardless of the neighbor_types filter. This allows to keep seeds with important neighbors that would be filtered out by neighbor_types criteria
      expands neighbors of seeds and filters seeds by number of neighbors of specified types and relations
    '''
    seeds = f's:{'|'.join(seed_types)}'
    neighbors = f'n:{'|'.join(neighbor_types)}' if neighbor_types else 'n'
    rels = f'r:{'|'.join(rel_types)}' if rel_types else 'r'
    parameters = dict()

    if dir == 'upstream':
      cypher =  f'MATCH ({neighbors})-[{rels}]->({seeds})\n'
    elif dir == 'downstream':
      cypher = f'MATCH ({seeds})-[{rels}]->({neighbors})\n'
    else:
      cypher = f'MATCH ({seeds})-[{rels}]-({neighbors})\n'
    
    if only_with_neighbors:
      cypher += f'WHERE '
      cypher += ' OR '.join([f'n.{prop} IN ${prop}List' for prop in only_with_neighbors.keys()])
      cypher += '\n'
      parameters = {f'{prop}List': list(only_with_neighbors[prop]) for prop in only_with_neighbors.keys()}

    cypher += 'WITH s, count(DISTINCT n) AS neighborCount, collect({rel:r, neighbor:n}) AS connections\n'
    cypher += f'WHERE neighborCount >= {min_neighbors}\n'
    cypher += 'UNWIND connections AS conn\n'

    cypher += 'RETURN s,conn.rel AS r,conn.neighbor AS n'
    return cypher,parameters
    

  @staticmethod
  def connect(regulator_objtypes:list[str], regulator_props:list[str],regulator_propName:str,
    target_objtypes:list[str], target_props:list[str]=[],target_propName='',
    by_relProps:dict[str,list[str|int|float]]={}, dir=False):

    parameters = dict()
    a = f'a:{'|'.join(regulator_objtypes)}'
    b = f'b:{'|'.join(target_objtypes)}'

    cypher = f'MATCH ({a})'
    if regulator_props:
      cypher += f'\nWHERE a.{regulator_propName} IN $regpropList\n'
      parameters['regpropList'] = regulator_props
    cypher += f'\nMATCH ({b})'
    if target_props:
      cypher += f'\nWHERE b.{target_propName} IN $tarpropList\n'
      parameters['tarpropList'] = target_props
    
    if dir:
      cypher += f'MATCH (a)-[r]->(b)\n'
    else:
      cypher += f'MATCH (a)-[r]-(b)\n'
    
    cypher = Cypher.add_relProps(cypher, by_relProps)
    cypher += '\nRETURN startNode(r) AS Regulator, r AS Relation, endNode(r) AS Target'
    return cypher, parameters
  

  @staticmethod
  def connect_objs(regulators:set[PSObject],targets:set[PSObject],
                   by_relProps:dict[str,list[str|int|float]]={}, dir=False):

    parameters = dict()
    a = f'a:{'|'.join({obj.objtype() for obj in regulators})}'
    b = f'b:{'|'.join({obj.objtype() for obj in targets})}'

    parameters['rURNs'] = [obj.urn() for obj in regulators]
    parameters['tURNs'] = [obj.urn() for obj in targets]

    if dir:
      cypher = f'MATCH ({a})-[r]->({b})\n'
    else:
      cypher = f'MATCH ({a})-[r]-({b})\n'

    cypher += """WHERE a.URN IN $rURNs AND b.URN IN $tURNs"""    
    cypher = Cypher.add_relProps(cypher, by_relProps,add_where=False)
    cypher += '\nRETURN startNode(r) AS Regulator, r AS Relation, endNode(r) AS Target'
    return cypher, parameters
  

  @staticmethod
  def ppi(interactors:list[PSObject], minref:int=2):
    '''
      interactors: list of PSObject
      output:
        cypher query, parameters for session.run(cypher,parameter)
    '''
    physical_interactions = '|'.join([v for v in PHYSICAL_INTERACTIONS])
    proteins = '|'.join([v for v in PROTEIN_TYPES])
    cypher = '\n'.join([
      'WITH $urnList AS urns',
      'UNWIND urns AS urn',
      f'MATCH (a:{proteins} {{URN:urn}})-[r:{physical_interactions}]-(b:{proteins})',
      f'WHERE r.{REFCOUNT} >= {minref}',
      'RETURN a, r, b'
    ])
    parameter = {'urnList':[obj.urn() for obj in interactors]}
    return cypher, parameter


  @staticmethod
  def common_neighbors(with_entity_types:list[str],nodes1:list[PSObject], nodes2:list[PSObject],
                      relProps2node1:dict[str,list],dir1common:str, 
                      relProps2node2:dict[str,list], dir2common):
    '''
    input:
      dir1common,dir2common in ['<','>','']\n
      relProps2node1,relProps2node2 are dicts {propName:[propValue1,propValue2,...]} for filtering relations between common neighbor and nodes1 and nodes2 respectively
    '''
    common_objtype_str = '|'.join(with_entity_types)
    common = f'common:{common_objtype_str}'

    objtypes1 = {p.objtype() for p in nodes1}
    objtypes2 = {p.objtype() for p in nodes2}
    objtypes_str1 = '|'.join(objtypes1)
    objtypes_str2 = '|'.join(objtypes2)
    r1_objtypes = '|'.join(relProps2node1.pop(OBJECT_TYPE, []))
    r1 = f'r1:{r1_objtypes}' if r1_objtypes else 'r1'
    r2_objtypes = '|'.join(relProps2node2.pop(OBJECT_TYPE, []))
    r2 = f'r2:{r2_objtypes}' if r2_objtypes else 'r2'

    n1 = f'n1:{objtypes_str1}'
    n2 = f'n2:{objtypes_str2}'

    cypher = f'MATCH ({n1})'
    if dir1common == '<':
      cypher += f'<-[{r1}]-({common})'
    elif dir1common == '>':
      cypher += f'-[{r1}]->({common})'
    else:
      cypher += f'-[{r1}]-({common})'

    if dir2common == '<':
      cypher += f'-[{r2}]->({n2})'
    elif dir2common == '>':
      cypher += f'<-[{r2}]-({n2})'
    else:
      cypher += f'-[{r2}]-({n2})'
    
    cypher += '\nWHERE n1.URN IN $urnList1 AND n2.URN IN $urnList2\n'

    cypher = Cypher.add_relProps(cypher, relProps2node1, letter='r1', add_where=False)
    cypher = Cypher.add_relProps(cypher, relProps2node2, letter='r2', add_where=False)  
    cypher += '\nRETURN n1, r1, common, r2, n2'

    parameters = {'urnList1':[obj.urn() for obj in nodes1], 'urnList2':[obj.urn() for obj in nodes2]}
    return cypher, parameters
  

  @staticmethod
  def __get_rel_labels(rel:PSRelation):
    labls = rel.values_dict(list(RELPROP_NEO4J))
    labls = labls + f',{REFCOUNT}:' + str(rel.count_refs()) 
    labls = labls + f',{SNIPPET_COUNT}:' + str(rel.count_snippets())
    return labls


  @staticmethod
  def create_rel(node1:PSObject, node2:PSObject, relation:PSRelation)->str:
    relType = relation.objtype()
    labels = Cypher.__get_rel_labels(relation)
    return '\n'.join([
          'MATCH',
          '(a:' + node1.objtype() + '),',
          '(b:' + node2.objtype() + ')',
          'WHERE a.URN = \"' + node1.urn() + '\" AND b.URN = \"' + node2.urn() + '\"',
          'CREATE (a)-[r:' + relType + ' {' + labels + '}]->(b)',
          'RETURN a.Name as rName, b.Name as tName, type(r) as rel_type'
          ])


  @staticmethod
  def importRel(relation:PSRelation)->tuple[str,dict]:
    relType = relation.objtype()
    rel_props = relation.values_dict(list(RELPROP_NEO4J))
    for prop, vals in rel_props.items():
      rel_props[prop] = vals[0] if len(vals) == 1 else vals
    rel_props[REFCOUNT] = relation.count_refs()
    rel_props[SNIPPET_COUNT] = relation.count_snippets()
    for prop, vals in relation.items():
      if prop not in DEAFAULT_DATABASE_RELPROPS:
        rel_props[prop] = vals[0] if isinstance(vals, list) and len(vals) == 1 else vals

    pairs = [{'aType':n1.objtype(),'aUrn': n1.urn(), 'bType': n2.objtype(), 'bUrn': n2.urn(), 'relProps': rel_props} for n1, n2 in relation.node_pairs()]
    cyphers_params = []
    for pair in pairs:
      cypher = '\n'.join([
          'UNWIND $pairs AS pair',
          f'MATCH (a:`{pair["aType"]}` {{URN: pair.aUrn}}), (b:`{pair["bType"]}` {{URN: pair.bUrn}})',
          f'CREATE (a)-[r:`{relType}` $relProps]->(b)',
          'RETURN a.Name AS rName, b.Name AS tName, type(r) AS rel_type'
      ])
      cyphers_params.append((cypher, {'pairs': [pair], 'relProps': rel_props}))
    return cyphers_params
  

  @staticmethod
  def importRels(rels:list[PSRelation],transaction_size=20000)->list[tuple[str,dict]]:
    """
    input:
      rels - list of PSRelation objects, all nodes must exist in the database
    output:
      list of (cypher_query, parameters) tuples, grouped by relation type and endpoint labels.
      Groups contain no shared endpoint URNs between pairs; all relationships are preserved.
      Groups may share endpoints with other groups and are not execution barriers.
      Each query handles all pairs for that group and returns the count of created relations.
      parameters['request_name'] holds regulatorType_relType_targetsType"""
    by_type = defaultdict(list)
    endpoint_groups = defaultdict(list)

    for rel in rels:
      relType = rel.objtype()
      rel_props = rel.values_dict(list(RELPROP_NEO4J))
      for prop, vals in rel_props.items():
        rel_props[prop] = vals[0] if len(vals) == 1 else vals

      rel_props[REFCOUNT] = rel.count_refs()
      rel_props[SNIPPET_COUNT] = rel.count_snippets()
      for prop, vals in rel.items():
        if prop not in DEAFAULT_DATABASE_RELPROPS:
         rel_props[prop] = vals[0] if isinstance(vals, list) and len(vals) == 1 else vals
      # Group node pairs by endpoint URNs to avoid conflicts within the same transaction.
      for n1, n2 in rel.node_pairs():
        key = (relType, n1.objtype(), n2.objtype())
        a_urn, b_urn = n1.urn(), n2.urn()
        groups = endpoint_groups[key]
        for group_index, endpoints in enumerate(groups):
          if a_urn not in endpoints and b_urn not in endpoints:
            break #If a suitable group is found, break skips the else.
        else: #If every existing group conflicts—or groups is empty—the loop finishes without break, so else creates a new group.
          group_index = len(groups)
          endpoints = set()
          groups.append(endpoints)
        endpoints.update((a_urn, b_urn))
        by_type[(*key, group_index)].append({'aUrn': a_urn, 'bUrn': b_urn, 'relProps': rel_props})
    
    queries = []
    for (relType, aType, bType, group_index), pair_list in by_type.items():
      a_label = aType.replace('`', '``')
      b_label = bType.replace('`', '``')
      cypher = '\n'.join([
          #'EXPLAIN',
          'UNWIND $batch AS pair',
          'CALL (pair) {',
          f'MATCH (a:`{a_label}` {{URN: pair.aUrn}}), (b:`{b_label}` {{URN: pair.bUrn}})',
          f'CREATE (a)-[r:`{relType}`]->(b)',
          'SET r = pair.relProps',
          'RETURN count(r) AS relcount}',
          f'IN TRANSACTIONS OF {transaction_size} ROWS',
          'RETURN sum(relcount) AS relcount'
      ])
      parameters = {'batch': pair_list, 'transaction_size': transaction_size, 'request_name': f'importRels_{aType}_{relType}_{bType}'}
      queries.append((cypher, parameters))

    print(f'Will import {len(rels)} relations in {len(queries)} batches')
    return queries
  
  
  @staticmethod
  def importNodes(nodes:list[PSObject],transaction_size=50000)->list[tuple[str,dict]]:
    '''
    output:
      list of (node_type, cypher_query, parameters) tuples, one per node type.
      Each query is compact and handles all nodes for that type, parameters have request_name for use with _unwind_.
    '''
    by_type = defaultdict(list)
    for node in nodes:
      objtype = node.objtype()
      props = {k.replace(':', ' '): v[0] for k, v in node.items() if k in ENTPROP_NEO4J}
      props['URN'] = node.urn()
      by_type[objtype].append(props)

    queries = []
    for objtype, prop_list in by_type.items():
      cypher = '\n'.join([
          'UNWIND $batch AS nodeProps',
          'CALL (nodeProps) {',
          f'MERGE (n:`{objtype}` {{URN: nodeProps.URN}})',
          'ON CREATE SET n = nodeProps, n._created = true',
          'WITH n, n._created IS NOT NULL AS wasCreated',
          'REMOVE n._created',
          'RETURN count(CASE WHEN wasCreated THEN 1 END) AS createdCount, count(n) AS totalProcessed}',
          f'IN TRANSACTIONS OF {transaction_size} ROWS',
          'RETURN sum(createdCount) AS createdCount, sum(totalProcessed) AS totalProcessed'
        ])
      queries.append((cypher, {'batch': prop_list, 'transaction_size': transaction_size, 'request_name': f'importNodes_{objtype}'}))
    
    return queries
