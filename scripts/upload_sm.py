import requests
import json
import mimetypes
import argparse
import sys

APP_DESC = """
一个上传图片到sm.ms图床的命令行工具
"""

# print(APP_DESC)
if len(sys.argv) == 1:
    sys.argv.append('--help')

parser = argparse.ArgumentParser()
parser.add_argument('-s', '--source', type=str, nargs='+', help="", required=True)
# parser.add_argument('-c', '--config', default="./config.json", help="读取配置文件", required=True)
args = parser.parse_args()

token = "C04vuBxTPIGdEmESumrFKgKcxwM7mCKy"

# 设置API URL
upload_url = 'https://sm.ms/api/v2/upload'
# 设置请求头部
headers = {
    # 'Content-Type': "multipart/form-data",
    'Authorization': token,  # 替换为你的授权令牌
}
# 禁用代理
proxies = {'http': None, 'https': None}
# 从参数中获取要上传的文件列表
img_list = args.source


def read_conf(path):
    with open(path, "r", encoding="utf-8") as f:
        confstr = f.read()
        conf = json.loads(confstr)
    return conf


def up_to_pic(img_list):
    # 获得本地图片路径后，上传至图床并记录返回的json字段
    for img in img_list:
        # 先判断传过来的是本地路径还是远程图片地址
        if "http" == img[:4]:
            # 非本地图片的话可以考虑下载到本地再上传，但是没这个必要
            print(img)
            continue
        else:
            try:
                res_json = upload(formatSource(img))
                # print(res_json)
                parse_response_url(res_json, img)
            except:
                print(img + "\t上传失败")


def upload(files):
    params = {
        'format': 'json',  # 你可以选择其他格式，如'json'或'xml'
    }
    r = requests.post(upload_url, headers=headers, params=params, files=files, proxies=proxies)
    # print(r.text)
    return json.loads(r.text)


def formatSource(filename):
    imageList = []
    mime_type = mimetypes.guess_type(filename)[0]
    imageList.append(
        ('smfile', (filename, open(filename, 'rb'), mime_type))
    )
    return imageList


def parse_response_url(json, img_path):
    # 从返回的json中解析字段
    if json['success'] != True:
        print("{}\tweb端返回失败,可能是APIKey不对. status_code {} .".format(
            img_path, json['status_code'])
        )
    else:
        img_url = json["data"]["url"]
        print(img_url)


up_to_pic(img_list)
