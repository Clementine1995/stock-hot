"""DeepSeek 每日点评（批次 4b）。

零第三方依赖，用标准库 urllib 直连 DeepSeek 的 OpenAI 兼容接口。
遵循 DOMAIN.md「模型调用治理」红线：
- 先记账再花钱：调用前按「日期 + 输入指纹」记回执，结果先落缓存再返回。
- 重试复用结果：同一天已有缓存直接读，不重复付费。
- 预算熔断：每日调用次数上限，超限即停（0=停用）。
- 无 key / 未开启时静默跳过，不报错。
- 关思考模式：默认 model=deepseek-chat（非 reasoner）。

配置（不入库）：项目根目录 config.local.json，结构见下方 load_config。
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import request

from src.indicators.mood import mood_temperature

_SHANGHAI_TZ = timezone(timedelta(hours=8))

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_PATH = _PROJECT_ROOT / "config.local.json"
_CACHE_DIR = _PROJECT_ROOT / "data" / "review"

_DEFAULT_CONFIG = {
    "enabled": False,          # 显式 true 才调模型
    "api_key": "",             # DeepSeek API key（不放库）
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-chat",  # 非思考模式，省 token
    "daily_budget": 3,         # 每日最多调用次数，0=停用
    "timeout": 60,
    "temperature": 0.4,
    "max_tokens": 600,
    "window_days": 5,          # 点评回看交易日数
    "top_plates": 5,           # 每日领涨板块取前几
}


def load_config() -> dict:
    """读取本地配置，合并默认值；文件不存在或损坏时返回默认（关闭状态）。"""
    cfg = dict(_DEFAULT_CONFIG)
    if _CONFIG_PATH.exists():
        try:
            user = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(user, dict):
                cfg.update(user)
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def _daily_lines(snapshots: list[dict], top_plates: int) -> list[str]:
    """把每个交易日压成一行文字，供 prompt 使用。"""
    lines = []
    for snap in snapshots:
        date = snap["date"]
        mood = snap.get("mood") or {}
        up, down = mood.get("up_count"), mood.get("down_count")
        lu, ld = mood.get("limit_up"), mood.get("limit_down")
        temp = None
        if None not in (up, down, lu, ld):
            try:
                temp = mood_temperature(up, down, lu, ld)
            except (TypeError, ValueError):
                temp = None
        strong = sorted(
            (p for p in snap.get("plates", []) if (p.get("strength") or 0) > 0),
            key=lambda p: p["strength"], reverse=True,
        )[:top_plates]
        names = "、".join(p["name"] for p in strong) or "无"
        temp_s = f"{temp:.1f}" if temp is not None else "—"
        lines.append(
            f"{date} 温度{temp_s} 涨{up}跌{down} 涨停{lu}跌停{ld} 领涨:{names}"
        )
    return lines


def build_prompt(snapshots: list[dict], top_plates: int = 5) -> str:
    """由近 N 日快照构造点评 prompt（纯函数，便于单测）。"""
    if not snapshots:
        return ""
    n = len(snapshots)
    body = "\n".join(_daily_lines(snapshots, top_plates))
    return (
        "你是A股盘后复盘助手。下面是最近{n}个交易日（含最新）的市场数据，"
        "请写一段简洁的盘面点评，按三段式：\n"
        "1) 近{n}日情绪温度趋势（升温/降温/震荡，结合温度数值）\n"
        "2) 持续性最强的题材主线（结合每日领涨板块里重复出现的）\n"
        "3) 最新一天一句话结论\n\n"
        "要求：只基于给定数据、不编造数字、不荐股、不超过200字、专业但口语化。\n\n"
        "数据：\n{body}"
    ).format(n=n, body=body)


def _call_deepseek(cfg: dict, prompt: str) -> tuple[str, dict]:
    """调用 DeepSeek chat/completions，返回 (内容, usage)。"""
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    body = {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": cfg["temperature"],
        "max_tokens": cfg["max_tokens"],
        "stream": False,
    }
    req = request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + cfg["api_key"],
        },
        method="POST",
    )
    with request.urlopen(req, timeout=cfg["timeout"]) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    content = payload["choices"][0]["message"]["content"]
    usage = payload.get("usage") or {}
    return content, usage


def _cache_path(date: str) -> Path:
    return _CACHE_DIR / f"{date}.json"


def _meta_path() -> Path:
    return _CACHE_DIR / "_meta.json"


def _read_meta() -> dict:
    if _meta_path().exists():
        try:
            return json.loads(_meta_path().read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _calls_today(date: str) -> int:
    """当日已发生的调用次数（用于预算熔断）。"""
    meta = _read_meta()
    return len(meta.get(date, []))


def _record_call(date: str, fingerprint: str, usage: dict) -> None:
    """记一笔调用回执（先记账再花钱）。"""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    meta = _read_meta()
    meta.setdefault(date, []).append({
        "fingerprint": fingerprint,
        "usage": usage,
        "at": datetime.now(_SHANGHAI_TZ).isoformat(timespec="seconds"),
    })
    _meta_path().write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _save_cache(date: str, review: str, fingerprint: str, usage: dict) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(date).write_text(
        json.dumps({
            "date": date,
            "review": review,
            "fingerprint": fingerprint,
            "usage": usage,
            "generated_at": datetime.now(_SHANGHAI_TZ).isoformat(timespec="seconds"),
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_review(date: str) -> dict | None:
    """读取某交易日已缓存的点评；无则返回 None。"""
    path = _cache_path(date)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def generate_review(snapshots: list[dict], force: bool = False) -> dict:
    """生成当日点评。返回统一结构，便于 server 直接透传前端。

    返回字段：
        ok           是否成功产出点评
        date         交易日
        review       点评文本（成功时）
        cached       是否命中缓存（未产生付费调用）
        usage        用量（token 数）
        skipped      是否被跳过（未启用/无 key/无数据/超预算）
        reason       跳过原因
        error        调用失败原因
    """
    cfg = load_config()
    if not cfg["enabled"] or not cfg.get("api_key"):
        return {"ok": False, "skipped": True, "reason": "未启用或无 API key（见 config.local.json）"}

    recent = snapshots[-cfg["window_days"]:]
    if not recent:
        return {"ok": False, "skipped": True, "reason": "无快照数据"}
    date = recent[-1]["date"]

    # 命中缓存 → 复用，不重复付费
    if not force:
        cached = load_review(date)
        if cached:
            return {"ok": True, "date": date, "review": cached.get("review"), "cached": True}

    # 预算熔断
    if cfg["daily_budget"] > 0 and _calls_today(date) >= cfg["daily_budget"]:
        return {"ok": False, "skipped": True, "reason": f"已达每日调用上限（{cfg['daily_budget']} 次）"}

    prompt = build_prompt(recent, cfg["top_plates"])
    fingerprint = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]

    # 预估 token（中文约 1 字 ≈ 1 token）
    print(f"[review] 调用前预估输入约 {len(prompt)} token，指纹 {fingerprint}")
    try:
        content, usage = _call_deepseek(cfg, prompt)
    except Exception as exc:  # noqa: BLE001 —— 网络/鉴权错误需如实返回
        return {"ok": False, "error": str(exc)}

    _save_cache(date, content, fingerprint, usage)
    _record_call(date, fingerprint, usage)
    print(f"[review] 完成，实际 usage={usage}")
    return {"ok": True, "date": date, "review": content, "cached": False, "usage": usage}
