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
        browser_opened = False  # 添加标志，记录浏览器是否已打开
        last_champion = None  # 记录上一次检测到的英雄
        
        while self.running:
            try:
                champion_id = self.game_api.get_current_champion_id()
                
                if champion_id != 0:
                    champion_alias = self.game_api.get_champion_alias(champion_id)
                    
                    # 只有当英雄变化时才更新数据
                    if champion_alias != None and champion_alias != last_champion:
                        last_champion = champion_alias
                        
                        # 规范化英雄名称，删除 '、. 和空格，并转为小写进行比较
                        normalized_champion = champion_alias.replace("'", "").replace(".", "").replace(" ", "").lower()
                        
                        # 特殊处理：Nunu 和 Willump
                        if normalized_champion == "nunu":
                            normalized_champion = "nunu&willump"
                        
                        # 查找匹配的英雄
                        found = False
                        for k in self.skin_dict:
                            
                            normalized_k = k.replace("'", "").replace(".", "").replace(" ", "").lower()
                            if normalized_champion == normalized_k:
                                available_skins = self.skin_dict[k]  # 使用原始键获取皮肤列表
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