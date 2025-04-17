import threading
import requests
import logging
import os
import time
import subprocess
import shutil

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
else:
    for file in os.listdir("installed"):
            file_path = os.path.join("installed", file)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
                logging.info(f"已清理: {file_path}")
            except Exception as e:
                logging.error(f"清理文件失败: {file_path}, 错误: {e}")
if not os.path.exists("profiles"):
    os.makedirs("profiles")

def check_for_updates(temp_dir):
    logging.info("检查远程仓库是否有更新...")
    
    # 如果临时目录已存在，先尝试获取最新的远程提交哈希
    if os.path.exists(temp_dir) and os.path.exists(os.path.join(temp_dir, ".git")):
        try:
            # 获取远程最新提交
            subprocess.run(["git", "-C", temp_dir, "fetch"], check=True)
            
            # 获取本地HEAD提交哈希
            local_hash = subprocess.check_output(
                ["git", "-C", temp_dir, "rev-parse", "HEAD"], 
                universal_newlines=True
            ).strip()
            
            # 获取远程最新提交哈希
            remote_hash = subprocess.check_output(
                ["git", "-C", temp_dir, "rev-parse", "origin/main"], 
                universal_newlines=True
            ).strip()
            
            # 比较本地和远程提交
            if local_hash == remote_hash:
                logging.info("远程仓库没有更新，跳过同步")
                return False
            else:
                logging.info("发现远程仓库有更新，需要同步")
                return True
        except Exception as e:
            logging.warning(f"检查更新时出错: {e}")
            return True
    else:
        logging.info("临时仓库不存在，需要执行完整同步")
        return True

# 同步skins目录
def sync_skins_repo():
    repo_url = "https://github.com/darkseal-org/lol-skins.git"
    temp_dir = os.path.join(os.getcwd(), "_temp_repo")
    skins_dir = os.path.join(os.getcwd(), "skins")
    
    # 如果不需要更新，直接返回
    if not check_for_updates(temp_dir):
        return True
    
    logging.info("开始同步skins目录...")
    
    try:
        os.makedirs(temp_dir, exist_ok=True)
        
        if os.path.exists(os.path.join(temp_dir, ".git")):
            logging.info("更新已存在的仓库...")
            subprocess.run(["git", "-C", temp_dir, "pull"], check=True)
        else:
            logging.info(f"克隆仓库到临时目录: {temp_dir}...")
            subprocess.run(["git", "clone", repo_url, temp_dir], check=True)
        
        if not os.path.exists(skins_dir):
            os.makedirs(skins_dir)
        
        repo_skins_dir = os.path.join(temp_dir, "skins")
        
        if not os.path.exists(repo_skins_dir):
            logging.error(f"源皮肤目录不存在: {repo_skins_dir}")
            return False
        
        logging.info("同步skins目录内容...")
        result = subprocess.run([
            "robocopy", 
            repo_skins_dir, 
            skins_dir, 
            "/E", "/PURGE", "/NFL", "/NDL", "/NJH", "/NJS"
        ], check=False)
        
        if result.returncode >= 8:
            logging.error(f"同步失败，robocopy返回代码: {result.returncode}")
            return False
        
        logging.info("skins目录同步完成")
        return True
    
    except Exception as e:
        logging.error(f"同步过程中发生错误: {e}")
        return False
    

# 执行同步
try:
    sync_result = sync_skins_repo()
except Exception as e:
    logging.error(f"同步skins目录失败: {e}")
    sync_result = False

# 初始化游戏API
try:
    game_api = GameAPI()
except:
    exit("先开游戏")

# 加载皮肤数据
normal_tools = tools()
skin_dict = normal_tools.list_skin_directories()

# 初始化modTools
modtools = modTools()

# 创建Web服务器
web_server = SkinWebServer(modtools)
web_server.start(18081)

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
