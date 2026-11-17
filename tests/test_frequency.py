"""板块强度榜出现频率统计的单测（纯函数，不碰真实接口）。"""

import unittest

from src.indicators.frequency import count_strong_rank_days


def _snap(date, plates):
    return {"date": date, "plates": plates}


def _plate(name, strength, code=None):
    return {"name": name, "code": code or name, "strength": strength}


class TestCountStrongRankDays(unittest.TestCase):
    def test_empty_returns_empty(self):
        self.assertEqual(count_strong_rank_days([]), [])

    def test_only_top_n_counted(self):
        """top_n=2：只有强度最高的 2 个板块上榜，其余不算。"""
        snaps = [
            _snap("2026-11-01", [
                _plate("A", 100), _plate("B", 90), _plate("C", 80), _plate("D", 70),
            ]),
        ]
        result = count_strong_rank_days(snaps, window=1, top_n=2)
        names = {r["name"] for r in result}
        self.assertEqual(names, {"A", "B"})

    def test_positive_strength_only(self):
        """强度<=0 的板块不进走强榜。"""
        snaps = [
            _snap("2026-11-01", [_plate("A", 100), _plate("B", -5), _plate("C", 0)]),
        ]
        result = count_strong_rank_days(snaps, window=1, top_n=15)
        names = {r["name"] for r in result}
        self.assertEqual(names, {"A"})

    def test_accumulates_across_days(self):
        """A 连续 3 日进榜 → 3 次；B 只在第 1 日进榜 → 1 次。"""
        snaps = [
            _snap("2026-11-01", [_plate("A", 10), _plate("B", 20)]),
            _snap("2026-11-02", [_plate("A", 30), _plate("B", -1)]),
            _snap("2026-11-03", [_plate("A", 5), _plate("B", -2)]),
        ]
        result = count_strong_rank_days(snaps, window=3, top_n=15)
        by_name = {r["name"]: r for r in result}
        self.assertEqual(by_name["A"]["rank_days"], 3)
        self.assertEqual(by_name["B"]["rank_days"], 1)

    def test_sorted_by_rank_days_desc(self):
        """B、C 均上榜 2 天，C 最近强度 30 > B 的 20，故 C 排前。"""
        snaps = [
            _snap("2026-11-01", [_plate("A", 10), _plate("B", 20), _plate("C", 30)]),
            _snap("2026-11-02", [_plate("B", 20), _plate("C", 30)]),
        ]
        result = count_strong_rank_days(snaps, window=2, top_n=15)
        names = [r["name"] for r in result]
        self.assertEqual(names, ["C", "B", "A"])
        self.assertEqual(result[0]["rank_days"], 2)

    def test_window_limits_to_recent_days(self):
        """window=2 只统计最近 2 日，忽略更早快照。"""
        snaps = [
            _snap("2026-11-01", [_plate("A", 10)]),
            _snap("2026-11-02", [_plate("A", -1)]),
            _snap("2026-11-03", [_plate("A", -1)]),
        ]
        result = count_strong_rank_days(snaps, window=2, top_n=15)
        # 11-02、11-03 均走弱，A 未进榜 → 结果为空
        self.assertEqual(result, [])

    def test_last_strength_is_most_recent(self):
        snaps = [
            _snap("2026-11-01", [_plate("A", 100)]),
            _snap("2026-11-02", [_plate("A", -7)]),
        ]
        result = count_strong_rank_days(snaps, window=10, top_n=15)
        by_name = {r["name"]: r for r in result}
        self.assertEqual(by_name["A"]["last_strength"], -7)
        self.assertEqual(by_name["A"]["last_date"], "2026-11-02")

    def test_daily_flags_match_rank_dates(self):
        """daily 数组逐日标记是否上榜（旧→新），长度等于窗口内交易日数。"""
        snaps = [
            _snap("2026-11-01", [_plate("A", 10), _plate("B", 20)]),
            _snap("2026-11-02", [_plate("A", 30), _plate("B", -1)]),
            _snap("2026-11-03", [_plate("A", -5), _plate("B", -2)]),
        ]
        result = count_strong_rank_days(snaps, window=3, top_n=15)
        by_name = {r["name"]: r for r in result}
        # A 只在 11-01、11-02 上榜（旧→新 = [1,1,0]）
        self.assertEqual(by_name["A"]["daily"], [1, 1, 0])
        # B 只在 11-01 上榜
        self.assertEqual(by_name["B"]["daily"], [1, 0, 0])


if __name__ == "__main__":
    unittest.main()
