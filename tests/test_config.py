"""配置管理属性测试。"""


from hypothesis import HealthCheck, given
from hypothesis import settings as h_settings
from hypothesis import strategies as st


# Feature: sequoia-x-v2, Property 1: 环境变量覆盖配置默认值
@given(
    db_path=st.text(
        min_size=1,
        max_size=100,
        alphabet=st.characters(
            whitelist_categories=("Lu", "Ll", "Nd"),
            whitelist_characters="/_.-",
        ),
    )
)
@h_settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_env_overrides_default(db_path: str, monkeypatch) -> None:
    """属性 1：任意合法 db_path 通过环境变量设置后，Settings 实例应反映该值。"""
    import sequoia_x.core.config as cfg_module
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://example.com/hook")
    monkeypatch.setattr(cfg_module, "_settings", None)
    from sequoia_x.core.config import Settings
    s = Settings()
    assert s.db_path == db_path


# Feature: sequoia-x-v2, Property 2: 缺失必填字段触发 ValidationError
def test_feishu_not_required(monkeypatch) -> None:
    from sequoia_x.core.config import Settings
    monkeypatch.delenv("FEISHU_WEBHOOK_URL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.feishu_webhook_url == ""
    assert settings.data_source == "tdx"


def test_baostock_pacing_settings(monkeypatch) -> None:
    """baostock 限速参数应支持通过环境变量配置。"""
    from sequoia_x.core.config import Settings

    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://example.com/hook")
    monkeypatch.setenv("BAOSTOCK_MAX_WORKERS", "2")
    monkeypatch.setenv("BAOSTOCK_REQUEST_DELAY_SECONDS", "1.2")
    monkeypatch.setenv("BAOSTOCK_REQUEST_JITTER_SECONDS", "0.8")
    monkeypatch.setenv("BAOSTOCK_ERROR_COOLDOWN_SECONDS", "60")

    s = Settings(_env_file=None)

    assert s.baostock_max_workers == 2
    assert s.baostock_request_delay_seconds == 1.2
    assert s.baostock_request_jitter_seconds == 0.8
    assert s.baostock_error_cooldown_seconds == 60
