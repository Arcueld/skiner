import threading
import requests
import logging
import os
import time
import subprocess
import shutil
import globals
import signal
import psutil
import sys
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm

from tools import *
from web_server import SkinWebServer
from champion_monitor import ChampionMonitor
from game_api import GameAPI
from game_stats import GameStats

def cleanup_processes():
    """清理所有相关进程"""
    current_process = psutil.Process()
    try:
        # 获取所有子进程
        children = current_process.children(recursive=True)
        for child in children:
            try:
                logging.info(f"正在终止进程: {child.pid}")
                child.terminate()
            except psutil.NoSuchProcess:
                pass
            except Exception as e:
                logging.error(f"终止进程 {child.pid} 时出错: {e}")
        
        # 等待所有子进程结束
        gone, alive = psutil.wait_procs(children, timeout=3)
        for p in alive:
            try:
                p.kill()
            except psutil.NoSuchProcess:
                pass
    except Exception as e:
        logging.error(f"清理进程时出错: {e}")

def signal_handler(signum, frame):
    """处理终止信号"""
    logging.info("收到终止信号，正在清理...")
    cleanup_processes()
    sys.exit(0)

# 注册信号处理器
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

'''
    config 
'''
# 屏蔽SSL警告
requests.packages.urllib3.disable_warnings() 
# 设置日志格式
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

### 初始化
globals.is_latest = checkIsLatestVersion()
if(not globals.is_latest):
    # 如果不是最新版本 更新皮肤相关数据
    t = threading.Thread(target=updateSkin)
    t.start()

def is_repo_valid(repo_path):
    """检查仓库是否完整有效"""
    try:
        # 检查必要的目录和文件是否存在
        required_paths = [
            os.path.join(repo_path, ".git"),
            os.path.join(repo_path, "skins"),
            os.path.join(repo_path, ".git", "HEAD"),
            os.path.join(repo_path, ".git", "config")
        ]
        
        for path in required_paths:
            if not os.path.exists(path):
                return False
        
        # 尝试获取HEAD提交
        result = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False
        )
        
        return result.returncode == 0 and result.stdout.strip()
    except Exception as e:
        logging.error(f"检查仓库完整性时出错: {e}")
        return False

def check_for_updates(temp_dir):
    """检查远程仓库是否有更新"""
    logging.info("检查远程仓库是否有更新...")
    
    try:
        # 检查仓库是否完整有效
        if os.path.exists(temp_dir) and is_repo_valid(temp_dir):
            # 获取远程最新提交
            subprocess.run(["git", "-C", temp_dir, "fetch"], check=True, capture_output=True)
            
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
        else:
            logging.info("临时仓库不存在或无效，需要执行完整同步")
            # 如果目录存在但不完整，删除它
            if os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                    logging.info(f"已删除不完整的临时目录: {temp_dir}")
                except Exception as e:
                    logging.error(f"删除不完整的临时目录失败: {e}")
            return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Git命令执行失败: {e}")
        return True
    except Exception as e:
        logging.error(f"检查更新时出错: {e}")
        return True

def sync_skins_repo():
    """同步skins目录"""
    repo_url = "https://github.com/darkseal-org/lol-skins.git"
    temp_dir = os.path.join(os.getcwd(), "_temp_repo")
    skins_dir = os.path.join(os.getcwd(), "skins")
    
    # 如果不需要更新，直接返回
    if not check_for_updates(temp_dir):
        return True
    
    logging.info("开始同步skins目录...")
    
    try:
        # 确保临时目录存在
        os.makedirs(temp_dir, exist_ok=True)
        
        # 克隆或更新仓库
        if is_repo_valid(temp_dir):
            logging.info("更新已存在的仓库...")
            subprocess.run(["git", "-C", temp_dir, "pull"], check=True, capture_output=True)
        else:
            logging.info(f"克隆仓库到临时目录: {temp_dir}...")
            result = subprocess.run(["git", "clone", repo_url, temp_dir], check=True)
            if result.returncode != 0:
                raise subprocess.CalledProcessError(result.returncode, "git clone")
        
        # 确保目标目录存在
        os.makedirs(skins_dir, exist_ok=True)
        
        repo_skins_dir = os.path.join(temp_dir, "skins")
        if not os.path.exists(repo_skins_dir):
            logging.error(f"源皮肤目录不存在: {repo_skins_dir}")
            return False
        
        # 使用robocopy同步目录
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
    
    except subprocess.CalledProcessError as e:
        logging.error(f"命令执行失败: {e}")
        if e.stdout:
            logging.error(f"命令输出: {e.stdout.decode()}")
        if e.stderr:
            logging.error(f"错误输出: {e.stderr.decode()}")
        return False
    except Exception as e:
        logging.error(f"同步过程中发生错误: {e}")
        return False

# 执行同步
try:
    sync_result = sync_skins_repo()
    if not sync_result:
        logging.error("同步skins目录失败，程序退出")
        sys.exit(1)
except Exception as e:
    logging.error(f"同步skins目录失败: {e}")
    sys.exit(1)

# 初始化游戏API
try:
    game_api = GameAPI()
except Exception as e:
    logging.error(f"GameAPI对象创建失败: {e}")
    sys.exit(1)

# 初始化游戏统计
game_stats = GameStats(game_api)

# 加载皮肤数据
normal_tools = tools()
skin_dict = normal_tools.list_skin_directories()

# 初始化modTools
try:
    modtools = modTools()
except Exception as e:
    logging.error(f"modTools对象创建失败: {e}")
    sys.exit(1)

# 创建Web服务器
web_server = SkinWebServer(modtools, game_stats)
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
finally:
    if 'champion_monitor' in locals():
        champion_monitor.stop()
    if 'web_server' in locals():
        web_server.stop()
