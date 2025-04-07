import os
import logging
import threading
import webbrowser
from flask import Flask, render_template, request, jsonify

class SkinWebServer:
    def __init__(self, modtools=None):
        self.app = Flask(__name__, template_folder='templates', static_folder='static')
        self.modtools = modtools
        self.current_champion = None
        self.available_skins = []
        
        # 注册路由
        self.register_routes()
        
        if not os.path.exists("templates"):
            os.makedirs("templates")
        
        self.create_template()
    
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
            
            # 导入并应用皮肤
            skin_path = f"skins\\{self.current_champion}\\{selected_skin}.zip"
            
            success = self.modtools.importMod(skin_path)
            if not success:
                return jsonify({"success": False, "message": "导入皮肤失败"})
            
            success = self.modtools.saveProfile(selected_skin)
            if not success:
                return jsonify({"success": False, "message": "保存配置文件失败"})
            
            # 启动overlay
            runOverlaythread, runOverlaythread_stop_event = self.modtools.runOverlay()
            
            return jsonify({"success": True, "message": f"已应用皮肤: {selected_skin}"})
            
        # 添加获取当前英雄和皮肤数据的API
        @self.app.route('/api/current_data')
        def get_current_data():
            return jsonify({
                "champion": self.current_champion,
                "skins": self.available_skins
            })
    
    def create_template(self):
        with open("templates/index.html", "w", encoding="utf-8") as f:
            f.write("""
<!DOCTYPE html>
<html>
<head>
    <title>英雄联盟皮肤选择器</title>
    <meta charset="utf-8">
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f0f0f0;
        }
        h1 {
            color: #1a1a1a;
            text-align: center;
        }
        .champion-info {
            background-color: #fff;
            border-radius: 5px;
            padding: 15px;
            margin-bottom: 20px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .skins-container {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 15px;
        }
        .skin-item {
            background-color: #fff;
            border-radius: 5px;
            padding: 10px;
            text-align: center;
            cursor: pointer;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            transition: transform 0.2s;
        }
        .skin-item:hover {
            transform: translateY(-5px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        .status {
            margin-top: 20px;
            padding: 10px;
            border-radius: 5px;
            text-align: center;
        }
        .success {
            background-color: #d4edda;
            color: #155724;
        }
        .error {
            background-color: #f8d7da;
            color: #721c24;
        }
        #loading {
            position: fixed;
            top: 10px;
            right: 10px;
            background-color: #007bff;
            color: white;
            padding: 5px 10px;
            border-radius: 3px;
            display: none;
        }
    </style>
</head>
<body>
    <div id="loading">正在更新...</div>
    <h1>英雄联盟皮肤选择器</h1>
    
    <div class="champion-info">
        <h2>当前英雄: <span id="champion-name">{{ champion }}</span></h2>
    </div>
    
    <h3>可用皮肤:</h3>
    <div id="skins-container" class="skins-container">
        {% for skin in skins %}
        <div class="skin-item" onclick="selectSkin('{{ skin }}')">
            {{ skin }}
        </div>
        {% endfor %}
    </div>
    
    <div id="status" class="status" style="display: none;"></div>
    
    <script>
        // 定期检查更新
        let lastChampion = '{{ champion }}';
        
        function checkForUpdates() {
            document.getElementById('loading').style.display = 'block';
            
            fetch('/api/current_data')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('loading').style.display = 'none';
                    
                    // 如果英雄变化了，更新页面
                    if (data.champion !== lastChampion) {
                        lastChampion = data.champion;
                        document.getElementById('champion-name').textContent = data.champion;
                        
                        // 更新皮肤列表
                        const skinsContainer = document.getElementById('skins-container');
                        skinsContainer.innerHTML = '';
                        
                        data.skins.forEach(skin => {
                            const skinItem = document.createElement('div');
                            skinItem.className = 'skin-item';
                            skinItem.textContent = skin;
                            skinItem.onclick = function() { selectSkin(skin); };
                            skinsContainer.appendChild(skinItem);
                        });
                    }
                })
                .catch(error => {
                    document.getElementById('loading').style.display = 'none';
                    console.error('更新检查失败:', error);
                });
        }
        
        // 每3秒检查一次更新
        setInterval(checkForUpdates, 3000);
        
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
                
                // 3秒后隐藏状态消息
                setTimeout(() => {
                    statusDiv.style.display = 'none';
                }, 3000);
            })
            .catch((error) => {
                console.error('Error:', error);
                const statusDiv = document.getElementById('status');
                statusDiv.style.display = 'block';
                statusDiv.className = 'status error';
                statusDiv.textContent = '发生错误: ' + error;
            });
        }
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
        def run_server():
            self.app.run(host='127.0.0.1', port=port, debug=False)
        
        server_thread = threading.Thread(target=run_server)
        server_thread.daemon = True
        server_thread.start()
        logging.info(f"Web服务器已启动，访问 http://127.0.0.1:{port}")
        return server_thread
    
    def open_browser(self):
        """打开浏览器访问Web页面"""
        webbrowser.open('http://127.0.0.1:5000')
        logging.info("已打开浏览器")