import os
import json
import random
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

# --- 資料庫連線設定 ---
# 提示：在本機測試時，請將 Neon 的 Connection String 放入環境變數或直接貼在下方
DATABASE_URL = os.environ.get('DATABASE_URL', 'your_neon_database_url_here')

def get_db_connection():
    # 建立連線，並設定回傳字典格式的資料
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

# --- 初始化資料庫表（若不存在則自動建立） ---
def init_db():
    # 預設的商品資料（Hello Kitty 聯名服飾系列）
    default_products = [
        {"name": "Kitty 經典刺繡大學T", "price": 1580, "category": "上衣"},
        {"name": "甜蜜粉紅蝴蝶結百褶裙", "price": 1280, "category": "下著"},
        {"name": "夢幻美樂蒂聯名針織外套", "price": 2200, "category": "外套"},
        {"name": "凱蒂貓帆布厚底休閒鞋", "price": 1980, "category": "鞋款"},
        {"name": "限量版 Kitty 造型丹寧外套", "price": 3200, "category": "外套"}
    ]
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 1. 建立商品表
        cur.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                price INT NOT NULL,
                category VARCHAR(50)
            );
        ''')
        
        # 2. 建立訂單表
        cur.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                order_date TIMESTAMP NOT NULL,
                original_total INT NOT NULL,
                discount_name VARCHAR(50),
                final_total INT NOT NULL,
                items TEXT NOT NULL
            );
        ''')
        
        # 檢查是否需要匯入預設商品
        cur.execute("SELECT COUNT(*) FROM products;")
        if cur.fetchone()[0] == 0:
            for p in default_products:
                cur.execute("INSERT INTO products (name, price, category) VALUES (%s, %s, %s);", 
                            (p['name'], p['price'], p['category']))
        
        conn.commit()
        cur.close()
        conn.close()
        print("資料庫初始化成功！")
    except Exception as e:
        print(f"資料庫初始化失敗: {e}")

# 在 App 啟動時或第一次請求時初始化資料庫
with app.app_context():
    # 如果 DATABASE_URL 還沒設定，先跳過避免報錯
    if 'your_neon_database_url' not in DATABASE_URL:
        init_db()

# --- 轉盤獎項定義 ---
LUCKY_WHEEL_OPTIONS = [
    {"id": 1, "text": "打 8 折", "type": "rate", "value": 0.8},
    {"id": 2, "text": "打 95 折", "type": "rate", "value": 0.95},
    {"id": 3, "text": "折 50 元", "type": "minus", "value": 50},
    {"id": 4, "text": "折 100 元", "type": "minus", "value": 100},
    {"id": 5, "text": "送 Kitty 造型別針 (不折價)", "type": "gift", "value": 0},
    {"id": 6, "text": "再接再厲 (不折價)", "type": "none", "value": 0}
]

