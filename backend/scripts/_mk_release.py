"""创建 GitHub Release 并上传四平台安装包。

用法:
    python backend/scripts/_mk_release.py v0.1.5

产物目录约定:
    dist-release/artifacts-<tag>/<artifact-name>/{nsis,msi,dmg,deb,appimage}/...
"""
import json, os, sys, glob, urllib.parse, urllib.request, urllib.error

REPO = "YYY2579/OpsPilot"
TAG = sys.argv[1] if len(sys.argv) > 1 else "v0.1.5"
BASE = r"C:\Users\25791\Desktop\OpsPilot\dist-release\artifacts-" + TAG

tok = open(r"C:\Users\25791\Desktop\github密钥.txt", encoding="utf-8").read().strip()
if " " in tok:
    tok = tok.split()[-1]
H = {"Authorization": "Bearer " + tok,
     "Accept": "application/vnd.github+json",
     "User-Agent": "opspilot"}

NOTES = """## OpsPilot {tag}

### 这次修的是什么

桌面端此前「点哪哪不动」——界面渲染正常，但 27 条接口全部静默失败。

**根因**：Tauri v2 只要配了 `build.frontendDist`，构建时就会把 `windows[].url` **覆盖回本地资源**。
壳因此一直加载打进去的本地前端，而 `tauri://` 下的 `fetch("/api/...")` 是跨源的，被 WebView 拦截且**不报错**。

**修法（v0.1.5 跳转壳）**：打进壳的 `dist` 只放一个跳转页，加载后立刻跳到
`http://127.0.0.1:8791`（后端同源托管的真正前端）。跳转之后页面与 API 完全同源。

> 早期版本 v0.1.0 已作废删除，不要用。

### ⚠️ 必须先起后端

**安装包里不含 Python 后端。** 它只是一个窗口（会自动跳到后端）。后端没起，窗口就停在排查提示页——这是设计，不是故障。

```bat
:: 方式一：一键（推荐）
启动 OpsPilot.bat

:: 方式二：手动
backend\\.venv\\Scripts\\python.exe -m uvicorn ops_pilot.server.app:app --host 127.0.0.1 --port 8791
```

也可以不装桌面端，后端起来后浏览器直接开 <http://127.0.0.1:8791>。

### 实机验收证据

| 项 | 结果 |
|---|---|
| 后端 `127.0.0.1:8791` | `LISTENING` |
| 壳内页面 → 后端 | **`ESTABLISHED` ×3**（`127.0.0.1:52337/54561/64756 → 8791`） |
| `/api/connections/servers` | `200`，返回真实靶机 `156.224.28.147` |
| 后端测试 | 199 passed |
| 前端类型检查 | `tsc -b --force` 0 error |

### 四平台产物

| 平台 | 文件 |
|---|---|
| Windows x64 | `OpsPilot_{v}_x64-setup.exe`（NSIS）/ `OpsPilot_{v}_x64_en-US.msi` |
| macOS ARM64 | `OpsPilot_{v}_aarch64.dmg` |
| macOS x64 | `OpsPilot_{v}_x64.dmg` |
| Linux x64 | `OpsPilot_{v}_amd64.deb` / `OpsPilot_{v}_amd64.AppImage` |

### 已知限制

- 桌面壳不含后端，无 PyInstaller sidecar，需手动起后端
- 开源版 OpenHands 无内置认证（JWT 未做），仅限本机/内网单机使用
- 无系统托盘 / 开机自启；底部面板（实时终端）MVP 置灰，v2 再做
""".replace("{tag}", TAG).replace("{v}", TAG.lstrip("v"))

CT = {".exe": "application/vnd.microsoft.portable-executable",
      ".msi": "application/x-msi",
      ".dmg": "application/x-apple-diskimage",
      ".deb": "application/vnd.debian.binary-package",
      ".AppImage": "application/x-executable"}


def api(path, data=None, method=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request("https://api.github.com" + path,
                                 data=body, method=method, headers=H)
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
        return json.loads(raw) if raw.strip() else {"ok": True, "status": r.status}
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read()[:400].decode("utf-8", "replace"))
        raise


# 1) 建 release
rel = api(f"/repos/{REPO}/releases",
          {"tag_name": TAG, "name": f"OpsPilot {TAG}",
           "body": NOTES, "draft": False, "prerelease": True},
          method="POST")
rid = rel["id"]
open(r"C:\Users\25791\Desktop\OpsPilot\.release_id", "w").write(str(rid))
print("release created:", rid, rel.get("html_url"))

# 2) 收集产物
# 只收该版本的文件名。不过滤的话，目录里残留的旧版本包会被一起传上去。
V = TAG.lstrip("v")
pats = [f"*/nsis/*{V}*.exe", f"*/msi/*{V}*.msi", f"*/dmg/*{V}*.dmg",
        f"*/deb/*{V}*.deb", f"*/appimage/*{V}*.AppImage"]
files = []
for p in pats:
    files += sorted(glob.glob(os.path.join(BASE, p)))
files = [f for f in files if "sig" not in f.lower()]
files = [f for f in files if V in os.path.basename(f)]
if not files:
    print("NO FILES under", BASE)
    sys.exit(1)

# 3) 上传
UP = f"https://uploads.github.com/repos/{REPO}/releases/{rid}/assets"
for path in files:
    name = os.path.basename(path)
    ext = os.path.splitext(name)[1]
    data = open(path, "rb").read()
    url = UP + "?" + urllib.parse.urlencode({"name": name})
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Authorization": "Bearer " + tok,
        "Accept": "application/vnd.github+json",
        "User-Agent": "opspilot",
        "Content-Type": CT.get(ext, "application/octet-stream"),
    })
    try:
        j = json.load(urllib.request.urlopen(req, timeout=900))
        print(f"OK   {name:42} {j['size']//1024:>7} KB  id={j['id']}", flush=True)
    except urllib.error.HTTPError as e:
        print(f"FAIL {name:42} {e.code} {e.read()[:200]}", flush=True)

print("DONE ->", rel.get("html_url"))
