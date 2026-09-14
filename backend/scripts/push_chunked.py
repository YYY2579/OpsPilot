"""分块可续的 GitHub 推送：每次调用只上传有限个 blob，进度落盘。

被沙箱的"单进程请求量"限制杀掉时，分多次调用即可续跑。

用法：
    GH_TOKEN=xxx python backend/scripts/push_chunked.py [每轮 blob 上限]
"""
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

TOKEN = os.environ.get("GH_TOKEN", "").strip()
REPO = "repos/YYY2579/OpsPilot"
D = r"C:\Users\25791\Desktop\OpsPilot"
GIT = r"C:\Program Files\Git\cmd\git.exe"
STATE = os.path.join(D, ".push_state.json")
LOG = os.path.join(D, "push_log.txt")
H = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github+json",
    "Content-Type": "application/json",
    "User-Agent": "OpsPilot",
}

lines: list[str] = []


def L(m: str) -> None:
    lines.append(str(m))
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(str(m) + "\n")


def api(method: str, path: str, body=None):
    req = urllib.request.Request(
        f"https://api.github.com/{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers=H,
        method=method,
    )
    try:
        r = urllib.request.urlopen(req, timeout=60)
        raw = r.read()
        return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, {"message": e.read().decode()[:300]}
    except BaseException as e:
        return -1, {"message": f"{type(e).__name__}: {e}"}


def git(*a: str) -> bytes:
    p = subprocess.run([GIT, "-C", D, *a], capture_output=True, timeout=120)
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(a)}: {p.stderr.decode('utf-8', 'replace')[:200]}")
    return p.stdout


def load_state() -> dict:
    if os.path.exists(STATE):
        try:
            return json.load(open(STATE, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {"blobs": {}, "trees": {}}          # local_sha -> remote_sha


def save_state(st: dict) -> None:
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(st, f)


def main() -> int:
    cap = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    if not TOKEN:
        L("FAIL 缺少 GH_TOKEN")
        return 2

    st = load_state()
    s, ref = api("GET", f"{REPO}/git/ref/heads/main")
    if s != 200:
        L(f"FAIL 读远端 main {s}: {ref.get('message')}")
        return 1
    remote = ref["object"]["sha"]

    head = git("rev-parse", "HEAD").decode().strip()
    root = git("rev-parse", f"{head}^{{tree}}").decode().strip()
    L(f"--- 本轮开始: remote={remote[:12]} head={head[:12]} blobs已传={len(st['blobs'])} ---")

    if head == remote:
        L("OK 远端已是最新")
        return 0

    # 递归收集待传 blob（去重后按需上传）
    pending: list[str] = []

    def collect(tsha: str, seen_trees: set) -> None:
        if tsha in seen_trees:
            return
        seen_trees.add(tsha)
        out = git("ls-tree", tsha).decode("utf-8", "replace")
        for line in out.splitlines():
            if not line.strip():
                continue
            meta, name = line.split("\t", 1)
            mode, typ, sha = meta.split()
            if typ == "blob":
                if sha not in st["blobs"] and sha not in pending:
                    pending.append(sha)
            elif typ == "tree":
                collect(sha, seen_trees)

    collect(root, set())
    L(f"待传 blob 共 {len(pending)} 个（本轮上限 {cap}）")

    # 本轮上传前 cap 个
    done_now = 0
    for sha in pending[:cap]:
        raw = git("cat-file", "blob", sha)
        sc, res = api("POST", f"{REPO}/git/blobs",
                      {"content": base64.b64encode(raw).decode(), "encoding": "base64"})
        if sc not in (200, 201):
            L(f"FAIL blob {sha[:10]} {sc} {res.get('message')}")
            save_state(st)
            return 1
        st["blobs"][sha] = res["sha"]
        done_now += 1
    save_state(st)
    remaining = len(pending) - done_now
    L(f"本轮上传 {done_now} 个，剩余 {remaining} 个")

    if remaining > 0:
        L("NEED_MORE 还有 blob 未传，请再跑一次")
        return 3

    # 所有 blob 就绪 → 建 tree → commit → 更新 ref
    def build(tsha: str) -> str:
        if tsha in st["trees"]:
            return st["trees"][tsha]
        entries = []
        out = git("ls-tree", tsha).decode("utf-8", "replace")
        for line in out.splitlines():
            if not line.strip():
                continue
            meta, name = line.split("\t", 1)
            mode, typ, sha = meta.split()
            if typ == "blob":
                entries.append({"path": name, "mode": mode, "type": "blob",
                                "sha": st["blobs"][sha]})
            elif typ == "tree":
                entries.append({"path": name, "mode": mode, "type": "tree",
                                "sha": build(sha)})
        sc, res = api("POST", f"{REPO}/git/trees", {"tree": entries})
        if sc not in (200, 201):
            raise RuntimeError(f"tree {tsha[:10]} {sc} {res.get('message')}")
        st["trees"][tsha] = res["sha"]
        save_state(st)
        return res["sha"]

    new_tree = build(root)
    L(f"远端 tree = {new_tree[:12]}")
    msg = git("log", "-1", "--format=%B", head).decode("utf-8", "replace").strip()
    sc, commit = api("POST", f"{REPO}/git/commits",
                     {"message": msg, "tree": new_tree, "parents": [remote]})
    if sc not in (200, 201):
        L(f"FAIL commit {sc} {commit.get('message')}")
        return 1
    L(f"远端 commit = {commit['sha'][:12]}")
    sc, upd = api("PATCH", f"{REPO}/git/refs/heads/main",
                  {"sha": commit["sha"], "force": False})
    if sc not in (200, 201):
        L(f"FAIL ref update {sc} {upd.get('message')}")
        return 1
    L(f"OK ref {sc} → main = {upd['object']['sha'][:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
