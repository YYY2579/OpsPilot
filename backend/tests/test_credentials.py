"""凭据解析与泄密断言测试（§A6.4）。

泄密测试是本模块最重要的测试：模拟"凭据串出现在输出里"必须被抓住。
"""
from __future__ import annotations

import pytest

from ops_pilot.credentials import (
    SECRET_PLACEHOLDER,
    CredentialError,
    CredentialResolver,
    assert_no_secrets,
    clear_credential_aliases,
    mask,
    set_credential_aliases,
)


@pytest.fixture(autouse=True)
def _clean_aliases():
    """每个用例前后清空别名表，避免测试间互相污染。"""
    clear_credential_aliases()
    yield
    clear_credential_aliases()


@pytest.fixture
def env():
    return {
        "OPSPILOT_HK_UBUNTU_HOST": "192.168.1.10",
        "OPSPILOT_HK_UBUNTU_PORT": "22",
        "OPSPILOT_HK_UBUNTU_USERNAME": "deploy",
        "OPSPILOT_HK_UBUNTU_PASSWORD": "s3cr3t-PASS",
    }


def test_resolve_from_env(env):
    cred = CredentialResolver(env).resolve("hk-ubuntu")
    assert (cred.host, cred.port, cred.username) == ("192.168.1.10", 22, "deploy")
    assert cred.password == "s3cr3t-PASS"
    assert cred.redacted() == {
        "server_id": "hk-ubuntu",
        "host": "192.168.1.10",
        "port": 22,
        "username": "deploy",
        "auth": "password",
    }


def test_server_id_normalization(env):
    # 大小写与分隔符：hk-ubuntu / HK-UBUNTU / hk.ubuntu 命中同一组变量
    r = CredentialResolver(env)
    assert r.resolve("HK-UBUNTU").host == "192.168.1.10"
    assert r.resolve("hk.ubuntu").host == "192.168.1.10"


def test_missing_host_is_missing_error():
    with pytest.raises(CredentialError) as excinfo:
        CredentialResolver({}).resolve("hk-ubuntu")
    assert excinfo.value.kind == "missing"


def test_incomplete_without_secret():
    with pytest.raises(CredentialError) as excinfo:
        CredentialResolver({"OPSPILOT_HK_UBUNTU_HOST": "192.168.1.10"}).resolve("hk-ubuntu")
    assert excinfo.value.kind == "incomplete"


def test_key_path_secret_reads_file(tmp_path):
    keyfile = tmp_path / "id_ed25519"
    keyfile.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n", encoding="utf-8")
    env = {
        "OPSPILOT_HK_UBUNTU_HOST": "192.168.1.10",
        "OPSPILOT_HK_UBUNTU_USERNAME": "deploy",
        "OPSPILOT_HK_UBUNTU_KEY_PATH": str(keyfile),
    }
    cred = CredentialResolver(env).resolve("hk-ubuntu")
    assert any("OPENSSH PRIVATE KEY" in s for s in cred.secrets())


def test_mask_uses_framework_placeholder():
    assert mask("token=s3cr3t-PASS end", ("s3cr3t-PASS",)) == f"token={SECRET_PLACEHOLDER} end"


def test_leak_detector_catches_password_in_prompt():
    secrets = ("s3cr3t-PASS",)
    prompt = f"检查服务器，密码是 s3cr3t-PASS 别外传"
    with pytest.raises(AssertionError):
        assert_no_secrets(prompt, secrets)


def test_leak_detector_passes_when_clean():
    assert_no_secrets("检查 HK-UBUNTU 的健康状态", ("s3cr3t-PASS",))


def test_redacted_view_never_contains_secret(env):
    cred = CredentialResolver(env).resolve("hk-ubuntu")
    dumped = str(cred.redacted())
    assert_no_secrets(dumped, cred.secrets())


# ---- 别名解析（主键 → credential_ref） ----
#
# 真实故障：Agent 的 Action 里只有 serverconnection 的**主键**，而环境变量按
# credential_ref 配置。缺这层映射时，Agent 调任何 SSH 工具都报 SSH missing，
# 但 /api/servers/{id}/health 却是通的 —— 极易误判成"工具坏了"。

def test_alias_resolves_primary_key_to_credential_ref(env):
    set_credential_aliases({"4d6cc8bd599d": "hk-ubuntu"})
    cred = CredentialResolver(env).resolve("4d6cc8bd599d")
    assert cred.host == "192.168.1.10"


def test_alias_is_case_insensitive(env):
    set_credential_aliases({"4D6CC8BD599D": "hk-ubuntu"})
    assert CredentialResolver(env).resolve("4d6cc8bd599d").host == "192.168.1.10"


def test_without_alias_primary_key_still_fails(env):
    """没有别名时必须如实报 missing，不能悄悄用别的主机连上去。"""
    with pytest.raises(CredentialError) as exc:
        CredentialResolver(env).resolve("4d6cc8bd599d")
    assert exc.value.kind == "missing"


def test_alias_missing_target_reports_original_id(env):
    """别名指向的配置也不存在时，报错里应是**原始** server_id，不是陌生的 ref。"""
    set_credential_aliases({"abc123": "not-configured"})
    with pytest.raises(CredentialError) as exc:
        CredentialResolver(env).resolve("abc123")
    assert "abc123" in exc.value.detail


def test_exact_match_wins_over_alias(env):
    """server_id 本身能解析时不应被别名改写。"""
    env2 = dict(env, OPSPILOT_ABC_HOST="10.0.0.1",
                OPSPILOT_ABC_USERNAME="u", OPSPILOT_ABC_PASSWORD="p")
    set_credential_aliases({"abc": "hk-ubuntu"})
    assert CredentialResolver(env2).resolve("abc").host == "10.0.0.1"


def test_set_aliases_replaces_previous_table():
    set_credential_aliases({"a": "x"})
    set_credential_aliases({"b": "y"})
    from ops_pilot.credentials import credential_aliases
    assert credential_aliases() == {"b": "y"}
