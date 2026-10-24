# from public import shared_data
# from public.shared_data import trade_flag, is_trade_status
# import threading
# from core.monitor import monitor_profit_loss
# from time import sleep
# from datetime import datetime
# from public.print_context import print_context
# from public.shared_data import variables_rlock
#
# monitor_thread = None
#
# from datetime import datetime, time
#
# def monitor_wrapper():
#     """线程退出自动重置标记"""
#     try:
#         monitor_profit_loss()
#     except Exception as e:
#         print_context(f"监控线程异常退出：{str(e)}")
#     finally:
#         with variables_rlock:
#             shared_data.threading_monitor_profit_loss = False
#             global monitor_thread
#             monitor_thread = None
#
#
#
# def _is_thread_running():
#     """统一的线程存活判断：对象存活 OR 标记为True"""
#     with variables_rlock:
#         alive = (monitor_thread is not None) and monitor_thread.is_alive()
#         flag = shared_data.threading_monitor_profit_loss
#         return alive or flag
#
#
# def run_monitor():
#     global monitor_thread
#     print_context("自动监控管理程序已启动 ............")
#
#     while True:
#         sleep(1)
#
#         # ---- 调整分析间隔 ----
#         try:
#             if is_trade_status():
#                 with shared_data.analyze_interval_lock:
#                     shared_data.analyze_interval = 60
#             else:
#                 with shared_data.analyze_interval_lock:
#                     if shared_data.analyze_interval != 600:
#                         shared_data.analyze_interval = 600
#         except Exception as e:
#             print_context(f"监控模块检测交易状态异常：{str(e)}")
#             continue
#
#         # ===== 核心修复：交易时段 AND 有持仓，才允许监控线程运行 =====
#         try:
#             in_trade_time = trade_flag()
#             has_position = is_trade_status()
#
#         except Exception as e:
#             print_context(f"读取交易/持仓状态失败：{str(e)}")
#             continue
#
#         run_allow = in_trade_time and has_position
#         thread_running = _is_thread_running()
#
#         # ---- 启动分支 ----
#         if run_allow and not thread_running:
#             with variables_rlock:
#                 # 双重检查，防止竞态
#                 if monitor_thread is None or not monitor_thread.is_alive():
#                     shared_data.threading_monitor_profit_loss = True
#                     now = datetime.now().strftime('%H:%M:%S')
#                     print_context(f"[{now}] 已开启自动平仓监控程序！")
#                     monitor_thread = threading.Thread(
#                         target=monitor_wrapper,
#                         name="MonitorThread",
#                         daemon=True
#                     )
#                     monitor_thread.start()
#
#         # ---- 停止分支：无持仓 / 非交易时段 ----
#         elif not run_allow and thread_running:
#             with variables_rlock:
#                 now = datetime.now().strftime('%H:%M:%S')
#                 if not has_position:
#                     reason = "无持仓"
#                 else:
#                     reason = "非交易时段"
#                 print_context(f"\n[{now}] {reason}，停止自动平仓监控！")
#                 shared_data.threading_monitor_profit_loss = False
#                 if monitor_thread is not None:
#                     monitor_thread.join(timeout=3)
#                     monitor_thread = None
#
#
# if __name__ == '__main__':
#
#     pass