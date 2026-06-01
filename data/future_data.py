# import numpy as np
# import pandas as pd
# from public import shared_data
# from data.data_from_sina import fetch_future_data
# from public.print_context import print_context
#
#
# def get_base_param_from_history(ts_code="m2609") -> dict | None:
#     """
#     :根据历史数据分析出交易参数：买多或卖空、交易价、止盈价、止损价
#     :param: ts_code
#     :return:
#     """
#     ts_code = ts_code if shared_data.ts_code is None else shared_data.ts_code
#     history_data = fetch_future_data(ts_code=ts_code)  # 从新浪财经网获取历史交易数据
#     # print_context(history_data)
#     max_range = history_data['extreme_diff'].max().round(0)  # 近交易日的极值差的最大值
#     min_range = history_data['extreme_diff'].min().round(0)  # 近交易日的极值差的最小值
#     avg_range = history_data['extreme_diff'].mean().round(0)  # 近交易日的极值差的平均值--平均波动
#     range_std = history_data['extreme_diff'].std().round(0)  # 标准差(用极值差列计算标准差)
#     support = history_data['low'].mean().round(0)  # 支撑位
#     resistance = history_data['high'].mean().round(0)  # 压力位
#     settle_price = history_data['settle_price'].iloc[0]  # 前一个交易日的结算价
#     max_gap_up = history_data['high_open_diff'].max().round(0)
#     min_gap_up = history_data['high_open_diff'].min().round(0)
#     avg_gap_up = history_data['high_open_diff'].mean().round(0)  # 平均高开差
#     avg_gap_down = history_data['low_open_diff'].mean().round(0)  # 平均低开差
#     max_gap_down = history_data['low_open_diff'].max().round(0)
#     min_gap_down = history_data['low_open_diff'].min().round(0)
#     cv = round(range_std / avg_range, 2)
#     result_dict = {"压力位": resistance, "支撑位": support, "最大波动": max_range, "平均波动": avg_range, "最小波动": min_range,
#                    "最大高开差": max_gap_up, "最小高开差": min_gap_up, "平均高开差": avg_gap_up, "最大低开差": max_gap_down,
#                    "最小低开差": min_gap_down, "平均低开差": avg_gap_down, "前日结算价": settle_price, "标准差": range_std}
#     if cv < 0.2:
#         result_dict['稳定性'] = f"极稳定-{cv}"
#     elif cv < 0.45:
#         result_dict['稳定性'] = f"稳定-{cv}"
#     elif cv < 0.6:
#         result_dict['稳定性'] = f"较稳定-{cv}"
#     elif cv < 0.8:
#         result_dict['稳定性'] = f"不稳定-{cv}"
#     else:
#         result_dict['稳定性'] = f"极不稳定-{cv}"
#     # for k, (key, value) in enumerate(result_dict.items()):
#     #     print(f'{k}.{key}: {value}')
#     # print_context(f'[{shared_data.ts_code}]价格走势稳定程序：{result_dict["稳定性"]}')
#     shared_data.history_data_analysis = result_dict
#
#     return result_dict
#
#
# def data_bins(col_name, days=5, n_bins=11):
#     """
#     本函数是对数据进行分箱操作
#     :param col_name:
#     :param days:
#     :param n_bins:
#     :return:
#     """
#
#     days = shared_data.target_days if shared_data.target_days is not None else days
#     df = fetch_future_data()[:days]
#     data_series = df[col_name]
#     min_extreme = data_series.min()
#     max_extreme = data_series.max()
#     bins = np.linspace(min_extreme, max_extreme, n_bins)
#     bin_labels = [f'{bins[i]:.2f} - {bins[i+1]:.2f}' for i in range(n_bins - 1)]
#     # print(df)
#     # print(bin_labels)
#     bin_counts = pd.cut(data_series, bins=bins, labels=bin_labels, include_lowest=True).value_counts()
#     bin_percent = (bin_counts / len(data_series)) * 100
#     bin_percent = bin_percent.reindex(bin_labels).fillna(0).round(2)
#     # 封装结果成df数据格式并保存到excel工作薄
#     result_df = pd.DataFrame({
#         '区间': bin_labels,
#         '占比': bin_percent
#     }).sort_values(by='占比', ascending=False)
#     # print(bin_counts)
#     # print(bin_percent)
#     # print(result_df)
#     result_list = []
#     for i in range(3):
#         bin_str = result_df['区间'].iloc[i]
#         val1, val2 = [float(x.strip()) for x in bin_str.split(' - ')]
#         per = result_df['占比'].iloc[i]
#         result_list.append((per, (val1, val2)))
#     print(result_list)
#     return result_list
#
#
# if __name__ == "__main__":
#     sina_data = get_base_param_from_history()
#     print(sina_data)
#     # data_bins(col_name="high_open_diff")
