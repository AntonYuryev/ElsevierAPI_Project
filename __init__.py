
from .ElsevierAPI.api.ResnetAPI.ResnetAPISession import open_api_session
from .ElsevierAPI.utils.utils import load_api_config

# __init__.py is the main entry point for the package. 
# It defines what is imported when you import ElsevierAPI and can also contain package-level variables and functions.
# open_api_session must be defined here to be accessible when importing ElsevierAPI. It creates and returns an instance of APISession using the API configuration loaded from a file.
