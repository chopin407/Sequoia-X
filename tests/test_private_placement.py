"""Native failures in the announcement provider must not kill the strategy process."""

import subprocess
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

from sequoia_x.core.config import Settings
from sequoia_x.strategy.private_placement import PrivatePlacementStrategy


def strategy():
    return PrivatePlacementStrategy(engine=Mock(), settings=Settings(_env_file=None))


def test_native_crash_is_catchable(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(
            return_value=subprocess.CompletedProcess(
                [], 1, b"", b"OPENSSL_Uplink: no OPENSSL_Applink"
            )
        ),
    )
    with pytest.raises(RuntimeError, match="OPENSSL_Applink"):
        strategy().run()


def test_timeout_is_catchable(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", Mock(side_effect=subprocess.TimeoutExpired("worker", 45))
    )
    with pytest.raises(RuntimeError, match="45"):
        strategy().run()


def test_success_preserves_leading_zero_codes(monkeypatch):
    from datetime import date

    def run(args, **kwargs):
        pd.DataFrame(
            {
                "股票代码": ["000001"],
                "发行方式": ["定向增发"],
                "发行日期": [date.today().isoformat()],
            }
        ).to_json(Path(args[-1]), orient="split", force_ascii=False)
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", run)
    assert strategy().run() == ["000001"]


def test_report_continues_after_placement_failure(monkeypatch):
    import main

    settings = Settings(_env_file=None, weekly_filter_enabled=False)
    engine = Mock()
    engine.filter_symbols.side_effect = lambda symbols: symbols
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "create_engine", lambda s: engine)
    monkeypatch.setattr("sys.argv", ["main.py"])
    for cls in vars(main).values():
        if (
            isinstance(cls, type)
            and issubclass(cls, main.BaseStrategy)
            and cls is not main.BaseStrategy
        ):
            monkeypatch.setattr(cls, "run", lambda self: [])
    monkeypatch.setattr(
        main.PrivatePlacementStrategy, "run", Mock(side_effect=RuntimeError("OPENSSL_Applink"))
    )
    report = Mock()
    monkeypatch.setattr(main, "ReportGenerator", lambda *a, **kw: report)
    main.main()
    report.generate.assert_called_once()
    args, kwargs = report.generate.call_args
    assert "PrivatePlacementStrategy" not in args[0]
    assert "PrivatePlacementStrategy" in kwargs["extra_section"]
    assert "未完成的策略" in kwargs["extra_section"]
