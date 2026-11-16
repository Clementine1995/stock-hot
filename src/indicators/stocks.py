"""板块成分股聚合与核心票筛选。

把「走强板块 → 成分股」聚合为去重的股票列表，并从每板块成分股中筛出
「领涨票」（题材先锋）与「中军」（大票/权重），口径见 REQ-002 §5.3。

依赖仅标准库，纯函数、无副作用，便于单测。
"""

import re

# 默认每板块取几只核心票
_DEFAULT_TOP_N = 5

# 排除的板块名：防御性/大蓝筹板块，不做题材监测（可扩展）
_EXCLUDE_PLATES = {"银行"}


def _parse_board(board) -> int:
    """从「几天几板」文本解析连板数。

    「首板」→1、「3连板」→3、「3天2板」→2；空或无法解析 →0。
    """
    if not board:
        return 0
    text = str(board)
    m = re.search(r"(\d+)连板", text)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)天(\d+)板", text)
    if m:
        return int(m.group(2))
    if "首板" in text:
        return 1
    return 0


def _num(value) -> float:
    """把数值或数值字符串安全转为 float，失败返回 0.0。

    成分股接口的市值字段是字符串，比较前需转换。
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def filter_strong_plates(plates: list[dict], exclude_names=None, top_n: int = 10) -> list[dict]:
    """筛出走强板块：strength > 0，排除指定板块，按强度降序取 top_n。

    行情差时走强板块不足 top_n 个，则全采（自然就 1~3 个）。
    """
    if exclude_names is None:
        exclude_names = _EXCLUDE_PLATES
    strong = [
        p for p in plates
        if p["strength"] > 0 and p["name"] not in exclude_names
    ]
    strong.sort(key=lambda p: p["strength"], reverse=True)
    return strong[:top_n]


def merge_stocks(plate_stocks: dict) -> list[dict]:
    """把 {板块名: 成分股列表} 合并为去重的股票列表。

    同一只股票可属多个板块，去重后每项追加 plates（所属板块名列表）。
    """
    by_code: dict[str, dict] = {}
    for plate_name, stocks in plate_stocks.items():
        for stock in stocks:
            code = stock["code"]
            item = by_code.get(code)
            if item is None:
                item = dict(stock)
                item["plates"] = []
                by_code[code] = item
            if plate_name not in item["plates"]:
                item["plates"].append(plate_name)
    return list(by_code.values())


def pick_leaders(stocks: list[dict], top_n: int = _DEFAULT_TOP_N) -> list[dict]:
    """筛领涨票（题材先锋）：连板数降序 → 领涨次数降序 → 当日涨幅降序。"""
    def key(stock):
        return (
            -_parse_board(stock.get("board")),
            -_num(stock.get("lead_count")),
            -_num(stock.get("change_pct")),
        )
    return sorted(stocks, key=key)[:top_n]


def pick_generals(stocks: list[dict], top_n: int = _DEFAULT_TOP_N) -> list[dict]:
    """筛中军（大票/权重）：成交额降序 → 总市值降序 → 主力净额降序。"""
    def key(stock):
        return (
            -_num(stock.get("turnover")),
            -_num(stock.get("total_mv")),
            -_num(stock.get("main_net")),
        )
    return sorted(stocks, key=key)[:top_n]


def collect_strong_stocks(collector, date: str, plates=None) -> list[dict]:
    """采集走强板块的成分股并去重聚合。

    流程：拉板块强度 → 筛走强板块（排除银行，top 10）→ 逐板块拉成分股 → 去重。
    调用方若已拉取板块排名，可传入 plates 避免重复请求。
    collector 需实现 fetch_plate_ranking 与 fetch_plate_stocks（见 collectors/base.py），
    本函数通过鸭子类型依赖采集器，不在模块内显式 import 采集层。
    """
    if plates is None:
        plates = collector.fetch_plate_ranking(date)
    strong = filter_strong_plates(plates)
    plate_stocks: dict[str, list] = {}
    for plate in strong:
        stocks = collector.fetch_plate_stocks(plate["code"], date)
        if stocks:
            plate_stocks[plate["name"]] = stocks
    return merge_stocks(plate_stocks)
