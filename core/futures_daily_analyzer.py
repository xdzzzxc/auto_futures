import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta
import sqlite3
from typing import Optional, Dict, Union

# -------------------------- 全局可调参数（日内短线通用） --------------------------
# 5秒一次采集数据，滑动窗口用于动态高低点计算
ROLL_WINDOW = 18
# ATR周期 Wilder标准
ATR_PERIOD = 14
# 高频RSI短线周期
RSI_PERIOD = 6
# 突破确认连续tick数量（过滤插针假突破）
BREAK_CONFIRM = 2
# 分箱数量：将当日价格区间均分N段，自动识别箱体支撑压力（pd.cut分箱核心）
PRICE_BIN_COUNT = 8
# ATR风控倍率：止损1倍，第一止盈1.6倍，第二止盈3倍（盈亏比达标）
ATR_STOP_MULTI = 1.0
ATR_TP1_MULTI = 1.6
ATR_TP2_MULTI = 3.0
# 禁止开仓时间：收盘前5分钟不再新开仓
CLOSE_FORBID_OFFSET = timedelta(minutes=5)

# 期货交易时段（通用模板，可按品种修改）
NIGHT_START = time(21, 0, 0)
MORNING_START = time(9, 0, 0)
MORNING_BREAK_END = time(10, 15, 0)
AFTERNOON_START = time(13, 30, 0)
DAY_CLOSE = time(15, 0, 0)


