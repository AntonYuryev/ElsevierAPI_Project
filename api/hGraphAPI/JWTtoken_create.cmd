curl -X POST \
  https://jwt-creator.access-controls.dev.platform.healthcare.elsevier.com/token \
  -H 'Accept: */*' \
  -H 'Authorization: Basic ZTk5Y2MzMGJkZjc1OGMyMjA2MDE1YjNmZjNhN2RkMTE6ZjlmY2JiZTFlZDk0MjM0NjM5YTBjYWU3OWZjOTJlMDU=' \
  -H 'Cache-Control: no-cache' \
  -H 'Connection: keep-alive' \
  -H 'Host: jwt-creator.access-controls.dev.platform.healthcare.elsevier.com' \
  -H 'Postman-Token: 5fb9186f-70f0-4941-b9bf-8befde290796,293c1ccc-1bfd-433b-90b0-f781945ff8b8' \
  -H 'User-Agent: PostmanRuntime/7.15.0' \
  -H 'accept-encoding: gzip, deflate' \
  -H 'cache-control: no-cache' \
  -H 'content-length: '

pause


curl -X GET \
  'https://kong.cert.platform.healthcare.elsevier.com/h/knowledge/graph/concept/search?query=hepatitis' \
  -H 'Accept: */*' \
  -H 'Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJleHAiOjE2NjI2NTc0NzIsImlzcyI6ImU5OWNjMzBiZGY3NThjMjIwNjAxNWIzZmYzYTdkZDExIiwiaHR0cDovL2tvbmcuY29tL2NsYWltcy9hcHBsaWNhdGlvbm5hbWUiOiJoLWdyYXBoLW5vbnByb2QifQ.SxHRiMyPSG1AzpAYGLAGfZeE9Dg-at7-HQAXLxoUFXI' \
  -H 'Cache-Control: no-cache' \
  -H 'Connection: keep-alive' \
  -H 'Host: kong.cert.platform.healthcare.elsevier.com' \
  -H 'Postman-Token: 6fd471c8-6715-4635-9240-693270974133,3c181ce3-d50e-4267-9131-a3e65cfc5091' \
  -H 'User-Agent: PostmanRuntime/7.15.0' \
  -H 'accept-encoding: gzip, deflate' \
  -H 'cache-control: no-cache' \
  -H 'cookie: AWSALB=eNX95cQ6Y67ZQtxQOM5hbSuqzhuJF0q/jI361o5c+4kY8vnN09RpYtVWTM/r8+H5UlKQeHFhRg8DktPLsCFeI6u04Z0R9fjdTfttczH+jJHvQ9gtaJSfmgdnDT25; AWSALBCORS=eNX95cQ6Y67ZQtxQOM5hbSuqzhuJF0q/jI361o5c+4kY8vnN09RpYtVWTM/r8+H5UlKQeHFhRg8DktPLsCFeI6u04Z0R9fjdTfttczH+jJHvQ9gtaJSfmgdnDT25' \
  -b 'AWSALB=eNX95cQ6Y67ZQtxQOM5hbSuqzhuJF0q/jI361o5c+4kY8vnN09RpYtVWTM/r8+H5UlKQeHFhRg8DktPLsCFeI6u04Z0R9fjdTfttczH+jJHvQ9gtaJSfmgdnDT25; AWSALBCORS=eNX95cQ6Y67ZQtxQOM5hbSuqzhuJF0q/jI361o5c+4kY8vnN09RpYtVWTM/r8+H5UlKQeHFhRg8DktPLsCFeI6u04Z0R9fjdTfttczH+jJHvQ9gtaJSfmgdnDT25'