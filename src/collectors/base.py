"""采集器抽象接口。

所有信源采集器实现统一的只读入口，上层（指标计算、渲染）只依赖此抽象。
后续接入 Tushare / 通达信 / AKShare 等信源时新增实现即可，不改动消费方。
"""

from abc import ABC, abstractmethod


class Collector(ABC):
    """金融行情采集器抽象基类。

    定义三类只读数据：
    1. 全板块强度排名（按交易日）
    2. 市场情绪家数（仅当前最新，接口不支持历史回查）
    3. 板块成分股（按交易日，支持历史回查）
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
    def fetch_latest_plate_ranking(self) -> tuple:
        """拉取最新交易日板块强度排名，返回 (日期, 板块列表)。

        当天数据在历史域可能未归档，最新数据走当日域（若信源区分当日/历史域）。
        返回的日期为该信源标注的实际交易日。
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

    @abstractmethod
    def fetch_mood_for(self, date: str) -> dict:
        """拉取指定交易日市场情绪家数。

        情绪接口仅支持最新交易日（不支持历史回查），故：
        - date 为最新交易日时，返回当日情绪；
        - date 为历史日期时，返回空 dict（避免把最新情绪误写入历史快照）。
        """

    @abstractmethod
    def fetch_plate_stocks(self, plate_id: str, date: str) -> list[dict]:
        """拉取指定板块在指定交易日的成分股列表。

        参数：
            plate_id  板块代码（如 801001）
            date      日期 YYYY-MM-DD
        返回股票列表，每项字段：
            code        股票代码
            name        股票名称
            tags        细分板块标签
            price       价格
            change_pct  当日涨幅 %
            turnover    成交额（元）
            main_net    主力净额（元）
            range_chg   区间涨幅
            board       几天几板（空=无连板）
            total_mv    总市值（元）
            float_mv    流通市值（元）
            lead_count  领涨次数
        """
