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
from src.indicators.mood import mood_temperature
from src.indicators.stocks import collect_strong_stocks, pick_generals, pick_leaders
from src.render.mood import build_mood_series
from src.render.wheel import build_panel_data
from src.storage.store import load_all_snapshots, load_all_stocks, save_snapshot, save_stocks

_SHANGHAI_TZ = timezone(timedelta(hours=8))
_WEB_DIR = Path(__file__).resolve().parent / "web"
_INDEX_PATH = _WEB_DIR / "index.html"


def _load_index() -> str:
    return _INDEX_PATH.read_text(encoding="utf-8")


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
        }

    return {
        "days": days,
        "series": series,
        "mood_series": mood_series,
        "stats": {"n_days": len(days), "n_records": records, "n_plates": len(series)},
        "latest": latest,
        "stock_pool": build_stock_pool(),
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
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
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
            stocks = collect_strong_stocks(collector, ds, plates)
            if stocks:
                save_stocks(ds, stocks)
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
