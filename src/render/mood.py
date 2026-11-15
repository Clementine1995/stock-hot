"""情绪温度面板生成。

读取 data/ 下全部快照，用 mood_temperature 计算每天温度，生成自包含 HTML：
当前温度大字 + 三色（绿=冰点 / 橙=中性 / 红=高温）+ 温度计色带 + 近 N 日曲线。

三档阈值（可调，见模块顶部常量）：<=40 冰点（绿）、>=60 高温（红）、之间中性（橙）。
"""

import json
from pathlib import Path

from ..indicators.mood import mood_temperature
from ..storage.store import load_all_snapshots

_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output"

_COLD_MAX = 40.0   # 温度 <= 40 判为冰点（绿）
_HOT_MIN = 60.0    # 温度 >= 60 判为高温（红），之间为中性（橙）

_COLOR_GRAY = "#9aa3ad"
_COLOR_COLD = "#0ca678"
_COLOR_HOT = "#e03131"
_COLOR_NEUTRAL = "#f08c00"


def build_mood_series(snapshots: list[dict]) -> list[dict]:
    """把快照列表转为温度序列 [{date, temperature}]；mood 不完整时温度记 None。"""
    series = []
    for snap in snapshots:
        mood = snap.get("mood") or {}
        try:
            temp = mood_temperature(
                mood.get("up_count"),
                mood.get("down_count"),
                mood.get("limit_up"),
                mood.get("limit_down"),
            )
        except (TypeError, ValueError):
            temp = None
        series.append({"date": snap["date"], "temperature": temp})
    return series


def temperature_color(temp) -> str:
    """温度三档颜色：绿（冰点）/ 橙（中性）/ 红（高温）；None 为灰。"""
    if temp is None:
        return _COLOR_GRAY
    if temp <= _COLD_MAX:
        return _COLOR_COLD
    if temp >= _HOT_MIN:
        return _COLOR_HOT
    return _COLOR_NEUTRAL


def temperature_state(temp) -> str:
    """温度三档中文状态。"""
    if temp is None:
        return "数据缺失"
    if temp <= _COLD_MAX:
        return "冰点 · 低温"
    if temp >= _HOT_MIN:
        return "高温 · 亢奋"
    return "中性 · 震荡"


def _line_chart_svg(series: list[dict]) -> str:
    """把温度序列画成 SVG 折线图（含 y 轴刻度、折线、数据点、日期标签）。"""
    width, height = 640, 250
    left, right = 56, 618
    top, bottom = 20, 208
    n = len(series)

    parts = []
    # y 轴刻度 + 网格
    for tick in (0, 20, 40, 60, 80, 100):
        y = bottom - (tick / 100.0) * (bottom - top)
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" '
            f'stroke="#eceef1" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-size="10" fill="#7b8794">{tick}</text>'
        )

    # 数据点（temperature 非 None）
    points = []
    for i, item in enumerate(series):
        if item["temperature"] is None:
            continue
        x = left + (right - left) * (i / (n - 1) if n > 1 else 0.5)
        y = bottom - (item["temperature"] / 100.0) * (bottom - top)
        points.append((x, y, item["temperature"], item["date"]))

    if not points:
        parts.append(
            f'<text x="{(left + right) / 2}" y="{top + 60}" text-anchor="middle" '
            f'font-size="13" fill="#9aa3ad">暂无有效温度数据</text>'
        )

    # 折线
    if len(points) >= 2:
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y, _, _ in points)
        parts.append(
            f'<polyline points="{poly}" fill="none" stroke="#4d5967" stroke-width="2"/>'
        )

    # 数据点 + 日期标签
    step = max(1, (n + 7) // 8)  # 标签隔几个显示，避免重叠
    for idx, (x, y, temp, date) in enumerate(points):
        color = temperature_color(temp)
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{bottom + 20}" text-anchor="middle" '
            f'font-size="10" fill="#7b8794">{date[5:].replace("-", "")}</text>'
        )

    return (
        f'<svg viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:760px">'
        f'{"".join(parts)}</svg>'
    )


def render_mood_html(series: list[dict]) -> str:
    """把温度序列渲染为自包含 HTML 字符串。"""
    current = series[-1] if series else {"date": "—", "temperature": None}
    temp = current["temperature"]
    color = temperature_color(temp)
    state = temperature_state(temp)
    marker_left = temp if temp is not None else 0
    chart = _line_chart_svg(series)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>情绪温度面板</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
    color: #1f2933; background: #f2f3f5;
  }}
  header {{
    padding: 12px 20px; background: #fff; border-bottom: 1px solid #e5e7eb;
  }}
  header h1 {{ margin: 0; font-size: 17px; }}
  .card {{
    background: #fff; border: 1px solid #e5e7eb; border-radius: 10px;
    margin: 14px 20px; padding: 18px 20px;
  }}
  .current {{ display: flex; align-items: center; gap: 18px; flex-wrap: wrap; }}
  .temp-big {{ font-size: 56px; font-weight: 800; line-height: 1; color: {color}; }}
  .temp-state {{ font-size: 18px; font-weight: 700; color: {color}; }}
  .temp-date {{ font-size: 13px; color: #7b8794; }}
  .thermo-bar {{
    height: 16px; border-radius: 8px; position: relative; margin: 8px 0 4px;
    background: linear-gradient(to right, #0ca678 0%, #0ca678 40%, #f08c00 60%, #e03131 100%);
  }}
  .thermo-marker {{
    position: absolute; top: -5px; left: {marker_left}%;
    width: 4px; height: 26px; background: #1f2933; border-radius: 2px;
    transform: translateX(-50%);
  }}
  .thermo-scale {{ display: flex; justify-content: space-between; font-size: 11px; color: #7b8794; }}
  .card h2 {{ margin: 0 0 12px; font-size: 14px; color: #4d5967; }}
</style>
</head>
<body>
<header><h1>情绪温度</h1></header>
<div class="card">
  <div class="current">
    <div class="temp-big">{temp if temp is not None else "—"}</div>
    <div>
      <div class="temp-state">{state}</div>
      <div class="temp-date">{current["date"]}</div>
    </div>
  </div>
  <div style="margin-top:16px">
    <div class="thermo-bar"><div class="thermo-marker"></div></div>
    <div class="thermo-scale"><span>0 冰点</span><span>50 中性</span><span>100 高温</span></div>
  </div>
</div>
<div class="card">
  <h2>近 N 日温度曲线</h2>
  {chart}
</div>
</body>
</html>
"""


def save_mood(series: list[dict]) -> Path:
    """生成情绪温度面板 HTML 到 output/，返回文件路径。"""
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    html = render_mood_html(series)
    path = _OUTPUT_DIR / "mood.html"
    path.write_text(html, encoding="utf-8")
    return path
