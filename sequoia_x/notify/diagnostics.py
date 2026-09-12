"""Report-only price diagnostics; does not change strategy selection."""

import pandas as pd


def number(value, suffix="", signed=False):
    if value is None or pd.isna(value):
        return "—"
    return f"{value:+.2f}{suffix}" if signed else f"{value:.2f}{suffix}"


def candidate_metrics(df, strategies, settings):
    df = df.sort_values("date").drop_duplicates("date")
    close = df["close"]
    last = df.iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    prev = close.iloc[-2] if len(df) >= 2 else float("nan")
    high20 = df.high.iloc[-21:-1].max() if len(df) >= 21 else float("nan")
    high120 = df.high.iloc[-121:-1].max() if len(df) >= 121 else float("nan")
    vol20 = df.volume.iloc[-21:-1].mean() if len(df) >= 21 else float("nan")
    low10 = df.low.iloc[-11:-1].min() if len(df) >= 11 else float("nan")
    def ratio(a, b):
        return a / b if pd.notna(b) and b > 0 else float("nan")
    day = (ratio(last.close, prev) - 1) * 100
    gap = (ratio(last.close, ma20) - 1) * 100
    reasons = []
    if day <= -settings.report_sharp_drop_pct:
        reasons.append("当日急跌")
    if gap >= settings.report_overheat_pct:
        reasons.append("显著偏离日MA20")
    if "UptrendLimitDownStrategy" in strategies:
        reasons.append("急跌策略命中，不代表错杀")
    if len(df) < 121:
        reasons.append("部分指标历史不足")
    if any(r != "部分指标历史不足" for r in reasons):
        group = "风险优先核查"
    elif last.close > high20:
        group = "20日突破已发生"
    elif any(
        s in strategies
        for s in ("TrendMeanReversionStrategy", "BowlReboundStrategy", "StopFallStrategy")
    ):
        group = "回调或止跌观察"
    elif any(s in strategies for s in ("HighTightFlagStrategy", "TripleVolumeBreakoutStrategy")):
        group = "整理等待确认"
    else:
        group = "强势或转强观察"
    weeks = (
        df.assign(date=pd.to_datetime(df.date))
        .set_index("date")
        .resample("W-FRI")
        .close.last()
        .dropna()
    )
    weeks = weeks[weeks.index <= pd.Timestamp(last.date)]
    if len(weeks) and pd.Timestamp(df.date.iloc[0]).weekday() != 0:
        weeks = weeks.iloc[1:]
    wma = weeks.rolling(20).mean().iloc[-1] if len(weeks) else float("nan")
    triple = "—"
    platform = float("nan")
    if "TripleVolumeBreakoutStrategy" in strategies:
        signal = (
            (df.volume >= df.volume.shift(1) * 3) & (close > df.open) & (close > close.shift(1))
        )
        positions = [i for i, v in enumerate(signal.iloc[:-1]) if v]
        if positions:
            i = positions[-1]
            triple = str(df.iloc[i].date)[:10]
            platform = df.high.iloc[i + 1 : -1].max()
            triple += "；" + ("已收盘突破平台" if last.close > platform else "尚未收盘突破平台")
    return dict(
        group=group,
        reasons="；".join(reasons) or "未触发本报告风险阈值（不代表低风险）",
        day=day,
        gap=gap,
        wgap=(ratio(last.close, wma) - 1) * 100,
        volume=ratio(last.volume, vol20),
        amount=last.turnover / 1e8,
        high20=high20,
        high120=high120,
        low10=low10,
        ma20=ma20,
        b20=(ratio(last.close, high20) - 1) * 100,
        b120=(ratio(last.close, high120) - 1) * 100,
        price=last.close,
        triple=triple,
        platform=platform,
    )


