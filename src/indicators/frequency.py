"""板块强度榜出现频率统计。

统计近 N 个交易日里，每个板块进入「走强榜 top_n」的天数，
用于识别反复上榜的高频题材（持续性主线）。纯函数、无副作用，便于单测。

口径：每交易日取「强度 > 0 且按强度降序」的前 top_n 个板块作为走强榜，
统计某板块进入该榜的天数。与轮动面板每列走强段（top15）口径一致。
"""

_DEFAULT_WINDOW = 10
_DEFAULT_TOP_N = 15


def count_strong_rank_days(
    snapshots: list[dict], window: int = _DEFAULT_WINDOW, top_n: int = _DEFAULT_TOP_N
) -> list[dict]:
    """统计最近 window 个交易日每个板块进入走强榜 top_n 的天数。

    参数：
        snapshots  按日期升序的快照列表（load_all_snapshots 的返回）
        window     统计窗口（最近多少个交易日，默认 10）
        top_n      走强榜取前多少名（默认 15，与轮动面板一致）

    返回：按「上榜天数降序 → 最近强度降序」排列，仅含至少上榜 1 天的板块，每项：
        name          板块名
        code          板块代码
        rank_days     窗口内进入走强榜的天数
        last_strength 最近一个交易日的实际强度（无论是否上榜，如实反映当前状态）
        last_date     最近一个交易日的日期
    """
    if not snapshots:
        return []

    recent = snapshots[-window:] if len(snapshots) > window else snapshots
    dates = [s["date"] for s in recent]

    # 第一遍：记录每个板块最近一个交易日的实际强度（含未上榜的），
    # 让「最近强度」如实反映当前状态，而非停留在最后一次上榜的旧值。
    latest: dict[str, dict] = {}
    for snap in recent:
        date = snap["date"]
        for plate in snap.get("plates", []):
            name = plate.get("name")
            if not name:
                continue
            latest[name] = {
                "name": name,
                "code": plate.get("code"),
                "last_strength": plate.get("strength") or 0,
                "last_date": date,
            }

    # 第二遍：统计进入走强榜 top_n 的天数，并记录逐日上榜日期
    rank: dict[str, int] = {}
    on_dates: dict[str, set] = {}
    for snap in recent:
        strong = sorted(
            (p for p in snap.get("plates", []) if (p.get("strength") or 0) > 0),
            key=lambda p: p["strength"],
            reverse=True,
        )[:top_n]
        for plate in strong:
            name = plate.get("name")
            if name:
                rank[name] = rank.get(name, 0) + 1
                on_dates.setdefault(name, set()).add(snap["date"])

    result = []
    for name, days in rank.items():
        info = latest.get(name)
        if info is None:
            continue
        on = on_dates.get(name, set())
        result.append({
            "name": name,
            "code": info["code"],
            "rank_days": days,
            "last_strength": info["last_strength"],
            "last_date": info["last_date"],
            # 近 window 日逐日是否上榜（旧→新，1=上榜 0=未上榜），供前端画节奏点
            "daily": [1 if d in on else 0 for d in dates],
        })
    result.sort(key=lambda x: (-x["rank_days"], -(x["last_strength"] or 0)))
    return result
