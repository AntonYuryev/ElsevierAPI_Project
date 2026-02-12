SET WSDL_URL=https://psweb-profservices.pathwaystudio.com//services/SputnikServiceSoap?WSDL

python -mzeep %WSDL_URL% 1>PSG@PSE_WSDL_psweb.txt
pause
