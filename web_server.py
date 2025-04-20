import os
import logging
import threading
import webbrowser
import json
from flask import Flask, render_template, request, jsonify, send_file

targetPort = None

class SkinWebServer:
    def __init__(self, modtools=None):
        self.app = Flask(__name__, template_folder='templates', static_folder='static')
        self.modtools = modtools
        self.current_champion = None
        self.available_skins = []
        self.skins_data = self.load_skins_json()
        
        # 注册路由
        self.register_routes()
        
        if not os.path.exists("templates"):
            os.makedirs("templates")
        
        self.create_template()
    
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
            logging.info(f"Looking for preview at: {preview_path}")
            
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
        .skin-item.selected {
            background-color: #e6f7ff;
            border: 2px solid #1890ff;
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
        .preview-container {
            background-color: #fff;
            border-radius: 5px;
            padding: 15px;
            margin: 20px 0;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            text-align: center;
        }
        .preview-image {
            max-width: 100%;
            max-height: 400px;
            display: block;
            margin: 0 auto;
        }
        .no-preview {
            padding: 50px;
            background-color: #f8f9fa;
            color: #6c757d;
            text-align: center;
            border-radius: 5px;
        }
        .action-buttons {
            margin-top: 20px;
            text-align: center;
        }
        .apply-button {
            background-color: #28a745;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
            transition: background-color 0.2s;
        }
        .apply-button:hover {
            background-color: #218838;
        }
        .apply-button:disabled {
            background-color: #6c757d;
            cursor: not-allowed;
        }
    </style>
</head>
<body>
    <div id="loading">Loading...</div>
    <h1>League of Legends Skin Selector</h1>
    
    <div class="champion-info">
        <h2>Current Champion: <span id="champion-name">{{ champion }}</span></h2>
    </div>
    
    <div class="preview-container">
        <h3>Skin Preview</h3>
        <div id="preview-content" class="no-preview">
            Select a skin to preview
        </div>
    </div>
    
    <div class="action-buttons">
        <button id="apply-button" class="apply-button" disabled>Apply Selected Skin</button>
    </div>
    
    <h3>Available Skins:</h3>
    <div id="skins-container" class="skins-container">
        {% for skin in skins %}
        <div class="skin-item" data-skin="{{ skin }}">
            {{ skin }}
        </div>
        {% endfor %}
    </div>
    
    <div id="status" class="status" style="display: none;"></div>
    
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
            previewContent.className = 'no-preview';
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
            previewContent.className = '';
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
                previewContent.className = 'no-preview';
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
        targetPort = port
        def run_server():
            import logging as flask_logging
            flask_logging.getLogger('werkzeug').setLevel(flask_logging.ERROR)
            # 修改为threaded=True确保请求能被正确处理
            self.app.run(host='127.0.0.1', port=port, debug=False, threaded=True, use_reloader=False)
    
        server_thread = threading.Thread(target=run_server)
        server_thread.daemon = True
        server_thread.start()
        logging.info(f"Web服务器已启动，访问 http://127.0.0.1:{targetPort}")
        return server_thread
    
    def open_browser(self):
        """打开浏览器访问Web页面"""
        webBrowser = webbrowser.get(using='windows-default')  # 使用系统默认
        webBrowser.open("http://127.0.0.1:18081")
        logging.info("已打开浏览器")