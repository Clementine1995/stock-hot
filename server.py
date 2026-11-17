"""本地常驻 Web 服务。

用法：
    python server.py [--port 8000]
启动后浏览器打开 http://127.0.0.1:8000

零第三方依赖（标准库 http.server），只绑定 127.0.0.1，不上云、不对外。
路由：
    GET  /            返回站点单页（web/index.html）
    GET  /api/data    返回全部快照 + 轮动/温度/报表所需的结构化数据
    POST /api/refresh 采集最近一个交易日（或指定 date）并落快照
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from src.collectors.kaipanla import KaipanlaCollector
from src.indicators.frequency import count_strong_rank_days
from src.indicators.mood import mood_temperature
from src.indicators.stocks import collect_strong_stocks, pick_generals, pick_leaders
from src.llm.review import generate_review, load_review
from src.render.mood import build_mood_series
from src.render.wheel import build_panel_data
from src.storage.store import load_all_snapshots, load_all_stocks, save_snapshot, save_stocks

_SHANGHAI_TZ = timezone(timedelta(hours=8))
_WEB_DIR = Path(__file__).resolve().parent / "web"
_INDEX_PATH = _WEB_DIR / "index.html"


def _load_index() -> str:
    return _INDEX_PATH.read_text(encoding="utf-8")


def _rank_plates(plates, key, reverse=True, n=10):
    """按某字段给板块排序取前 n（忽略缺失值）。"""
    return sorted(
        (p for p in plates if p.get(key) is not None),
        key=lambda p: p[key], reverse=reverse,
    )[:n]


def build_web_data() -> dict:
    """组装前端单页所需的结构化数据。"""
    snapshots = load_all_snapshots()
    days, series, records = build_panel_data(snapshots)
    mood_series = build_mood_series(snapshots)

    latest = None
    if snapshots:
        snap = max(snapshots, key=lambda s: s["date"])
        mood = snap.get("mood") or {}
        try:
            temp = mood_temperature(
                mood.get("up_count"), mood.get("down_count"),
                mood.get("limit_up"), mood.get("limit_down"),
            )
        except (TypeError, ValueError):
            temp = None
        plates = snap["plates"]
        strong = sorted(
            (p for p in plates if p["strength"] > 0),
            key=lambda p: p["strength"], reverse=True,
        )[:10]
        weak = sorted(
            (p for p in plates if p["strength"] < 0),
            key=lambda p: p["strength"],
        )[:10]
        latest = {
            "date": snap["date"],
            "temperature": temp,
            "mood": mood,
            "strong_top10": strong,
            "weak_top10": weak,
            # 板块多维榜单（当日市场全景）
            "change_top10": _rank_plates(plates, "change_pct", True),      # 涨幅榜
            "change_bottom10": _rank_plates(plates, "change_pct", False),  # 跌幅榜
            "main_net_top10": _rank_plates(plates, "main_net", True),      # 主力净流入榜
            "main_net_bottom10": _rank_plates(plates, "main_net", False),  # 主力净流出榜
            "turnover_top10": _rank_plates(plates, "turnover", True),      # 成交额榜
        }

    return {
        "days": days,
        "series": series,
        "mood_series": mood_series,
        "stats": {"n_days": len(days), "n_records": records, "n_plates": len(series)},
        "latest": latest,
        "stock_pool": build_stock_pool(),
        "plate_frequency": count_strong_rank_days(snapshots, window=10, top_n=15),
    }


def build_stock_pool() -> dict:
    """从最新成分股快照构建票池：每个板块的领涨票 top5 + 中军 top5。"""
    snapshots = load_all_stocks()
    if not snapshots:
        return None
    latest = max(snapshots, key=lambda s: s["date"])
    stocks = latest["stocks"]

    by_plate: dict[str, list] = {}
    for stock in stocks:
        for plate in stock.get("plates") or []:
            by_plate.setdefault(plate, []).append(stock)

    pool = []
    for plate_name, plate_stocks in by_plate.items():
        pool.append({
            "name": plate_name,
            "leaders": pick_leaders(plate_stocks),
            "generals": pick_generals(plate_stocks),
        })

    def plate_turnover(item):
        return sum((g.get("turnover") or 0) for g in item["generals"])

    pool.sort(key=plate_turnover, reverse=True)
    return {"date": latest["date"], "plates": pool}


def find_latest_trading_day(collector: KaipanlaCollector, start):
    """找最近一个「有数据」的交易日，返回 (date, plates)。

    优先用当日域拿最新交易日（当天数据在历史域未归档）；
    当日域不可用时回退到历史域逐日回退。
    """
    day_str, plates = collector.fetch_latest_plate_ranking()
    if day_str and plates:
        return datetime.strptime(day_str, "%Y-%m-%d").date(), plates
    day = start
    for _ in range(15):  # 最多回退 15 个自然日，覆盖节假日
        plates = collector.fetch_plate_ranking(day.strftime("%Y-%m-%d"))
        if plates:
            return day, plates
        day -= timedelta(days=1)
    return None, None


def collect_stocks_archived(collector, start_date_str, plates):
    """采集核心票成分股，当天历史域未归档时回退到最近归档日。

    成分股接口 ZhiShuStockList_W8 只在历史域归档 T-1 及更早数据，
    当天返回 errcode=1020（fetch_plate_stocks 已转成空列表）。
    返回 (实际归档日, 成分股列表)；全部失败返回 (start_date_str, [])。
    """
    day = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    for _ in range(10):  # 最多回退 10 个自然日，覆盖长假
        date_str = day.strftime("%Y-%m-%d")
        stocks = collect_strong_stocks(collector, date_str, plates)
        if stocks:
            return date_str, stocks
        day -= timedelta(days=1)
    return start_date_str, []


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, ctype: str, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, obj, status: int = 200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(status, "application/json; charset=utf-8", body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", _load_index().encode("utf-8"))
        elif parsed.path == "/api/data":
            self._send_json(build_web_data())
        elif parsed.path == "/api/plate_stocks":
            self._handle_plate_stocks(parsed)
        elif parsed.path == "/api/review":
            self._handle_review_get()
        else:
            self._send_json({"error": "not found"}, 404)

    def _handle_review_get(self):
        """读取最新交易日的点评缓存（不产生付费调用）。"""
        snapshots = load_all_snapshots()
        if not snapshots:
            self._send_json({"ok": False, "review": None})
            return
        date = max(snapshots, key=lambda s: s["date"])["date"]
        cached = load_review(date)
        if cached:
            self._send_json({"ok": True, "date": date, "review": cached.get("review"), "cached": True})
        else:
            self._send_json({"ok": False, "date": date, "review": None})

    def _handle_plate_stocks(self, parsed):
        """按需拉取指定板块的核心票（领涨 top5 + 中军 top5）。"""
        qs = parse_qs(parsed.query)
        code = qs.get("code", [None])[0]
        date = qs.get("date", [None])[0]
        if not code:
            self._send_json({"ok": False, "error": "缺少 code 参数"}, 400)
            return
        # 未指定日期时，优先用最近已归档的成分股快照日期；无则退回最新板块快照日期
        if not date:
            stocks_snaps = load_all_stocks()
            if stocks_snaps:
                date = max(stocks_snaps, key=lambda s: s["date"])["date"]
            else:
                snapshots = load_all_snapshots()
                if not snapshots:
                    self._send_json({"ok": False, "error": "暂无快照数据"}, 200)
                    return
                date = max(snapshots, key=lambda s: s["date"])["date"]
        collector = KaipanlaCollector()
        try:
            stocks = collector.fetch_plate_stocks(code, date)
            # 当天成分股未归档（errcode=1020 → 空列表），往前回退到最近归档日
            day = datetime.strptime(date, "%Y-%m-%d").date()
            for _ in range(10):
                if stocks:
                    break
                day -= timedelta(days=1)
                date = day.strftime("%Y-%m-%d")
                stocks = collector.fetch_plate_stocks(code, date)
            leaders = pick_leaders(stocks)
            generals = pick_generals(stocks)
            self._send_json({
                "ok": True,
                "date": date,
                "n_stocks": len(stocks),
                "leaders": leaders,
                "generals": generals,
            })
        except Exception as exc:  # noqa: BLE001
            self._send_json({"ok": False, "error": str(exc)}, 500)

    def _handle_review_post(self, parsed):
        """生成当日点评（手动触发，付费调用）。"""
        qs = parse_qs(parsed.query)
        force = qs.get("force", ["0"])[0] in ("1", "true", "True")
        snapshots = load_all_snapshots()
        result = generate_review(snapshots, force=force)
        self._send_json(result)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/review":
            self._handle_review_post(parsed)
            return
        if parsed.path != "/api/refresh":
            self._send_json({"error": "not found"}, 404)
            return
        qs = parse_qs(parsed.query)
        date_arg = qs.get("date", [None])[0]
        collector = KaipanlaCollector()
        try:
            if date_arg:
                day = datetime.strptime(date_arg, "%Y-%m-%d").date()
                plates = collector.fetch_plate_ranking(date_arg)
            else:
                today = datetime.now(_SHANGHAI_TZ).date()
                day, plates = find_latest_trading_day(collector, today)
            if not plates:
                self._send_json({"ok": False, "error": "未找到可采集的交易日"}, 200)
                return
            ds = day.strftime("%Y-%m-%d")
            mood = collector.fetch_mood_for(ds)
            save_snapshot(ds, plates, mood)
            # 成分股：历史域当天未归档（errcode=1020），回退到最近归档日
            stock_date, stocks = collect_stocks_archived(collector, ds, plates)
            if stocks:
                save_stocks(stock_date, stocks)
            self._send_json({"ok": True, "date": ds, "n_plates": len(plates), "n_stocks": len(stocks)})
        except Exception as exc:  # noqa: BLE001 —— 采集异常需如实返回前端
            self._send_json({"ok": False, "error": str(exc)}, 500)

    def log_message(self, fmt, *args):  # 精简访问日志
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main():
    port = 8000
    if len(sys.argv) == 3 and sys.argv[1] == "--port":
        port = int(sys.argv[2])
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"stock-hot 站点已启动: http://127.0.0.1:{port}")
    print("浏览器打开上面的地址即可；按 Ctrl+C 停止。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
