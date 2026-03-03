import subprocess,os
from textblob.blob import TextBlob


USERDIR = "C:\\Users\\Administrator\\Documents\\MedScan Reader Projects\\user_dict"
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

class MedScan:
# uses local MedScan installation to markup text and extrcat relations
  license = str()
  organism = 'Mammal'
  #input_type = 'sentence'
  sentence_maxlen = 3500
  def __init__(self,license,medscan_dir=MEDSCANDIR,user_dir=USERDIR,org_name = 'Mammal'):
      self.medscan_dir = medscan_dir
      self.user_dir = user_dir if user_dir else self.medscan_dir
      self.organism = org_name
      self.license = license
      self.objnames = self._load_objnames()


  def markup_sentence(self,sentence:str):
      locscan = os.path.join(self.medscan_dir, 'locscan')
      sentences = list()
      for i in range (0, len(sentence), self.sentence_maxlen):
          sentences.append(sentence[i:i+self.sentence_maxlen])

      if len(sentences) > 1:
          print('Below sentence is too long and was split for MedScan processing:\n%s' % sentence)

      markup = str()
      for s in sentences:
          completed_process = subprocess.run([locscan, "-t"+self.license, "-W"+USERDIR,"-Q"+self.organism, "sentence:"+s], capture_output=True)
          #print(completed_process.stderr)
          complete_markup = completed_process.stdout.decode('utf-8').strip()
          sentence_start = complete_markup.find('msrc\t', 20)
          sentence_start = 0 if sentence_start < 0 else sentence_start + 5
          concept_scan_markup_pos = complete_markup.find('\r\n<\t#', len(s)+25)
          if concept_scan_markup_pos < 0:
              concept_scan_markup_pos = len(complete_markup)
          markup += complete_markup[sentence_start:concept_scan_markup_pos]+ ' '
      return markup.strip()


  def _load_objnames(self):
    """
    Returns {msid:name}, {msid:urn}
    """
    def process_row(line:str):
        dic_row = line.split('\t')
        msid = dic_row[0]
        name = dic_row[1]
        urn = dic_row[2].strip()
        return msid, name, urn
    
    msid2name = dict()
    msid2urn = dict()
    with open(os.path.join(self.medscan_dir, 'xfdata', f'{self.organism}.ObjectNames.tab'), 'r', encoding='utf-8') as f:
      line = f.readline()
      while line:
        msid, name, urn = process_row(line)
        msid2name[msid] = name
        msid2urn[msid] = urn
        line = f.readline()

    
    user_names_path = os.path.join(self.user_dir, f'{self.organism}.UserNames.tab')
    if os.path.exists(user_names_path):
      with open(user_names_path, 'r', encoding='utf-8') as f:
        line = f.readline()
        while line:
          msid, name, urn = process_row(line)
          msid2name[msid] = name
          msid2urn[msid] = urn
          line = f.readline()

    return msid2name, msid2urn


  def find_concepts(self,paragraph:str) -> dict: 
      blob = TextBlob(paragraph)
      sentences = list(blob.sentences)
      to_return = dict()
      for sentence in sentences:
          medscan_markup = self.markup_sentence(str(sentence))
          range2dict = dict() #{id_range:{id:obj_name}}
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
                  try: obj_name = self.objnames[msid]
                  except KeyError:
                      obj_name = medscan_markup[id_end+1:markup_end]
                      print('"%s" with MedScan ID %s doesn\'t have object name' % (obj_name,msid))     
                  try:                
                      range2dict[id_range][msid] = obj_name
                  except KeyError:
                      range2dict[id_range] = {msid:obj_name}

              markup_pos = medscan_markup.find('ID{',markup_end+1)
          
          to_return[medscan_markup] = range2dict
      
      return to_return # {medscan_markup:{id_range:{id:obj_name}}}, str

  @staticmethod
  def get_drugs(range2dict:dict):
      drugs = []
      for r in [PROTEIN,SMALLMOL,COMPLEX,FUNCTIONALCLASS]: # protein concepts are included for biologics
          try:
              msid_drugs = list(range2dict[r].keys())
              drugs += [x[1] for x in msid_drugs]
          except KeyError: continue
      return drugs if drugs else ['']

  @staticmethod
  def get_diseases(range2dict:dict):
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
  