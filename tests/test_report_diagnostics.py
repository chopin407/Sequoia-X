"""Report diagnostics distinguish risk, overlapping signals and historical events."""

from unittest.mock import Mock

import numpy as np
import pandas as pd

from sequoia_x.core.config import Settings
from sequoia_x.notify.diagnostics import candidate_metrics, diagnostic_markdown


def data():
    prices = np.linspace(10, 15, 150)
    return pd.DataFrame(
        dict(
            date=pd.bdate_range(end="2026-09-11", periods=150),
            open=prices,
            high=prices + 0.1,
            low=prices - 0.1,
            close=prices,
            volume=100.0,
            turnover=1e8,
        )
    )


def test_overheat_overrides_breakout_classification():
    df = data()
    df.loc[149, ["open", "high", "low", "close"]] = 30
    m = candidate_metrics(df, ["TurtleTradeStrategy"], Settings(_env_file=None))
    assert m["group"] == "风险优先核查"
    assert "显著偏离" in m["reasons"]
    assert m["volume"] == 1


def test_sharp_drop_is_not_a_normal_pullback():
    df = data()
    df.loc[149, "close"] = 10
    m = candidate_metrics(df, ["TrendMeanReversionStrategy"], Settings(_env_file=None))
    assert m["group"] == "风险优先核查"
    assert "急跌" in m["reasons"]


def test_all_overlap_is_reported_without_attractiveness_labels():
    engine = Mock()
    engine.load_all_ohlcv.return_value = {"600000": data()}
    engine.get_stock_name.return_value = "测试"
    text = diagnostic_markdown(
        engine,
        {
            "RpsYilinStrategy": ["600000"],
            "TurtleTradeStrategy": ["600000"],
            "HighTightFlagStrategy": ["600000"],
        },
        Settings(_env_file=None),
    )
    assert "多策略共同入选（1只）" in text
    assert "不增加独立确认" in text
    assert "### 高吸引力" not in text


def test_historical_triple_volume_reports_signal_date_and_platform():
    df = data()
    df.loc[140, "volume"] = 400
    df.loc[140, "open"] = df.loc[140, "close"] - 0.1
    df.loc[141:148, "high"] = 20
    m = candidate_metrics(df, ["TripleVolumeBreakoutStrategy"], Settings(_env_file=None))
    assert str(df.loc[140, "date"].date()) in m["triple"]
    assert "尚未收盘突破平台" in m["triple"]
    assert m["platform"] == 20


def test_history_shortage_does_not_invent_metrics():
    m = candidate_metrics(data().tail(1), [], Settings(_env_file=None))
    assert pd.isna(m["volume"])
    assert pd.isna(m["b120"])
