"""板块成分股聚合与核心票筛选的行为测试。"""

import unittest

from src.indicators.stocks import (
    _parse_board,
    filter_strong_plates,
    merge_stocks,
    pick_generals,
    pick_leaders,
)


class ParseBoardTest(unittest.TestCase):
    def test_first_board_is_one(self):
        self.assertEqual(_parse_board("首板"), 1)

    def test_n_lianban(self):
        self.assertEqual(_parse_board("3连板"), 3)
        self.assertEqual(_parse_board("8连板"), 8)

    def test_n_tian_m_ban(self):
        self.assertEqual(_parse_board("3天2板"), 2)

    def test_empty_is_zero(self):
        self.assertEqual(_parse_board(""), 0)
        self.assertEqual(_parse_board(None), 0)


class FilterStrongPlatesTest(unittest.TestCase):
    def test_keeps_strong_excludes_negative_and_bank(self):
        plates = [
            {"code": "1", "name": "芯片", "strength": 100},
            {"code": "2", "name": "银行", "strength": 90},
            {"code": "3", "name": "机器人", "strength": 50},
            {"code": "4", "name": "农业", "strength": -10},
        ]
        result = filter_strong_plates(plates, top_n=10)
        names = [p["name"] for p in result]
        self.assertEqual(names, ["芯片", "机器人"])

    def test_top_n_limit(self):
        plates = [
            {"code": str(i), "name": f"板块{i}", "strength": 100 - i}
            for i in range(10)
        ]
        result = filter_strong_plates(plates, top_n=3)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["name"], "板块0")


class MergeStocksTest(unittest.TestCase):
    def test_dedup_and_accumulate_plates(self):
        plate_stocks = {
            "芯片": [
                {"code": "000001", "name": "A"},
                {"code": "000002", "name": "B"},
            ],
            "机器人": [
                {"code": "000002", "name": "B"},
                {"code": "000003", "name": "C"},
            ],
        }
        result = merge_stocks(plate_stocks)
        by_code = {s["code"]: s for s in result}
        self.assertEqual(len(result), 3)
        self.assertEqual(by_code["000001"]["plates"], ["芯片"])
        self.assertEqual(sorted(by_code["000002"]["plates"]), ["机器人", "芯片"])
        self.assertEqual(by_code["000003"]["plates"], ["机器人"])


class PickLeadersTest(unittest.TestCase):
    def test_board_priority_then_lead_count_then_change(self):
        stocks = [
            {"code": "1", "board": "3连板", "lead_count": 2, "change_pct": 5.0},
            {"code": "2", "board": "首板", "lead_count": 5, "change_pct": 9.0},
            {"code": "3", "board": "", "lead_count": 3, "change_pct": 10.0},
            {"code": "4", "board": "3连板", "lead_count": 1, "change_pct": 3.0},
        ]
        result = pick_leaders(stocks, top_n=2)
        self.assertEqual([s["code"] for s in result], ["1", "4"])


class PickGeneralsTest(unittest.TestCase):
    def test_turnover_then_mv_then_main_net(self):
        stocks = [
            {"code": "1", "turnover": 100, "total_mv": "1000", "main_net": 10},
            {"code": "2", "turnover": 200, "total_mv": "500", "main_net": 5},
            {"code": "3", "turnover": 200, "total_mv": "800", "main_net": 0},
        ]
        result = pick_generals(stocks, top_n=2)
        self.assertEqual([s["code"] for s in result], ["3", "2"])

    def test_total_mv_string_is_sorted_numerically(self):
        stocks = [
            {"code": "a", "turnover": 0, "total_mv": "900", "main_net": 0},
            {"code": "b", "turnover": 0, "total_mv": "1000", "main_net": 0},
        ]
        result = pick_generals(stocks, top_n=1)
        self.assertEqual(result[0]["code"], "b")


if __name__ == "__main__":
    unittest.main()
