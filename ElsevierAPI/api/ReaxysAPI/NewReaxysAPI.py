from odata import ODataService
import json


Service = ODataService('https://demodal-data-api.rx-nonprod.cm-elsevier.com/data/', reflect_entities=True)
print()