import threading
import requests
import logging
import json
import os
import time
import subprocess

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

# 同步skins目录
def sync_skins_repo():
    import uuid
    import shutil
    
    repo_url = "https://github.com/darkseal-org/lol-skins.git"
    # 在当前目录下创建临时目录
    temp_dir_name = f"_temp_repo_{uuid.uuid4().hex[:8]}"
    temp_dir = os.path.join(os.getcwd(), temp_dir_name)
    skins_dir = os.path.join(os.getcwd(), "skins")
    
    logging.info("开始同步skins目录...")
    
    try:
        # 创建临时目录
        os.makedirs(temp_dir, exist_ok=True)
        logging.info(f"克隆仓库到临时目录: {temp_dir}...")
        subprocess.run(["git", "clone", repo_url, temp_dir], check=True)
        
        # 确保skins目录存在
        if not os.path.exists(skins_dir):
            os.makedirs(skins_dir)
        
        # 复制skins目录内容
        repo_skins_dir = os.path.join(temp_dir, "skins")
        
        # 检查源目录是否存在
        if not os.path.exists(repo_skins_dir):
            logging.error(f"源皮肤目录不存在: {repo_skins_dir}")
            return False
        
        # 使用robocopy进行目录同步 (Windows特有命令)
        logging.info("同步skins目录内容...")
        result = subprocess.run([
            "robocopy", 
            repo_skins_dir, 
            skins_dir, 
            "/E",      # 复制所有子目录，包括空目录
            "/PURGE",  # 删除目标中存在但源中不存在的文件
            "/NFL",    # 不记录文件名
            "/NDL",    # 不记录目录名
            "/NJH",    # 不显示作业头
            "/NJS"     # 不显示作业摘要
        ], check=False)
        
        # robocopy返回值: 0=无文件复制, 1=复制成功, >1=有错误
        if result.returncode >= 8:
            logging.error(f"同步失败，robocopy返回代码: {result.returncode}")
            return False
        
        logging.info("skins目录同步完成")
        return True
    
    except Exception as e:
        logging.error(f"同步过程中发生错误: {e}")
        return False
    
    finally:
        # 清理临时目录
        try:
            if os.path.exists(temp_dir):
                logging.info(f"清理临时目录: {temp_dir}")
                shutil.rmtree(temp_dir)
        except Exception as e:
            logging.warning(f"清理临时目录失败: {e}")

# 执行同步
try:
    sync_result = sync_skins_repo()
except Exception as e:
    logging.error(f"同步skins目录失败: {e}")
    sync_result = False

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

# 定期同步skins目录
def periodic_sync(interval_hours=24):
    while True:
        # 等待指定的小时数
        time.sleep(interval_hours * 3600)
        try:
            logging.info(f"执行定期同步，间隔: {interval_hours}小时")
            sync_skins_repo()
            # 重新加载皮肤数据
            new_skin_dict = normal_tools.list_skin_directories()
            # 更新监控器中的皮肤字典
            champion_monitor.skin_dict = new_skin_dict
            logging.info("皮肤数据已更新")
        except Exception as e:
            logging.error(f"定期同步失败: {e}")

# 启动定期同步线程
sync_thread = threading.Thread(target=periodic_sync, args=(24,))  # 每24小时同步一次
sync_thread.daemon = True
sync_thread.start()

# 保持主线程运行
try:
    logging.info("程序已启动，等待英雄选择...")
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    logging.info("程序已退出")
