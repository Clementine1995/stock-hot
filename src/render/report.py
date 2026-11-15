"""数字统计报表生成。

输出 Markdown 文本报表：情绪温度、市场情绪家数、板块强度 Top10（走强/走弱）。
"""

from pathlib import Path

_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output"


def render_report(date: str, plates: list[dict], mood: dict, temperature) -> str:
    """生成报表 Markdown 文本。"""
    strong = sorted(
        (p for p in plates if p["strength"] > 0),
        key=lambda p: p["strength"], reverse=True,
    )
    weak = sorted(
        (p for p in plates if p["strength"] < 0),
        key=lambda p: p["strength"],
    )

    lines = [
        f"# stock-hot 数字报表 · {date}",
        "",
        "## 情绪温度",
        f"- 温度：**{temperature}** / 100",
        "",
        "## 市场情绪",
        f"- 上涨 {mood['up_count']} 家 / 下跌 {mood['down_count']} 家",
        f"- 涨停 {mood['limit_up']} 家 / 跌停 {mood['limit_down']} 家",
        "",
        "## 板块强度 Top10（走强）",
    ]
    for i, plate in enumerate(strong[:10], 1):
        lines.append(f"{i}. {plate['name']}　{plate['strength']}")
    lines += ["", "## 板块强度 Bottom10（走弱）"]
    for i, plate in enumerate(weak[:10], 1):
        lines.append(f"{i}. {plate['name']}　{plate['strength']}")
    lines.append("")
    return "\n".join(lines)


def save_report(date: str, plates: list[dict], mood: dict, temperature) -> Path:
    """生成数字报表到 output/，返回文件路径。"""
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    text = render_report(date, plates, mood, temperature)
    path = _OUTPUT_DIR / f"report-{date}.md"
    path.write_text(text, encoding="utf-8")
    return path
