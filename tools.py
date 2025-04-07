import os
import logging
import psutil
import subprocess
import threading
import time
import selectors
import ctypes


from ctypes import wintypes

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
                # 处理英雄名称，删除 '、. 和空格
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
        command = f"mod-tools.exe import \"{mod_path}\" \"{self.installed_path}\{mod_name}\" --game:\"{self.game_path}\""
        
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
        
    def saveProfile(self, mod_name: str):
        command = f"mod-tools.exe mkoverlay \"{self.installed_path}\" \"{self.profile_path}\Default Profile\" --game:\"{self.game_path}\" \"--mods:{mod_name}\" --noTFT \"\""
        
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
        command = f"mod-tools.exe runoverlay \"{self.profile_path}\\Default Profile\" \"{self.profile_path}\\Default Profile.config\" --game:\"{self.game_path}\" \"--mods:Nottingham Ezreal\" --opts:none"
        
        # 创建停止事件
        stop_event = threading.Event()
        
        # 创建一个线程来运行命令并实时获取输出
        def run_command():
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='gbk'
            )

            # 获取父进程 ID，找到子进程并终止它们
            parent_pid = process.pid

            # 单独线程读取 stdout
            def read_stdout():
                for line in iter(process.stdout.readline, ''):
                    logging.info(f"Overlay output: {line.strip()}")
                process.stdout.close()

            stdout_thread = threading.Thread(target=read_stdout)
            stdout_thread.start()

            # 主线程等待 stop_event
            while not stop_event.is_set() and process.poll() is None:
                time.sleep(0.1)

            if stop_event.is_set():
                logging.info("Received stop signal, terminating overlay process...")

                # 使用 psutil 查找并终止子进程
                try:
                    parent_process = psutil.Process(parent_pid)
                    for child in parent_process.children(recursive=True):
                        logging.info(f"Killing child process {child.pid}")
                        child.terminate()  # 尝试正常终止子进程
                        child.wait(timeout=5)  # 等待子进程退出
                except psutil.NoSuchProcess:
                    logging.warning("No such process found")

                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logging.warning("Process didn't exit in time. Killing...")
                    process.kill()  # 强制终止

            stdout_thread.join()

            # 读取 stderr 输出
            stderr = process.stderr.read()
            process.stderr.close()
            if stderr:
                logging.error(f"Overlay error: {stderr.strip()}")

        overlay_thread = threading.Thread(target=run_command)
        overlay_thread.daemon = True
        overlay_thread.start()

        logging.info("Overlay process started in background thread")

        if wait:
            overlay_thread.join()
            logging.info("Overlay process completed")

        return overlay_thread, stop_event