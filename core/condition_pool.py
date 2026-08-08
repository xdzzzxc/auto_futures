config_pool = {
    "trade_001": {
        "enabled": True,
        "conditions": [
            "direction == 'sideways'",
            "open > pre_settle",
            "gap_percent > 0.002"
        ],
        "priority": 10,

        "trade_params": {
        "trade_direction": "fall",
        "trade_price": "open + 20",
        "profit_price": "resistance - 10",
        "loss_price": "support + 5"
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