#!/usr/bin/env python3
"""通过 GitHub Git Data API 推送本地提交（当 git push 被网络/代理阻断时的替代方案）。

用法: python push_via_api.py <本地提交sha短号>
原理: 复刻本地 commit 对象（blob/tree/commit 逐字节一致）到远端，更新 main ref。
前提: GH_TOKEN 有效、远端基线 = 本地提交的 parent。
"""
import json, urllib.request, urllib.error, base64, subprocess, os, sys
from datetime import datetime, timezone, timedelta

TOKEN = os.environ.get("GH_TOKEN", "")
REPO = "repos/YYY2579/OpsPilot"
D = r"C:\Users\25791\Desktop\OpsPilot"
GIT = r"C:\Program Files\Git\cmd\git.exe"
H = {"Authorization": f"token {TOKEN}", "Accept": "application/vnd.github+json",
     "Content-Type": "application/json", "User-Agent": "OpsPilot"}


def api(method, path, body=None):
    req = urllib.request.Request(f"https://api.github.com/{path}",
        data=json.dumps(body).encode() if body is not None else None, headers=H, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        raw = resp.read()
        return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        return e.code, {"message": e.read().decode()[:400]}


def g(*a):
    r = subprocess.run([GIT, "-C", D] + list(a), capture_output=True, timeout=60)
    return (r.stdout or r.stderr).decode("utf-8", "replace").strip()


def parse_commit(sha):
    raw = subprocess.run([GIT, "-C", D, "cat-file", "commit", sha],
                         capture_output=True, timeout=30).stdout.decode("utf-8", "replace")
    head, msg = raw.split("\n\n", 1)
    info = {}
    for ln in head.splitlines():
        for k, p in [("tree", "tree "), ("parent", "parent "),
                     ("author", "author "), ("committer", "committer ")]:
            if ln.startswith(p):
                info[k] = ln[len(p):]
    info["message"] = msg
    return info


def iso(field):
    name_email, ts, tz = field.rsplit(" ", 2)
    sign = 1 if tz.startswith("+") else -1
    dt = datetime.fromtimestamp(int(ts),
        tz=timezone(sign * timedelta(hours=int(tz[1:3]), minutes=int(tz[3:5]))))
    return dt.isoformat()


def push(commit_short):
    c = parse_commit(commit_short)
    parent = c["parent"]
    local_full = g("rev-parse", commit_short)

    # 校验远端基线
    s, ref = api("GET", f"{REPO}/git/ref/heads/main")
    assert s == 200, ref
    remote = ref["object"]["sha"]
    if remote != parent:
        print(f"✗ 远端 main ({remote[:12]}) != 本地 parent ({parent[:12]})，先同步")
        sys.exit(1)

    # 上传变更 blob
    changed = g("diff", "--name-only", parent[:7], commit_short).split()
    print(f"提交 {local_full[:12]}，变更 {len(changed)} 个文件")
    entries = []
    for path in changed:
        content = open(os.path.join(D, path), "rb").read()
        s, b = api("POST", f"{REPO}/git/blobs",
                   {"content": base64.b64encode(content).decode(), "encoding": "base64"})
        assert s == 201, (path, s, b)
        local_blob = subprocess.run([GIT, "-C", D, "hash-object", "--stdin"],
                                    input=content, capture_output=True, timeout=30).stdout.decode().strip()
        mark = "✓" if b["sha"] == local_blob else "✗"
        print(f"  {mark} {path}")
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": b["sha"]})

    # 建树
    s, pc = api("GET", f"{REPO}/git/commits/{parent}")
    assert s == 200, pc
    s, t = api("POST", f"{REPO}/git/trees", {"base_tree": pc["tree"]["sha"], "tree": entries})
    assert s == 201, t
    ok = "✓" if t["sha"] == c["tree"] else "✗"
    print(f"  tree {ok} {t['sha'][:12]}")

    # 建 commit
    name_email = c["committer"].rsplit(" ", 2)[0]
    name, email = name_email.rsplit(" <", 1)
    email = email.rstrip(">")
    body = {"message": c["message"], "tree": t["sha"], "parents": [parent],
            "author": {"name": name, "email": email, "date": iso(c["author"])},
            "committer": {"name": name, "email": email, "date": iso(c["committer"])}}
    s, nc = api("POST", f"{REPO}/git/commits", body)
    assert s == 201, nc
    match = nc["sha"] == local_full
    print(f"  commit {'✓ 一致' if match else '✗ 不一致'} {nc['sha'][:12]}")

    # 更新 ref
    s, r = api("PATCH", f"{REPO}/git/refs/heads/main", {"sha": nc["sha"], "force": False})
    print(f"  ref: {s} → main = {r.get('object', {}).get('sha', '?')[:12]}")
    return match


if __name__ == "__main__":
    push(sys.argv[1] if len(sys.argv) > 1 else "HEAD")
