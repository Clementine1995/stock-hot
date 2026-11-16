"""采集命令：拉开盘啦当天数据并落本地快照。

用法：python collect.py [YYYY-MM-DD]
不带日期时默认使用今天（北京时间）。
"""

import sys
from datetime import datetime, timedelta, timezone

from src.collectors.kaipanla import KaipanlaCollector
from src.indicators.stocks import collect_strong_stocks
from src.storage.store import save_snapshot, save_stocks

_SHANGHAI_TZ = timezone(timedelta(hours=8))


def main() -> int:
    collector = KaipanlaCollector()
    if len(sys.argv) > 1:
        date = sys.argv[1]
        print(f"采集 {date} 板块强度排名 ...")
        plates = collector.fetch_plate_ranking(date)
    else:
        print("采集最新交易日板块强度排名 ...")
        date, plates = collector.fetch_latest_plate_ranking()
        if not date:
            date = datetime.now(_SHANGHAI_TZ).strftime("%Y-%m-%d")
    print(f"板块数: {len(plates)}")
    if plates:
        top = plates[0]
        print(f"  最强: {top['name']} 强度={top['strength']}")

    mood = collector.fetch_mood_for(date)
    if mood:
        print(f"  情绪: {mood}")
    else:
        print("  历史回补：情绪不可回查，置空")

    path = save_snapshot(date, plates, mood)
    print(f"已保存快照: {path}")

    print("采集走强板块成分股 ...")
    stocks = collect_strong_stocks(collector, date, plates)
    if stocks:
        stocks_path = save_stocks(date, stocks)
        print(f"  成分股 {len(stocks)} 只，已保存: {stocks_path}")
    else:
        print("  无走强板块成分股")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
