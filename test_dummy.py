import urllib.request, json
url = "http://127.0.0.1:5050/api/search_probid?q=2024.9%EB%AA%A8%5F"
req = urllib.request.Request(url)
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode())
    for r in data['results']:
        if r['step_id'] is None:
            print("FOUND DUMMY:", r['problem_id'])
