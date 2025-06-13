import os
import logging
import psutil
import subprocess
import threading
import time
import ctypes
import requests
import json
import time
import globals

requests.packages.urllib3.disable_warnings() 
# 设置日志格式
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from ctypes import wintypes

SKINS_JSON_PATH = "skins.json"
SAVE_DIR = "id_skins"
MAX_WORKERS = 32
RETRIES = 5
TIMEOUT = 10

class tools:

    def check_game_path(self, path: str) -> str:
        if os.path.exists(path) and "LeagueClient.exe" in path:
            return os.path.dirname(path)  
        elif os.path.exists(path) and "League of Legends.exe" in path:
            return os.path.dirname(path)
        return ""

    def get_full_process_image_name(self, pid: int) -> str:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h_process = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h_process:
            return ""

        buffer_len = wintypes.DWORD(32767)
        buffer = ctypes.create_unicode_buffer(buffer_len.value)
        if ctypes.windll.kernel32.QueryFullProcessImageNameW(h_process, 0, buffer, ctypes.byref(buffer_len)):
            ctypes.windll.kernel32.CloseHandle(h_process)
            return buffer.value
        ctypes.windll.kernel32.CloseHandle(h_process)
        return ""

    def detect_game_path(self):
        target_names = {"LeagueClient.exe", "League of Legends.exe"}
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] in target_names:
                    full_path = self.get_full_process_image_name(proc.info['pid'])
                    result = self.check_game_path(full_path)
                    if result:
                        result = result.replace("LeagueClient","Game")
                        return result
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return ""
    
    def list_skin_directories(self):
        """
        遍历skins目录下的所有子目录，返回目录结构
        
        Returns:
            dict: 包含所有英雄及其皮肤的字典
        """
        skins_path = os.path.join(os.getcwd(), "skins")
        
        # 检查skins目录是否存在
        if not os.path.exists(skins_path):
            logging.warning(f"skins目录不存在: {skins_path}")
            return {}
        
        # 遍历目录结构
        skins_dict = {}
        for champion in os.listdir(skins_path):
            champion_path = os.path.join(skins_path, champion)
            if os.path.isdir(champion_path):
                # 特殊处理 Nunu & Willump
                if champion == "Nunu & Willump":
                    normalized_champion = "Nunu"
                else:
                    # 处理英雄名称，删除 '、. 和空格 转小写
                    normalized_champion = champion.replace("'", "").replace(".", "").replace(" ", "")
                
                skins_dict[normalized_champion] = []
                for skin in os.listdir(champion_path):
                    # TODO: 暂时忽略炫彩的处理
                    if skin.lower() == "chromas": 
                        continue
                    skin_path = os.path.join(champion_path, skin)
                    if os.path.isdir(skin_path) or (os.path.isfile(skin_path) and skin.endswith('.zip')):
                        # 如果是zip文件，去掉.zip后缀
                        skin_name = skin
                        if skin.endswith('.zip'):
                            skin_name = skin[:-4]
                        skins_dict[normalized_champion].append(skin_name)
        
        logging.info(f"皮肤目录扫描完成，共发现 {len(skins_dict)} 个英雄")
        return skins_dict
    
    
    
