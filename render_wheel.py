"""渲染命令：把 data/ 下全部快照生成题材强度轮动面板（日历墙版）。

用法：python render_wheel.py
产物：output/wheel.html（自包含，双击即可打开）
"""

from src.storage.store import load_all_snapshots
from src.render.wheel import build_panel_data, save_wheel


def main() -> int:
    snapshots = load_all_snapshots()
    print(f"读取快照 {len(snapshots)} 份")
    days, series, records = build_panel_data(snapshots)
    for day in days:
        print(f"  {day['date']}: 强势 {len(day['strong'])} / 弱势 {len(day['weak'])}")
    print(f"共 {len(days)} 个交易日 · {records} 条记录 · {len(series)} 个题材")
    path = save_wheel()
    print(f"已生成面板: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
