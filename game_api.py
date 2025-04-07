import json
import logging
import requests
import subprocess
import os

class GameAPI:
    def __init__(self):
        self.url = None
        self.summoner_id = None
        self.initialize()
    
    def initialize(self):
        """初始化游戏API连接"""
        output, error = subprocess.Popen(
            "wmic PROCESS WHERE name='LeagueClientUx.exe' GET commandline", 
            shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        ).communicate()
        
        output = output.decode("gbk")
        app_port = output.split('--app-port=')[-1].split(' ')[0].strip('\"') 
        auth_token = output.split('--remoting-auth-token=')[-1].split(' ')[0].strip('\"') 
        self.url = "https" + '://' + 'riot:' + auth_token + '@' + "127.0.0.1" + ':' + app_port
        if(auth_token == ""):
            exit("请先启动lol")
        # 获取召唤师ID
        self.get_summoner_id()
        
        # 确保champion.json文件存在
        if not os.path.exists("champion.json"):
            self.create_champion_json()
    
    def get_summoner_id(self):
        """获取当前召唤师ID"""
        res = requests.get(url=self.url + "/lol-summoner/v1/current-summoner", verify=False)
        self.summoner_id = str(res.json()['summonerId'])
        logging.info("已获取召唤师ID")
        return self.summoner_id
    
    def get_current_champion_id(self):
        """获取当前选择的英雄ID"""
        res = requests.get(url=self.url + "/lol-champ-select-legacy/v1/current-champion", verify=False)
        return res.json()
    
    def get_champion_alias(self, champion_id):
        """根据英雄ID获取英雄别名"""
        with open("champion.json", "r", encoding="utf-8") as f:
            champions = json.load(f)
        
        for champion in champions:
            if champion["id"] == champion_id:
                return champion["alias"]
        
        return None
    
    def create_champion_json(self):
        """创建champion.json文件"""
        res = requests.get(
            url=self.url + f"/lol-champions/v1/inventories/{self.summoner_id}/champions-minimal", 
            verify=False
        )
        
        champions = []
        for champion in res.json():
            champions.append({
                "id": champion["id"],
                "name": champion["name"],
                "alias": champion["alias"]
            })
        
        with open("champion.json", "w", encoding="utf-8") as f:
            json.dump(champions, f, ensure_ascii=False, indent=2)
        
        logging.info("已创建champion.json文件")