class modTools:
    def __init__(self):
        self.tools = tools()
        self.installed_path = os.path.join(os.getcwd(), "installed")
        self.profile_path = os.path.join(os.getcwd(), "profiles")
        self.game_path = self.tools.detect_game_path()
        if not self.game_path:
            raise RuntimeError("Game path not found. Please start the game first.")
        
        

    '''
    example command:

    mod-tools.exe import "skins/Ezreal/Striker Ezreal.zip" "installed/Striker Ezrea" --game:"E:/WeGameApps/英雄联盟/Game/"
    mod-tools.exe mkoverlay "installed/" "profiles/Default Profile" --game:"E:/WeGameApps/英雄联盟/Game/" "--mods:Nottingham Ezreal" --noTFT ""
    mod-tools.exe runoverlay  "profiles/Default Profile" "profiles/Default Profile.config" --game:"E:/WeGameApps/英雄联盟/Game/" "--mods:Nottingham Ezreal" --opts:none
    '''

    def importMod(self, mod_path: str):
        mod_name = mod_path.replace(".zip","").split("\\")[-1]
        command = f"SBTX.exe TXSBI \"{mod_path}\" \"{self.installed_path}\{mod_name}\" --game:\"{self.game_path}\""
        
        out, err = subprocess.Popen(
            command,
            shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        ).communicate()

        if err:
            logging.error(err.decode())
            return False
        else:
            logging.info(out.decode("gbk"))
            return True
        
    def saveProfile(self, mod_name: str):
        command = f"SBTX.exe TXSBM \"{self.installed_path}\" \"{self.profile_path}\Default Profile\" --game:\"{self.game_path}\" \"--mods:{mod_name}\" --noTFT \"\""
        
        out, err = subprocess.Popen(
            command,
            shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        ).communicate()

        if err:
            logging.err(err.decode("gbk"))
            return False
        else:
            logging.info(out.decode("gbk"))
            return True
        
    def runOverlay(self, wait=False):
        """
        在单独的线程中运行overlay并实时返回标准输出
        
        Args:
            wait (bool): 如果为True，则主线程将等待overlay线程完成
            
        Returns:
            tuple: (threading.Thread, threading.Event) 返回线程对象和停止事件，可用于后续操作
        """
        command = f"SBTX.exe TXSBR \"{self.profile_path}\\Default Profile\" \"{self.profile_path}\\Default Profile.config\" --game:\"{self.game_path}\" \"--mods:Nottingham Ezreal\" --opts:none"
        
        # 创建停止事件
        stop_event = threading.Event()
        
        # Check if process has admin privileges
        def is_admin():
            try:
                return ctypes.windll.shell32.IsUserAnAdmin() != 0
            except:
                return False
        
        # Create a thread to run the command
        def run_command():
            # Check if we already have admin privileges
            if is_admin():
                # Run normally as we already have admin rights
                logging.info("Already running with admin privileges, executing overlay normally")
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='gbk'
                )

                # Get parent process ID to find and terminate child processes
                parent_pid = process.pid

                # Separate thread to read stdout
                def read_stdout():
                    for line in iter(process.stdout.readline, ''):
                        logging.info(f"Overlay output: {line.strip()}")
                    process.stdout.close()

                stdout_thread = threading.Thread(target=read_stdout)
                stdout_thread.start()

                # Main thread waits for stop_event
                while not stop_event.is_set() and process.poll() is None:
                    time.sleep(0.1)

                if stop_event.is_set():
                    logging.info("Received stop signal, terminating overlay process...")

                    # Use psutil to find and terminate child processes
                    try:
                        parent_process = psutil.Process(parent_pid)
                        for child in parent_process.children(recursive=True):
                            logging.info(f"Killing child process {child.pid}")
                            child.terminate()
                            child.wait(timeout=5)
                    except psutil.NoSuchProcess:
                        logging.warning("No such process found")

                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        logging.warning("Process didn't exit in time. Killing...")
                        process.kill()

                stdout_thread.join()

                # Read stderr output
                stderr = process.stderr.read()
                process.stderr.close()
                if stderr:
                    logging.error(f"Overlay error: {stderr.strip()}")
            else:
                # Need to request admin privileges
                try:
                    logging.info("Starting overlay with admin privileges...")
                    
                    # Prepare arguments
                    overlay_args = f"runoverlay \"{self.profile_path}\\Default Profile\" \"{self.profile_path}\\Default Profile.config\" --game:\"{self.game_path}\" \"--mods:Nottingham Ezreal\" --opts:none"
                    
                    # Request admin privileges using ShellExecuteW
                    result = ctypes.windll.shell32.ShellExecuteW(
                        None,
                        "runas",
                        os.path.join(os.getcwd(), "mod-tools.exe"),
                        overlay_args,
                        os.getcwd(),
                        1
                    )
                    
                    # ShellExecute returns value > 32 if successful
                    if result <= 32:
                        error_codes = {
                            0: "Out of memory",
                            2: "File not found",
                            3: "Path not found",
                            5: "Access denied",
                            8: "Out of memory",
                            11: "Invalid parameter",
                            26: "Sharing violation",
                            27: "File name too long",
                            28: "Printer out of paper",
                            29: "Write fault",
                            30: "Read fault",
                            31: "General failure",
                            32: "Sharing violation"
                        }
                        error_msg = error_codes.get(result, f"Unknown error code: {result}")
                        logging.error(f"Failed to start overlay: {error_msg}")
                    else:
                        logging.info("Successfully started overlay with admin privileges")
                    
                    # Wait for stop event
                    while not stop_event.is_set():
                        time.sleep(0.5)
                    
                    if stop_event.is_set():
                        logging.info("Received stop signal, but cannot directly terminate admin process. Please close overlay window manually.")
                    
                except Exception as e:
                    logging.error(f"Error starting overlay: {e}")

        overlay_thread = threading.Thread(target=run_command)
        overlay_thread.daemon = True
        overlay_thread.start()

        logging.info("Overlay process started in background thread")

        if wait:
            overlay_thread.join()
            logging.info("Overlay process completed")

        return overlay_thread, stop_event
    

