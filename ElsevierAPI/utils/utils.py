
import time,sys,os,json, requests,re,traceback,urllib3,unicodedata,certifi,http.client,socket,ssl
from scipy import stats
import numpy as np
from urllib.parse import quote as urlencode
from collections import Counter
from itertools import chain as iterchain
from math import ceil
from statistics import mean, median
from typing import Generator
from datetime import timedelta,datetime
from xml.dom import minidom
from requests.auth import HTTPBasicAuth
from lxml import etree as et
from concurrent.futures import ThreadPoolExecutor,as_completed
import matplotlib.pyplot as plt
from functools import partial
from urllib.error import URLError


# The "Safety Net" for almost all urllib-related failures:
NETWORK_EXCEPTIONS = (
    ConnectionError,               # Reset, Aborted, Refused, Broken Pipe
    URLError,                      # DNS issues, No network
    http.client.HTTPException,     # RemoteDisconnected, IncompleteRead, etc.
    socket.timeout,                # Request took too long
    TimeoutError,                  # Built-in timeout (Python 3.11+)
    ssl.SSLError                   # HTTPS/Certificate issues
)

DEFAULT_CONFIG_DIR = os.path.join(os.getcwd(),'ElsevierAPI/')
PATH2APICONFIG = os.path.join(DEFAULT_CONFIG_DIR,'.path2APIconfig.json')
PCT = '%'

CHROME_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.google.com/'  # Optional: set a referer if needed
}


def current_time():
  """Prints the current date and time in a human-readable format."""
  now = datetime.now()
  return now.strftime('%Y-%m-%d %H:%M:%S')


def execution_time(execution_start):
    return "{}".format(str(timedelta(seconds=time.time() - execution_start)))


def execution_time2(execution_start:float,current_iteration:int,number_of_iterations:int):
    '''
    input:
        if "number_of_iterations" is supplied assumes that "execution_start" is global start
        otherwise assumes "execution_start" is the start of the current iteration if "remaining_iterations" is supplied
        
    output:
        tuple: time passed from execution_start, remaining_time
    '''
    delta = time.time() - execution_start
    time_passed = "{}".format(str(timedelta(seconds=delta)))
    remaining_iterations = number_of_iterations - current_iteration
    remaining_time = delta*float(remaining_iterations/current_iteration)
    remaining_time_str = "{}".format(str(timedelta(seconds=remaining_time)))
    return time_passed, remaining_time_str


def load_api_config(api_config_file='')->dict[str,str]:# file with your API keys and API URLs
  if not api_config_file:
    print('No API config file was specified\nWill use API config file specified in %s instead'% PATH2APICONFIG)
    api_config_file = json.loads(open(PATH2APICONFIG,'r').read())

  try:
    return dict(json.load(open(api_config_file,'r')))
  except FileNotFoundError:
    print("Cannot find API config file: %s" % api_config_file)
    print('No working API server was specified!!! Goodbye')
    return dict()


def fname(path2file:str):
  '''
    generates file name from path without extension
  '''
  return os.path.splitext(os.path.basename(path2file))[0]


def dir2flist(path2dir:str,include_subdirs=True,subdirs_only=False,file_ext='',fnames_has:list[str]=[]):
    my_path = os.path.join(path2dir, '')
    my_files = []
    for root, dirs, files in os.walk(my_path):
        if not include_subdirs and root != my_path: continue
        if subdirs_only and root == my_path: continue
        [my_files.append(os.path.join(root, f)) for f in files if f.lower().endswith(file_ext)]
        # The endswith() function in Python will return True if the input suffix is an empty string.
        # This is because an empty string is considered to be a suffix of any string, including itself.

    return [f for f in my_files if any(s in f for s in fnames_has)] if fnames_has else my_files


def dirList(path2dir:str,include_subdirs=True,subdirs_only=False,file_ext=''):
  '''
  Geerator of: file number,file name tuples
  '''
  my_path = os.path.join(path2dir, '')
  counter = 0
  for root, dirs, files in os.walk(my_path):
    if not include_subdirs and root != my_path: continue
    if subdirs_only and root == my_path: continue
    for f in files:
      if f.lower().endswith(file_ext):
        counter += 1
        yield counter, os.path.join(root, f)


