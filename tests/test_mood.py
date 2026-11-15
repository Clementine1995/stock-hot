"""情绪温度计算的行为测试。"""

import unittest

from src.indicators.mood import mood_temperature


class MoodTemperatureTest(unittest.TestCase):
    def test_neutral_market_is_mid(self):
        """上涨=下跌、涨停=跌停 → 中性温度 50。"""
        self.assertEqual(mood_temperature(2000, 2000, 10, 10), 50.0)

    def test_broad_rally_is_hot(self):
        """普涨 + 涨停多 → 触及上限 100。"""
        self.assertEqual(mood_temperature(4000, 1000, 100, 5), 100.0)

    def test_broad_selloff_is_cold(self):
        """普跌 + 跌停多 → 触及下限 0。"""
        self.assertEqual(mood_temperature(1000, 4000, 5, 100), 0.0)

    def test_real_2026_11_13_data(self):
        """实测 2026-11-13：上涨765/下跌4748/涨停37/跌停33 → 普跌低温。"""
        self.assertEqual(mood_temperature(765, 4748, 37, 33), 15.9)

    def test_zero_total_raises(self):
        """上涨+下跌为 0 时抛 ValueError，不静默。"""
        with self.assertRaises(ValueError):
            mood_temperature(0, 0, 0, 0)


if __name__ == "__main__":
    unittest.main()
