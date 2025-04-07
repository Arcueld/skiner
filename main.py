import threading
import requests
import logging
import json
import os
import time

from tools import tools
from tools import modTools
from web_server import SkinWebServer
from champion_monitor import ChampionMonitor
from game_api import GameAPI

'''
    config 
'''
# 屏蔽SSL警告
requests.packages.urllib3.disable_warnings() 
# 设置日志格式
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

### 初始化

# 创建必要的目录
if not os.path.exists("installed"):
    os.makedirs("installed")
if not os.path.exists("profiles"):
    os.makedirs("profiles")

# 初始化游戏API
game_api = GameAPI()

# 加载皮肤数据
normal_tools = tools()
skin_dict = normal_tools.list_skin_directories()

# 初始化modTools
modtools = modTools()

# 创建Web服务器
web_server = SkinWebServer(modtools)
web_server.start()

# 创建并启动英雄监控
champion_monitor = ChampionMonitor(game_api, web_server, skin_dict)
champion_monitor.start_monitoring()

# 保持主线程运行
try:
    logging.info("程序已启动，等待英雄选择...")
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    logging.info("程序已退出")
