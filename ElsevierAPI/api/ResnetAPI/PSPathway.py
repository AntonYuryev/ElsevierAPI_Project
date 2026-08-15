from .NetworkxObjects import PSObject
from .ResnetGraph import ResnetGraph,RESNET,OBJECT_TYPE
from lxml import etree as et
from .rnef2sbgn import rnef2sbgn_str,minidom

################################## PSPathway, PSPathway, PSPathway, PSPathway##########################################
class PSPathway(PSObject):
  pass
  def __init__(self,dic=dict(),g=ResnetGraph()):
      super().__init__(dic)
      self.graph = ResnetGraph()
      
      self.update(dic)
      self.graph.update(g)
      self.graph.urn2rel.update(g.urn2rel)


  @classmethod
  def from_resnet(cls, resnet:et._Element, add_annotation=PSObject(),make_rnef=True,ignore_graph=False):
    pathway = PSPathway()
    pathway['Name'] = [resnet.get('name','no_name')]
    pathway['URN'] = [resnet.get('urn','no_urn')]
    pathway[OBJECT_TYPE] = [resnet.get('type','no_type')]
    pathway.update(add_annotation)
    [pathway.update_with_value(p.get('name'),p.get('value')) for p in resnet.findall('properties/attr','')]

    if not ignore_graph:
      nodes, rels = ResnetGraph._parse_nodes_controls(resnet)
      pathway.graph.add_psobjs(nodes)
      pathway.graph.__add_psrels__(rels,add_nodes=False,edge_duplication=False)
      if make_rnef:
        pathway[RESNET] = et.tostring(resnet)
    
      layout = resnet.find('attachments/layout')
      if layout is not None:
        pathway['layout'] = et.tostring(layout)
    return pathway



  @classmethod
  def from_pathway(cls,other:"PSPathway"):
      return PSPathway(other,other.graph)


  def number_of_nodes(self, obj_type=''):
      if obj_type:
          try:
              return self['#'+obj_type]
          except KeyError:
              obj_count = len([obj_t for i,obj_t in self.graph.nodes.data(OBJECT_TYPE) if obj_type in obj_t[OBJECT_TYPE]])
              self['#'+obj_type] = obj_count
              return obj_count
      else:
          return len(self.graph)


  def merge_pathway(self, other:"PSPathway"):
      '''
      Merges pathway.graph\n
      Removes properties 'layout','resnet' as they are no longer applicable
      '''
      self.pop('layout','')
      self.pop('resnet','')
      for prop_name,values in other.items():
          if prop_name not in ['layout','resnet']:
              self.update_with_list(prop_name,values)

      self.graph = self.graph.compose(other.graph)


  def member_dbids(self,with_values:list=[],in_properties:list=['ObjTypeName']):
      return self.graph.ids4nodes(with_values,in_properties)

  
  def get_members(self,with_values:list=[],in_properties=['ObjTypeName']):
      return self.graph.psobjs_with(in_properties,with_values)


  def props2rnef(self):
      props_element = et.Element('properties',attrib=None, nsmap=None)
      for prop_name,prop_val in self.items():
          for val in prop_val:
              et.SubElement(props_element, 'attr', {'name':str(prop_name), 'value':str(val)},nsmap=None)
      return str(et.tostring(props_element).decode("utf-8"))


  def to_xml_s(self,ent_props:list,rel_props:list,add_props2rel=dict(),add_props2pathway=dict(),format='RNEF',as_batch=True, prettify=True):
    '''
    Returns
    -------
    pathway XML string. supports RNEF and SBGN XML formats
    '''
    self.graph.load_references()
    graph_xml_str = self.graph.to_rnefstr(ent_props,rel_props,add_props2rel,add_props2pathway)
    resnet = et.fromstring(graph_xml_str,parser=None)
    resnet.set('type','Pathway')
    resnet.set('Name',self.name())
    resnet.set('URN',self.urn())

    pathway_props = et.SubElement(resnet, 'properties',attrib=None, nsmap=None)
    for prop_name,prop_val in self.items():
      if prop_name not in [RESNET,'layout','Name','URN',OBJECT_TYPE]:
        for val in prop_val:
          et.SubElement(pathway_props, 'attr', {'name':str(prop_name), 'value':str(val)}, nsmap=None)

    if 'layout' in self and self['layout']:
      my_layout = et.fromstring(self['layout'],parser=None)
      attachments = et.Element('attachments',attrib=None, nsmap=None)
      attachments.append(my_layout)
    else: 
      attachments = et.Element('attachments',attrib=None, nsmap=None)
    resnet.append(attachments)

    if format == 'SBGN':
      pathway_xml_str = et.tostring(resnet).decode("utf-8")
      pathway_xml_str = rnef2sbgn_str(resnet)
    else:
      if as_batch:
        batch_xml = et.Element('batch',attrib=None, nsmap=None)
        batch_xml.insert(0,resnet)
        pathway_xml_str = et.tostring(batch_xml).decode("utf-8")
      else:
        pathway_xml_str = et.tostring(resnet).decode("utf-8")

      if prettify:
        #minidom does not work without xml_declaration:
        declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
        pathway_xml_str = declaration + pathway_xml_str
        pretty_xml_str = str(minidom.parseString(pathway_xml_str).toprettyxml(indent='   '))
        # minidom.parseString returns declaration as  '<?xml version="1.0?">
        pathway_xml_str = pretty_xml_str[pretty_xml_str.find('?',5)+3:]
        # minido inserts empty lines into layout section
        pathway_xml_str = '\n'.join([line for line in pathway_xml_str.split('\n') if line.strip()])

    return str(pathway_xml_str)


  def _2rnef(self,fname, ent_props:list,rel_props:list,add_props2rel=dict(),add_props2pathway=dict()):
    self.update(add_props2pathway)
    with open(fname,'w',encoding='utf-8') as f:
      f.write('<batch>\n') 
      props_str = self.props2rnef()
      f.write(props_str+'\n')
      f.write(self.graph.to_rnefstr(ent_props,rel_props,add_props2rel))
      f.write('\n</batch>') 


  def load_references(self,postgres=None):
    return self.graph.load_references(postgres=postgres)
  
  def rels(self):
    return self.graph._psrels()