class FuturesDailyAnalyzer:
    def __init__(
            self,
            db_path: str,
            ts_code: str,
            pre_high: float,
            pre_low: float,
            pre_close: float,
            pre_settle: float,
            today_open: float
    ):
        """
        初始化日内行情分析器
        :param db_path: 品种sqlite数据库文件路径
        :param ts_code: 合约代码 如 ma2609
        :param pre_high: 昨日最高价
        :param pre_low: 昨日最低价
        :param pre_close: 昨日收盘价
        :param pre_settle: 昨日结算价
        :param today_open: 今日开盘价
        """
        self.db_path = db_path
        self.ts_code = ts_code
        self.pre_high = pre_high
        self.pre_low = pre_low
        self.pre_close = pre_close
        self.pre_settle = pre_settle
        self.today_open = today_open

        # 缓存变量
        self.df_today: Optional[pd.DataFrame] = None  # 当日全量行情DataFrame
        self.pivot_info: Dict = {}  # Pivot静态支撑压力
        self.bin_info: Dict = {}     # pd.cut分箱箱体支撑压力
        self.last_signal: str = "wait"
        self.break_cnt = 0  # 突破计数

    def load_today_data(self) -> pd.DataFrame:
        """
        读取数据库当前品种当日所有行情数据，返回清洗后的DataFrame
        表字段约定（和你write_price入库对应）：date_inner 时间, price_text 价格, ts_code 合约
        """
        conn = sqlite3.connect(self.db_path)
        # 获取今日日期字符串
        today_str = datetime.now().strftime("%Y-%m-%d")
        sql = f"""
            SELECT date_inner, price_text 
            FROM {self.ts_code} 
            WHERE date_inner LIKE '{today_str}%'
            ORDER BY date_inner ASC
        """
        df = pd.read_sql(sql, conn)
        conn.close()

        # 数据清洗
        df["date_inner"] = pd.to_datetime(df["date_inner"])
        df["price"] = pd.to_numeric(df["price_text"], errors="coerce")
        df = df.dropna(subset=["price"])  # 剔除价格空值脏数据

        # 过滤休市无效数据
        def trade_time_filter(dt: datetime) -> bool:
            t = dt.time()
            night = NIGHT_START <= t or t <= time(2, 30)
            am = MORNING_START <= t <= MORNING_BREAK_END
            pm = AFTERNOON_START <= t <= DAY_CLOSE
            return night or am or pm

        df = df[df["date_inner"].apply(trade_time_filter)].reset_index(drop=True)
        self.df_today = df
        return df

    def calc_pivot(self) -> Dict:
        """计算静态Pivot整套支撑压力（日内基础锚点）"""
        p = (self.pre_high + self.pre_low + self.pre_close) / 3
        r1 = 2 * p - self.pre_low
        r2 = p + (self.pre_high - self.pre_low)
        r3 = r1 + (self.pre_high - self.pre_low)
        s1 = 2 * p - self.pre_high
        s2 = p - (self.pre_high - self.pre_low)
        s3 = s1 - (self.pre_high - self.pre_low)
        self.pivot_info = {
            "pivot": round(p, 2),
            "R1": round(r1, 2), "R2": round(r2, 2), "R3": round(r3, 2),
            "S1": round(s1, 2), "S2": round(s2, 2), "S3": round(s3, 2)
        }
        return self.pivot_info

    def calc_price_bin_support_resist(self) -> Dict:
        """
        【你要求的pd.cut分箱分析法核心】
        将当日全部价格区间均分为PRICE_BIN_COUNT个箱体，自动识别箱体压力/支撑
        箱体区间底部=支撑，箱体区间顶部=压力；价格落在哪个箱体判断强弱
        """
        df = self.df_today
        if len(df) < 10:
            self.bin_info = {"msg": "当日行情数据不足，无法分箱"}
            return self.bin_info

        price_min = df["price"].min()
        price_max = df["price"].max()
        # pd.cut均分价格区间，生成箱体
        bins = pd.cut(df["price"], bins=PRICE_BIN_COUNT, retbins=True)[1]
        bin_list = np.round(bins, 2).tolist()

        # 构建箱体支撑压力映射
        bin_levels = []
        for i in range(len(bin_list)-1):
            sup = bin_list[i]
            res = bin_list[i+1]
            bin_levels.append({"箱体支撑": sup, "箱体压力": res})

        # 当前价格所在箱体
        curr_price = df["price"].iloc[-1]
        curr_box_idx = pd.cut([curr_price], bins=bin_list).codes[0]

        self.bin_info = {
            "全部分箱区间端点": bin_list,
            "箱体支撑压力列表": bin_levels,
            "当前价格所处箱体序号": int(curr_box_idx),
            "当前箱体支撑": bin_levels[curr_box_idx]["箱体支撑"],
            "当前箱体压力": bin_levels[curr_box_idx]["箱体压力"],
            "最低箱体支撑": bin_list[0],
            "最高箱体压力": bin_list[-1]
        }
        return self.bin_info

    def calc_rolling_dynamic_level(self) -> Optional[Dict]:
        """滚动窗口动态高低点（短期实时支撑压力，补充分箱静态箱体）"""
        df = self.df_today
        if len(df) < ROLL_WINDOW:
            return None
        win_slice = df["price"].tail(ROLL_WINDOW)
        dyn_sup = round(win_slice.min(), 2)
        dyn_res = round(win_slice.max(), 2)
        return {"动态支撑": dyn_sup, "动态压力": dyn_res}

    def calc_atr(self) -> Optional[float]:
        """ATR波动率，用于动态止损止盈，numpy计算轻量化"""
        df = self.df_today
        if len(df) < ATR_PERIOD + 1:
            return None
        prices = df["price"].values
        tr_arr = []
        for i in range(1, len(prices)):
            tr = abs(prices[i] - prices[i-1])
            tr_arr.append(tr)
        tr_series = pd.Series(tr_arr)
        atr = tr_series.rolling(window=ATR_PERIOD).mean().iloc[-1]
        return round(float(atr), 2)

    def calc_rsi(self) -> Optional[float]:
        """短期RSI动量，区分超买超卖"""
        df = self.df_today
        if len(df) < RSI_PERIOD + 1:
            return None
        ser = df["price"]
        delta = ser.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_g = gain.rolling(RSI_PERIOD).mean()
        avg_l = loss.rolling(RSI_PERIOD).mean()
        rs = avg_g / avg_l
        rsi = 100 - (100 / (1 + rs))
        return round(float(rsi.iloc[-1]), 2)

    def get_stop_tp(self, entry_price: float, direction: str) -> Optional[Dict]:
        """
        根据ATR自动计算止损、分批止盈
        :param entry_price: 开仓价
        :param direction: long / short
        """
        atr = self.calc_atr()
        if atr is None or atr <= 0:
            return None
        if direction == "long":
            sl = round(entry_price - ATR_STOP_MULTI * atr, 2)
            tp1 = round(entry_price + ATR_TP1_MULTI * atr, 2)
            tp2 = round(entry_price + ATR_TP2_MULTI * atr, 2)
        elif direction == "short":
            sl = round(entry_price + ATR_STOP_MULTI * atr, 2)
            tp1 = round(entry_price - ATR_TP1_MULTI * atr, 2)
            tp2 = round(entry_price - ATR_TP2_MULTI * atr, 2)
        else:
            return None
        return {
            "入场价": entry_price,
            "止损价": sl,
            "第一止盈(减仓)": tp1,
            "第二止盈(全平)": tp2,
            "当前ATR": atr,
            "理论盈亏比": round(ATR_TP1_MULTI / ATR_STOP_MULTI, 2)
        }

    def forbid_new_order_check(self) -> bool:
        """判断是否临近收盘，禁止新开仓"""
        now_dt = datetime.now()
        close_dt = datetime.combine(now_dt.date(), DAY_CLOSE)
        if now_dt >= close_dt - CLOSE_FORBID_OFFSET:
            return True
        return False

    def generate_signal(self) -> Dict:
        """
        核心每秒执行一次：整合分箱箱体、Pivot、动态高低、RSI、突破确认生成交易信号
        返回：信号wait/long/short + 全套支撑压力、止损止盈参考
        """
        # 1 加载当日数据
        df = self.load_today_data()
        if len(df) < max(ROLL_WINDOW, ATR_PERIOD, RSI_PERIOD):
            return {"signal": "wait", "msg": "当日入库行情数据不足，指标无法计算"}
        if self.forbid_new_order_check():
            return {"signal": "wait", "msg": "临近收盘，禁止新开仓，仅持有仓位可平仓"}

        # 2 批量计算所有指标
        self.calc_pivot()
        self.calc_price_bin_support_resist()
        dyn_level = self.calc_rolling_dynamic_level()
        atr_val = self.calc_atr()
        rsi_val = self.calc_rsi()

        curr_price = df["price"].iloc[-1]
        pivot = self.pivot_info
        bin_data = self.bin_info

        signal = "wait"
        msg = "价格在箱体/Pivot中枢震荡，无有效突破，观望"
        long_condition = False
        short_condition = False

        # ========== 做多判断逻辑 ==========
        # 条件1：价格突破Pivot一级压力R1
        cond1_long = curr_price > pivot["R1"]
        # 条件2：价格站上当前箱体上沿压力
        cond2_long = curr_price > bin_data["当前箱体压力"]
        # 条件3：未超买 RSI<70
        cond3_long = rsi_val < 70
        # 条件4：现价高于短期动态压力
        cond4_long = curr_price > dyn_level["动态压力"]

        if cond1_long and cond2_long and cond3_long and cond4_long:
            self.break_cnt += 1
            if self.break_cnt >= BREAK_CONFIRM:
                signal = "long"
                msg = (
                    f"多头确认：突破R1({pivot['R1']})+突破箱体压力{bin_data['当前箱体压力']} "
                    f"RSI={rsi_val}无超买，短期动量向上"
                )
                self.break_cnt = 0

        # ========== 做空判断逻辑 ==========
        cond1_short = curr_price < pivot["S1"]
        cond2_short = curr_price < bin_data["当前箱体支撑"]
        cond3_short = rsi_val > 30
        cond4_short = curr_price < dyn_level["动态支撑"]

        if cond1_short and cond2_short and cond3_short and cond4_short:
            self.break_cnt += 1
            if self.break_cnt >= BREAK_CONFIRM:
                signal = "short"
                msg = (
                    f"空头确认：跌破S1({pivot['S1']})+跌破箱体支撑{bin_data['当前箱体支撑']} "
                    f"RSI={rsi_val}无超卖，短期动量向下"
                )
                self.break_cnt = 0

        # 无突破重置计数器
        if signal == "wait":
            self.break_cnt = 0

        # 生成止盈止损参考
        risk_info = None
        if signal in ["long", "short"]:
            risk_info = self.get_stop_tp(entry_price=curr_price, direction=signal)

        return {
            "当前现价": curr_price,
            "Pivot中枢体系": self.pivot_info,
            "分箱箱体体系": self.bin_info,
            "短期动态支撑压力": dyn_level,
            "RSI动量": rsi_val,
            "ATR波动率": atr_val,
            "交易信号": signal,
            "信号说明": msg,
            "开仓对应止损止盈方案": risk_info
        }


# -------------------------- 外部调用示范 --------------------------
if __name__ == "__main__":
    # 1. 实例化分析器，填入你的参数
    analyzer = FuturesDailyAnalyzer(
        db_path="./futures_ma2609.db",
        ts_code="ma2609",
        pre_high=2492,
        pre_low=2431,
        pre_close=2458,
        pre_settle=2461,
        today_open=2465
    )

    # 2. 每秒循环执行（适配你1秒一次分析需求）
    import time
    while True:
        res = analyzer.generate_signal()
        print("=" * 60)
        for k, v in res.items():
            print(f"{k}: {v}")
        time.sleep(1)  # 1秒执行一次分析