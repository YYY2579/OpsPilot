import json, urllib.request, os, sys, urllib.parse

tok = open(r'C:\Users\25791\Desktop\github密钥.txt', encoding='utf-8').read().strip()
if ' ' in tok:
    tok = tok.split()[-1]
REL = open(r'C:\Users\25791\Desktop\OpsPilot\.release_id').read().strip()
BASE = 'https://uploads.github.com/repos/YYY2579/OpsPilot/releases/' + REL + '/assets'

FILES = {
    'win-exe': r'C:\Users\25791\Desktop\OpsPilot\dist-release\artifacts\opspilot-windows-x64\nsis\OpsPilot_0.1.0_x64-setup.exe',
    'win-msi': r'C:\Users\25791\Desktop\OpsPilot\dist-release\artifacts\opspilot-windows-x64\msi\OpsPilot_0.1.0_x64_en-US.msi',
    'mac-arm': r'C:\Users\25791\Desktop\OpsPilot\dist-release\artifacts\opspilot-macos-arm64\dmg\OpsPilot_0.1.0_aarch64.dmg',
    'mac-x64': r'C:\Users\25791\Desktop\OpsPilot\dist-release\artifacts\opspilot-macos-x64\dmg\OpsPilot_0.1.0_x64.dmg',
    'linux-deb': r'C:\Users\25791\Desktop\OpsPilot\dist-release\artifacts\opspilot-linux-x64\deb\OpsPilot_0.1.0_amd64.deb',
    'linux-appimage': r'C:\Users\25791\Desktop\OpsPilot\dist-release\artifacts\opspilot-linux-x64\appimage\OpsPilot_0.1.0_amd64.AppImage',
}
CT = {'.exe': 'application/vnd.microsoft.portable-executable',
      '.msi': 'application/x-msi',
      '.dmg': 'application/x-apple-diskimage',
      '.deb': 'application/vnd.debian.binary-package',
      '.AppImage': 'application/x-executable'}

want = sys.argv[1:] or list(FILES)
for key in want:
    path = FILES[key]
    name = os.path.basename(path)
    ext = os.path.splitext(name)[1]
    data = open(path, 'rb').read()
    url = BASE + '?' + urllib.parse.urlencode({'name': name})
    r = urllib.request.Request(url, data=data, method='POST', headers={
        'Authorization': 'Bearer ' + tok,
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'ops',
        'Content-Type': CT.get(ext, 'application/octet-stream'),
    })
    try:
        j = json.load(urllib.request.urlopen(r, timeout=900))
        print(f'OK   {name:40} {j["size"]//1024} KB  id={j["id"]}', flush=True)
    except urllib.error.HTTPError as e:
        print(f'FAIL {name:40} {e.code} {e.read()[:200]}', flush=True)
print('DONE')
