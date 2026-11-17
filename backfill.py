"""回补历史交易日的板块强度 + 市场情绪快照。

用法：
    python backfill.py [N] [起始日期]
- N: 回补的交易日数量（默认 10）
- 起始日期: 从该日期往前逐日回补（默认今天，北京时间）

从起始日期往前逐日尝试，遇到有数据的交易日就存快照，自动跳过周末/节假日，
攒够 N 个交易日停止。三种情形：
- 快照已存在且情绪完整 → 跳过；
- 快照已存在但情绪为空 → 只回填情绪（历史接口可回查）；
- 快照不存在 → 板块强度 + 情绪一并采集存储。
"""

import sys
from datetime import datetime, timedelta, timezone

from src.collectors.kaipanla import KaipanlaCollector
from src.storage.store import save_snapshot, load_snapshot, snapshot_path

_SHANGHAI_TZ = timezone(timedelta(hours=8))


def _mood_complete(mood: dict) -> bool:
    """判断 mood 是否含温度计算所需的完整家数原料。"""
    if not mood:
        return False
    return (
        mood.get("up_count") is not None
        and mood.get("down_count") is not None
        and mood.get("limit_up") is not None
        and mood.get("limit_down") is not None
    )


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    if len(sys.argv) > 2:
        start = datetime.strptime(sys.argv[2], "%Y-%m-%d").date()
    else:
        start = datetime.now(_SHANGHAI_TZ).date()

    collector = KaipanlaCollector()
    saved = 0
    day = start
    print(f"开始回补 {n} 个交易日（从 {start} 往前）...")
    while saved < n:
        ds = day.strftime("%Y-%m-%d")
        if snapshot_path(ds).exists():
            snap = load_snapshot(ds)
            if _mood_complete(snap.get("mood") or {}):
                saved += 1
                print(f"{ds} 快照与情绪已完整，跳过（{saved}/{n}）")
            else:
                mood = collector.fetch_mood_history(ds)
                if _mood_complete(mood):
                    save_snapshot(ds, snap["plates"], mood)
                    saved += 1
                    print(f"{ds} 已回填情绪（上涨 {mood['up_count']} / 下跌 {mood['down_count']}），{saved}/{n}")
                else:
                    print(f"{ds} 情绪回查为空，跳过")
        else:
            plates = collector.fetch_plate_ranking(ds)
            if plates:
                mood = collector.fetch_mood_history(ds)
                save_snapshot(ds, plates, mood)
                saved += 1
                mood_str = (
                    f"上涨 {mood['up_count']} / 下跌 {mood['down_count']}"
                    if _mood_complete(mood) else "情绪空"
                )
                print(f"{ds} 交易日，{len(plates)} 板块，{mood_str}，已存（{saved}/{n}）")
            else:
                print(f"{ds} 非交易日，跳过")
        day -= timedelta(days=1)

    print(f"完成：已回补 {saved} 个交易日")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
