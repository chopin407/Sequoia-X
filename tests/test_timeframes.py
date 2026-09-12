from unittest.mock import Mock

import numpy as np
import pandas as pd

from sequoia_x.strategy.timeframes import analyze_timeframes, weekly_direction


def bars(end="2026-09-11", periods=160):
    dates = pd.bdate_range(end=end, periods=periods)
    price = np.linspace(10, 30, periods)
    return pd.DataFrame(
        {
            "date": dates,
            "open": price,
            "high": price + 1,
            "low": price - 1,
            "close": price,
            "volume": 1000,
        }
    )


def test_midweek_extreme_move_does_not_change_completed_week():
    df = bars()
    expected = weekly_direction(df)
    extra = bars(end="2026-09-16", periods=3)
    extra[["open", "high", "low", "close"]] = 1
    actual = weekly_direction(pd.concat([df, extra], ignore_index=True))
    assert actual == expected
    assert actual["week"] == "2026-09-11"
    assert actual["allow_entry"]


def test_friday_changes_weekly_direction():
    df = bars()
    df.loc[df.index[-5:], ["open", "high", "low", "close"]] = 1
    assert not weekly_direction(df)["allow_entry"]


def test_short_history_is_not_a_buy():
    assert not weekly_direction(bars(periods=40))["allow_entry"]


def test_no_reordering_and_exits_independent_of_entry():
    good = bars()
    falling = bars()
    falling.loc[falling.index[-2:], "close"] = 1
    engine = Mock()
    engine.load_all_ohlcv.return_value = {"600000": good, "000001": falling}
    result, states, exits = analyze_timeframes(
        engine, {"daily": ["000001", "600000"]}, ["000001", "688001"]
    )
    assert result == {"daily": ["600000"]}
    assert "退出提示" in exits["000001"]
    assert "此前10日" in exits["000001"]
    assert "无法评估" in exits["688001"]


def test_report_contains_holdings_even_without_entries(tmp_path):
    from sequoia_x.core.config import Settings
    from sequoia_x.notify.report import ReportGenerator
    from sequoia_x.strategy.timeframes import timeframe_markdown

    section = timeframe_markdown({}, {}, {"600000": "退出提示：连续两日收盘低于日MA20"})
    path = ReportGenerator(Settings(_env_file=None, report_output_dir=str(tmp_path))).generate(
        {}, {"high": [], "medium": []}, extra_section=section
    )
    assert "600000" in path.read_text(encoding="utf-8")
    assert "退出提示" in path.read_text(encoding="utf-8")
