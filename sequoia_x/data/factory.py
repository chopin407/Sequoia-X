"""Select the configured market data provider."""

from sequoia_x.data.engine import DataEngine
from sequoia_x.data.tdx import TdxDataEngine


def create_engine(settings, local_only=False):
    if settings.data_source == "tdx":
        engine = TdxDataEngine(settings)
        engine.local_only = local_only
        return engine
    if local_only:
        raise RuntimeError("baostock 尚未缓存股票状态，无法离线排除 ST；请使用 TDX 本地数据库")
    engine = DataEngine(settings)
    if not engine.get_all_symbols():
        raise RuntimeError("无法获得有效股票池，停止扫描")
    return engine
