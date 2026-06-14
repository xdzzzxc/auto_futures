from datetime import datetime
time_str = datetime.now().strftime("%H:%M:%S")
print(type(time_str), time_str)
print(time_str > "21:00")