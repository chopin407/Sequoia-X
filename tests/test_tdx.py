"""TDX contract, universe enforcement and report-only workflow regression tests."""

import sqlite3
from contextlib import closing
from unittest.mock import Mock

import pytest

from sequoia_x.core.config import Settings
from sequoia_x.data.tdx import TdxDataEngine
from sequoia_x.data.universe import eligible
from sequoia_x.notify.report import ReportGenerator


@pytest.fixture
def engine(tmp_path):
    return TdxDataEngine(Settings(_env_file=None, tdx_db_path=str(tmp_path / "tdx.db")))


@pytest.mark.parametrize(
    "code,name,exchange,expected",
    [
        ("600000", "浦发银行", "sh", True),
        ("688001", "华兴源创", "sh", True),
        ("300001", "特锐德", "sz", True),
        ("301001", "凯淳股份", "sz", True),
        ("000001", "平安银行", "sz", True),
        ("600000", "*ST测试", "sh", False),
        ("000001", "ＳＴ测试", "sz", False),
        ("600000", "退市测试", "sh", False),
        ("920001", "北交所", "bj", False),
        ("830001", "北交所", "bj", False),
        ("510300", "ETF", "sh", False),
        ("900901", "B股", "sh", False),
        ("000001", "上证指数", "sh", False),
        ("600000", "", "sh", False),
    ],
)
def test_universe(code, name, exchange, expected):
    assert eligible(code, name, exchange) is expected


def test_units_and_order(engine, monkeypatch):
    bars = [
        {
            "Time": f"2025-01-{day:02d}T15:00:00+08:00",
            "Open": 9220,
            "High": 9360,
            "Low": 9190,
            "Close": 9350,
            "Volume": 597742,
            "Amount": 555882176000,
        }
        for day in (3, 2)
    ]
    monkeypatch.setattr(engine, "_get", lambda *a, **kw: {"List": bars})
    rows = engine._fetch_daily("600000")
    assert [r[1] for r in rows] == ["2025-01-02", "2025-01-03"]
    assert rows[0][2:] == (9.22, 9.36, 9.19, 9.35, 59774200, 555882176)


def test_application_error_even_with_http_200(engine):
    response = Mock()
    response.json.return_value = {"code": 1, "msg": "upstream failed", "data": None}
    engine.session.get = Mock(return_value=response)
    with pytest.raises(RuntimeError, match="upstream failed"):
        engine._get("/kline/day")


def seed(engine):
    with closing(sqlite3.connect(engine.db_path)) as conn, conn:
        for code, active, ok, day in [
            ("600000", 1, 1, "2025-01-03"),
            ("688001", 0, 1, "2025-01-03"),
            ("300001", 1, 0, "2025-01-03"),
            ("000001", 1, 1, "2025-01-02"),
        ]:
            conn.execute(
                "INSERT INTO stock_universe VALUES (?,?,?,?)", (code, "测试", "sh", active)
            )
            conn.execute("INSERT INTO sync_state VALUES (?,?,?)", (code, ok, day))
            conn.execute(
                "INSERT INTO stock_daily (symbol,date,open,high,low,close,volume,turnover) "
                "VALUES (?,?,10,11,9,10,100,1000)",
                (code, day),
            )


def test_all_strategy_inputs_exclude_inactive_failed_and_stale(engine):
    seed(engine)
    assert set(engine.load_all_ohlcv()) == {"600000"}
    assert set(engine.strategy_frame()["symbol"]) == {"600000"}
    assert engine.filter_symbols(["688001", "600000", "920001"]) == ["600000"]


def test_refresh_removes_new_st_and_bj(engine, monkeypatch):
    seed(engine)
    monkeypatch.setattr(
        engine,
        "_get",
        lambda path, **kw: {
            "List": [
                {"Code": "600000", "Name": "*ST测试"},
                {"Code": "688001", "Name": "正常"},
                {"Code": "920001", "Name": "北交所"},
                {"Code": "300001", "Name": "正常"},
            ]
        },
    )
    assert set(engine.get_all_symbols()) == {"688001", "300001"}
    assert "600000" not in engine.load_all_ohlcv()


def test_local_report_does_not_query_external_names(engine, tmp_path):
    seed(engine)
    settings = Settings(_env_file=None, report_output_dir=str(tmp_path / "reports"))
    report = ReportGenerator(settings, engine=engine)
    report._fetch_tencent_names = Mock(side_effect=AssertionError("external query"))
    path = report.generate({"MaVolume": ["600000"]}, {"high": [], "medium": []})
    assert "测试" in path.read_text(encoding="utf-8")
    assert "2025-01-03" in path.read_text(encoding="utf-8")


def test_main_generates_report_without_notifier(monkeypatch, tmp_path):
    import main

    settings = Settings(_env_file=None, report_output_dir=str(tmp_path), weekly_filter_enabled=False)
    fake_engine = Mock()
    fake_engine.filter_symbols.side_effect = lambda symbols: symbols
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "create_engine", lambda s: fake_engine)
    monkeypatch.setattr("sys.argv", ["main.py"])
    classes = [
        value
        for value in vars(main).values()
        if isinstance(value, type)
        and issubclass(value, main.BaseStrategy)
        and value is not main.BaseStrategy
    ]
    for cls in classes:
        monkeypatch.setattr(cls, "run", lambda self: [])
    report = Mock()
    monkeypatch.setattr(main, "ReportGenerator", lambda *a, **kw: report)
    main.main()
    report.generate.assert_called_once()
    assert not hasattr(main, "FeishuNotifier")


def test_failed_sync_cannot_reuse_previous_success(engine, monkeypatch):
    seed(engine)
    monkeypatch.setattr(engine, "_fetch_daily", Mock(side_effect=RuntimeError("offline")))
    with pytest.raises(RuntimeError, match="全部失败"):
        engine._sync(["600000"])
    assert not engine.load_all_ohlcv()


def test_finance_contract(engine, monkeypatch):
    seed(engine)
    fetch = Mock(return_value={"LiuTongGuBen": 1000})
    monkeypatch.setattr(engine, "_get", fetch)
    assert engine.get_market_caps(["600000"]) == {"600000": 10000}
    fetch.assert_called_once_with("/finance", exchange="sh", code="600000")


def test_skip_sync_uses_local_data_without_network(engine, monkeypatch, tmp_path):
    import main
    from sequoia_x.core.config import Settings
    seed(engine)
    settings = Settings(_env_file=None, tdx_db_path=engine.db_path,
                        report_output_dir=str(tmp_path / 'offline'), weekly_filter_enabled=False)
    monkeypatch.setattr(main, 'get_settings', lambda: settings)
    monkeypatch.setattr('sys.argv', ['main.py', '--skip-sync'])
    monkeypatch.setattr('requests.sessions.Session.request',
                        Mock(side_effect=AssertionError('network is forbidden')))
    monkeypatch.setattr(TdxDataEngine, 'sync_today_bulk',
                        Mock(side_effect=AssertionError('sync is forbidden')))
    monkeypatch.setattr(main.PrivatePlacementStrategy, 'run',
                        Mock(side_effect=AssertionError('event fetch is forbidden')))
    main.main()
    reports = list((tmp_path / 'offline').glob('*.md'))
    assert len(reports) == 1
    assert '本地快照模式' in reports[0].read_text(encoding='utf-8')


def test_skip_sync_and_backfill_are_exclusive(monkeypatch):
    import main
    monkeypatch.setattr('sys.argv', ['main.py', '--skip-sync', '--backfill'])
    with pytest.raises(SystemExit) as exc:
        main.main()
    assert exc.value.code == 2
