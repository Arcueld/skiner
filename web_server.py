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
    def __init__(self, modtools=None):
        self.app = Flask(__name__, template_folder='templates', static_folder='static')
        self.modtools = modtools
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
        
        self.create_template()
        
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
                .replace("LeeSin","Lee Sin").replace("MasterYi","Master Yi").replace("Miss Fortune","MissFortune") \
                .replace("Nunu","Nunu & Willump").replace("RekSai","Rek'Sai").replace("RenataGlasc","Renata Glasc").replace("TahmKench","Tahm Kench") \
                .replace("Velkoz","Vel'Koz").replace("XinZhao","Xin Zhao").replace("KSante","K'Sante")
                
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
    
    def create_template(self):
        with open("templates/index.html", "w", encoding="utf-8") as f:
            f.write("""
<!DOCTYPE html>
<html>
<head>
    <title>League of Legends Skin Selector</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary-color: #1a73e8;
            --secondary-color: #4285f4;
            --background-color: #f8f9fa;
            --card-background: #ffffff;
            --text-primary: #202124;
            --text-secondary: #5f6368;
            --success-color: #34a853;
            --error-color: #ea4335;
            --border-radius: 8px;
            --shadow: 0 2px 4px rgba(0,0,0,0.1);
            --transition: all 0.3s ease;
            --preview-height: 600px;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Roboto', sans-serif;
            background-color: var(--background-color);
            color: var(--text-primary);
            line-height: 1.6;
            padding: 20px;
            min-height: 100vh;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
        }

        .left-panel {
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        .right-panel {
            position: sticky;
            top: 20px;
            height: calc(100vh - 40px);
        }

        .header {
            text-align: center;
            padding: 20px;
            background: var(--card-background);
            border-radius: var(--border-radius);
            box-shadow: var(--shadow);
            grid-column: 1 / -1;
        }

        .header h1 {
            color: var(--primary-color);
            font-size: 2.5em;
            margin-bottom: 10px;
        }

        .champion-info {
            background: var(--card-background);
            border-radius: var(--border-radius);
            padding: 20px;
            box-shadow: var(--shadow);
            text-align: center;
        }

        .champion-info h2 {
            color: var(--text-primary);
            font-size: 1.8em;
            margin-bottom: 10px;
        }

        .preview-container {
            background: var(--card-background);
            border-radius: var(--border-radius);
            padding: 20px;
            box-shadow: var(--shadow);
            text-align: center;
            height: var(--preview-height);
            display: flex;
            flex-direction: column;
            position: relative;
        }

        .preview-container h3 {
            color: var(--text-primary);
            margin-bottom: 20px;
        }

        .preview-content {
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
        }

        .preview-image {
            max-width: 100%;
            max-height: calc(var(--preview-height) - 100px);
            object-fit: contain;
            border-radius: var(--border-radius);
            box-shadow: var(--shadow);
        }

        .no-preview {
            padding: 40px;
            background: var(--background-color);
            border-radius: var(--border-radius);
            color: var(--text-secondary);
            font-size: 1.2em;
            width: 100%;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .skins-container {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 20px;
            overflow-y: auto;
            max-height: calc(100vh - 400px);
            padding-right: 10px;
        }

        .skins-container::-webkit-scrollbar {
            width: 8px;
        }

        .skins-container::-webkit-scrollbar-track {
            background: var(--background-color);
            border-radius: 4px;
        }

        .skins-container::-webkit-scrollbar-thumb {
            background: var(--secondary-color);
            border-radius: 4px;
        }

        .skin-item {
            background: var(--card-background);
            border-radius: var(--border-radius);
            padding: 15px;
            text-align: center;
            cursor: pointer;
            transition: var(--transition);
            box-shadow: var(--shadow);
            border: 2px solid transparent;
        }

        .skin-item:hover {
            transform: translateY(-5px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
            border-color: var(--primary-color);
        }

        .skin-item.selected {
            background-color: #e8f0fe;
            border-color: var(--primary-color);
        }

        .action-buttons {
            margin: 20px 0;
            text-align: center;
        }

        .apply-button {
            background-color: var(--success-color);
            color: white;
            border: none;
            padding: 12px 30px;
            border-radius: var(--border-radius);
            cursor: pointer;
            font-size: 1.1em;
            font-weight: 500;
            transition: var(--transition);
            box-shadow: var(--shadow);
        }

        .apply-button:hover {
            background-color: #2d9249;
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        }

        .apply-button:disabled {
            background-color: var(--text-secondary);
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }

        .status {
            margin: 20px auto;
            padding: 15px;
            border-radius: var(--border-radius);
            text-align: center;
            max-width: 600px;
            display: none;
        }

        .status.success {
            background-color: #e6f4ea;
            color: var(--success-color);
            border: 1px solid var(--success-color);
        }

        .status.error {
            background-color: #fce8e6;
            color: var(--error-color);
            border: 1px solid var(--error-color);
        }

        #loading {
            position: fixed;
            top: 20px;
            right: 20px;
            background-color: var(--primary-color);
            color: white;
            padding: 10px 20px;
            border-radius: var(--border-radius);
            display: none;
            box-shadow: var(--shadow);
            z-index: 1000;
        }

        @media (max-width: 1024px) {
            .container {
                grid-template-columns: 1fr;
            }

            .right-panel {
                position: static;
                height: auto;
            }

            .preview-container {
                height: 400px;
            }

            .skins-container {
                max-height: none;
            }
        }

        @media (max-width: 768px) {
            .container {
                padding: 10px;
            }

            .header h1 {
                font-size: 2em;
            }

            .preview-container {
                height: 300px;
            }

            .preview-image {
                max-height: 250px;
            }
        }
    </style>
</head>
<body>
    <div id="loading">Loading...</div>
    <div class="container">
        <div class="header">
            <h1>League of Legends Skin Selector</h1>
        </div>
        
        <div class="left-panel">
            <div class="champion-info">
                <h2>Current Champion: <span id="champion-name">{{ champion }}</span></h2>
            </div>
            
            <div class="skins-container">
                {% for skin in skins %}
                <div class="skin-item" data-skin="{{ skin }}">
                    {{ skin }}
                </div>
                {% endfor %}
            </div>
        </div>
        
        <div class="right-panel">
            <div class="preview-container">
                <h3>Skin Preview</h3>
                <div id="preview-content" class="preview-content no-preview">
                    Select a skin to preview
                </div>
            </div>
            
            <div class="action-buttons">
                <button id="apply-button" class="apply-button" disabled>Apply Selected Skin</button>
            </div>
        </div>
        
        <div id="status" class="status"></div>
    </div>
    
    <script>
        // Store skin data from server
        let skinData = [];
        let lastChampion = '{{ champion }}';
        let currentSelectedSkin = null;
        
        // Initial data load
        fetchCurrentData();
        
        // Periodically check for updates
        setInterval(fetchCurrentData, 3000);
        
        function fetchCurrentData() {
            document.getElementById('loading').style.display = 'block';
            
            fetch('/api/current_data')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('loading').style.display = 'none';
                    
                    // Store skin data for later use
                    skinData = data.skins_data || [];
                    
                    // If champion changed, update the page
                    if (data.champion !== lastChampion) {
                        lastChampion = data.champion;
                        document.getElementById('champion-name').textContent = data.champion;
                        
                        // Update skin list
                        const skinsContainer = document.getElementById('skins-container');
                        skinsContainer.innerHTML = '';
                        
                        data.skins.forEach(skin => {
                            const skinItem = document.createElement('div');
                            skinItem.className = 'skin-item';
                            skinItem.textContent = skin;
                            skinItem.dataset.skin = skin;
                            skinItem.addEventListener('click', function() {
                                previewSkin(skin);
                            });
                            skinsContainer.appendChild(skinItem);
                        });
                        
                        // Reset preview and selection state
                        resetPreview();
                    }
                })
                .catch(error => {
                    document.getElementById('loading').style.display = 'none';
                    console.error('Update check failed:', error);
                });
        }
        
        function resetPreview() {
            const previewContent = document.getElementById('preview-content');
            previewContent.className = 'preview-content no-preview';
            previewContent.innerHTML = 'Select a skin to preview';
            currentSelectedSkin = null;
            document.getElementById('apply-button').disabled = true;
            
            // Remove selected state from all skin items
            document.querySelectorAll('.skin-item').forEach(item => {
                item.classList.remove('selected');
            });
        }
        
        function previewSkin(skinName) {
            // Update selection state
            document.querySelectorAll('.skin-item').forEach(item => {
                if (item.dataset.skin === skinName) {
                    item.classList.add('selected');
                } else {
                    item.classList.remove('selected');
                }
            });
            
            const previewContent = document.getElementById('preview-content');
            previewContent.className = 'preview-content';
            previewContent.innerHTML = '<p>Loading preview...</p>';
            
            // Get current champion
            const champion = document.getElementById('champion-name').textContent;
            
            // Load preview image
            const img = new Image();
            img.onload = function() {
                previewContent.innerHTML = '';
                img.className = 'preview-image';
                previewContent.appendChild(img);
            };
            img.onerror = function() {
                previewContent.className = 'preview-content no-preview';
                previewContent.innerHTML = 'Preview image not available';
            };
            
            // Use the skin name to request the preview
            img.src = `/api/skin_preview/${encodeURIComponent(skinName)}?champion=${encodeURIComponent(champion)}`;
            
            // Update current selected skin and enable apply button
            currentSelectedSkin = skinName;
            document.getElementById('apply-button').disabled = false;
        }
        
        // Apply button click event
        document.getElementById('apply-button').addEventListener('click', function() {
            if (currentSelectedSkin) {
                selectSkin(currentSelectedSkin);
            }
        });
        
        function selectSkin(skin) {
            fetch('/api/select_skin', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    skin: skin
                }),
            })
            .then(response => response.json())
            .then(data => {
                const statusDiv = document.getElementById('status');
                statusDiv.style.display = 'block';
                
                if (data.success) {
                    statusDiv.className = 'status success';
                } else {
                    statusDiv.className = 'status error';
                }
                
                statusDiv.textContent = data.message;
                
                // Hide status message after 3 seconds
                setTimeout(() => {
                    statusDiv.style.display = 'none';
                }, 3000);
            })
            .catch((error) => {
                console.error('Error:', error);
                const statusDiv = document.getElementById('status');
                statusDiv.style.display = 'block';
                statusDiv.className = 'status error';
                statusDiv.textContent = 'Error: ' + error;
            });
        }
        
        // Initialize click handlers for skin items
        document.querySelectorAll('.skin-item').forEach(item => {
            item.addEventListener('click', function() {
                previewSkin(this.dataset.skin);
            });
        });
    </script>
</body>
</html>
            """)
    
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