def checkIsLatestVersion():
    logging.info("检查lol版本, 判断是否需要更新皮肤数据...")
    version = requests.get("https://ddragon.leagueoflegends.com/api/versions.json").json()[0]

    try:
        with open("version", "r") as f:
            current_version = f.read().strip()

        if current_version != version:
            logging.info(f"当前版本: {current_version}，最新版本: {version}")
            with open("version", "w") as f:
                f.write(version)
            return False
        else:
            logging.info("当前版本已是最新")
            return True
    except:
        
        with open("version", "w") as f:
            f.write(version)
        return False # 也返回false 方便初始化


def sync_skinsId(output_path=SKINS_JSON_PATH, max_workers=MAX_WORKERS):
    """
    同步皮肤数据
    """
    # 加载本地已有数据
    if os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as f:
            local_data = json.load(f)
    else:
        local_data = {}

    # 获取最新版本号
    version = requests.get("https://ddragon.leagueoflegends.com/api/versions.json").json()[0]

    # 获取所有英雄列表
    champion_list_url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json"
    champion_list = requests.get(champion_list_url).json()["data"]
    champion_keys = list(champion_list.keys())

    def fetch_skins_if_new_added(champion_key, retries=5, delay=1):
        """
        获取单个英雄皮肤信息，判断是否有新增皮肤（基于 skin id）
        """
        url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion/{champion_key}.json"
        for attempt in range(retries):
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                data = response.json()["data"][champion_key]
            
                # 跳过原皮
                new_skins = [
                    {"id": skin["id"], "name": skin["name"], "num": skin["num"]}
                    for skin in data["skins"]  
                    if skin["num"] != 0

                ]
                # 差量判断逻辑
                local_skins = local_data.get(champion_key, [])
                local_ids = {skin["id"] for skin in local_skins}
                new_ids = {skin["id"] for skin in new_skins}
                if not new_ids.issubset(local_ids):  # 有新增
                    return champion_key, new_skins
                else:
                    return champion_key, None  # 无新增
            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(delay)
                else:
                    return champion_key, f"Error: {str(e)}"

    result = local_data.copy()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(fetch_skins_if_new_added, key) for key in champion_keys]
        for future in tqdm(as_completed(futures), total=len(futures), desc="Checking skins"):
            champ_key, skins = future.result()
            if isinstance(skins, list):
                result[champ_key] = skins
            elif skins is None:
                pass
            else:
                logging.warning(f"{champ_key} failed: {skins}")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    logging.info(f"皮肤id更新完毕，共 {len(result)} 个英雄")

def download_all_skins(skins_json_path=SKINS_JSON_PATH, save_dir=SAVE_DIR, max_workers=MAX_WORKERS):
    os.makedirs(save_dir, exist_ok=True)

    with open(skins_json_path, "r", encoding="utf-8") as f:
        skins_data = json.load(f)

    tasks = []
    skipped = 0

    for champion_key, skins in skins_data.items():
        for skin in skins:
            skin_id = skin["id"]
            skin_num = skin["num"]
            save_path = os.path.join(save_dir, f"{skin_id}.jpg")
            if os.path.exists(save_path):
                skipped += 1
                continue  
            tasks.append((champion_key, skin_id, skin_num))

    logging.info(f"{skipped} skins already downloaded. {len(tasks)} skins to download.")

    def download_skin(champion_key, skin_id, skin_num):
        url = f"https://ddragon.leagueoflegends.com/cdn/img/champion/splash/{champion_key}_{skin_num}.jpg"
        save_path = os.path.join(save_dir, f"{skin_id}.jpg")

        for attempt in range(RETRIES):
            try:
                resp = requests.get(url, timeout=TIMEOUT)
                if resp.status_code == 200:
                    with open(save_path, "wb") as f:
                        f.write(resp.content)
                    return True
                time.sleep(1)
            except Exception:
                time.sleep(1)
        return False

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_task = {
            executor.submit(download_skin, champion_key, skin_id, skin_num): (champion_key, skin_id)
            for champion_key, skin_id, skin_num in tasks
        }

        for future in tqdm(as_completed(future_to_task), total=len(future_to_task), desc="Downloading skins"):
            champion_key, skin_id = future_to_task[future]
            try:
                success = future.result()
                if not success:
                    pass 
            except Exception as e:
                logging.error(f"[!] Exception for {champion_key}:{skin_id} -> {e}")

    logging.info("All new skins downloaded.")

def updateSkin():
    sync_skinsId()
    download_all_skins()