def path2folderlist(path2dir:str, first_folder=''):
  '''
  output:
    list of folder until first_folder, no first_folder in the list
  '''
  drive, path_without_drive = os.path.splitdrive(path2dir)
  folders = []
  while True:
    path_without_drive, tail = os.path.split(path_without_drive)
    if tail == first_folder:
        break
    folders.insert(0, tail) # Insert at the beginning to maintain order
  return folders


def normalize_filename(name:str) -> str:
  """
  Normalizes a filename by replacing illegal characters.
  """
  replacements = {'>': '-', '<': '-', '|': '-', '/': '-', ':': '_'}
  return "".join(replacements.get(char, char) for char in name)
    

def pretty_xml(xml_string:str, remove_declaration = False):
  '''
  xml_string must have xml declration
  '''
  pretty_xml = str(minidom.parseString(xml_string).toprettyxml(indent='   '))
  pretty_xml = "\n".join([line for line in pretty_xml.splitlines() if line.strip()])
  return pretty_xml[pretty_xml.find('\n')+1:] if remove_declaration else pretty_xml


def file_head(full_path:str,number_of_lines = 10000):
    path, filename = os.path.split(full_path)
    filename,ext = os.path.splitext(filename)
    with open(full_path,'r',encoding='utf-8') as f:
        path2test = os.path.join(path,filename+f'-first{number_of_lines}'+ext)
        with open(path2test,'w',encoding='utf-8') as t:
            for counter in range(0,number_of_lines):
                t.write(f.readline())
    return


def remove_duplicates(items:list):
  '''
    keeps uids order in uids
  '''
  seen = set()
  return [i for i in items if i not in seen and not seen.add(i)]


def unpack(list_of_lists:list[list|tuple],make_unique=True):
  if make_unique:
    return list(dict.fromkeys(iterchain.from_iterable(list_of_lists)))
  else:
    return list(iterchain.from_iterable(list_of_lists))
  #  flat_list = [item for sublist in list_of_lists for item in sublist]


def next_tag(in_xml_file:str,tag:str,namespace=''):
    if namespace:
        tag = '{'+namespace+'}'+tag

    context = et.iterparse(in_xml_file,tag=tag)
    for event, elem in context:
        assert(isinstance(elem,et._Element))
        yield elem
        #yield et.tostring(elem).decode()
        elem.clear()
    return


def all_tags(element:et._Element):
    tags = set()  # Use a set to store unique tag names
    tags.add((element.tag))
    [tags.update(all_tags(child)) for child in element]
    #print(tags)
    return tags


def all_child_parents(element:et._Element):
    child2parent = {c.tag:p.tag for p in element.iter() for c in p}
    print(child2parent)
    return child2parent


def urn_encode(string:str,prefix:str):
  """
    input:
        prefix - desired string after urn: prefix
    output:
        urn:prefix:URN-encoded(string) 
  """
  encoded_string = urlencode(string, safe='-_.!~')
  return f"urn:{prefix}:{encoded_string}"


def sortdict(indic:dict,by_key=True,reverse=False,return_top=0):
  i = 0 if by_key else 1
  sorted_items= sorted(indic.items(), key=lambda item: item[i],reverse=reverse)
  return dict(sorted_items[:return_top]) if return_top else dict(sorted_items)


def list2str(dic:dict):
  '''
  converts list values in a dictionary to semicolon separated strings
  '''
  return {k:';'.join(map(str,v)) for k,v in dic.items()}


