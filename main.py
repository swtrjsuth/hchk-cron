import urllib.request
import json

payload = {'test':'123'}
request = urllib.request.Request(
    'https://webhook.site/3dd7f803-bc1b-4e91-9157-852eb36c9d2d',
    headers={'x-test':'test', 'Content-Type':'application/json'},
    data=json.dumps(payload).encode('utf-8'),
    method="POST"
    )
response = urllib.request.urlopen(request)
print(response.read().decode('utf8'))
