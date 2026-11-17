"""DeepSeek 点评单测（只测纯函数与跳过逻辑，不实际调付费 API）。"""

import unittest
from unittest.mock import patch

from src.llm.review import build_prompt, generate_review


def _snap(date, plates, mood):
    return {"date": date, "plates": plates, "mood": mood}


def _plate(name, strength):
    return {"name": name, "code": name, "strength": strength}


_MOOD = {"up_count": 100, "down_count": 50, "limit_up": 10, "limit_down": 2}


class TestBuildPrompt(unittest.TestCase):
    def test_empty_returns_empty(self):
        self.assertEqual(build_prompt([]), "")

    def test_contains_date_temp_and_plate(self):
        snaps = [
            _snap("2026-11-16", [_plate("AI应用", 100), _plate("芯片", 50)], _MOOD),
        ]
        p = build_prompt(snaps, top_plates=5)
        self.assertIn("2026-11-16", p)
        self.assertIn("AI应用", p)
        self.assertIn("温度", p)

    def test_missing_mood_handled(self):
        # mood 为空时温度显示 "—"，不抛异常
        snaps = [_snap("2026-11-16", [_plate("AI应用", 100)], {})]
        p = build_prompt(snaps)
        self.assertIn("温度—", p)


class TestGenerateReviewSkips(unittest.TestCase):
    def test_skips_when_disabled(self):
        with patch("src.llm.review.load_config", return_value={"enabled": False, "api_key": ""}):
            r = generate_review([_snap("2026-11-16", [], _MOOD)])
            self.assertFalse(r["ok"])
            self.assertTrue(r.get("skipped"))

    def test_skips_without_key(self):
        with patch("src.llm.review.load_config", return_value={"enabled": True, "api_key": ""}):
            r = generate_review([_snap("2026-11-16", [], _MOOD)])
            self.assertFalse(r["ok"])
            self.assertTrue(r.get("skipped"))


if __name__ == "__main__":
    unittest.main()
