import os

from .ResnetGraph import ResnetGraph,df,REFCOUNT,CHILDS,DBID,PSObject,OBJECT_TYPE
from .NetworkxObjects import RELATION_PROPS,ALL_PSREL_PROPS,EFFECT
from .references import PS_BIBLIO_PROPS,PS_SENTENCE_PROPS,PS_REFIID_TYPES
from ...utils.utils import load_api_config
from ..EmbioPSG_API.PSnx2Neo4j import neo4j_nx

ALL_CHILDS = -1

class Neo4APISession():
    '''
    manages graph retrieval from database and loading cache files
    '''
    pass
    entProps = ['Name'] # Name is highly recommended to make sense of the data
    relProps = ['URN'] # URNs are used as MultiDiGraph keys in self.Graph
    reference_cache_size = 1000000 # max number of reference allowed in self.Graph. Clears self.Graph if exceeded
    resnet_size = 1000 # number of <node><control> sections in RNEF dump
    max_rnef_size = 100000000 # max size of RNEF XML dump file. If dump file exceeds max_file_size new file is opened with index++
    data_dir = ''
    sep = '\t'
    neo4j = None

######################################  CONFIGURATION  ######################################   
    def postgres(self):
      return self.neo4j.postgres
    
    def __init__(self):
        self.APIconfig = load_api_config()
        self.neo4j = neo4j_nx(self.APIconfig) if self.APIconfig else None


    def set_dir(self,indir:str):
        self.data_dir = os.path.join(indir, '')


    def add_rel_props(self, add_props:list):
        self.relProps = self.relProps+[i for i in add_props if i not in self.relProps]
        my_sent_props = set(PS_SENTENCE_PROPS).intersection(add_props)
        if my_sent_props:
            ms = 5
            if self.max_sessions > ms:
              print(f'{type(self).__name__} decreases multithreading to {ms} to retreive sentence properties')
              self.max_sessions = ms
            if 'TextRef' not in self.relProps:
                self.relProps.append('TextRef')
            

    def add_ent_props(self, add_props: list):
        self.entProps = self.entProps+[i for i in add_props if i not in self.entProps]

    
    def add_dump_file(self, dump_fname, replace_main_dump=False):
        if replace_main_dump:
            self.DumpFiles = []
        self.DumpFiles.append(dump_fname)

#########################  MULTITHREADED PROCESSING, RETRIEVAL   ##################################
    def connect_entities_neo4j(self,nodes1:set[PSObject],nodes2:set[PSObject],
                        by_relation_type=[],with_effect=[],in_direction=''):
      '''
      input:
        in_direction: '>' or '<'
      output:
        #connection ResnetGraph without references !!!
      '''
      by_relProps = {OBJECT_TYPE:by_relation_type, EFFECT:with_effect}
      if in_direction == '>':
        connectionsG = self.neo4j.connect_objs(nodes1,nodes2,by_relProps,dir=True)
      elif in_direction == '<':
        connectionsG = self.neo4j.connect_objs(nodes2,nodes1,by_relProps,dir=True)
      else:
        connectionsG = self.neo4j.connect_objs(nodes1,nodes2,by_relProps,dir=False)
      # this connectionG does not have references
      # use self.load_references to add connectionsG to self.Graph together with references
      return connectionsG   

    def _load_childs_(self,parents:list[PSObject], max_childs=ALL_CHILDS)->tuple[set[PSObject],set[PSObject]]:
        parents_wthCHILDS = set(self.neo4j._load_children_(parents,max_childs=max_childs))
        children = set(ResnetGraph.childs(parents_wthCHILDS))
        return children,parents_wthCHILDS 
