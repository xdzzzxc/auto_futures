# 自定义命名空间（一本临时通讯录：名字→值）
ns = {"open": 3000, "fall": "枚举对象_做空"}

# eval第2个参数就是传入这个命名空间ns
res1 = eval("open + 50", ns, {})
res2 = eval("fall", ns, {})

print(res1)   # 3050
print(res2)   # 枚举对象_做空