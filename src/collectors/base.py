"""采集器抽象接口。

所有信源采集器实现统一的只读入口，上层（指标计算、渲染）只依赖此抽象。
后续接入 Tushare / 通达信 / AKShare 等信源时新增实现即可，不改动消费方。
"""

from abc import ABC, abstractmethod


class Collector(ABC):
    """金融行情采集器抽象基类。

    定义两类只读数据：
    1. 全板块强度排名（按交易日）
    2. 市场情绪家数（仅当前最新，接口不支持历史回查）
    """

    name: str = "base"

    @abstractmethod
    def fetch_plate_ranking(self, date: str) -> list[dict]:
        """拉取指定交易日全板块强度排名。

        参数 date 格式 YYYY-MM-DD（交易日）。
        返回板块列表，每项字段：
            code       板块代码
            name       板块名称
            strength   强度（开盘啦私有指标，正=走强，负=走弱）
            change_pct 涨跌幅 %
            turnover   成交额（元）
            main_net   主力净额（元）
        """

    @abstractmethod
    def fetch_market_mood(self) -> dict:
        """拉取当前市场情绪家数。

        返回字段：
            up_count    上涨家数
            down_count  下跌家数
            limit_up    涨停家数
            limit_down  跌停家数
            bl          涨跌比（口径待确认，公式 v1 暂不使用）
        """
