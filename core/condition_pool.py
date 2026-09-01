config_pool = {
    "trade_001": {
        "comment":"抄底做多：大盘趋势向上，小幅高开，K线短期下跌，价格向上突破阈值",
        "enabled": True,
        "conditions": [
            "shared_data.ts_code == ts_code",
            "any(map(ts_code.startswith, ['m', 'c', 'jd']))",
            # "大盘走势 == 'rise'",
            "total_rows < 3000",
            # "今日开盘价 > 昨日结算价 and 今日开盘价 > 昨日收盘价",
            "最新K线走势 == 'rise'",
            # "0 < 最新价 - 今日开盘价 < 5"
        ],
        "priority": 10,

        "trade_params": {
        "trade_direction": "rise",  # 下单方向（买多、卖空）
        "trade_price": "今日开盘价",  # 此参数用于条件单设置
        "profit_price": "今日开盘价 + round((历史平均高开差+历史最大高开差)/2)",
        "loss_price": "历史支撑位"
        }
    },
"trade_002": {
        "enabled": True,
        "conditions": [
            "direction == 'sideways'",
            "open > pre_settle",
            "gap_percent > 0.002"
        ],
        "priority": 12,

        "trade_params": {
        "trade_direction": "rise",
        "trade_price": "open + 50",
        "profit_price": "resistance - 10",
        "loss_price": "support + 5"
        }
    }
}


if __name__ == '__main__':
    pass