GREEK2ENGLISH = {
      "α": "alpha",
      "β": "beta",
      "γ": "gamma",
      "δ": "delta",
      "ε": "epsilon",
      "ζ": "zeta",
      "η": "eta",
      "θ": "theta",
      "ι": "iota",
      "κ": "kappa",
      "λ": "lambda",
      "μ": "mu",
      "ν": "nu",
      "ξ": "xi",
      "ο": "omicron",
      "π": "pi",
      "ρ": "rho",
      "σ": "sigma",
      "τ": "tau",
      "υ": "upsilon",
      "φ": "phi",
      "χ": "chi",
      "ψ": "psi",
      "ω": "omega",
      "Α": "Alpha",
      "Β": "Beta",
      "Γ": "Gamma",
      "Δ": "Delta",
      "Ε": "Epsilon",
      "Ζ": "Zeta",
      "Η": "Eta",
      "Θ": "Theta",
      "Ι": "Iota",
      "Κ": "Kappa",
      "Λ": "Lambda",
      "Μ": "Mu",
      "Ν": "Nu",
      "Ξ": "Xi",
      "Ο": "Omicron",
      "Π": "Pi",
      "Ρ": "Rho",
      "Σ": "Sigma",
      "Τ": "Tau",
      "Υ": "Upsilon",
      "Φ": "Phi",
      "Χ": "Chi",
      "Ψ": "Psi",
      "Ω": "Omega"
  }

pattern = re.compile("|".join(GREEK2ENGLISH.keys()))
def greek2english(text: str) -> str:
  return pattern.sub(lambda m: GREEK2ENGLISH[re.escape(m.group(0))], text)

'''
def greek2english(text:str):
  for symbol, spelling in GREEK2ENGLISH.items():
    text = text.replace(symbol, spelling)
  return text
'''

def replace_non_unicode(text:str):
  normalized_text = ''.join(c for c in unicodedata.normalize('NFKD', text) if unicodedata.category(c) != 'Mn')
  return normalized_text


def normalize(s:str):
  text = greek2english(s)
  text = re.sub(r'[^a-zA-Z0-9\s]', ' ', text)  # Remove non-alphanumeric characters
  text = replace_non_unicode(text)
  text = text.replace('  ',' ')
  return text


def tokenize(s:str):
  text = normalize(s)
  tokens = text.lower().split()  # Split into words and convert to lowercase
  return tokens


def match_tokens(tokens1:list,tokens2:list):
  if len(tokens1) == len(tokens2):
    for i, token1 in enumerate(tokens1):
      if token1 != tokens2[1]:
          return False
    return True
  else:
      return False


def get_auth_token(**kwargs):
    """
    kwargs:
        token_url,
        client_id,
        client_secret,
        username,
        password
    output:
        authorization header, retreival time stamp
    """
    try:
        auth = HTTPBasicAuth(kwargs.pop('username'), kwargs.pop('password'))
        data = {"grant_type": 'password'}
        response = requests.post(kwargs['token_url'], auth=auth, data=data)
    except KeyError:
        try:
            data = {'client_id':kwargs['client_id'],'client_secret':kwargs['client_secret']}
            data.update({"grant_type": 'client_credentials'})
            response = requests.post(kwargs['token_url'],  data=data)
        except KeyError:
            print('No valid credetials are supplied to access SBS server')
            return None
        
    body = response.json()
    token = str(body['access_token'])
    return {"Authorization": "Bearer " + token}, time.time()


def print_error_info(x:Exception,thread_name =''):
  exc_type, exc_value, exc_traceback = sys.exc_info()
  traceback_list = traceback.extract_tb(exc_traceback)
  error_message = f'{thread_name} thread has finished with error "{x}"\n{x.__doc__}:'
  for tb_info in traceback_list:
    filename = tb_info.filename
    module_name = tb_info.name
    line_number = tb_info.lineno
    error_message += f"  - File: {filename}, Function: {module_name}, Line: {line_number}\n"
  print(error_message)


def run_tasks(tasks:list)->dict:
  '''
  Executes a list of tasks concurrently using ThreadPoolExecutor
  Args:
    tasks: A list of tuples, where each tuple contains a function and a tuple of its arguments. For example:
            [(func1, (arg1, arg2)), (func2, (arg1,))]
    if function has one argument convert it to tuple as (my_list,)
  '''
  future_dic = {}
  with ThreadPoolExecutor() as ex:
    for func, args in tasks:
      future_dic[func.__name__] = ex.submit(func, *args)

    result_dic = dict()
    for func_name, future in future_dic.items():
      try:
        result_dic[func_name] = future.result()
      except Exception as e:
        print_error_info(e,func_name)
    return result_dic
  
