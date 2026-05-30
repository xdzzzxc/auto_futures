import requests
import os
token = os.getenv("push_token")


def dict_to_text(dict_data:dict) -> str:
    text = ""
    for key, value in dict_data.items():
        text += f"{key}: {value}\n"
    return text


def send_msg(msg, title="国泰君安"):
    if type(msg) is dict:
        msg = dict_to_text(msg)
    url = f'https://www.pushplus.plus/send'
    payload = {
        "token": token,
        "title": title,
        "content": msg,
        "template": "txt"  # 纯文本格式
    }
    try:
        res = requests.post(url, data=payload, timeout=10)
        res_json = res.json()
        print(f"已发送信息： 主题 - {title}\n{res_json}")

    except Exception as e:
        print(f"Error:{e}")


# if __name__ == '__main__':
#     msg = test_dict
#     send_msg(msg)