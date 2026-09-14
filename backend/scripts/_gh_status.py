import json, urllib.request

tok = open(r'C:\Users\25791\Desktop\github密钥.txt', encoding='utf-8').read().strip()
if ' ' in tok:
    tok = tok.split()[-1]
H = {'Authorization': 'Bearer ' + tok, 'Accept': 'application/vnd.github+json', 'User-Agent': 'ops'}


def api(path):
    return json.load(urllib.request.urlopen(
        urllib.request.Request('https://api.github.com' + path, headers=H), timeout=60))


d = api('/repos/YYY2579/OpsPilot/actions/runs?per_page=3')
for r in d['workflow_runs']:
    print(r['id'], r['status'], r['conclusion'], r['head_branch'], r['created_at'])
run = d['workflow_runs'][0]['id']
if d['workflow_runs'][0]['status'] != 'completed':
    js = api(f'/repos/YYY2579/OpsPilot/actions/runs/{run}/jobs')
    for j in js['jobs']:
        print(f"  [{j['status']:12}] {str(j['conclusion']):8} {j['name'][:55]}")