'''
def multithreadOLD(big_list:list, func, **kwargs):
  """"
  input:
    big_list: list of items to be processed
    func: function to be applied to each item in big_list
    **kwargs: additional keyword arguments to be passed to func:
      max_workers: number of threads to use for processing
  output:
    list of results from applying func to each item in big_list
  """
  max_workers = kwargs.pop('max_workers', 10)
  def chunk_func(chunk:list):
    return [func(item,**kwargs) for item in chunk]
  
  results = []
  with ThreadPoolExecutor(max_workers=max_workers) as ex:
    futures = [ex.submit(chunk_func, chunk) for i,chunk in list2chunks_generator(big_list,max_workers)]   
    [results.extend(f.result()) for f in as_completed(futures)]
  return results
'''

def multithread(big_list: list, func, **kwargs):
    """
    input:
      big_list: list of items to be processed
      func: function to be applied to each item in big_list
      **kwargs: additional keyword arguments to be passed to func:
        max_workers: number of threads to use for processing
    output:
      list of results from applying func to each item in big_list in the same order as big_list
    """
    max_workers = kwargs.pop('max_workers', None)
    iterable_func = partial(func, **kwargs)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
      results = list(executor.map(iterable_func, big_list))

    return results


def list2chunks_generator(input_list:list, num_chunks:int=0, chunk_size:int=0)->Generator[tuple[int,list],None,None]:
    '''
      generates tuple(chunk number, chunk) of input_list
      hint: Generator[YieldType, SendType, ReturnType]
    '''
    list_length = len(input_list)
    if chunk_size:
      num_chunks = ceil(list_length / chunk_size)
    else:
      assert num_chunks > 0, "Either num_chunks or chunk_size must be specified and positive."

    if list_length == 0:
      return 0,[]# Yields nothing for empty list
    if num_chunks == 0:
      yield 0,input_list # Yield the whole list as one chunk

    base_chunk_size = list_length // num_chunks
    remainder = list_length % num_chunks
    start = 0
    for i in range(num_chunks):
      real_chunk_size = base_chunk_size + int(i < remainder) # distributing remainder among chunks
      if real_chunk_size == 0 and start < list_length:
        continue

      end = start + real_chunk_size
      yield i, input_list[start:end]
      start = end
      if start >= list_length:
        break


def bisect(data_list:list, criterion):
    """
    input:
      data_list - list of objects in ascending order
      criterion - function applied to the element in the list. Must return bool

    Returns:
      index of the first element object with true criterion.
    """
    low = 0
    high = len(data_list) - 1
    bisector_index = -1

    while low <= high:
      mid = (low + high) // 2
      if criterion(data_list[mid]):
        bisector_index = mid
        high = mid - 1 # This element's criterion is true, search lower
      else:
        low = mid + 1  # This element's criterion is not true, search higher

    return bisector_index


def attempt_request4(url:str,retries=10,backoff_factor=1):
  retry_strategy = urllib3.Retry(
    total=retries,
    backoff_factor=backoff_factor,
    status_forcelist=[429, 500, 502, 503, 504]
    )
  
  http = urllib3.PoolManager(
        cert_reqs='CERT_REQUIRED',  # Ensure certificate verification is required
        ca_certs=certifi.where(),    # Use certifi's CA bundle
        retries=retry_strategy
    )
  
  try:
    return http.request('GET', url)
  except urllib3.exceptions.MaxRetryError as e:
      print(f"Error: Max retries exceeded: {e}")
      if e.reason:
          print(f"  Reason: {e.reason}")
      return None
  except urllib3.exceptions.NewConnectionError as e:
      print(f"Connection Error: {e}")
      return None
  except urllib3.exceptions.SSLError as e:
      print(f"SSL Error: {e}")
      return None
  except Exception as e:
      print(f"An unexpected error occurred: {e}")
      return None


