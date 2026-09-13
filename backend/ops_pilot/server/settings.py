"""运行配置加载（无第三方依赖）。

启动时按顺序读取（已存在的环境变量优先，不覆盖）：
1. <仓库根>/.env       —— 凭据与本地配置（已 gitignore）
2. <仓库根>/key.txt    —— 兼容既有文件（KEY=VALUE 或裸 sk- key）

安全：只读入内存，不打印、不落库（§A6.4）。
"""
from __future__ import annotations

import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]     # OpsPilot/
_ENV_FILE = REPO_ROOT / ".env"
_KEY_FILE = REPO_ROOT / "key.txt"

_LOADED = False


def _load_file(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()   # 去行内注释
            key = key.strip()
        elif line.startswith("sk-"):        # 裸模型密钥（key.txt 的实际格式）
            key, value = "DEEPSEEK_API_KEY", line
        else:
            continue
        if key and key not in os.environ:
            os.environ[key] = value
            count += 1
    return count


def load_env(force: bool = False) -> dict[str, int]:
    """幂等加载；返回每个文件的载入条数（不含内容）。"""
    global _LOADED
    if _LOADED and not force:
        return {}
    _LOADED = True
    return {"env": _load_file(_ENV_FILE), "key": _load_file(_KEY_FILE)}


def repo_root() -> Path:
    return REPO_ROOT
