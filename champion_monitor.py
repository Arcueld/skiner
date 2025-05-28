import time
import logging
import threading

class ChampionMonitor:
    def __init__(self, game_api, web_server, skin_dict):
        self.game_api = game_api  
        self.web_server = web_server  
        self.skin_dict = skin_dict  
        self.running = False
        self.monitor_thread = None
        
        # 特殊英雄名称映射
        self.champion_name_mapping = {
            "aurelionsol": "Aurelion Sol",
            "belveth": "Bel'Veth",
            "chogath": "Cho'Gath",
            "khazix": "Kha'Zix",
            "drmundo": "Dr. Mundo",
            "jarvaniv": "Jarvan IV",
            "kogmaw": "Kog'Maw",
            "leesin": "Lee Sin",
            "masteryi": "Master Yi",
            "missfortune": "Miss Fortune",
            "nunu": "Nunu & Willump",
            "reksai": "Rek'Sai",
            "renataglasc": "Renata Glasc",
            "tahmkench": "Tahm Kench",
            "velkoz": "Vel'Koz",
            "xinzhao": "Xin Zhao",
            "Velkoz": "Vel'Koz"
        }
    
    def normalize_champion_name(self, name):
        """规范化英雄名称，用于比较"""
        if not name:
            return None
        # 特殊处理 Nunu & Willump
        if name == "Nunu & Willump":
            return "Nunu"
        # 特殊处理 Vel'Koz
        if name == "Vel'Koz":
            return "Velkoz"
        # 删除所有特殊字符并转为小写
        return ''.join(c.lower() for c in name if c.isalnum())
    
    def get_original_champion_name(self, normalized_name):
        """获取原始英雄名称"""
        # 检查是否在特殊映射中
        if normalized_name in self.champion_name_mapping:
            return self.champion_name_mapping[normalized_name]
        return None
    
    def start_monitoring(self):
        """开始监控英雄选择"""
        if self.running:
            logging.warning("监控已经在运行中")
            return
        
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        logging.info("开始监控英雄选择...")
        return self.monitor_thread
    
    def stop_monitoring(self):
        """停止监控"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
            logging.info("已停止监控英雄选择")
    
    def _monitor_loop(self):
        """监控循环"""
        browser_opened = False
        last_champion = None
        
        while self.running:
            try:
                champion_id = self.game_api.get_current_champion_id()
                
                if champion_id != 0:
                    champion_alias = self.game_api.get_champion_alias(champion_id)
                    
                    # 只有当英雄变化时才更新数据
                    if champion_alias and champion_alias != last_champion:
                        last_champion = champion_alias
                        
                        # 规范化英雄名称
                        normalized_champion = self.normalize_champion_name(champion_alias)
                        
                        # 查找匹配的英雄
                        found = False
                        for skin_champion in self.skin_dict:
                            normalized_skin_champion = self.normalize_champion_name(skin_champion)
                            
                            if normalized_champion == normalized_skin_champion:
                                available_skins = self.skin_dict[skin_champion]
                                logging.info(f"找到 {len(available_skins)} 个 {champion_alias} 的皮肤: {available_skins}")
                                
                                # 更新Web服务器数据
                                self.web_server.update_champion_data(champion_alias, available_skins)
                                
                                # 只有第一次才打开浏览器
                                if not browser_opened:
                                    self.web_server.open_browser()
                                    browser_opened = True
                                found = True
                                break
                        
                        if not found:
                            logging.warning(f"未找到英雄 {champion_alias} 的皮肤")
                else:
                    # 如果没有选择英雄，重置上一次英雄记录
                    last_champion = None
                    
            except Exception as e:
                logging.error(f"监控过程中发生错误: {e}")
            
            time.sleep(0.3)