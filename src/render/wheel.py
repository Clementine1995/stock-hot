"""题材强度轮动面板（日历墙版）。

读取 data/ 下全部快照，生成自包含 HTML（数据内联，双击即开），还原「A股题材强度轮动」日历墙：
- 顶部查看型工具栏：标题 + 统计副标题（N 交易日 · N 条记录 · N 个题材）+ 搜索框 + 强势/弱势/全部筛选
- 主体：8 列日历墙，每个交易日一张卡片（强势红 / 弱势绿两段 + 「弱势题材」分隔）
- 点击题材：同名题材跨卡黄底高亮 + 底部左侧详情面板 + 右侧横向轮动轨迹

颜色遵循 A 股惯例：涨/走强=红，跌/走弱=绿。
"""

import json
from pathlib import Path

from ..storage.store import load_all_snapshots

_TOP_N = 15

_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output"

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>A股题材强度轮动</title>
<style>
  :root {
    --up: #e03131;
    --up-name: #c0392b;
    --down: #0ca678;
    --down-name: #6b7280;
    --hl-bg: #fff3bf;
    --hl-line: #f08c00;
    --line: #e6e3dc;
    --bg: #f5f3ef;
    --card: #ffffff;
    --text: #2b2a28;
    --muted: #9a958c;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; }
  body {
    font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
    color: var(--text); background: var(--bg);
  }

  /* 顶部查看型工具栏 */
  header.toolbar {
    background: var(--card); border-bottom: 1px solid var(--line);
    padding: 12px 20px 10px;
    position: sticky; top: 0; z-index: 20;
  }
  .title-row { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
  .title-row h1 { margin: 0; font-size: 18px; font-weight: 700; }
  .title-row h1 .dot { color: var(--up); }
  .stats { font-size: 12px; color: var(--muted); }
  .controls { margin-left: auto; display: flex; align-items: center; gap: 8px; }
  .controls input[type=search], .controls select {
    font: inherit; font-size: 12px; padding: 5px 10px;
    border: 1px solid var(--line); border-radius: 6px; background: #fff; color: var(--text);
  }
  .controls input[type=search] { width: 150px; }
  .hint { font-size: 11px; color: var(--muted); margin-top: 6px; }
  .hint b { color: var(--text); font-weight: 600; }

  /* 日历墙主体 */
  main#grid {
    display: grid;
    grid-template-columns: repeat(8, minmax(118px, 1fr));
    gap: 8px; padding: 14px 20px; align-items: start;
  }
  .card {
    background: var(--card); border: 1px solid var(--line); border-radius: 8px;
    overflow: hidden; box-shadow: 0 1px 2px rgba(0,0,0,.04);
  }
  .card-head {
    padding: 6px 8px; font-weight: 700; font-size: 12px; text-align: center;
    background: #faf9f6; border-bottom: 1px solid var(--line); letter-spacing: .5px;
  }
  .entries { padding: 4px 6px 6px; }
  .entry {
    display: flex; align-items: center; gap: 4px;
    padding: 2px 3px; margin: 1px 0; border-radius: 4px; font-size: 11px;
    cursor: pointer; border: 1px solid transparent; user-select: none; line-height: 1.35;
  }
  .entry .nm { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .entry .val { font-weight: 700; flex-shrink: 0; font-variant-numeric: tabular-nums; }
  .entry.strong .nm { color: var(--up-name); }
  .entry.strong .val { color: var(--up); }
  .entry.weak .nm { color: var(--down-name); }
  .entry.weak .val { color: var(--down); }
  .entry.hl { background: var(--hl-bg); border-color: var(--hl-line); }
  .divider {
    font-size: 10px; color: var(--muted); margin: 4px 3px 2px;
    padding-top: 3px; border-top: 1px dashed var(--line);
  }
  .empty-tip { padding: 40px; text-align: center; color: var(--muted); font-size: 13px; }

  /* 底部：详情面板 + 横向轨迹 */
  footer#detail {
    position: sticky; bottom: 0; background: var(--card);
    border-top: 2px solid var(--line); padding: 10px 20px 14px; z-index: 20;
    display: flex; gap: 24px; align-items: flex-start; flex-wrap: wrap;
  }
  #detail-panel { min-width: 180px; }
  .dp-title { font-size: 15px; font-weight: 700; }
  .dp-meta { font-size: 12px; color: var(--muted); margin-top: 4px; }
  .dp-meta .u { color: var(--up); font-weight: 700; }
  .dp-meta .d { color: var(--down); font-weight: 700; }
  .dp-meta b { color: var(--text); }
  #timeline { flex: 1; min-width: 260px; }
  .tl-label { font-size: 11px; color: var(--muted); margin-bottom: 5px; }
  #tl-cells { display: flex; gap: 3px; overflow-x: auto; padding-bottom: 4px; }
  .tcell {
    flex: 0 0 52px; text-align: center; padding: 4px 2px 3px;
    border-radius: 5px; color: #fff; line-height: 1.25;
  }
  .tcell.up { background: var(--up); }
  .tcell.down { background: var(--down); }
  .tcell.empty { background: #e5e1d8; color: #a8a198; }
  .tcell .td { display: block; font-size: 9px; opacity: .92; }
  .tcell .tv { display: block; font-size: 10px; font-weight: 700; font-variant-numeric: tabular-nums; }
</style>
</head>
<body>
<header class="toolbar">
  <div class="title-row">
    <h1><span class="dot">●</span> A股题材强度轮动</h1>
    <span class="stats">__N_DAYS__ 个交易日 · __N_RECORDS__ 条记录 · __N_PLATES__ 个题材</span>
    <div class="controls">
      <input id="search" type="search" placeholder="搜索题材…">
      <select id="filter">
        <option value="all">全部</option>
        <option value="strong">强势</option>
        <option value="weak">弱势</option>
      </select>
    </div>
  </div>
  <div class="hint">点击任意题材 → <b>同名题材自动高亮</b>并生成轮动轨迹 · <b style="color:var(--up)">红=走强</b> · <b style="color:var(--down)">绿=走弱</b></div>
</header>
<main id="grid"></main>
<footer id="detail">
  <div id="detail-panel"><div class="empty-tip">点击上方任一题材查看轮动轨迹</div></div>
  <div id="timeline"></div>
</footer>
<script>
const DAYS = __DAYS__;
const SERIES = __SERIES__;

function fmt(n) {
  if (n === undefined || n === null) return '—';
  return Number(n).toLocaleString('zh-CN');
}
function md(date) { return date.slice(5).replace('-', ''); }

function entryEl(item, kind) {
  const el = document.createElement('div');
  el.className = 'entry ' + kind;
  el.dataset.name = item.name;
  const nm = document.createElement('span');
  nm.className = 'nm'; nm.textContent = item.name;
  const val = document.createElement('span');
  val.className = 'val'; val.textContent = fmt(item.strength);
  el.appendChild(nm); el.appendChild(val);
  el.addEventListener('click', () => selectPlate(item.name));
  return el;
}

function renderGrid() {
  const grid = document.getElementById('grid');
  grid.innerHTML = '';
  if (!DAYS.length) {
    grid.innerHTML = '<div class="empty-tip">暂无数据，请先运行回补/采集命令生成快照</div>';
    return;
  }
  DAYS.forEach(day => {
    const card = document.createElement('div');
    card.className = 'card';
    const head = document.createElement('div');
    head.className = 'card-head';
    head.textContent = md(day.date);
    card.appendChild(head);

    const entries = document.createElement('div');
    entries.className = 'entries';
    day.strong.forEach(it => entries.appendChild(entryEl(it, 'strong')));
    if (day.weak.length) {
      const div = document.createElement('div');
      div.className = 'divider';
      div.textContent = '弱势题材';
      entries.appendChild(div);
    }
    day.weak.forEach(it => entries.appendChild(entryEl(it, 'weak')));
    card.appendChild(entries);
    grid.appendChild(card);
  });
}

/* 搜索 + 强势/弱势筛选 */
function applyFilters() {
  const q = document.getElementById('search').value.trim().toLowerCase();
  const f = document.getElementById('filter').value; // all | strong | weak
  document.querySelectorAll('.entry').forEach(e => {
    const name = e.dataset.name;
    const isStrong = e.classList.contains('strong');
    const matchQ = !q || name.toLowerCase().indexOf(q) >= 0;
    const matchF = f === 'all' || (f === 'strong' ? isStrong : !isStrong);
    e.style.display = (matchQ && matchF) ? '' : 'none';
  });
  document.querySelectorAll('.card').forEach(c => {
    const weakV = Array.from(c.querySelectorAll('.entry.weak')).some(e => e.style.display !== 'none');
    const strongV = Array.from(c.querySelectorAll('.entry.strong')).some(e => e.style.display !== 'none');
    const div = c.querySelector('.divider');
    if (div) div.style.display = weakV ? '' : 'none';
    c.style.display = (weakV || strongV) ? '' : 'none';
  });
}

let selectedName = null;
function selectPlate(name) {
  selectedName = name;
  document.querySelectorAll('.entry').forEach(e => {
    e.classList.toggle('hl', e.dataset.name === name);
  });
  renderDetail(name);
  renderTimeline(name);
}

function renderDetail(name) {
  const panel = document.getElementById('detail-panel');
  const series = SERIES[name] || {};
  const dates = DAYS.map(d => d.date); // 最新在前
  let upDays = 0, downDays = 0;
  for (let i = 0; i < dates.length; i++) {
    const v = series[dates[i]];
    if (v === undefined || v <= 0) break;
    upDays++;
  }
  for (let i = 0; i < dates.length; i++) {
    const v = series[dates[i]];
    if (v === undefined || v >= 0) break;
    downDays++;
  }
  const cur = series[dates[0]];

  panel.innerHTML = '';
  const title = document.createElement('div');
  title.className = 'dp-title'; title.textContent = name;
  const meta = document.createElement('div');
  meta.className = 'dp-meta';
  meta.innerHTML = '上涨 <span class="u">' + upDays + '</span> 天 · 回调 <span class="d">' + downDays +
    '</span> 天 · 当前强度 <b>' + fmt(cur) + '</b>';
  panel.appendChild(title);
  panel.appendChild(meta);
}

function renderTimeline(name) {
  const tl = document.getElementById('timeline');
  const series = SERIES[name] || {};
  const dates = DAYS.map(d => d.date);
  tl.innerHTML = '<div class="tl-label">' + name + ' 轮动轨迹（近' + dates.length + '个交易日）</div>';
  const cells = document.createElement('div');
  cells.id = 'tl-cells';
  dates.forEach(d => {
    const v = series[d];
    const cell = document.createElement('div');
    cell.className = 'tcell ' + (v === undefined ? 'empty' : (v > 0 ? 'up' : 'down'));
    const td = document.createElement('span');
    td.className = 'td'; td.textContent = md(d);
    const tv = document.createElement('span');
    tv.className = 'tv'; tv.textContent = fmt(v);
    cell.appendChild(td); cell.appendChild(tv);
    cells.appendChild(cell);
  });
  tl.appendChild(cells);
}

document.getElementById('search').addEventListener('input', applyFilters);
document.getElementById('filter').addEventListener('change', applyFilters);

renderGrid();
applyFilters();
</script>
</body>
</html>
"""


def build_panel_data(snapshots: list[dict]) -> tuple[list[dict], dict, int]:
    """把快照列表转为面板数据 (days, series, records)。

    days: 每个交易日 {date, strong[top15 降序], weak[top15 最弱在前]}，最新在前。
    series: 题材名 -> {date: strength}，用于跨卡高亮与底部轨迹。
    records: 全部条目总数（强势+弱势）。
    """
    days = []
    series: dict[str, dict[str, float]] = {}
    records = 0
    for snap in snapshots:
        date = snap["date"]
        plates = snap["plates"]
        for plate in plates:
            series.setdefault(plate["name"], {})[date] = plate["strength"]
        strong = sorted(
            (p for p in plates if p["strength"] > 0),
            key=lambda p: p["strength"], reverse=True,
        )[:_TOP_N]
        weak = sorted(
            (p for p in plates if p["strength"] < 0),
            key=lambda p: p["strength"],
        )[:_TOP_N]
        records += len(strong) + len(weak)
        days.append({"date": date, "strong": strong, "weak": weak})
    days.sort(key=lambda d: d["date"], reverse=True)
    return days, series, records


def render_wheel_html(days: list[dict], series: dict, records: int) -> str:
    """把面板数据渲染为自包含 HTML 字符串。"""
    return (
        _HTML_TEMPLATE
        .replace("__N_DAYS__", str(len(days)))
        .replace("__N_RECORDS__", str(records))
        .replace("__N_PLATES__", str(len(series)))
        .replace("__DAYS__", json.dumps(days, ensure_ascii=False))
        .replace("__SERIES__", json.dumps(series, ensure_ascii=False))
    )


def save_wheel() -> Path:
    """读全部快照，生成日历墙轮动面板 HTML 到 output/，返回文件路径。"""
    snapshots = load_all_snapshots()
    days, series, records = build_panel_data(snapshots)
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    html = render_wheel_html(days, series, records)
    path = _OUTPUT_DIR / "wheel.html"
    path.write_text(html, encoding="utf-8")
    return path
