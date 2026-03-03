import subprocess,os
from textblob.blob import TextBlob
from collections import defaultdict
from .NetworkxObjects import PSObject
from .references import Reference, SENTENCE


DEFAULT_USERDIR = 'D:\\MEDSCAN\\MedScan Reader Projects\\user_dict'
MEDSCANDIR = 'D:\\MEDSCAN\\DevStandard10.bin\\Standard.bin\\'

PROTEIN = 0
SMALLMOL = 1000000
CELLOBJ = 2000000
COMPLEX = 3000000
CELLPROCESS = 4000000
VIRUS = 5000000
TISSUE = 6000000
ORGANISM = 7000000
ORGAN = 8000000
DISEASE = 9000000
CELLTYPE = 10000000
CELLLINENAME = 11000000
TREATMENT = 13000000
CLINPARAM = 15000000
MEDPROCEDURE = 16000000
GENETICVARIANT = 17000000
PATHOGEN = 18000000
FUNCTIONALCLASS = 12000000
UNCLASSIFIED = 31000000
DOMAIN = 45000000

MEDSCAN_ID = 'MedScan ID'

class MedScan:
# uses local MedScan installation to markup text and extrcat relations
  license = str()
  organism = 'Mammal'
  #input_type = 'sentence'
  sentence_maxlen = 3500
  def __init__(self,license,medscan_dir=MEDSCANDIR,user_dir=DEFAULT_USERDIR,org_name = 'Mammal'):
      self.medscan_dir = medscan_dir
      self.user_dir = os.path.abspath(user_dir) if user_dir else os.path.abspath(self.medscan_dir)
      self.organism = org_name
      self.license = license
      self.objnames = self.load_objnames() # {msid:(name,urn)}


  def __cmd1(self):
    locscan = os.path.join(self.medscan_dir, 'locscan')
    return [locscan, "-t"+self.license, "-W", self.user_dir, "-Q"+self.organism]
  
  @staticmethod
  def __run(cmd:list):
    completed_process = subprocess.run(cmd, capture_output=True)
    if completed_process.returncode != 0:
      raise RuntimeError(f"Command failed with return code {completed_process.returncode}\nMedscan error:{completed_process.stderr.decode('utf-8')}")
    return completed_process.stdout.decode('utf-8').strip()


  def markup_sentence(self,sentence:str):
      sentences = []
      for i in range (0, len(sentence), self.sentence_maxlen):
        sentences.append(sentence[i:i+self.sentence_maxlen])

      if len(sentences) > 1:
        print('Below sentence is too long and was split for MedScan processing:\n%s' % sentence)

      markup = str()
      cmd1 = self.__cmd1()
      for s in sentences:
        cmd = cmd1 + ["sentence:"+s]
        completed_process = self.__run(cmd)
        complete_markup = completed_process.decode('utf-8').strip()
        sentence_start = complete_markup.find('msrc\t', 20)
        sentence_start = 0 if sentence_start < 0 else sentence_start + 5
        concept_scan_markup_pos = complete_markup.find('\r\n<\t#', len(s)+25)
        if concept_scan_markup_pos < 0:
            concept_scan_markup_pos = len(complete_markup)
        markup += complete_markup[sentence_start:concept_scan_markup_pos]+ ' '
      return markup.strip()


  def load_objnames(self)->dict[str,tuple[str,str]]:
    """
    output:
      {msid:(name,urn)}
    """
    def process_row(line:str):
        dic_row = line.split('\t')
        msid = dic_row[0]
        name = dic_row[1]
        urn = dic_row[2].strip()
        return msid, name, urn
    
    msid2name_urn = dict()
    with open(os.path.join(self.medscan_dir, 'xfdata', f'{self.organism}.ObjectNames.tab'), 'r', encoding='utf-8') as f:
      line = f.readline()
      while line:
        msid, name, urn = process_row(line)
        msid2name_urn[msid] = (name,urn)
        line = f.readline()

    
    user_names_path = os.path.join(self.user_dir, f'{self.organism}.UserNames.tab')
    if os.path.exists(user_names_path):
      with open(user_names_path, 'r', encoding='utf-8') as f:
        line = f.readline()
        while line:
          msid, name, urn = process_row(line)
          msid2name_urn[msid] = (name,urn)
          line = f.readline()

    return msid2name_urn


  def find_concepts(self,paragraph:str) -> dict: 
      blob = TextBlob(paragraph)
      sentences = list(blob.sentences)
      to_return = dict()
      for sentence in sentences:
          medscan_markup = self.markup_sentence(str(sentence))
          range2dict = defaultdict(dict) #{id_range:{id:obj_name}}
          markup_pos = medscan_markup.find('ID{')
          while markup_pos >= 0:
              markup_start = markup_pos + 3
              id_end = medscan_markup.find('=',markup_start)
              msids = list(medscan_markup[markup_start:id_end].split(','))
              id_range =  (int(msids[0]) // 1000000) * 1000000
              first_msid = 0 if len(msids) == 1 else 1
              markup_end = medscan_markup.find('}',markup_start+5)
              if markup_end < 0: break #hack for broken markup
              for i in range(first_msid, len(msids)):
                  msid = msids[i]
                  if msid in self.objnames:
                    obj_name = self.objnames[msid][0]
                  else:
                      obj_name = medscan_markup[id_end+1:markup_end]
                      print('"%s" with MedScan ID %s doesn\'t have object name' % (obj_name,msid)) 

                  range2dict[id_range][msid] = obj_name

              markup_pos = medscan_markup.find('ID{',markup_end+1)
          to_return[medscan_markup] = dict(range2dict)
      
      return to_return # {medscan_markup:{id_range:{id:obj_name}}}, str


  @staticmethod
  def get_drugs(range2dict:dict):
    '''
    input:
      range2dict: {id_range:{id:obj_name}}
    '''
    drugs = []
    for r in [PROTEIN,SMALLMOL,COMPLEX,FUNCTIONALCLASS]: # protein concepts are included for biologics
        try:
            msid_drugs = list(range2dict[r].keys())
            drugs += [x[1] for x in msid_drugs]
        except KeyError: continue
    return drugs if drugs else ['']


  @staticmethod
  def get_diseases(range2dict:dict):
    '''
    input:
      range2dict: {id_range:{id:obj_name}}
    '''
    try:
        msid_diseases = list(range2dict[DISEASE].keys())
        return [x[1] for x in msid_diseases]
    except KeyError: return ['']


  @staticmethod
  def get_concept_type(id_range:int):
      range2type = {PROTEIN:'Protein', SMALLMOL:'Compound',COMPLEX:'Protein',CELLPROCESS:'Cell process',DISEASE:'Disease',FUNCTIONALCLASS:'Protein',
              MEDPROCEDURE:'Medical procedure', CELLTYPE:'Cell type', CLINPARAM:'Clinical parameter', CELLOBJ:'Cell object', ORGANISM:'Organism',
              TREATMENT:'Treatment', UNCLASSIFIED:'Unclassified', DOMAIN:'Domain', VIRUS:'Virus', CELLLINENAME:'CellLineName', TISSUE:'Tissue', 
              GENETICVARIANT:'GeneticVariant', ORGAN:'Organ',PATHOGEN:'Pathogen'
              }
      try:
          return range2type[id_range]
      except KeyError:
          print('Name for %d range is not implemented' % id_range)
          return NotImplemented


  @staticmethod
  def id2objtype(id:int):
    range2type = {PROTEIN:'Protein', SMALLMOL:'SmallMol',COMPLEX:'Complex',CELLPROCESS:'CellProcess',DISEASE:'Disease',FUNCTIONALCLASS:'FunctionalClass',
              MEDPROCEDURE:'MedicalProcedure', CELLTYPE:'CellType', CLINPARAM:'ClinicalParameter', CELLOBJ:'CellObject', ORGANISM:'Organism',
              TREATMENT:'Treatment', UNCLASSIFIED:'Unclassified', DOMAIN:'Domain', VIRUS:'Virus', CELLLINENAME:'CellLineName', TISSUE:'Tissue', 
              GENETICVARIANT:'GeneticVariant', ORGAN:'Organ',PATHOGEN:'Pathogen'
              }
    id_range = (id // 1000000) * 1000000
    if id_range in range2type:
        return range2type[id_range] 
    else:
        print('Name for %d range is not implemented' % id_range)
        return NotImplemented
    

  def map_names(self, terms:list[str], work_dir='')->dict[str,tuple[str,str]]:
    '''
    output:
      {term:(msid, urn)}
    '''
    temp_file = os.path.join(work_dir, 'terms2map.txt') if work_dir else 'terms2map.txt'
    with open(temp_file, 'w', encoding='utf-8') as f:
      [f.write(t+'\n') for t in terms]
    cmd = self.__cmd1() +['-O0m', '-k0', 'dict:'+temp_file]
    complete_markup = MedScan.__run(cmd)
    output_lines = complete_markup.splitlines()
    markups = [l[4:].strip() for l in output_lines]
    fout = os.path.join(work_dir, 'mapped_terms.txt') if work_dir else 'mapped_terms.txt'
    with open(fout, 'w', encoding='utf-8') as f:
      [f.write(l+'\n') for l in markups]

    def iscomplete(markup:str):
      if markup.startswith('ID{') and markup.endswith('}'):
        if markup.find('{', 4) == -1:
          return True
      return False

    mapped_terms = []
    for markup in markups:
      map_tuple = (markup, '','','')
      if iscomplete(markup):
        equal_pos = markup.find('=',4)
        id = markup[3:equal_pos]
        comma_pos = id.find(',')
        if comma_pos > 0:
          id = id[comma_pos+1:]
        term = markup[equal_pos+1:-1]
        ms_name,ms_urn =  self.objnames.get(id, ('',''))
        map_tuple = (term, id, ms_name, ms_urn)
      mapped_terms.append(map_tuple)
    return mapped_terms
    

  def mapPSobjs(self, objs:list['PSObject'], work_dir='')->dict[str,tuple[str,str]]:
    '''
    output:
      [PSObject with added attributes: 'MedScan ID', 'MedScan name', 'MedScan URN']
    '''
    obj_names = [o.name() for o in objs]
    mapped_tuples = self.map_names(obj_names, work_dir=work_dir)
    for i, o in enumerate(objs):
      msid = mapped_tuples[i][1]
      if msid: # if msid is not empty
        o[MEDSCAN_ID] = [msid]
        o['MedScan name'] = [mapped_tuples[i][2]]
        o['MedScan URN'] = [mapped_tuples[i][3]]
        o['MedScan objtype'] = [MedScan.id2objtype(int(msid))]
    return objs
  

  def annotate(self,ref:Reference):
    base_text_ref = ref._make_textref()
    for secname, paragraphs in ref.sections.items():
      textref_suf = Reference._textref_suffix(secname)
      sentence_idx = 1
      for paragraph in paragraphs:
        paragraph_annotation = self.find_concepts(paragraph) # paragraph_annotation = {snippet:{id_range:{id:obj_name}}}
        for sentence_markup, range2dict in paragraph_annotation.items():
          if range2dict:
            text_ref = base_text_ref+'#'+textref_suf+':'+str(sentence_idx)
            ref.add_sentence_prop(text_ref,SENTENCE,sentence_markup)
            for msid_range, concept_dict in range2dict.items():
              prop_name = self.get_concept_type(msid_range)
              ref.add_sentence_props(text_ref,prop_name,list(concept_dict.values()))
          sentence_idx +=1