def most_frequent(data:list,if_data_empty_return=''):
    """
    output:
      most frequently occurring value in a list.
    """
    if not data:
        return None
    counts = Counter(data)
    most_common = counts.most_common(1)
    return most_common[0][0]


def processRNEF(path2rnef:str,how2process_function,**kwargs):
  '''
  Multithreaded processing of "path2rnef" by applying a specified how2process_function to each <resnet> element\n
  input:
    how2process_function - function to process each resnet element.\n
    Must: accept <resnet> element as string as 1st argument and "kwargs" as input, return tuple 
    (node_count:int, control_count:int, pathway_count:int)\n
    Hint: use ResnetGraph.from_resnet or ResnetGraph._parse_nodes_controls to process <resnet> element\n
  '''
  start = time.time()
  max_workers = kwargs.pop('max_workers',None)
  control_counter = 0
  pathway_counter  = 0
  node_counter = 0
  resnet_counter = 0
  with ThreadPoolExecutor(max_workers,thread_name_prefix='ProcessRNEF') as executor:
    futures = []
    max_workers = executor._max_workers
    print(f'Processing {os.path.basename(path2rnef)} file in {max_workers} threads ...')
    MAX_IN_FLIGHT_FUTURES = 2*max_workers
    context = et.iterparse(path2rnef, tag="resnet", recover=True) #huge_tree=True
    for action, resnet_elem in context:
      resnet_str = et.tostring(resnet_elem).decode() # for multithreading pass string not element
      if len(futures) >= MAX_IN_FLIGHT_FUTURES:
        for f in as_completed(futures):
          try:
            node_count, control_count, pathway_count = f.result()
            node_counter += node_count
            control_counter += control_count
            pathway_counter += pathway_count
          except Exception as e:
            print_error_info(executor,how2process_function.__name__)
          futures.remove(f) # Remove the completed future
          break # Break from the as_completed loop to add the new task
      future = executor.submit(how2process_function,resnet_str,**kwargs)
      futures.append(future)
      resnet_counter += 1
      if resnet_counter > 0 and resnet_counter%5000 == 0:
        elapsed_time = execution_time(start)
        print(f'Read {resnet_counter} resnet sections in {elapsed_time}')
        print(f'Processed {node_counter} nodes, {control_counter} controls, {pathway_counter} pathways')
      resnet_elem.clear()
      while resnet_elem.getprevious() is not None:
        del resnet_elem.getparent()[0]
    del context
    elapsed_time = execution_time(start)
    print(f'In total read {resnet_counter} resnet sections in {elapsed_time}')

    for f in as_completed(futures):
      try:
        node_count, control_count, pathway_count = f.result()
        node_counter += node_count
        control_counter += control_count
        pathway_counter += pathway_count
      except Exception as e:
        print_error_info(executor,how2process_function.__name__)
      
    elapsed_time = execution_time(start)
    print(f'Finished processing {node_counter} nodes, {control_counter} controls, {pathway_counter} pathways from "{path2rnef}" in {elapsed_time}')



