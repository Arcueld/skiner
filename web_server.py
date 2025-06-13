import os
import logging
import threading
import webbrowser
import json
import atexit
import signal
import psutil
from flask import Flask, render_template, request, jsonify, send_file

targetPort = None

class SkinWebServer:
    def __init__(self, modtools=None, game_stats=None):
        self.app = Flask(__name__, template_folder='templates', static_folder='static')
        self.modtools = modtools
        self.game_stats = game_stats
        self.current_champion = None
        self.available_skins = []
        self.skins_data = self.load_skins_json()
        self.server_thread = None
        self.overlay_thread = None
        self.overlay_stop_event = None
        
        # 注册路由
        self.register_routes()
        
        if not os.path.exists("templates"):
            os.makedirs("templates")
        
        # 注册退出处理
        atexit.register(self.cleanup)
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        """处理终止信号"""
        logging.info("收到终止信号，正在清理...")
        self.cleanup()
        os._exit(0)
    
    def cleanup(self):
        """清理所有相关进程"""
        logging.info("正在清理Web服务器相关进程...")
        
        # 停止overlay
        if self.overlay_stop_event:
            self.overlay_stop_event.set()
            if self.overlay_thread:
                self.overlay_thread.join(timeout=2)
        
        # 获取当前进程
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
    
    def load_skins_json(self):
        """加载skins.json文件中的皮肤数据"""
        try:
            with open("skins.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Failed to load skins.json: {e}")
            return {}
    
    def get_skin_id(self, champion, skin_name):
        """根据英雄名和皮肤名获取皮肤ID"""
        if not champion or not skin_name or champion not in self.skins_data:
            return None
        
        # 规范化英雄名称，删除 '、. 和空格
        normalized_champion = champion.replace("'", "").replace(".", "").replace(" ", "")
        
        # 在skins.json中查找对应的皮肤
        for skin in self.skins_data.get(champion, []):
            if skin["name"] == skin_name:
                return skin["id"]
        
        return None
    
    def register_routes(self):
        @self.app.route('/')
        def index():
            return render_template('index.html', 
                                champion=self.current_champion, 
                                skins=self.available_skins)
        
        @self.app.route('/api/select_skin', methods=['POST'])
        def select_skin():
            data = request.json
            selected_skin = data.get('skin')
            
            if not selected_skin or not self.current_champion:
                return jsonify({"success": False, "message": "无效的选择"})
            
            skin_path = f"skins\\{self.current_champion}\\{selected_skin}.zip"
            success = self.modtools.importMod(skin_path)
            
            # 导入失败，尝试处理特殊英雄名称(适配lol-skins 老改名干什么玩意)
            if not success:
                # 处理特殊英雄名称
                processed_champion = self.current_champion.replace("AurelionSol","Aurelion Sol").replace("BelVeth","Bel'Veth").replace("ChoGath","Cho'Gath").replace("KhaZix","Kha'Zix").replace("Rakan","Rakan") \
                .replace("DrMundo","Dr. Mundo").replace("JarvanIV","Jarvan IV").replace("Khazix","Kha'Zix").replace("KogMaw","Kog'Maw") \
                .replace("LeeSin","Lee Sin").replace("MasterYi","Master Yi").replace("MissFortune","Miss Fortune") \
                .replace("Nunu","Nunu & Willump").replace("RekSai","Rek'Sai").replace("RenataGlasc","Renata Glasc").replace("TahmKench","Tahm Kench") \
                .replace("Velkoz","Vel'Koz").replace("XinZhao","Xin Zhao").replace("KSante","K'Sante").replace("Kaisa","Kai'Sa")
                
                # 再次尝试导入
                skin_path = f"skins\\{processed_champion}\\{selected_skin}.zip"
                success = self.modtools.importMod(skin_path)
                if not success:
                    return jsonify({"success": False, "message": f"导入皮肤失败: {skin_path}"})
            
            success = self.modtools.saveProfile(selected_skin)
            if not success:
                return jsonify({"success": False, "message": "保存配置文件失败"})
            
            # 启动overlay
            self.overlay_thread, self.overlay_stop_event = self.modtools.runOverlay()
            
            return jsonify({"success": True, "message": f"已应用皮肤: {selected_skin}"})
        
        # 获取皮肤预览图片
        @self.app.route('/api/skin_preview/<skin_name>')
        def get_skin_preview(skin_name):
            champion = request.args.get('champion')
            if not champion:
                return jsonify({"error": "Champion parameter is required"}), 400
            
            # 从skins.json中获取皮肤ID
            skin_id = self.get_skin_id(champion, skin_name)
            if not skin_id:
                return jsonify({"error": f"Skin ID not found for {skin_name}"}), 404
            
            preview_path = os.path.join(os.getcwd(), "id_skins", f"{skin_id}.jpg")
            
            if os.path.exists(preview_path):
                return send_file(preview_path, mimetype='image/jpeg')
            else:
                return jsonify({"error": "Preview not found"}), 404
        
        # 添加获取当前英雄和皮肤数据的API
        @self.app.route('/api/current_data')
        def get_current_data():
            # 获取当前英雄的皮肤数据，包括ID
            skins_with_data = []
            if self.current_champion in self.skins_data:
                for skin_data in self.skins_data[self.current_champion]:
                    if skin_data["name"] in self.available_skins:
                        skins_with_data.append(skin_data)
            
            return jsonify({
                "champion": self.current_champion,
                "skins": self.available_skins,
                "skins_data": skins_with_data
            })
        
        # 添加获取队友战绩的API
        @self.app.route('/api/teammates_stats')
        def get_teammates_stats():
            if not self.game_stats:
                return jsonify({"error": "Game stats not initialized"}), 500
            mode = request.args.get('mode')
            stats = self.game_stats.get_teammates_stats(mode=mode)
            if stats:
                return jsonify(stats)
            return jsonify({"error": "无法获取队友战绩"}), 500

        # 添加获取当前游戏玩家的API
        @self.app.route('/api/current_players')
        def get_current_players():
            if not self.game_stats:
                return jsonify({"error": "Game stats not initialized"}), 500
            
            players = self.game_stats.get_current_game_players()
            if players:
                return jsonify(players)
            return jsonify({"error": "无法获取当前游戏玩家信息"}), 500

        @self.app.route('/api/match_detail/<game_id>')
        def get_match_detail(game_id):
            if not self.game_stats:
                return jsonify({"error": "Game stats not initialized"}), 500
            detail = self.game_stats.get_match_detail(game_id)
            if detail:
                return jsonify(detail)
            return jsonify({"error": "无法获取对局详情"}), 500
    
        # 添加通过 Summoner ID 获取指定召唤师战绩的API
        @self.app.route('/api/summoner_match_history_by_id/<int:summoner_id>')
        def get_summoner_match_history_by_id(summoner_id):
            if not self.game_stats:
                return jsonify({"error": "Game stats not initialized"}), 500
            # 默认获取全部模式的战绩，从请求参数中获取模式
            mode = request.args.get('mode', 'ALL')
            match_history = self.game_stats.get_player_match_history(summoner_id, mode=mode) # 传递模式参数
            if match_history is not None:
                # 返回战绩列表
                return jsonify({"matchHistory": match_history})
            # 注意：通过ID获取可能无法直接获取名字，前端需要自己处理显示
            return jsonify({"error": f"无法获取召唤师 (ID: {summoner_id}) 的战绩"}), 500

    def update_champion_data(self, champion, skins):
        """更新当前英雄和可用皮肤数据"""
        self.current_champion = champion
        self.available_skins = skins
        logging.info(f"Web服务器已更新英雄数据: {champion}, 皮肤数量: {len(skins)}")
    
    def start(self, port=5000):
        """在新线程中启动Web服务器"""
        global targetPort
        targetPort = port
        def run_server():
            import logging as flask_logging
            flask_logging.getLogger('werkzeug').setLevel(flask_logging.ERROR)
            # 修改为threaded=True确保请求能被正确处理
            self.app.run(host='127.0.0.1', port=port, debug=False, threaded=True, use_reloader=False)
    
        self.server_thread = threading.Thread(target=run_server)
        self.server_thread.daemon = True
        self.server_thread.start()
        logging.info(f"Web服务器已启动，访问 http://127.0.0.1:{targetPort}")
        return self.server_thread
    
    def open_browser(self):
        """打开浏览器访问Web页面"""
        webBrowser = webbrowser.get(using='windows-default')  # 使用系统默认
        webBrowser.open("http://127.0.0.1:18081")
        logging.info("已打开浏览器")