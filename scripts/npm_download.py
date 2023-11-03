# -*-coding:utf-8-*-
import json
import os, re
from pathlib import Path
from urllib.request import urlretrieve


def node_modules(file_dir):
    """  通过递归遍历 node_modules 每个子包的package.json 解析下载链接 """
    links = []
    for root, dirs, files in os.walk(file_dir):
        if 'package.json' in files:
            package_json_file = os.path.join(root, 'package.json')
            try:
                with open(package_json_file, 'r', encoding='UTF-8') as load_f:
                    load_dict = json.load(load_f)
                    # print(load_dict)
                    if '_resolved' in load_dict.keys():
                        links.append(load_dict['_resolved'])
            except Exception as e:
                print(package_json_file)
                print('Error:', e)
    return links


def package_lock(package_lock_path):
    """ 通过递归遍历 package-lock.json 解析下载链接 """
    links = []
    with open(package_lock_path, 'r', encoding='UTF-8') as load_f:
        load_dict = json.load(load_f)
        # print(load_dict)
        search(load_dict, "resolved", links)
    return links


def yarn_lock(package_lock_path):
    """ 通过递归遍历 xxx-yarn.lock 解析下载链接 """
    links = []
    with open(package_lock_path, 'r', encoding='UTF-8') as load_f:
        for line in load_f:
            if line.find('resolved') >= 0:
                line = line.replace('resolved', '')
                url = line.strip().strip('"')
                links.append(url)
    return links


def search(json_object, key, links):
    """  遍历查找指定的key   """
    for k in json_object:
        if k == key:
            links.append(json_object[k])
        if isinstance(json_object[k], dict):
            search(json_object[k], key, links)
        if isinstance(json_object[k], list):
            for item in json_object[k]:
                if isinstance(item, dict):
                    search(item, key, links)


def download_file(path, store_path):
    """ 根据下载链接下载  """
    # 判断输出的目录是否存在
    if store_path is None:
        store_path = 'F:\\tool\\nodejs'
    if not Path(store_path).exists():
        os.makedirs(store_path, int('0755'))

    links = []
    if path.endswith("package-lock.json"):
        links = package_lock(path)
    elif path.endswith("yarn.lock"):
        links = yarn_lock(path)
    else:
        links = node_modules(path)
    print("links:" + str(len(links)))
    # print(links)
    for url in links:
        if not isinstance(url, str):
            continue
        try:
            filename = url.split('/')[-1]
            index = filename.find('?')
            if index > 0:
                filename = filename[:index]
            index = filename.find('#')
            if index > 0:
                filename = filename[:index]
            filepath = os.path.join(store_path, filename)
            if not Path(filepath).exists():
                print("down:" + url)
                urlretrieve(url, filepath)
            # else:
            #     print("file already exists:", filename)
        except Exception as e:
            print('Error Url:' + url)
            print('Error:', e)

def re_find_in_dir(path: str = '', pattern: list = []):
    """
    在指定目录下，查找符合规则的目录、文件。规则有多个时，拼接成 '*a*b' 进行匹配
    :param path: 指定目录
    :param pattern: 匹配规则
    :return: 符合规则的结果
    """
    match_file = []
    pattern_str = '.*' + '.*'.join(pattern)
    # print(pattern, pattern_str)
    re_pattern = re.compile(pattern=pattern_str)

    file_list = os.listdir(path)
    # print(file_list)
    for file_name in file_list:
        full_path = os.path.join(path, file_name)
        if os.path.isdir(full_path):
            match_file.extend(re_find_in_dir(full_path, pattern))
        if re_pattern.search(full_path):
            match_file.append(full_path)

    return match_file

if __name__ == '__main__':
    # down_link = "C:\\Users\\Administrator\AppData\Roaming\\npm\\node_modules"
    # down_link = "D:\\Git\\vue\\1\package-yarn.lock"
    # down_link = "D:\\Git\\vue\\node_modules"
    # down_link = "F:\\test\\.package-lock.json"
    # download_file(down_link,"F:\\tool\\nodejs")
    # print("ok")
    fpath = 'D:\\tool\\vue-p'

    package_files = re_find_in_dir(fpath, ['package-lock.json'])
    yarn_files = re_find_in_dir(fpath, ['yarn.lock'])
    package_files.extend(yarn_files)
    print(package_files)
    for tt in package_files:
        print(tt)
        download_file(tt,"D:\\tool\\nodejs")