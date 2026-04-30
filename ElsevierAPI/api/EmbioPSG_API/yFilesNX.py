from yfiles_jupyter_graphs import GraphWidget
from ..ResnetAPI.ResnetGraph import ResnetGraph, nx
from ..ResnetAPI.NetworkxObjects import PSObject, PSRelation

NODE_COLORS = {
    'Disease' : "#5100ff",
    'Protein' : "#C70000",
    'GeneticVariant' : "#ff00ee",
    'CellObject' : "#afb0af",   
    'CellProcess' : "#d9ff50",
    'FunctionalClass' : "#ef9a5e",
    'Complex' : "#e62232",
    'CellType' : "#86d1fa",
    'ClinicalParameter' : "#5ECD40",
    'MedicalProcedure' : "#2D2C2B",   
    'Organ' : "#5E0404",
    'Pathogen' : "#626161",
    'SmallMol' :  "#15ff00",
    'Tissue' : "#a50895",
    'Treatment' : "#0011ff",
    'Virus' : "#352B2B",
    }

EDGE_COLORS = {
    "Expression": "#3498db",   
    "FunctionalAssociation": "#2ecc71",
    'GeneticChange': "#e74c3c",
    'Regulation': "#f1c40f", 
    'MolSynthesis': "#9b59b6",
    'Biomarker': "#e67e22",
    'QuantitativeChange': "#1abc9c",
    'DirectRegulation': "#34495e",
    'ClinicalTrial': "#d35400",
    'MolTransport': "#7f8c8d",
    'StateChange': "#c0392b",
    'miRNAEffect': "#8e44ad",
    'ProtModification': "#27ae60",
    'ChemicalReaction': "#2980b9",
    'PromoterBinding': "#16a085",
    'CellExpression': "#2c3e50",
    'Binding': "#d35400",
    }


EDGE_THICKNESS = {
        'Binding': 3,
        'Biomarker': 2,
        'CellExpression': 2,
        'ChemicalReaction': 3,
        'ClinicalTrial': 2,
        'DirectRegulation': 3,
        "Expression": 2,
        "FunctionalAssociation": 1,
        'GeneticChange': 2,
        'miRNAEffect': 3,
        'MolSynthesis': 2,
        'MolTransport': 2,
        'PromoterBinding': 3,
        'ProtModification': 3,
        'QuantitativeChange': 2,
        'Regulation': 1,
        'StateChange': 2
    }

def apply_edge_color(edge):
    rel_type = edge.get("label")
    return EDGE_COLORS.get(rel_type, "#000000")


def apply_node_color(node):
    rel_type = node.get("label")  
    return NODE_COLORS.get(rel_type, "#FAF8F8")


def apply_edge_thickness(edge):
    rel_type = edge.get("label")
    return EDGE_THICKNESS.get(rel_type, 1)  # Default thickness is 1


def ps2yf_nodes(o:PSObject):
  node4yf = PSObject()
  #node4yf['id'] = o.uid()
  node4yf['label'] = o.objtype()
  node4yf['Name'] = o.name()
  node4yf['URN'] = o.urn()
  [node4yf.__setitem__(k, v_list[0]) for k,v_list in o.items()]
  node4yf['color'] = NODE_COLORS.get(o.objtype(), "#FAF8F8")
  return node4yf

def ps2yf_edges(r:PSRelation):
  edge4yf = PSRelation()
  #edge4yf['id'] = r.urn()
  edge4yf['type'] = r.objtype()
  [edge4yf.__setitem__(k, v_list[0]) for k,v_list in r.items()]
  edge4yf['color'] = EDGE_COLORS.get(r.objtype(), "#000000")
  edge4yf['thickness'] = EDGE_THICKNESS.get(r.objtype(), 1)
  return edge4yf

def ps2yf(g:ResnetGraph):
  g4yf = nx.MultiDiGraph()
  for r,t,rel in g.iterate():
    r_y2f = ps2yf_nodes(r)
    t_y2f = ps2yf_nodes(t)
    g4yf.add_node(r.uid(), **r_y2f)
    g4yf.add_node(t.uid(), **t_y2f)
    g4yf.add_edge(r.uid(), t.uid(), **ps2yf_edges(rel))  # rel is already a PSRelation object
  w = GraphWidget(graph=g4yf)
  w.edge_color_mapping = 'color'
  w.node_color_mapping = 'color'
  w.edge_thickness_factor_mapping = 'thickness'
  w.node_label_mapping = 'Name'
  w.edge_label_visibility = False
  return w

  