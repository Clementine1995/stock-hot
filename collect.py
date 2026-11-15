"""采集命令：拉开盘啦当天数据并落本地快照。

用法：python collect.py [YYYY-MM-DD]
不带日期时默认使用今天（北京时间）。
"""

import sys
from datetime import datetime, timedelta, timezone

from src.collectors.kaipanla import KaipanlaCollector
from src.storage.store import save_snapshot

_SHANGHAI_TZ = timezone(timedelta(hours=8))


def main() -> int:
    if len(sys.argv) > 1:
        date = sys.argv[1]
    else:
        date = datetime.now(_SHANGHAI_TZ).strftime("%Y-%m-%d")

    collector = KaipanlaCollector()
    print(f"采集 {date} 板块强度排名 ...")
    plates = collector.fetch_plate_ranking(date)
    print(f"板块数: {len(plates)}")
    if plates:
        top = plates[0]
        print(f"  最强: {top['name']} 强度={top['strength']}")

    print("采集市场情绪 ...")
    mood = collector.fetch_market_mood()
    print(f"  情绪: {mood}")

    path = save_snapshot(date, plates, mood)
    print(f"已保存快照: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
