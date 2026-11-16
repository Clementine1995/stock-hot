"""开盘啦匿名接口采集器。

数据来源：开盘啦 App 老版本匿名接口（apiv=w42），无需 token、无需抓包。
接口域名与字段映射出处见 docs/research-开盘啦数据源调研.md：

    历史数据  apphis.longhuvip.com  RealRankingInfo  板块强度排名（支持 Date 回查）
    当日数据  apphwhq.longhuvip.com MoodNumCount      市场情绪家数（仅返回最新）

依赖仅 Python 标准库，无第三方包。
"""

import json
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

from .base import Collector

# 北京时间（Asia/Shanghai 无夏令时，恒为 UTC+8）
_SHANGHAI_TZ = timezone(timedelta(hours=8))

_HIS_HOST = "https://apphis.longhuvip.com/w1/api/index.php"
_HQ_HOST = "https://apphwhq.longhuvip.com/w1/api/index.php"

# 接口固定客户端标识；接口不要求 token / UserID，仅需随机 DeviceID。
_API_VERSION = "w42"
_APP_VERSION = "5.21.0.2"
_USER_AGENT = "Dalvik/2.1.0 (Linux; U; Android 9; 23116PN5BC Build/PQ3A.190605.01141736)"

# RealRankingInfo 返回 list[][] 的字段下标（语义见调研文档）
_PLATE_CODE = 0
_PLATE_NAME = 1
_PLATE_STRENGTH = 2
_PLATE_CHANGE_PCT = 3
_PLATE_TURNOVER = 5
_PLATE_MAIN_NET = 6

# RealRankingInfo 分页参数：st 必须固定为 30，改成其他值接口返回空；
# Index 为起始偏移，每页 +30 直到返回空。
_PAGE_SIZE = 30

# MoodNumCount 返回 list 的字段名
_MOOD_UP = "SZJS"      # 上涨家数
_MOOD_DOWN = "XDJS"    # 下跌家数
_MOOD_LIMIT_UP = "ZTJS"    # 涨停家数
_MOOD_LIMIT_DOWN = "DTJS"  # 跌停家数
_MOOD_BL = "bl"        # 涨跌比（口径待确认）

# ZhiShuStockList_W8 返回 list[][] 的字段下标（成分股，见 REQ-002 §5.2）
_STOCK_CODE = 0        # 股票代码
_STOCK_NAME = 1        # 股票名称
_STOCK_TAGS = 4        # 细分板块标签（如「光模块、光通信」）
_STOCK_PRICE = 5       # 价格
_STOCK_CHANGE_PCT = 6  # 当日涨幅 %
_STOCK_TURNOVER = 7    # 成交额（元）
_STOCK_MAIN_NET = 13   # 主力净额（元）
_STOCK_RANGE_CHG = 20  # 区间涨幅
_STOCK_BOARD = 23      # 几天几板（「首板」/「3连板」，空=无连板）
_STOCK_TOTAL_MV = 37   # 总市值（元）
_STOCK_FLOAT_MV = 38   # 流通市值（元）
_STOCK_LEAD_COUNT = 40 # 领涨次数


def _row_get(row: list, index: int):
    """安全读取 list 下标，越界返回 None。"""
    return row[index] if index < len(row) else None


