"""TDX HTTP adapter. Raw prices are isolated from baostock adjusted history."""

import sqlite3
from contextlib import closing
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from sequoia_x.data.engine import DataEngine, logger
from sequoia_x.data.universe import eligible


class TdxDataEngine(DataEngine):
    def __init__(self, settings):
        super().__init__(settings.model_copy(update={"db_path": settings.tdx_db_path}))
        self.base_url = settings.tdx_base_url.rstrip("/")
        self.timeout = settings.tdx_timeout_seconds
        self.session = requests.Session()
        self.session.trust_env = False  # 局域网请求不经过系统代理
        retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[502, 503, 504])
        self.session.mount("http://", HTTPAdapter(max_retries=retry))
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            tables = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if (
                "stock_universe" not in tables
                and conn.execute("SELECT COUNT(*) FROM stock_daily").fetchone()[0]
            ):
                raise ValueError("TDX_DB_PATH 包含其他来源行情，请使用独立空数据库")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS stock_universe "
                "(symbol TEXT PRIMARY KEY, name TEXT, exchange TEXT, active INTEGER)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS sync_state "
                "(symbol TEXT PRIMARY KEY, ok INTEGER, last_date TEXT)"
            )

    def _get(self, path, **params):
        response = self.session.get(self.base_url + path, params=params, timeout=self.timeout)
        response.raise_for_status()
        body = response.json()
        if body.get("code") != 0:
            raise RuntimeError(f"TDX {path}: {body.get('msg', 'invalid response')}")
        return body["data"]

    def get_all_symbols(self):
        rows = []
        for exchange in ("sh", "sz"):
            data = self._get("/code/all", exchange=exchange)
            if not data or not data.get("List"):
                raise RuntimeError(f"TDX {exchange} 股票名单为空，停止扫描")
            for item in data["List"]:
                code, name = item["Code"], item["Name"]
                if eligible(code, name, exchange):
                    rows.append((code, name, exchange, 1))
        if not rows:
            raise RuntimeError("TDX 合规股票池为空")
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute("UPDATE stock_universe SET active=0")
            conn.executemany("INSERT OR REPLACE INTO stock_universe VALUES (?,?,?,?)", rows)
        self.invalidate_cache()
        return [r[0] for r in rows]

    def get_stock_name(self, symbol):
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            row = conn.execute(
                "SELECT name FROM stock_universe WHERE symbol=?", (symbol,)
            ).fetchone()
        return row[0] if row else ""

    @staticmethod
    def _code(symbol):
        return ("sh" if symbol.startswith("6") else "sz") + symbol

    def _fetch_daily(self, symbol, last_date=None):
        records = []
        today = datetime.now(ZoneInfo("Asia/Shanghai"))
        # 每页800根，从最新向前补齐；保留末日重写，避免盘中数据永久固化。
        for offset in range(0, 64000, 800):
            data = self._get("/kline/day", code=self._code(symbol), start=offset, count=800)
            bars = (data or {}).get("List") or []
            if not bars:
                break
            for bar in bars:
                day = bar["Time"][:10]
                if day > today.date().isoformat():
                    continue
                if day == today.date().isoformat() and today.hour < 15:
                    continue
                if day < self.start_date or bar["Volume"] <= 0:
                    continue
                prices = [float(bar[k]) / 1000 for k in ("Open", "High", "Low", "Close")]
                if min(prices) <= 0 or prices[1] < max(prices) or prices[2] > min(prices):
                    raise ValueError(f"{symbol} {day}: invalid OHLC")
                records.append(
                    (symbol, day, *prices, float(bar["Volume"]) * 100, float(bar["Amount"]) / 1000)
                )
            earliest = min(b["Time"][:10] for b in bars)
            if len(bars) < 800 or earliest <= (last_date or self.start_date):
                break
        return sorted({r[1]: r for r in records}.values(), key=lambda r: r[1])

    def _sync(self, symbols):
        success = 0
        # 中断或失败的股票不可凭旧数据进入本次报告。
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute("UPDATE sync_state SET ok=0")
        for i, symbol in enumerate(symbols, 1):
            try:
                rows = self._fetch_daily(symbol, self._get_last_date(symbol))
                if not rows:
                    raise RuntimeError("无已完成的日线")
                with closing(sqlite3.connect(self.db_path)) as conn, conn:
                    conn.executemany(
                        "INSERT OR REPLACE INTO stock_daily "
                        "(symbol,date,open,high,low,close,volume,turnover) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        rows,
                    )
                    conn.execute(
                        "INSERT OR REPLACE INTO sync_state VALUES (?,1,?)", (symbol, rows[-1][1])
                    )
                success += 1
            except Exception as exc:
                logger.warning("[%s] TDX 同步失败，排除本次扫描: %s", symbol, exc)
            if i % 100 == 0:
                logger.info("TDX 同步 %d/%d，成功 %d", i, len(symbols), success)
        self.invalidate_cache()
        if not success:
            raise RuntimeError("TDX 同步全部失败，不生成选股报告")
        return success

    def sync_today_bulk(self):
        return self._sync(self.get_all_symbols())

    def backfill(self, symbols):
        self._sync(symbols)

    def _load_from_db(self):
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            df = pd.read_sql(
                "SELECT d.*, u.name FROM stock_daily d "
                "JOIN stock_universe u ON d.symbol=u.symbol AND u.active=1 "
                "JOIN sync_state s ON d.symbol=s.symbol AND s.ok=1 "
                "WHERE s.last_date=(SELECT MAX(last_date) FROM sync_state WHERE ok=1) "
                "ORDER BY d.symbol,d.date",
                conn,
            )
        return {str(s): g.reset_index(drop=True) for s, g in df.groupby("symbol", sort=False)}

    def get_ohlcv(self, symbol):
        return self.load_all_ohlcv().get(symbol, pd.DataFrame())

    def get_market_caps(self, symbols):
        caps = {}
        for symbol in symbols:
            try:
                info = self._get("/finance", exchange=self._code(symbol)[:2], code=symbol)
                caps[symbol] = (
                    float(info["LiuTongGuBen"]) * self.get_ohlcv(symbol).iloc[-1]["close"]
                )
            except Exception as exc:
                logger.warning("[%s] TDX 流通市值获取失败: %s", symbol, exc)
        return caps

    def report_status(self):
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            total = conn.execute("SELECT COUNT(*) FROM stock_universe WHERE active=1").fetchone()[0]
            latest = conn.execute("SELECT MAX(last_date) FROM sync_state WHERE ok=1").fetchone()[0]
        return (
            f"- 数据源：TDX（不复权）；行情日期：{latest or '无'}；"
            f"股票池：{total}；实际扫描：{len(self.load_all_ohlcv())}。\n"
            "- 范围：沪深主板、科创板、创业板；排除 ST、退市名称、北交所、"
            "同步失败及行情日期落后的股票。\n"
            "> 不复权价格可能受除权除息影响；共振标签不代表已验证收益。"
        )


    def report_exclusions(self):
        """Explain cached synchronization omissions without requesting remote data."""
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            latest = conn.execute("SELECT MAX(last_date) FROM sync_state WHERE ok=1").fetchone()[0]
            rows = conn.execute(
                "SELECT u.symbol,u.name,s.ok,s.last_date FROM stock_universe u "
                "LEFT JOIN sync_state s ON u.symbol=s.symbol WHERE u.active=1 "
                "AND (s.ok IS NULL OR s.ok!=1 OR s.last_date IS NULL OR s.last_date!=?) "
                "ORDER BY u.symbol", (latest or "",)
            ).fetchall()
        lines = ["", "股票状态来自缓存名单；当前缓存未记录名单更新时间，不能据此确认最新ST状态。",
                 "公司公告和除权除息事件未核验，不复权造成的价格跳变可能影响全部技术指标。", ""]
        if rows:
            lines += [f"<details><summary>未扫描股票及原因（{len(rows)}只）</summary>", "",
                      "| 代码 | 名称 | 最近成功行情日 | 原因 |", "|---|---|---|---|"]
            for symbol,name,ok,day in rows:
                reason = ("尚无同步记录" if ok is None else
                          "上次同步未成功或未完成" if not ok else "行情日期落后")
                lines.append(f"| {symbol} | {name} | {day or '—'} | {reason} |")
            lines += ["", "</details>", ""]
        return "\n".join(lines)
