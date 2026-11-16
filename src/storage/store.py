"""本地快照读写。

数据目录 data/（项目内），按交易日存 JSON 快照，作为后续指标计算与渲染的唯一数据来源。
两类快照：
- snapshot-YYYY-MM-DD.json：板块强度排名 + 市场情绪（历史情绪不可回查，只能每天累积）
- stocks-YYYY-MM-DD.json：板块成分股（走强板块，支持历史回查）
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 北京时间（Asia/Shanghai 无夏令时，恒为 UTC+8）
_SHANGHAI_TZ = timezone(timedelta(hours=8))

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def snapshot_path(date: str) -> Path:
    """返回某交易日快照文件路径。"""
    return DATA_DIR / f"snapshot-{date}.json"


def save_snapshot(date: str, plates: list[dict], mood: dict) -> Path:
    """把某交易日的板块排名与市场情绪落成一份 JSON 快照，返回文件路径。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "date": date,
        "collected_at": datetime.now(_SHANGHAI_TZ).isoformat(timespec="seconds"),
        "plates": plates,
        "mood": mood,
    }
    path = snapshot_path(date)
    path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_snapshot(date: str) -> dict:
    """读取某交易日快照；不存在时抛出 FileNotFoundError。"""
    path = snapshot_path(date)
    return json.loads(path.read_text(encoding="utf-8"))


def load_all_snapshots() -> list[dict]:
    """读取 data/ 下全部快照，按日期升序返回。"""
    snapshots = []
    for path in sorted(DATA_DIR.glob("snapshot-*.json")):
        snapshots.append(json.loads(path.read_text(encoding="utf-8")))
    snapshots.sort(key=lambda s: s["date"])
    return snapshots


def stocks_path(date: str) -> Path:
    """返回某交易日成分股快照文件路径。"""
    return DATA_DIR / f"stocks-{date}.json"


def save_stocks(date: str, stocks: list[dict]) -> Path:
    """把某交易日的成分股列表落成 JSON 快照，返回文件路径。

    stocks 为已按股票代码去重、且每项含 plates（所属板块名列表）的列表，
    去重与聚合逻辑在指标层（indicators/stocks.py）完成，本函数只负责落盘。
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "date": date,
        "collected_at": datetime.now(_SHANGHAI_TZ).isoformat(timespec="seconds"),
        "stocks": stocks,
    }
    path = stocks_path(date)
    path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_stocks(date: str) -> dict:
    """读取某交易日成分股快照；不存在时抛出 FileNotFoundError。"""
    path = stocks_path(date)
    return json.loads(path.read_text(encoding="utf-8"))


def load_all_stocks() -> list[dict]:
    """读取 data/ 下全部成分股快照，按日期升序返回。"""
    snapshots = []
    for path in sorted(DATA_DIR.glob("stocks-*.json")):
        snapshots.append(json.loads(path.read_text(encoding="utf-8")))
    snapshots.sort(key=lambda s: s["date"])
    return snapshots
