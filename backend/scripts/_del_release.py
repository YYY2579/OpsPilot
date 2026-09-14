import json, urllib.request

tok = open(r'C:\Users\25791\Desktop\github密钥.txt', encoding='utf-8').read().strip()
if ' ' in tok:
    tok = tok.split()[-1]
H = {'Authorization': 'Bearer ' + tok, 'Accept': 'application/vnd.github+json', 'User-Agent': 'ops'}
REPO = '/repos/YYY2579/OpsPilot'


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request('https://api.github.com' + REPO + path, data=data,
                               headers=H, method=method)
    try:
        resp = urllib.request.urlopen(r, timeout=60)
    except urllib.error.HTTPError as e:
        return {'_error': e.code, '_body': e.read()[:200].decode('utf-8', 'ignore')}
    raw = resp.read()
    if not raw.strip():                    # 204 No Content（DELETE 的正常返回）
        return {'ok': True, 'status': resp.status}
    return json.loads(raw)


# 1) 删 v0.1.0 release（连不上后端的空壳，留着会误导）
rel = api('GET', '/releases/tags/v0.1.0')
if '_error' in rel:
    print('release v0.1.0 not found:', rel['_error'])
else:
    rid = rel['id']
    for a in rel.get('assets', []):
        r = api('DELETE', f'/releases/assets/{a["id"]}')
        print('  asset deleted', a['name'], '->', 'ok' if '_error' not in r else r['_error'])
    r = api('DELETE', f'/releases/{rid}')
    print('release v0.1.0 deleted ->', 'ok' if '_error' not in r else r)

# 2) 清理其余未发布的旧 release（v0.1.1/v0.1.2/v0.1.3 都是中间态，只保留最终版）
for tag in ('v0.1.1', 'v0.1.2', 'v0.1.3'):
    r = api('GET', f'/releases/tags/{tag}')
    if '_error' in r:
        print(f'{tag}: no release (ok)')
        continue
    print(f'{tag}: has release id={r["id"]} — 保留待合并说明')

print()
print('--- remaining releases ---')
for r in api('GET', '/releases'):
    print(' ', r['tag_name'], r['id'], 'assets=', len(r.get('assets', [])))
