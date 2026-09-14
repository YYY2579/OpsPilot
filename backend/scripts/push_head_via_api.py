#!/usr/bin/env python3
"""把本地提交以 GitHub Git Data API 方式推送到远端（当 git push 被代理阻断时用）。

与 backend/scripts/push_via_api.py 的区别：
后者要求"远端基线 == 本地提交的 parent"，因此**每一次本地提交都必须逐一推送**。
本脚本用于**跨多个本地提交**的场景：以远端当前 main 为唯一 parent，
把本地 HEAD 的完整 tree 提交上去（等价于 squash push）。

用法:
    GH_TOKEN=xxx python scripts/push_head_via_api.py <本地提交sha>
"""
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

TOKEN = os.environ.get("GH_TOKEN", "")
REPO = "repos/YYY2579/OpsPilot"
D = r"C:\Users\25791\Desktop\OpsPilot"
GIT = r"C:\Program Files\Git\cmd\git.exe"
H = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github+json",
    "Content-Type": "application/json",
    "User-Agent": "OpsPilot",
}


def api(method: str, path: str, body=None):
    req = urllib.request.Request(
        f"https://api.github.com/{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers=H,
        method=method,
    )
    try:
        resp = urllib.request.urlopen(req, timeout=90)
        raw = resp.read()
        return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        return exc.code, {"message": exc.read().decode()[:400]}


def git(*args: str) -> bytes:
    return subprocess.run([GIT, "-C", D, *args], capture_output=True, timeout=120).stdout


def upload_blob(sha: str) -> str:
    """把本地 blob 上传到远端，返回远端 blob sha（内容相同则 sha 相同）。"""
    raw = git("cat-file", "blob", sha)
    status, res = api("POST", f"{REPO}/git/blobs",
                      {"content": base64.b64encode(raw).decode(), "encoding": "base64"})
    if status not in (200, 201):
        raise RuntimeError(f"blob {sha[:10]} 上传失败 {status}: {res.get('message')}")
    return res["sha"]


def build_tree(local_tree_sha: str) -> str:
    """递归把本地 tree 重建到远端（逐层上传 blob 与 tree），返回远端 tree sha。"""
    entries = []
    # ls-tree 输出: <mode> <type> <sha>\t<name>
    out = git("ls-tree", local_tree_sha).decode("utf-8", "replace")
    for line in out.splitlines():
        if not line.strip():
            continue
        meta, name = line.split("\t", 1)
        mode, typ, sha = meta.split()
        if typ == "blob":
            entries.append({"path": name, "mode": mode, "type": "blob",
                            "sha": upload_blob(sha)})
        elif typ == "tree":
            entries.append({"path": name, "mode": mode, "type": "tree",
                            "sha": build_tree(sha)})
    status, res = api("POST", f"{REPO}/git/trees", {"tree": entries})
    if status not in (200, 201):
        raise RuntimeError(f"tree 上传失败 {status}: {res.get('message')}")
    return res["sha"]


def main() -> None:
    if not TOKEN:
        raise SystemExit("缺少 GH_TOKEN")
    local = sys.argv[1] if len(sys.argv) > 1 else "HEAD"

    status, ref = api("GET", f"{REPO}/git/ref/heads/main")
    if status != 200:
        raise SystemExit(f"读取远端 main 失败 {status}: {ref.get('message')}")
    remote_sha = ref["object"]["sha"]
    print(f"远端 main = {remote_sha[:12]}")

    head_sha = git("rev-parse", local).decode().strip()
    message = git("log", "-1", "--format=%B", head_sha).decode("utf-8", "replace").strip()
    tree_sha = git("rev-parse", f"{head_sha}^{{tree}}").decode().strip()
    print(f"本地 {local} = {head_sha[:12]}  tree={tree_sha[:12]}")

    if head_sha == remote_sha:
        print("✓ 远端已是最新，无需推送")
        return

    new_tree = build_tree(tree_sha)
    print(f"远端 tree = {new_tree[:12]}")

    status, commit = api("POST", f"{REPO}/git/commits",
                         {"message": message, "tree": new_tree, "parents": [remote_sha]})
    if status not in (200, 201):
        raise SystemExit(f"创建 commit 失败 {status}: {commit.get('message')}")
    print(f"远端 commit = {commit['sha'][:12]}")

    status, updated = api("PATCH", f"{REPO}/git/refs/heads/main",
                          {"sha": commit["sha"], "force": False})
    if status not in (200, 201):
        raise SystemExit(f"更新 ref 失败 {status}: {updated.get('message')}")
    print(f"✓ ref: {status} → main = {updated['object']['sha'][:12]}")


if __name__ == "__main__":
    main()
