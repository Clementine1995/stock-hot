"""回补历史交易日的板块强度快照。

用法：
    python backfill.py [N] [起始日期]
- N: 回补的交易日数量（默认 10）
- 起始日期: 从该日期往前逐日回补（默认今天，北京时间）

从起始日期往前逐日尝试，遇到有数据的交易日就存快照，自动跳过周末/节假日，
攒够 N 个交易日停止。已存在的快照不重复采集（保留原有含情绪字段的当日快照）。
"""

import sys
from datetime import datetime, timedelta, timezone

from src.collectors.kaipanla import KaipanlaCollector
from src.storage.store import save_snapshot, snapshot_path

_SHANGHAI_TZ = timezone(timedelta(hours=8))


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
            saved += 1
            print(f"{ds} 已有快照，跳过（{saved}/{n}）")
        else:
            plates = collector.fetch_plate_ranking(ds)
            if plates:
                # 历史情绪接口不可回查，mood 置空；轮动面板只用 plates
                save_snapshot(ds, plates, {})
                saved += 1
                print(f"{ds} 交易日，{len(plates)} 板块，已存（{saved}/{n}）")
            else:
                print(f"{ds} 非交易日，跳过")
        day -= timedelta(days=1)

    print(f"完成：已回补 {saved} 个交易日")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
