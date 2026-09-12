"""Completed-week trend gate and daily exit observations (no order execution)."""

import pandas as pd


def weekly_direction(daily: pd.DataFrame) -> dict:
    """Aggregate daily bars as of their last date; omit weeks whose Friday is later.

    Without an exchange calendar, a holiday-shortened week is conservatively used
    only once later dated data exists. The first partial listing week is omitted.
    """
    if daily.empty:
        return {"direction": "数据不足", "week": "—", "allow_entry": False}
    frame = daily.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values("date").drop_duplicates("date").set_index("date")
    as_of = frame.index.max().normalize()
    weeks = (
        frame.resample("W-FRI")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["close"])
    )
    weeks = weeks[weeks.index <= as_of]
    if len(weeks) and frame.index.min().weekday() != 0:
        weeks = weeks.iloc[1:]
    week = str(weeks.index[-1].date()) if len(weeks) else "—"
    if len(weeks) < 21:
        return {"direction": "数据不足", "week": week, "allow_entry": False}
    fast = weeks["close"].rolling(10).mean()
    slow = weeks["close"].rolling(20).mean()
    rising = (
        weeks["close"].iloc[-1] > fast.iloc[-1] > slow.iloc[-1] and slow.iloc[-1] > slow.iloc[-2]
    )
    return {
        "direction": "向上" if rising else "未确认向上",
        "week": week,
        "allow_entry": bool(rising),
    }


def analyze_timeframes(engine, strategy_results: dict, holdings: list[str]):
    """Filter candidates after original rankings; never re-rank RPS on bullish subset."""
    data = engine.load_all_ohlcv()
    symbols = set(holdings)
    for selected in strategy_results.values():
        symbols.update(selected)
    states = {s: weekly_direction(data.get(s, pd.DataFrame())) for s in sorted(symbols)}
    filtered = {
        name: [s for s in selected if states[s]["allow_entry"]]
        for name, selected in strategy_results.items()
    }
    exits = {}
    for symbol in holdings:
        df = data.get(symbol)
        if df is None or len(df) < 21:
            exits[symbol] = "无法评估：行情缺失、被股票池排除或历史不足"
            continue
        df = df.sort_values("date")
        ma20 = df["close"].rolling(20).mean()
        reasons = []
        if (df["close"].iloc[-2:] < ma20.iloc[-2:]).all():
            reasons.append("连续两日收盘低于日MA20")
        if df["close"].iloc[-1] < df["low"].iloc[-11:-1].min():
            reasons.append("收盘跌破此前10日最低价")
        if reasons:
            exits[symbol] = "退出提示：" + "；".join(reasons)
        elif not states[symbol]["allow_entry"]:
            exits[symbol] = "周线未确认向上，暂停新增；未触发日线退出条件"
        else:
            exits[symbol] = "未触发日线退出条件"
    return filtered, states, exits


def timeframe_markdown(raw: dict, states: dict, exits: dict) -> str:
    lines = [
        "## 周线方向与日线候选",
        "",
        "周线条件：周收盘 > 周MA10 > 周MA20，且周MA20较前一周上升。",
        "仅使用行情日期之前已结束的周；周中不使用本周未完成周线。",
        "原策略仍在完整合规股票池中计算，之后过滤周线方向；不会缩小RPS排名基数。",
        "日线结果是候选提示；整理、止跌和公告类入选仍需入场确认，不等同于买入指令。",
        "",
        "| 代码 | 已完成周截至 | 周线方向 | 日线候选处理 |",
        "|---|---|---|---|",
    ]
    candidates = {s for symbols in raw.values() for s in symbols}
    kept = sum(states[s]["allow_entry"] for s in candidates)
    lines.insert(2, f"日线去重候选 {len(candidates)} 只，周线保留 {kept} 只，过滤 {len(candidates)-kept} 只。此比例仅针对候选，不代表全市场宽度。")
    for symbol, state in states.items():
        action = (
            ("保留候选" if state["allow_entry"] else "过滤候选")
            if symbol in candidates
            else "持仓观察"
        )
        lines.append(f"| {symbol} | {state['week']} | {state['direction']} | {action} |")
    if not states:
        lines.append("| — | — | — | 本次没有日线候选或配置持仓 |")
    lines += ["", "## 持仓日线退出提示", ""]
    if exits:
        lines += ["| 代码 | 状态 |", "|---|---|"]
        lines += [f"| {symbol} | {reason} |" for symbol, reason in exits.items()]
    else:
        lines.append("未配置 HOLDING_SYMBOLS，未评估持仓卖点。")
    lines += [
        "",
        "信号在收盘后确认，用于下一交易日决策；不自动下单。"
        "退出规则未包含成本止损、持仓日期和可成交性判断。",
        "",
    ]
    return "\n".join(lines)
