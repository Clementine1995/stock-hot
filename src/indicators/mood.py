"""情绪温度自算。

开盘啦匿名接口不暴露「市场情绪温度计 0–100」真值，这里用已确认可拿的
市场情绪家数原料自算一个 0–100 温度，口径见 docs/requirements/REQ-001 §5。

v1 公式（缩放系数集中在模块顶部，便于后续用历史数据标定）：
    广度项 = (上涨 − 下跌) / (上涨 + 下跌) × 广度系数          # −50 ~ +50
    强度项 = clamp((涨停 − 跌停) × 强度系数, −50, +50)         # 连板率暂缺，用净差替代
    温度   = clamp(中性基准 + 广度项 + 强度项, 0, 100)
"""

_BREADTH_SCALE = 50.0    # 广度项缩放系数
_STRENGTH_SCALE = 0.5    # 强度项缩放系数
_STRENGTH_CAP = 50.0     # 强度项上下限
_BASE = 50.0             # 中性基准温度


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def mood_temperature(up_count, down_count, limit_up, limit_down) -> float:
    """按 v1 公式计算情绪温度（0–100，保留 1 位小数）。

    参数：
        up_count    上涨家数
        down_count  下跌家数
        limit_up    涨停家数
        limit_down  跌停家数
    上涨+下跌为 0 时抛出 ValueError，不静默掩盖缺失事实。
    """
    total = up_count + down_count
    if total <= 0:
        raise ValueError(f"上涨+下跌家数必须大于 0，实际为 {total}")
    breadth = (up_count - down_count) / total * _BREADTH_SCALE
    strength = _clamp(
        (limit_up - limit_down) * _STRENGTH_SCALE, -_STRENGTH_CAP, _STRENGTH_CAP
    )
    return round(_clamp(_BASE + breadth + strength, 0.0, 100.0), 1)
