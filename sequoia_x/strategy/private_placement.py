"""定增公告监控策略：推送最近发布的定向增发公告。"""

import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from sequoia_x.core.logger import get_logger
from sequoia_x.strategy.base import BaseStrategy

logger = get_logger(__name__)


class PrivatePlacementStrategy(BaseStrategy):
    """定增公告监控策略。

    数据源：akshare stock_qbzf_em()（东方财富-全部增发）
    逻辑：筛选最近 7 天内发行日期的定向增发公告，推送至飞书。

    Attributes:
        webhook_key: 路由到 'private_placement' 飞书机器人。
    """

    webhook_key: str = "private_placement"
    _LOOKBACK_DAYS: int = 7  # 回看天数，覆盖一周内的新公告

    def _fetch_data(self) -> pd.DataFrame:
        """隔离第三方原生库；进程崩溃或超时转换为可捕获异常。"""
        script = (
            "import sys; import akshare as ak; "
            "ak.stock_qbzf_em().to_json(sys.argv[1], orient='split', force_ascii=False)"
        )
        with tempfile.TemporaryDirectory(prefix="sequoia_placement_") as directory:
            output = Path(directory) / "data.json"
            try:
                result = subprocess.run(
                    [sys.executable, "-X", "utf8", "-c", script, str(output)],
                    capture_output=True, timeout=45, check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("定增数据获取超过45秒，已终止子进程") from exc
            if result.returncode != 0:
                # 不输出第三方完整日志，以免其中携带代理或认证配置。
                applink = b"OPENSSL_Applink" in result.stderr
                reason = "OPENSSL_Applink 原生库错误" if applink else "第三方数据接口异常"
                raise RuntimeError(f"定增数据获取失败：{reason}（退出码 {result.returncode}）")
            if not output.is_file():
                raise RuntimeError("定增数据子进程未返回结果")
            return pd.read_json(output, orient="split", dtype=False)

    def run(self) -> list[str]:
        """拉取定增公告；失败交由主流程记录，继续生成其他策略报告。"""
        df = self._fetch_data()

        if df is None or df.empty:
            logger.info("PrivatePlacementStrategy 无定增数据")
            return []

        # 只保留定向增发（排除公开增发）
        df = df[df["发行方式"] == "定向增发"]

        if df.empty:
            return []

        # 按发行日期过滤：只保留最近 N 天内的公告
        today = date.today()
        cutoff = today - timedelta(days=self._LOOKBACK_DAYS)

        df["发行日期"] = pd.to_datetime(df["发行日期"], errors="coerce")
        df = df.dropna(subset=["发行日期"])
        df = df[df["发行日期"].dt.date >= cutoff]

        if df.empty:
            logger.info("PrivatePlacementStrategy 近期无新定增公告")
            return []

        # 按发行日期降序（最新的在前）
        df = df.sort_values("发行日期", ascending=False)

        # 提取股票代码（去掉可能的前缀，保留纯数字）
        symbols = df["股票代码"].astype(str).str.extract(r"(\d{6})")[0].dropna().tolist()

        # 去重（同一只票可能有多次定增）
        seen = set()
        unique_symbols = []
        for s in symbols:
            if s not in seen:
                seen.add(s)
                unique_symbols.append(s)

        logger.info(f"PrivatePlacementStrategy 选出 {len(unique_symbols)} 只股票")
        return unique_symbols
