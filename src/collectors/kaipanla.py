"""开盘啦匿名接口采集器。

数据来源：开盘啦 App 老版本匿名接口（apiv=w42），无需 token、无需抓包。
接口域名与字段映射出处见 docs/research-开盘啦数据源调研.md：

    历史数据  apphis.longhuvip.com  RealRankingInfo  板块强度排名（支持 Date 回查）
    当日数据  apphwhq.longhuvip.com MoodNumCount      市场情绪家数（仅返回最新）

依赖仅 Python 标准库，无第三方包。
"""

import gzip
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

# iOS 端专用接口（异动提醒等新功能仅走 iOS 链路，域名/协议版本与 Android 不同）
_IOS_HOST = "https://apphq.longhuvip.com/w1/api/index.php"

# 接口固定客户端标识；接口不要求 token / UserID，仅需随机 DeviceID。
_API_VERSION = "w42"
_APP_VERSION = "5.21.0.2"
_USER_AGENT = "Dalvik/2.1.0 (Linux; U; Android 9; 23116PN5BC Build/PQ3A.190605.01141736)"

# iOS 端客户端标识（异动接口：PhoneOSNew=2 / apiv=w33 / iOS UA，仍为匿名接口）
_IOS_API_VERSION = "w33"
_IOS_APP_VERSION = "5.11.0.3"
_IOS_USER_AGENT = "lhb/5.11.3 (com.kaipanla.www; build:1; iOS 16.3.1) Alamofire/5.11.3"

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

    def _post_ios(self, params: dict) -> dict:
        """向开盘啦 iOS 端接口发 POST 请求并解析 JSON（异动提醒等仅 iOS 链路可用）。"""
        body_params = dict(params)
        body_params.update({
            "PhoneOSNew": "2",
            "VerSion": _IOS_APP_VERSION,
            "apiv": _IOS_API_VERSION,
        })
        data = urllib.parse.urlencode(body_params).encode("utf-8")
        request = urllib.request.Request(
            _IOS_HOST,
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "User-Agent": _IOS_USER_AGENT,
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            raw = response.read()
            if response.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            return json.loads(raw.decode("utf-8"))

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

    def fetch_mood_history(self, date: str) -> dict:
        """拉取指定交易日全市场情绪（支持历史回查）。

        HisZhangFuDetail（c=HisHomeDingPan）带 Day 参数、历史域 apphis，
        返回 info 字典含全市场上涨/下跌家数与涨停/跌停家数，口径与
        MoodNumCount 一致（SZJS/XDJS/ZTJS/DTJS 对应 SZJS/XDJS/SJZT/SJDT）。

        非交易日（errcode=1020）返回空 dict。
        """
        payload = self._post(_HIS_HOST, {
            "a": "HisZhangFuDetail",
            "c": "HisHomeDingPan",
            "Day": date,
        })
        errcode = str(payload.get("errcode"))
        if errcode == "1020":
            return {}
        if errcode != "0":
            raise RuntimeError(
                f"HisZhangFuDetail 接口返回错误: errcode={errcode}"
            )

        def _to_int(value):
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        info = payload.get("info") or {}
        return {
            "up_count": _to_int(info.get("SZJS")),
            "down_count": _to_int(info.get("XDJS")),
            # SJZT/SJDT 为「实际涨停/实际跌停」，与 MoodNumCount 的 ZTJS/DTJS 口径一致
            "limit_up": _to_int(info.get("SJZT")),
            "limit_down": _to_int(info.get("SJDT")),
            "sign": info.get("sign"),
        }

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

    def fetch_limit_up_ladder(self, date: str) -> dict:
        """拉取指定交易日的全市场连板梯队（GetYTFP_SCTD，历史域 apphis）。

        返回按连板高度（2 板及以上）降序的梯队 + 首板数量：
            {
                "date": date,
                "max_board": int,           # 最高连板（无 2 板及以上则为 0）
                "first_board_count": int,   # 首板数量
                "ladder": [{"board": int, "stocks": [{"code","name"}, ...]}, ...],
            }
        反包板（Tip=0）与打开高度标注（Tip=9）不在标准梯队内，不采集。
        """
        payload = self._post(_HIS_HOST, {
            "a": "GetYTFP_SCTD",
            "c": "FuPanLa",
            "Date": date,
        })
        errcode = str(payload.get("errcode"))
        if errcode == "1020":
            return {"date": date, "max_board": 0, "first_board_count": 0, "ladder": []}
        if errcode != "0":
            raise RuntimeError(f"GetYTFP_SCTD 接口返回错误: errcode={errcode}")
        groups = payload.get("List") or []
        ladder_map: dict[int, list] = {}
        first_count = 0
        for group in groups:
            tip = str(group.get("Tip", ""))
            stocks = group.get("Stocks") or []
            if tip == "1":
                first_count = len(stocks)
            elif tip in ("0", "9"):
                continue  # 反包板 / 高度标注，不进标准梯队
            else:
                try:
                    board = int(tip)
                except (TypeError, ValueError):
                    continue
                if board >= 2:
                    ladder_map[board] = [
                        {"code": s.get("StockID"), "name": s.get("Name")}
                        for s in stocks
                    ]
        ladder = [
            {"board": board, "stocks": ladder_map[board]}
            for board in sorted(ladder_map, reverse=True)
        ]
        return {
            "date": date,
            "max_board": max(ladder_map) if ladder_map else 0,
            "first_board_count": first_count,
            "ladder": ladder,
        }

    def fetch_serious_abnormal(self, date: str) -> dict:
        """拉取指定交易日的严重异动（偏离值预警，GetPianLiZhi_Index，iOS 域 apphq）。

        返回偏离值监控中的个股（即将触发/临近触发严重异动），结构：
            {
                "date": date,
                "total": int,          # 监控池总数（Many_Num）
                "abnormal": [          # 接口只返回偏离值最大的前几只
                    {"code","name","flag","reason","change_pct","days",
                     "cum_deviation","trigger_desc","trigger_threshold",
                     "deviation_left","trigger_date","trigger_price","status"},
                    ...
                ],
            }
        非交易日（errcode=1020）返回 total=0 + 空列表。
        """
        payload = self._post_ios({
            "a": "GetPianLiZhi_Index",
            "c": "StockBidYiDong",
            "Day": date,
        })
        errcode = str(payload.get("errcode"))
        if errcode == "1020":
            return {"date": date, "total": 0, "abnormal": []}
        if errcode != "0":
            raise RuntimeError(f"GetPianLiZhi_Index 接口返回错误: errcode={errcode}")
        total = payload.get("Many_Num") or 0
        rows = payload.get("List") or []
        abnormal = []
        for row in rows:
            abnormal.append({
                "code": _row_get(row, 0),
                "name": _row_get(row, 1),
                "flag": _row_get(row, 2),
                "reason": _row_get(row, 3),
                "change_pct": _row_get(row, 4),
                "days": _row_get(row, 5),
                "cum_deviation": _row_get(row, 6),
                "trigger_desc": _row_get(row, 7),
                "trigger_threshold": _row_get(row, 8),
                "deviation_left": _row_get(row, 9),
                "trigger_date": _row_get(row, 10),
                "trigger_price": _row_get(row, 11),
                "status": _row_get(row, 12),
            })
        return {"date": date, "total": total, "abnormal": abnormal}