def diagnostic_markdown(engine, results, settings):
    data = engine.load_all_ohlcv()
    hits = {}
    for strategy, symbols in results.items():
        for symbol in set(symbols):
            hits.setdefault(symbol, []).append(strategy)
    returns = {
        s: df.close.iloc[-1] / df.close.iloc[-121] - 1
        for s, df in data.items()
        if len(df) >= 121 and df.close.iloc[-121] > 0
    }
    rps = pd.Series(returns, dtype=float).rank(pct=True) * 100
    metrics = {
        s: candidate_metrics(data[s], strategies, settings)
        for s, strategies in hits.items()
        if s in data and not data[s].empty
    }
    lines = [
        "## 候选分层与风险核查",
        "",
        f"风险展示阈值：当日跌幅≥{settings.report_sharp_drop_pct:g}%，或收盘高于日MA20≥"
        f"{settings.report_overheat_pct:g}%。阈值未经收益校准，仅标记风险，不改变策略入选。",
        "分类按风险提示优先；同组按代码排列，不是买入优先级。周线向上不能抵消日线急跌或价格过热。",
        "",
    ]
    for group in (
        "风险优先核查",
        "20日突破已发生",
        "回调或止跌观察",
        "整理等待确认",
        "强势或转强观察",
    ):
        members = sorted(s for s, m in metrics.items() if m["group"] == group)
        if not members:
            continue
        lines += [
            f"### {group}（{len(members)}只）",
            "",
            "| 代码 / 名称 | 收盘 | 日涨跌 | 距日MA20 | 距周MA20 | 量比 | 成交额(亿) | RPS120 |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for s in members:
            m = metrics[s]
            lines.append(
                f"| {s} {engine.get_stock_name(s)} | {number(m['price'])} | "
                f"{number(m['day'], '%', True)} | "
                f"{number(m['gap'], '%', True)} | {number(m['wgap'], '%', True)} | "
                f"{number(m['volume'])} | "
                f"{number(m['amount'])} | {number(rps.get(s))} |"
            )
        lines.append("")
    lines += [
        "量比统一为当日成交量÷此前20日均量（不含当日），与个别策略内部口径不同。"
        "RPS120为可用完整股票池的120交易日收益百分位；不是未来胜率。",
        "",
        "## 候选依据与观察价位",
        "",
        "前高、MA20和前10日低点仅供检查突破保持或结构破坏，不是推荐委托价或保证可成交的止损价。",
        "",
        "| 代码 | 命中策略 | 距20日前高 | 距120日前高 | "
        "前20日高 / 前120日高 | 日MA20 / 前10日低 | 风险提示 |",
        "|---|---|---|---|---|---|---|",
    ]
    for s, m in sorted(metrics.items()):
        lines.append(
            f"| {s} | {', '.join(hits[s])} | {number(m['b20'], '%', True)} | "
            f"{number(m['b120'], '%', True)} | "
            f"{number(m['high20'])} / {number(m['high120'])} | "
            f"{number(m['ma20'])} / {number(m['low10'])} | {m['reasons']} |"
        )
    triples = [s for s in metrics if "TripleVolumeBreakoutStrategy" in hits[s]]
    if triples:
        lines += [
            "",
            "### 历史三倍量信号核对",
            "",
            "三倍量是历史事件，不意味着今天三倍量。平台区间为信号次日至昨日。",
            "",
            "| 代码 | 最近历史信号日期 / 当前状态 | 平台高点 |",
            "|---|---|---|",
        ]
        for s in sorted(triples):
            lines.append(f"| {s} | {metrics[s]['triple']} | {number(metrics[s]['platform'])} |")
    multi = {s: strategies for s, strategies in hits.items() if len(strategies) > 1}
    lines += [
        "",
        f"## 多策略共同入选（{len(multi)}只）",
        "",
        "完整列出所有多策略命中，不按预设组合挑选，不标记高/中吸引力。"
        "同源价量条件可能重叠，不等于多份独立证据。",
        "",
        "| 代码 | 命中数 | 策略 | 解释 |",
        "|---|---|---|---|",
    ]
    for s, strategies in sorted(multi.items()):
        note = "相关信号，尚未验证增益"
        if {"RpsYilinStrategy", "TurtleTradeStrategy"} <= set(strategies):
            note = "120日突破通常已包含20日突破，不增加独立确认；仍需检查过热风险"
        lines.append(f"| {s} | {len(strategies)} | {', '.join(strategies)} | {note} |")
    if not multi:
        lines.append("| — | 0 | — | 无共同入选 |")
    return "\n".join(lines) + "\n"
