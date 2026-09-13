"""诊断结论与错误码体系。

对外暴露：Diagnosis / ok / fail / not_implemented / 错误码常量表。
"""
from __future__ import annotations

from ops_pilot.diagnostics.codes import (
    ERRORS, ALL_LAYERS, ErrorSpec, all_codes, spec_of,
)
from ops_pilot.diagnostics.conclusion import (
    OK, Diagnosis, add_evidence, fail, map_ssh_error, not_implemented, ok,
)

__all__ = [
    "ERRORS", "ALL_LAYERS", "ErrorSpec", "all_codes", "spec_of",
    "OK", "Diagnosis", "add_evidence", "fail", "map_ssh_error",
    "not_implemented", "ok",
]