def plot_distribution(distribution_list:list[dict[str,int|float]],**kwargs):
  '''
    input:
      distribution_list: [{distribution_name:[distribution values]}]
    kwargs: 
      'number_of_bins':int,edgecolor:'black',xlabel:values,ylabel:'counts',title,outdir
  '''
  kwargs['alpha'] = kwargs.pop('alpha',0.5) # transperancy value
  kwargs['bins'] = kwargs.pop('number_of_bins',50)
  kwargs['edgecolor'] = kwargs.pop('edgecolor',"black")
  data_dir = kwargs.pop('outdir','')
  xlabel = kwargs.pop('xlabel',"values")
  ylabel = kwargs.pop('ylabel',"counts")

  for dic in distribution_list:
    for name, distribution in dic.items():
      print(f'Plotting distribution for {name} with {len(distribution)} values')
      counts, bins, patches = plt.hist(distribution, **kwargs)
      if 'label'  not in kwargs:
        max_idx = np.argmax(counts)
        visual_mode = (bins[max_idx] + bins[max_idx + 1]) / 2
        average = round(mean(distribution),3)
        _median = round(median(distribution),3)
        percent_below_avg = round(float(stats.percentileofscore(distribution, average, kind='weak')),2)
        percent_below_mode = round(stats.percentileofscore(distribution, visual_mode, kind='weak'),2)
        skewness = stats.skew(distribution).item()
        new_label = f'Mean: {average}, %ile: {percent_below_avg}\nMedian: {_median}\nMode: {visual_mode}, %ile: {percent_below_mode}\nSkewness: {skewness:.2f}'
      
      plt.legend(handles=[patches], labels=[new_label], loc='upper right')
      plt.xlabel(xlabel)
      plt.ylabel(ylabel)
      plt.title(f'{name}: {len(distribution)}')
      #plt.xlim(xmin=-2, xmax=2)
      #plt.ylim(ymax=1)
      fout = os.path.join(data_dir,name+'.histogram.png')
      plt.savefig(fout)
      y_min, y_max = plt.gca().get_ylim()
      print(f'y-axis scale for "{name}":', y_min, "to", y_max)

  print(f'Finished building plots for {len(distribution_list)} distribution')


def plot_dependecies(Xvalues:list,Yvalues:dict[str,list], **kwargs):
  '''
  Yvalues = {label:[values]}
  '''
  title = kwargs.get('title',"Dependency Graph")
  for label, y_values in Yvalues.items():   
    plt.figure(figsize=(10, 6)) # Optional: Makes the graph larger
    plt.plot(Xvalues, y_values, label=label)
    plt.title(title)
    plt.xlabel(kwargs.get('xlabel',''))
    plt.ylabel(kwargs.get('ylabel',''))
    plt.grid(True) # Optional: Add a grid for better readability
  plt.legend(loc='upper right')
  plt.gca().ticklabel_format(useOffset=False, style='plain')
  #plt.show()# Display the plot
  data_dir = kwargs.pop('outdir','')
  fout = os.path.join(data_dir,title+'.dependency.png')
  plt.savefig(fout)
  print(f'Finished building {len(Yvalues)} dependency plots')


def scatter_plot(Xvalues:list,Yvalues:dict[str,list], **kwargs):
  '''
  Yvalues = {label:[values]}
  kwargs:
    trend_line: default False
  '''
  title = kwargs.get('title',"Scatter plot")
  for label, y_values in Yvalues.items():
    plt.plot(Xvalues, y_values,'o', label=label) # 'o' = marker='o', linestyle='none'
    if kwargs.get('trend_line',False):
      z = np.polyfit(Xvalues, y_values, 1)
      p = np.poly1d(z)
      plt.plot(Xvalues, p(Xvalues), "r--", label='Trend Line')
    plt.title(title)
    plt.xlabel(kwargs.get('xlabel',''))
    plt.ylabel(kwargs.get('ylabel',''))
    plt.grid(True) # Optional: Add a grid for better readability
  plt.legend(loc='upper right')
  plt.gca().ticklabel_format(useOffset=False, style='plain')
  #plt.show()# Display the plot
  data_dir = kwargs.pop('outdir','')
  fout = os.path.join(data_dir,title+'.scatter.png')
  plt.savefig(fout)
  print(f'Finished building {len(Yvalues)} scatter plots')


class Tee(object):
    def __init__(self, filename, mode="w"):
        self.file = open(filename, mode,encoding='utf-8')
        self.stdout = sys.stdout
        print(f'Runtime messages will be in {filename}')

    def write(self, data):
        self.file.write(data)
        self.stdout.write(data)

    def flush(self):
        self.file.flush()
        self.stdout.flush()

    def __enter__(self):
        sys.stdout = self  # Redirect stdout to this object

    def __exit__(self, exc_type, exc_value, traceback):
        sys.stdout = self.stdout  # Restore original stdout