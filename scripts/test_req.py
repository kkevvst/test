import requests
import json
import mimetypes
import argparse
import sys

token = "C04vuBxTPIGdEmESumrFKgKcxwM7mCKy"

# 设置API URL
upload_url = 'https://sm.ms/api/v2/upload'

# 设置请求头部
headers = {
    # 'Content-Type': "multipart/form-data",
    'Authorization': token,  # 替换为你的授权令牌
}

# 设置请求参数
# params = {
#     'format': 'json',  # 你可以选择其他格式，如'json'或'xml'
# }
def formatSource(filename):
    imageList = []
    mime_type = mimetypes.guess_type(filename)[0]
    imageList.append(
        ('source', (filename, open(filename, 'rb'), mime_type))
    )
    return imageList
# 选择要上传的图片文件
image_file_path = '/Users/hua/Desktop/test.png'  # 替换为你的图片文件路径
# 禁用代理
proxies = {'http': None, 'https': None}
# 发起POST请求并上传图片
with open(image_file_path, 'rb') as image_file:
    mime_type = mimetypes.guess_type(image_file_path)[0]
    image_files = [('smfile', (image_file_path, image_file, mime_type)),]
    files = {'smfile': (image_file_path, image_file)}
    params = {
        # 'smfile': image_file,
        'format': 'json',  # 你可以选择其他格式，如'json'或'xml'
    }
    response = requests.post(upload_url, headers=headers, params=params, files=image_files, proxies=proxies)
    # response = requests.post('https://sm.ms/api/v2/profile', headers=headers, proxies=proxies)
# 解析响应
if response.status_code == 200:
    result = response.json()
    print('上传成功:')
    print(f'图片URL: {result["data"]["url"]}')
else:
    print(f'上传失败，状态码: {response.status_code}')
    print(response.text)
