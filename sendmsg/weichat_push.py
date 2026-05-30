import requests
import os
sender = os.getenv(r"wei_push")

def send_msg(msg, title="缘煦-国泰君安"):
    url = f'https://sctapi.ftqq.com/{sender}.send'
    if isinstance(msg, dict):
        msg_txt = ""
        for k, v in msg.items():
            msg_txt += f"•{k}: {v}\n"
        msg = msg_txt
    else:
        msg = str(msg)
    msg = msg.replace("\n", "\n\n")
    data = {'title': title, 'desp': msg}
    res = requests.post(url, data=data)
    print(f"send msg: {res.text}")

# if __name__ == '__main__':
#     send_msg(title="期货国泰君安", msg="您已进行期货交易中！")