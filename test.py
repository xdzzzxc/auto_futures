import ast
x=1
y=2
expr = "x == y"
strr = f"x:{x} y:{y}, '{expr}':{eval(expr)}"
print(strr)

code = """
x = 100
y = x * 2
print(y)
"""
exec(code)
# print(res) # None，没有返回值
node = ast.parse("[1,2,3]", mode="eval").body
res = ast.literal_eval(node)
print(res)

text = "{'ts_code':'000001','price':12.5}"
data = ast.literal_eval(text)
print(data["ts_code"])
print(type(data)) # dict