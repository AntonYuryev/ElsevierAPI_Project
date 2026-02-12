from pubmed import NCBIeutils
import os
import xml.etree.ElementTree as ET


GEO_CACHE = os.path.join(os.getcwd(),'ElsevierAPI/.cache/NCBI/__ncbigeocache__/')

query = ('KLRG1','KLRG1')


class GEOprofiles(NCBIeutils):
  def __init__(self,query:tuple):
    self.params = {'db':'geoprofiles','term':query[0]}
    self.cache_path = GEO_CACHE
    self.query = query


  def download_profiles(self):
    for xml_str in self.fetch(self.query[1]):
      print(xml_str)
      abstractTree = ET.fromstring(xml_str)
      articles = abstractTree.findall('PubmedArticle')


if __name__ == "__main__":
    geo = GEOprofiles(query)
    geo.download_profiles()
    print()