class KaipanlaCollector(Collector):
    """开盘啦匿名接口采集器。"""

    name = "kaipanla"

    def __init__(self, timeout: float = 30.0):
        self._timeout = timeout

    def _post(self, host: str, params: dict) -> dict:
        """向开盘啦接口发 POST 表单请求并解析 JSON。

        失败（网络异常 / 非 200 / 非 JSON）时抛出原始异常，保留上下文，不静默。
        """
        body_params = dict(params)
        body_params.update({
            "PhoneOSNew": "1",
            "DeviceID": str(uuid.uuid4()),
            "VerSion": _APP_VERSION,
            "apiv": _API_VERSION,
        })
        data = urllib.parse.urlencode(body_params).encode("utf-8")
        request = urllib.request.Request(
            host,
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "User-Agent": _USER_AGENT,
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw)

    def fetch_plate_ranking(self, date: str) -> list[dict]:
        """拉取指定交易日板块强度排名（历史域 apphis，Date 回查）。"""
        _, plates = self._fetch_plate_ranking(_HIS_HOST, date)
        return plates

    def fetch_latest_plate_ranking(self) -> tuple:
        """拉取最新交易日板块强度排名（当日域 apphwhq），返回 (日期, 板块列表)。

        历史域当天数据未归档（errcode=1020），最新数据须走当日域；
        该域忽略 Date、恒返回最新，返回的 Day 字段标注实际交易日。
        """
        today = datetime.now(_SHANGHAI_TZ).strftime("%Y-%m-%d")
        return self._fetch_plate_ranking(_HQ_HOST, today)

    def _fetch_plate_ranking(self, host: str, date: str) -> tuple:
        """分页拉取板块强度排名，返回 (实际交易日, 板块列表)。"""
        plates: list[dict] = []
        seen: set[str] = set()
        day = None
        index = 0
        while True:
            payload = self._post(host, {
                "Order": "1",
                "a": "RealRankingInfo",
                "st": str(_PAGE_SIZE),
                "c": "ZhiShuRanking",
                "Index": str(index),
                "Date": date,
                "Type": "1",
                "ZSType": "7",
            })
            errcode = str(payload.get("errcode"))
            if errcode == "1020":
                # 1020 = 非交易日或数据未更新，返回已收集结果
                break
            if errcode != "0":
                raise RuntimeError(f"RealRankingInfo 接口返回错误: errcode={errcode}")
            if day is None:
                day = (payload.get("Day") or [None])[0]
            rows = payload.get("list") or []
            if not rows:
                break
            new_count = 0
            for row in rows:
                code = row[_PLATE_CODE]
                if code in seen:
                    continue
                seen.add(code)
                plates.append({
                    "code": code,
                    "name": row[_PLATE_NAME],
                    "strength": row[_PLATE_STRENGTH],
                    "change_pct": row[_PLATE_CHANGE_PCT],
                    "turnover": row[_PLATE_TURNOVER],
                    "main_net": row[_PLATE_MAIN_NET],
                })
                new_count += 1
            if new_count == 0:
                # 整页重复说明翻页越界，停止，避免死循环
                break
            index += _PAGE_SIZE
        return day, plates

    def fetch_market_mood(self) -> dict:
        payload = self._post(_HQ_HOST, {
            "a": "MoodNumCount",
            "c": "MarketMood",
        })
        if str(payload.get("errcode")) != "0":
            raise RuntimeError(
                f"MoodNumCount 接口返回错误: errcode={payload.get('errcode')}"
            )
        mood = payload.get("list") or {}
        return {
            "up_count": mood.get(_MOOD_UP),
            "down_count": mood.get(_MOOD_DOWN),
            "limit_up": mood.get(_MOOD_LIMIT_UP),
            "limit_down": mood.get(_MOOD_LIMIT_DOWN),
            "bl": mood.get(_MOOD_BL),
        }

    def fetch_mood_for(self, date: str) -> dict:
        """拉取指定交易日市场情绪；情绪接口仅支持最新交易日。

        date 为最新交易日时返回当日情绪，历史日期返回空 dict，
        避免把「最新情绪」误写入历史快照（历史情绪接口不可回查）。
        """
        latest_date, _ = self.fetch_latest_plate_ranking()
        if latest_date == date:
            return self.fetch_market_mood()
        return {}

    def fetch_plate_stocks(self, plate_id: str, date: str) -> list[dict]:
        """拉取指定板块在指定交易日的完整成分股列表。

        ZhiShuStockList_W8 的 Type=22 返回完整成分股（非 top9），
        域名必须是历史域 apphis（当日期域返回空），字段映射见 REQ-002 §5.2。
        """
        payload = self._post(_HIS_HOST, {
            "a": "ZhiShuStockList_W8",
            "c": "ZhiShuRanking",
            "PlateID": plate_id,
            "Date": date,
            "Type": "22",
        })
        errcode = str(payload.get("errcode"))
        if errcode == "1020":
            # 非交易日或数据未更新，返回空列表
            return []
        if errcode != "0":
            raise RuntimeError(
                f"ZhiShuStockList_W8 接口返回错误: errcode={errcode}"
            )
        rows = payload.get("list") or []
        stocks = []
        for row in rows:
            stocks.append({
                "code": _row_get(row, _STOCK_CODE),
                "name": _row_get(row, _STOCK_NAME),
                "tags": _row_get(row, _STOCK_TAGS),
                "price": _row_get(row, _STOCK_PRICE),
                "change_pct": _row_get(row, _STOCK_CHANGE_PCT),
                "turnover": _row_get(row, _STOCK_TURNOVER),
                "main_net": _row_get(row, _STOCK_MAIN_NET),
                "range_chg": _row_get(row, _STOCK_RANGE_CHG),
                "board": _row_get(row, _STOCK_BOARD),
                "total_mv": _row_get(row, _STOCK_TOTAL_MV),
                "float_mv": _row_get(row, _STOCK_FLOAT_MV),
                "lead_count": _row_get(row, _STOCK_LEAD_COUNT),
            })
        return stocks
