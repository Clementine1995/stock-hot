"""渲染命令：把 data/ 下全部快照生成情绪温度面板。

用法：python render_mood.py
产物：output/mood.html（自包含，双击即可打开）
"""

from src.render.mood import build_mood_series, save_mood
from src.storage.store import load_all_snapshots


def main() -> int:
    snapshots = load_all_snapshots()
    print(f"读取快照 {len(snapshots)} 份")
    series = build_mood_series(snapshots)
    for item in series:
        print(f"  {item['date']}: 温度 {item['temperature']}")
    path = save_mood(series)
    print(f"已生成面板: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
