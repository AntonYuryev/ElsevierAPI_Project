from ElsevierAPI.utils.utils import execution_time, Tee, time,datetime, json
from ElsevierAPI.api.ResnetAPI.Drugs4Disease import Drugs4Targets
from ElsevierAPI.api.ResnetAPI.PathwayStudioZeepAPI import load_api_config


def do_the_job(dt:Drugs4Targets):
    dt.make_report()
    # dt.add_etm_refs('Drugs',['glioma'])

    report_fpath = dt.report_path('.xlsx')
    dt.print_report(report_fpath)

    raw_data_fpath= dt.report_path('_raw_data.xlsx')
    dt.print_rawdata(raw_data_fpath)

    dt.clear()
    

if __name__ == "__main__":
    print(f'Script was started at {datetime.now()}')
    start = time.time()
    parameters_list = list(json.load(open("configs/drugs4diseases_parameters.json", "r")))
    
    for parameters in parameters_list:
      assert isinstance(parameters,dict)
      skip = parameters.pop('skip', False)
      if not skip:
        with Tee(log_path):
          disease_start = time.time()
          print(f'Finding drugs for {parameters["disease"]}')
          print(f'Script started at {datetime.fromtimestamp(disease_start)}')
          dt = Drugs4Targets(load_api_config(), **parameters)
          log_path = dt.report_path('.log')
          print(f'Runtime messages will be written to "{log_path}"')  
          do_the_job(dt)

        print(f'{parameters["disease"]} finished in {execution_time(disease_start)} at {datetime.now()}')
        print(f'Total script execution time: {execution_time(start)}')

    print(f'Script finished in {execution_time(start)} at {datetime.now()}')
