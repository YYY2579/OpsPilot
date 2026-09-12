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
    mask,
)


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
