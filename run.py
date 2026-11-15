"""stock-hot 一条命令入口。

流程：采集开盘啦数据 → 落快照 → 算情绪温度 → 渲染轮动面板 + 温度面板 + 数字报表。

用法：python run.py [YYYY-MM-DD]
不带日期默认今天（北京时间）。数据目录 data/，产物 output/。
"""

import sys
from datetime import datetime, timedelta, timezone

from src.collectors.kaipanla import KaipanlaCollector
from src.indicators.mood import mood_temperature
from src.render.mood import build_mood_series, save_mood
from src.render.report import save_report
from src.render.wheel import build_panel_data, save_wheel
from src.storage.store import load_all_snapshots, save_snapshot

_SHANGHAI_TZ = timezone(timedelta(hours=8))


def main() -> int:
    if len(sys.argv) > 1:
        date = sys.argv[1]
    else:
        date = datetime.now(_SHANGHAI_TZ).strftime("%Y-%m-%d")

    print(f"[1/4] 采集 {date} ...")
    collector = KaipanlaCollector()
    plates = collector.fetch_plate_ranking(date)
    if not plates:
        print(f"错误：{date} 无板块数据（非交易日或数据未更新）。")
        print("      请指定交易日，例如：python run.py 2026-11-13")
        return 1
    mood = collector.fetch_market_mood()
    save_snapshot(date, plates, mood)
    print(f"      板块 {len(plates)} 个")

    print("[2/4] 计算情绪温度 ...")
    temperature = mood_temperature(
        mood["up_count"], mood["down_count"],
        mood["limit_up"], mood["limit_down"],
    )
    print(f"      温度 {temperature}")

    print("[3/4] 渲染面板 ...")
    snapshots = load_all_snapshots()
    days, series = build_panel_data(snapshots)
    wheel_path = save_wheel(days, series)
    mood_series = build_mood_series(snapshots)
    mood_path = save_mood(mood_series)
    print(f"      轮动面板 {wheel_path.name}")
    print(f"      温度面板 {mood_path.name}")

    print("[4/4] 生成数字报表 ...")
    report_path = save_report(date, plates, mood, temperature)
    print(f"      报表 {report_path.name}")

    print("完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
