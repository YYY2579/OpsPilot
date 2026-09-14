import json, urllib.request, os, zipfile, sys

tok = open(r'C:\Users\25791\Desktop\github密钥.txt', encoding='utf-8').read().strip()
if ' ' in tok:
    tok = tok.split()[-1]
H = {'Authorization': 'Bearer ' + tok, 'Accept': 'application/vnd.github+json', 'User-Agent': 'ops'}
BASE_OUT = r'C:\Users\25791\Desktop\OpsPilot\dist-release'
RUN_ID = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].isdigit() else "34863672023"
WANT = [a for a in sys.argv[1:] if not a.isdigit()]
OUT = os.path.join(BASE_OUT, "artifacts-" + (os.environ.get("REL_TAG") or RUN_ID))
os.makedirs(OUT, exist_ok=True)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


op_no = urllib.request.build_opener(NoRedirect)
op_ok = urllib.request.build_opener()


def api(path):
    return json.load(urllib.request.urlopen(
        urllib.request.Request('https://api.github.com' + path, headers=H), timeout=60))


def dl_nofollow(url, dest):
    try:
        r = op_no.open(urllib.request.Request(url, headers=H), timeout=120)
    except urllib.error.HTTPError as e:
        if e.code not in (302, 301):
            raise
        r = op_ok.open(urllib.request.Request(e.headers['Location'],
                                              headers={'User-Agent': 'ops'}), timeout=600)
    data = r.read()
    open(dest, 'wb').write(data)
    return len(data)


ar = api('/repos/YYY2579/OpsPilot/actions/runs/34863672023/artifacts')
for a in ar['artifacts']:
    if WANT and a['name'] not in WANT:
        continue
    zp = os.path.join(OUT, a['name'] + '.zip')
    if os.path.exists(zp) and os.path.getsize(zp) > 1024:
        print('SKIP(exists)', a['name'])
        continue
    n = dl_nofollow(a['archive_download_url'], zp)
    z = zipfile.ZipFile(zp)
    names = [x for x in z.namelist() if not x.startswith('_')]
    z.extractall(os.path.join(OUT, a['name']))
    print(f"OK {a['name']:26} {n//1024:7} KB -> {names[:8]}", flush=True)
print('DONE')