# --- 路由與首頁 (Hello Kitty POS 介面) ---
@app.route('/')
def index():
    # 從資料庫撈取商品列表
    products = []
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM products ORDER BY id;")
        products = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"撈取商品失敗: {e}")
        # 備用防呆資料
        products = [{"id":1, "name":"[未連線資料庫] 測試商品", "price": 3200, "category":"測試"}]

    # 用 HTML 模板字串渲染，方便單一 app.py 獨立運作
    html_template = """
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Hello Kitty 夢幻服飾 POS 系統</title>
        <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Fredoka+One&family=Noto+Sans+TC:wght@400;700&display=swap');
            body {
                font-family: 'Noto Sans TC', sans-serif;
                background-color: #FFF0F5; /* 薰衣草粉紅底色 */
                background-image: radial-gradient(#FFB6C1 10%, transparent 11%), radial-gradient(#FFB6C1 10%, transparent 11%);
                background-size: 30px 30px;
                background-position: 0 0, 15px 15px;
            }
            .kitty-card {
                border: 3px solid #FF69B4;
                border-radius: 20px;
                background-color: rgba(255, 255, 255, 0.95);
                box-shadow: 0 8px 0px #FFB6C1;
            }
            .kitty-btn {
                background: linear-gradient(to bottom, #FF69B4, #FF1493);
                color: white;
                border-radius: 50px;
                box-shadow: 0 4px 0 #C71585;
                transition: all 0.1s ease;
            }
            .kitty-btn:active {
                transform: translateY(4px);
                box-shadow: 0 0px 0 #C71585;
            }
            /* 幸運轉盤樣式 */
            .wheel-container {
                position: relative;
                width: 300px;
                height: 300px;
                margin: 0 auto;
            }
            .wheel {
                width: 100%;
                height: 100%;
                border-radius: 50%;
                border: 8px solid #FF69B4;
                position: relative;
                overflow: hidden;
                transition: transform 4s cubic-bezier(0.25, 0.1, 0.25, 1);
                background: conic-gradient(
                    #FFC0CB 0deg 60deg, #FFB6C1 60deg 120deg, 
                    #FF69B4 120deg 180deg, #FFC0CB 180deg 240deg, 
                    #FFB6C1 240deg 300deg, #FF69B4 300deg 360deg
                );
            }
            .wheel-pointer {
                position: absolute;
                top: -15px;
                left: 50%;
                transform: translateX(-50%);
                width: 0;
                height: 0;
                border-left: 15px solid transparent;
                border-right: 15px solid transparent;
                border-top: 30px solid #FF1493;
                z-index: 10;
            }
            .wheel-text {
                position: absolute;
                width: 100%;
                height: 100%;
                text-align: center;
                transform-origin: 50% 50%;
                padding-top: 20px;
                font-weight: bold;
                color: #FFF;
                text-shadow: 1px 1px 2px #000;
            }
        </style>
    </head>
    <body class="p-4 md:p-8">

        <div class="max-w-7xl mx-auto mb-6 text-center">
            <h1 class="text-3xl md:text-5xl font-extrabold text-[#FF1493] tracking-wider drop-shadow-sm flex justify-center items-center gap-3">
                <i class="fa-solid fa-ribbon text-[#FF69B4]"></i> 
                Hello Kitty 夢幻時尚 POS 系統 
                <i class="fa-solid fa-ribbon text-[#FF69B4]"></i>
            </h1>
            <p class="text-pink-600 mt-2">滿額 $3,000 即可觸發幸運魔法蝴蝶結轉盤！🎀</p>
        </div>

        <div class="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-3 gap-6">
            
            <div class="lg:col-span-2 kitty-card p-6">
                <h2 class="text-xl font-bold text-pink-700 mb-4 border-b-2 border-pink-200 pb-2">
                    <i class="fa-solid fa-shirt"></i> 聯名服飾商品清單
                </h2>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {% for p in products %}
                    <div class="border-2 border-pink-100 rounded-xl p-4 bg-pink-50/50 hover:bg-pink-100/50 transition cursor-pointer flex justify-between items-center"
                         onclick="addToCart({{ p.id }}, '{{ p.name }}', {{ p.price }})">
                        <div>
                            <span class="text-xs bg-pink-400 text-white px-2 py-0.5 rounded-full">{{ p.category }}</span>
                            <h3 class="font-bold text-gray-800 mt-1">{{ p.name }}</h3>
                            <p class="text-pink-600 font-extrabold mt-1">${{ p.price }}</p>
                        </div>
                        <div class="w-10 h-10 rounded-full bg-white flex items-center justify-center border border-pink-300 text-pink-500 shadow-sm">
                            <i class="fa-solid fa-plus"></i>
                        </div>
                    </div>
                    {% endfor %}
                </div>
            </div>

            <div class="kitty-card p-6 flex flex-col justify-between h-[calc(100vh-200px)] min-h-[550px]">
                <div>
                    <h2 class="text-xl font-bold text-pink-700 mb-4 border-b-2 border-pink-200 pb-2 flex justify-between items-center">
                        <span><i class="fa-solid fa-cart-shopping"></i> 購物車清單</span>
                        <button onclick="clearCart()" class="text-xs text-pink-400 hover:text-pink-600">清空</button>
                    </h2>
                    
                    <div id="cart-items" class="space-y-3 max-h-[250px] overflow-y-auto pr-1">
                        <p class="text-gray-400 text-center py-8">購物車空空的，快去選購 Kitty 服飾吧 🐾</p>
                    </div>
                </div>

                <div class="border-t-2 border-pink-200 pt-4 mt-4 space-y-2">
                    <div class="flex justify-between text-gray-700">
                        <span>商品原始總額:</span>
                        <span id="summary-original" class="font-bold">$0</span>
                    </div>
                    
                    <div id="wheel-status-box" class="bg-pink-50 border border-pink-200 rounded-lg p-2 text-xs text-center text-pink-600 hidden">
                        <span id="wheel-status-text">🎉 已達 $3,000 門檻！獲得一次抽獎機會！</span>
                    </div>

                    <div class="flex justify-between text-gray-700">
                        <span>套用抽獎獎項:</span>
                        <span id="summary-discount-name" class="text-pink-500 font-bold">未使用</span>
                    </div>
                    <div class="flex justify-between text-2xl font-extrabold text-[#FF1493] pt-2 border-t border-dashed border-pink-200">
                        <span>應付總額:</span>
                        <span id="summary-final">$0</span>
                    </div>

                    <button onclick="processCheckout()" class="w-full kitty-btn py-3 mt-4 text-lg font-bold tracking-wider">
                        <i class="fa-solid fa-heart shadow-sm"></i> 確認結帳
                    </button>
                    <button onclick="openReportModal()" class="w-full border-2 border-pink-300 text-pink-600 hover:bg-pink-50 rounded-full py-1.5 text-xs font-bold mt-2 transition">
                        <i class="fa-solid fa-chart-line"></i> 查看後台營收報表
                    </button>
                </div>
            </div>
        </div>

        <div id="wheel-modal" class="fixed inset-0 bg-black/50 hidden items-center justify-center z-50 backdrop-blur-xs p-4">
            <div class="bg-white rounded-3xl max-w-sm w-full p-6 text-center border-4 border-[#FF69B4] relative">
                <div class="absolute -top-12 left-1/2 -translate-x-1/2 text-5xl">🎀</div>
                <h3 class="text-2xl font-black text-[#FF1493] mb-2 mt-2">Kitty 滿額驚喜！</h3>
                <p class="text-gray-600 text-sm mb-6">消費滿 $3,000 即可轉動下方蝴蝶結魔法盤！</p>
                
                <div class="wheel-container mb-6">
                    <div class="wheel-pointer"></div>
                    <div id="wheel-element" class="wheel">
                        </div>
                </div>

                <button id="spin-btn" onclick="startSpinning()" class="kitty-btn w-full py-3 text-lg font-bold">
                    ✨ 啟動魔法轉盤 ✨
                </button>
            </div>
        </div>

        <div id="report-modal" class="fixed inset-0 bg-black/50 hidden items-center justify-center z-50 p-4">
            <div class="bg-white rounded-2xl max-w-4xl w-full max-h-[85vh] p-6 border-2 border-pink-400 flex flex-col justify-between">
                <div>
                    <div class="flex justify-between items-center border-b-2 border-pink-200 pb-3 mb-4">
                        <h3 class="text-xl font-bold text-pink-700"><i class="fa-solid fa-chart-pie"></i> Kitty POS 後台報表</h3>
                        <button onclick="closeReportModal()" class="text-gray-400 hover:text-gray-600 text-xl">&times;</button>
                    </div>
                    <div class="grid grid-cols-3 gap-4 mb-4 text-center">
                        <div class="bg-pink-50 p-3 rounded-xl border border-pink-200">
                            <p class="text-xs text-gray-500">總銷售額</p>
                            <p id="report-revenue" class="text-xl font-black text-pink-600">$0</p>
                        </div>
                        <div class="bg-pink-50 p-3 rounded-xl border border-pink-200">
                            <p class="text-xs text-gray-500">總訂單數</p>
                            <p id="report-count" class="text-xl font-black text-pink-600">0 筆</p>
                        </div>
                        <div class="bg-pink-50 p-3 rounded-xl border border-pink-200">
                            <p class="text-xs text-gray-500">平均客單價</p>
                            <p id="report-avg" class="text-xl font-black text-pink-600">$0</p>
                        </div>
                    </div>
                    <div class="overflow-y-auto max-h-[40vh] border border-gray-100 rounded-lg">
                        <table class="w-full text-left border-collapse text-sm">
                            <thead>
                                <tr class="bg-pink-100 text-pink-700">
                                    <th class="p-2">訂單ID</th>
                                    <th class="p-2">時間</th>
                                    <th class="p-2">原始金額</th>
                                    <th class="p-2">所用獎項</th>
                                    <th class="p-2">最終實收</th>
                                </tr>
                            </thead>
                            <tbody id="report-table-body" class="divide-y divide-gray-100">
                                </tbody>
                        </table>
                    </div>
                </div>
                <div class="text-right mt-4">
                    <button onclick="closeReportModal()" class="bg-gray-200 text-gray-700 px-6 py-2 rounded-full font-medium text-sm">關閉</button>
                </div>
            </div>
        </div>

        <script>
            let cart = [];
            let luckyWheelReward = null; // 用來記錄抽中的獎項
            let wheelUsed = false;       // 是否已執行過抽獎

            // 獎項清單（與後端一致，供前端轉盤文字渲染）
            const options = """ + json.dumps(LUCKY_WHEEL_OPTIONS, ensure_ascii=False) + """;

            // 初始化轉盤文字與角度
            const wheelEl = document.getElementById('wheel-element');
            options.forEach((opt, idx) => {
                const angle = idx * 60;
                const textDiv = document.createElement('div');
                textDiv.className = 'wheel-text';
                textDiv.style.transform = `rotate(${angle}deg)`;
                textDiv.innerText = opt.text;
                wheelEl.appendChild(textDiv);
            });

            // 1. 新增商品至購物車
            function addToCart(id, name, price) {
                const existing = cart.find(item => item.id === id);
                if (existing) {
                    existing.quantity += 1;
                } else {
                    cart.push({ id, name, price, quantity: 1 });
                }
                updateCartUI();
            }

            // 2. 變更數量
            function changeQuantity(id, delta) {
                const item = cart.find(item => item.id === id);
                if (item) {
                    item.quantity += delta;
                    if (item.quantity <= 0) {
                        cart = cart.filter(i => i.id !== id);
                    }
                }
                updateCartUI();
            }

            // 3. 清空購物車
            function clearCart() {
                cart = [];
                luckyWheelReward = null;
                wheelUsed = false;
                document.getElementById('wheel-element').style.transform = 'rotate(0deg)';
                updateCartUI();
            }

            // 4. 更新購物車與金額的 UI 計算
            function updateCartUI() {
                const container = document.getElementById('cart-items');
                if (cart.length === 0) {
                    container.innerHTML = '<p class="text-gray-400 text-center py-8">購物車空空的，快去選購 Kitty 服飾吧 🐾</p>';
                    document.getElementById('summary-original').innerText = '$0';
                    document.getElementById('summary-final').innerText = '$0';
                    document.getElementById('summary-discount-name').innerText = '未使用';
                    document.getElementById('wheel-status-box').classList.add('hidden');
                    return;
                }

                // 渲染項目
                container.innerHTML = cart.map(item => `
                    <div class="flex justify-between items-center p-2 bg-white rounded-xl border border-pink-100 shadow-xs">
                        <div class="max-w-[150px]">
                            <p class="font-bold text-gray-800 text-sm truncate">${item.name}</p>
                            <p class="text-xs text-pink-500 font-bold">$${item.price}</p>
                        </div>
                        <div class="flex items-center gap-2">
                            <button onclick="changeQuantity(${item.id}, -1)" class="w-6 h-6 bg-pink-100 text-pink-600 rounded-full font-bold text-xs">-</button>
                            <span class="text-sm font-bold w-4 text-center">${item.quantity}</span>
                            <button onclick="changeQuantity(${item.id}, 1)" class="w-6 h-6 bg-pink-100 text-pink-600 rounded-full font-bold text-xs">+</button>
                        </div>
                    </div>
                `).join('');

                // 計算原始總價
                const originalTotal = cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);
                document.getElementById('summary-original').innerText = `$${originalTotal}`;

                // 滿 3000 促銷邏輯判斷
                const statusBox = document.getElementById('wheel-status-box');
                if (originalTotal >= 3000) {
                    statusBox.classList.remove('hidden');
                    if (!wheelUsed) {
                        // 自動彈出抽獎轉盤
                        document.getElementById('wheel-modal').style.display = 'flex';
                    }
                } else {
                    statusBox.classList.add('hidden');
                    luckyWheelReward = null; // 不滿額自動失效
                    wheelUsed = false;
                }

                // 計算最終折扣價
                let finalTotal = originalTotal;
                if (luckyWheelReward && originalTotal >= 3000) {
                    document.getElementById('summary-discount-name').innerText = luckyWheelReward.text;
                    if (luckyWheelReward.type === 'rate') {
                        finalTotal = Math.round(originalTotal * luckyWheelReward.value);
                    } else if (luckyWheelReward.type === 'minus') {
                        finalTotal = Math.max(0, originalTotal - luckyWheelReward.value);
                    }
                } else {
                    document.getElementById('summary-discount-name').innerText = '未使用';
                }

                document.getElementById('summary-final').innerText = `$${finalTotal}`;
            }

            // 5. 執行啟動轉盤
            function startSpinning() {
                if (wheelUsed) return;
                wheelUsed = true;
                document.getElementById('spin-btn').disabled = true;
                document.getElementById('spin-btn').innerText = '魔法使勁旋轉中...';

                // 打開後端提供的隨機抽獎 API 確保公平與數據安全
                fetch('/api/spin')
                    .then(res => res.json())
                    .then(data => {
                        luckyWheelReward = data.reward;
                        const index = options.findIndex(o => o.id === luckyWheelReward.id);
                        
                        // 計算旋轉度數 (基礎5圈 1800度 + 逆向對準指針角度)
                        const degrees = 1800 + (360 - (index * 60));
                        wheelEl.style.transform = `rotate(${degrees}deg)`;

                        // 轉盤動畫結束 (4000 毫秒)
                        setTimeout(() => {
                            alert(`✨ 恭喜抽中：【${luckyWheelReward.text}】！✨`);
                            document.getElementById('wheel-modal').style.display = 'none';
                            updateCartUI();
                        }, 4100);
                    });
            }

            // 6. 送出結帳到後台
            function processCheckout() {
                if (cart.length === 0) {
                    alert('購物車沒有衣服可以結帳唷！');
                    return;
                }
                const originalTotal = cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);
                
                const orderData = {
                    original_total: originalTotal,
                    discount_name: (originalTotal >= 3000 && luckyWheelReward) ? luckyWheelReward.text : '無',
                    final_total: parseInt(document.getElementById('summary-final').innerText.replace('$', '')),
                    items: cart
                };

                fetch('/api/checkout', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(orderData)
                })
                .then(res => res.json())
                .then(data => {
                    if(data.success) {
                        alert('🐾 結帳成功！訂單已記錄至資料庫。');
                        clearCart();
                    } else {
                        alert('結帳失敗：' + data.message);
                    }
                });
            }

            // 7. 後台報表視窗與 API 載入
            function openReportModal() {
                document.getElementById('report-modal').style.display = 'flex';
                fetch('/api/reports')
                    .then(res => res.json())
                    .then(data => {
                        document.getElementById('report-revenue').innerText = `$${data.summary.total_revenue}`;
                        document.getElementById('report-count').innerText = `${data.summary.total_orders} 筆`;
                        document.getElementById('report-avg').innerText = `$${data.summary.avg_order}`;
                        
                        const tbody = document.getElementById('report-table-body');
                        if(data.orders.length === 0) {
                            tbody.innerHTML = '<tr><td colspan="5" class="p-4 text-center text-gray-400">尚無營收紀錄。</td></tr>';
                            return;
                        }
                        tbody.innerHTML = data.orders.map(o => `
                            <tr class="hover:bg-gray-50">
                                <td class="p-2 font-mono">#${o.id}</td>
                                <td class="p-2 text-xs text-gray-500">${o.order_date}</td>
                                <td class="p-2">$${o.original_total}</td>
                                <td class="p-2 text-pink-500 font-medium">${o.discount_name}</td>
                                <td class="p-2 font-bold text-gray-800">$${o.final_total}</td>
                            </tr>
                        `).join('');
                    });
            }

            function closeReportModal() {
                document.getElementById('report-modal').style.display = 'none';
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(html_template, products=products)

# --- API 1：安全隨機抽取轉盤獎項 ---
@app.route('/api/spin', methods=['GET'])
def api_spin():
    reward = random.choice(LUCKY_WHEEL_OPTIONS)
    return jsonify({"reward": reward})

# --- API 2：結帳扣款並寫入 Neon 資料庫 ---
@app.route('/api/checkout', methods=['POST'])
def api_checkout():
    data = request.json
    if not data:
        return jsonify({"success": False, "message": "資料無效"}), 400
        
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 插入訂單紀錄
        cur.execute('''
            INSERT INTO orders (order_date, original_total, discount_name, final_total, items)
            VALUES (%s, %s, %s, %s, %s);
        ''', (
            datetime.now(),
            data['original_total'],
            data['discount_name'],
            data['final_total'],
            json.dumps(data['items'], ensure_ascii=False)
        ))
        
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# --- API 3：拉取後台報表與經營指標 ---
@app.route('/api/reports', methods=['GET'])
def api_reports():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 1. 撈取所有歷史訂單（限最新 100 筆流水帳）
        cur.execute("SELECT id, to_char(order_date, 'YYYY-MM-DD HH24:MI') as order_date, original_total, discount_name, final_total FROM orders ORDER BY id DESC LIMIT 100;")
        orders = cur.fetchall()
        
        # 2. 統計關鍵指標
        cur.execute("SELECT SUM(final_total) as total_revenue, COUNT(*) as total_orders, ROUND(AVG(final_total)) as avg_order FROM orders;")
        metrics = cur.fetchone()
        
        cur.close()
        conn.close()
        
        summary = {
            "total_revenue": metrics['total_revenue'] if metrics['total_revenue'] else 0,
            "total_orders": metrics['total_orders'] if metrics['total_orders'] else 0,
            "avg_order": int(metrics['avg_order']) if metrics['avg_order'] else 0
        }
        
        return jsonify({"orders": orders, "summary": summary})
    except Exception as e:
        return jsonify({"orders": [], "summary": {"total_revenue": 0, "total_orders": 0, "avg_order": 0}, "error": str(e)}), 500

# WSGI 生產環境進入點
if __name__ == '__main__':
    app.run(debug=True)