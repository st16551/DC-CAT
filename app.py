from flask import Flask, render_template_string, request, redirect, url_for, session
import sqlite3
import requests
from datetime import datetime

app = Flask(__name__)
app.secret_key = "my_guild_secret_key_abcxyz888_666"

# ==================== 🛠️ Discord 設定 ====================
CLIENT_ID = "1549954226937929778"
CLIENT_SECRET = "Mh4hq0GCl5oWSjzHEIPQgKnIw7eddvjg"
REDIRECT_URI = "https://dc-cat.onrender.com/callback"

ADMIN_DISCORD_IDS = [
    "407651643836858388",
]
# =========================================================

def init_db():
    conn = sqlite3.connect("guild_database.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS loot_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            leader_name TEXT,
            item_name TEXT,
            loot_date TEXT,
            members TEXT,
            total_price REAL,
            tax_rate REAL,
            status TEXT DEFAULT 'pending'
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS split_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            member_name TEXT,
            item_name TEXT,
            total_per_person REAL,
            leader_name TEXT,
            status INTEGER DEFAULT 0,
            FOREIGN KEY(project_id) REFERENCES loot_projects(id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# 全新設計的儀表板 HTML 模板 (採用側邊欄與統計卡片風格)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>SpiritVale 戰利品管理系統</title>
    <style>
        :root {
            --bg-body: #07090e;
            --bg-sidebar: #0e1320;
            --bg-card: #131b2e;
            --border-color: #1e293b;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent-gold: #f59e0b;
            --accent-blue: #3b82f6;
            --accent-green: #10b981;
            --danger-red: #ef4444;
        }
        * { box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
            background-color: var(--bg-body); 
            margin: 0; 
            color: var(--text-main); 
            display: flex;
            min-height: 100vh;
        }
        
        /* 側邊欄導航 */
        .sidebar {
            width: 260px;
            background-color: var(--bg-sidebar);
            border-right: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            padding: 24px;
            justify-content: space-between;
        }
        .brand {
            font-size: 18px;
            font-weight: 800;
            color: var(--accent-gold);
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 40px;
            letter-spacing: 0.5px;
        }
        .nav-menu {
            display: flex;
            flex-direction: column;
            gap: 8px;
            flex-grow: 1;
        }
        .nav-item {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px 16px;
            border-radius: 10px;
            text-decoration: none;
            color: var(--text-muted);
            font-weight: 600;
            font-size: 14px;
            transition: all 0.2s;
        }
        .nav-item:hover {
            color: var(--text-main);
            background: rgba(255, 255, 255, 0.03);
        }
        .nav-item.active {
            color: white;
            background: linear-gradient(135deg, #2563eb, #1d4ed8);
            box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
        }
        
        .user-panel {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border-color);
            padding: 15px;
            border-radius: 12px;
            font-size: 13px;
        }
        .user-info { margin-bottom: 10px; color: var(--text-muted); word-break: break-all; }
        .user-info b { color: var(--text-main); }
        
        /* 主內容區 */
        .main-content {
            flex-grow: 1;
            padding: 40px;
            overflow-y: auto;
            max-width: calc(100vw - 260px);
        }
        .top-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
        }
        .top-bar h1 {
            margin: 0;
            font-size: 24px;
            font-weight: 700;
        }
        
        /* 數據統計方塊 */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 5px;
        }
        .stat-label { font-size: 13px; color: var(--text-muted); font-weight: 600; }
        .stat-value { font-size: 22px; font-weight: 700; color: var(--accent-gold); }
        
        /* 卡片與表單容器 */
        .card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            padding: 25px;
            margin-bottom: 25px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.3);
        }
        .card h3 {
            margin-top: 0;
            font-size: 16px;
            color: var(--text-main);
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        .form-group { display: flex; flex-direction: column; gap: 8px; }
        .form-group.full { grid-column: span 2; }
        label { font-weight: 600; font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
        
        input, textarea, select { 
            padding: 12px 14px; 
            background: #0b101d; 
            border: 1px solid var(--border-color); 
            border-radius: 8px; 
            color: white; 
            font-size: 14px; 
            outline: none;
            transition: all 0.2s;
        }
        input:focus, textarea:focus { border-color: var(--accent-gold); box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.15); }
        
        .btn { 
            padding: 10px 20px; 
            text-decoration: none; 
            border-radius: 8px; 
            background: linear-gradient(135deg, #059669, #047857); 
            color: white; 
            border: none; 
            cursor: pointer; 
            font-size: 14px; 
            font-weight: 600; 
            transition: all 0.2s; 
            box-shadow: 0 4px 12px rgba(5, 150, 105, 0.3);
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }
        .btn:hover { transform: translateY(-1px); filter: brightness(1.1); }
        .btn-secondary { background: #334155; box-shadow: none; }
        .btn-secondary:hover { background: #475569; }
        .btn-discord { background: #5865F2; box-shadow: 0 4px 12px rgba(88, 101, 242, 0.3); width: 100%; }
        .btn-discord:hover { background: #4752c4; }
        
        /* 表格樣式 */
        table { width: 100%; border-collapse: collapse; margin-top: 5px; }
        th, td { padding: 14px 16px; border-bottom: 1px solid var(--border-color); text-align: left; font-size: 14px; }
        th { background-color: #0b101d; color: var(--text-muted); font-weight: 600; }
        tr:hover td { background-color: rgba(255, 255, 255, 0.01); }
        
        .status-badge { padding: 6px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; display: inline-block; }
        .status-unpaid { background: rgba(239, 68, 68, 0.1); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.2); }
        .status-paid { background: rgba(16, 185, 129, 0.1); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.2); }
    </style>
</head>
<body>
    <!-- 左側導覽列 -->
    <div class="sidebar">
        <div>
            <div class="brand">
                <span>🛡️</span> SpiritVale 管理
            </div>
            <div class="nav-menu">
                <a href="/?tab=dashboard" class="nav-item {% if tab == 'dashboard' %}active{% endif %}">
                    <span>📊</span> 分錢明細總覽
                </a>
                <a href="/?tab=create" class="nav-item {% if tab == 'create' %}active{% endif %}">
                    <span>➕</span> 登記打寶項目
                </a>
                <a href="/?tab=pending" class="nav-item {% if tab == 'pending' %}active{% endif %}">
                    <span>⏳</span> 待售寶物庫
                </a>
            </div>
        </div>

        <div class="user-panel">
            {% if user %}
                <div class="user-info">
                    登入身分：<br><b>{{ user.username }}</b> {% if is_admin %}<span style="color:var(--accent-gold);">(幹部)</span>{% endif %}
                </div>
                <a href="/logout" class="btn btn-secondary" style="width: 100%; padding: 8px; font-size: 13px;">登出系統</a>
            {% else %}
                <div class="user-info" style="margin-bottom: 12px;">尚未透過 Discord 驗證</div>
                <a href="/login" class="btn btn-discord" style="padding: 10px; font-size: 13px;">🔐 Discord 登入</a>
            {% endif %}
        </div>
    </div>

    <!-- 右側主內容 -->
    <div class="main-content">
        <div class="top-bar">
            <h1>
                {% if tab == 'create' %}登記打寶項目
                {% elif tab == 'pending' %}待售寶物庫管理
                {% else %}分錢與領取狀態總覽{% endif %}
            </h1>
        </div>

        {% if tab == 'dashboard' %}
        <!-- 統計數據面板 -->
        <div class="stats-grid">
            <div class="stat-card">
                <span class="stat-label">總分發紀錄筆數</span>
                <span class="stat-value">{{ records|length }} 筆</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">待售寶物數量</span>
                <span class="stat-value" style="color: var(--accent-blue);">{{ pending_count }} 件</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">系統連線狀態</span>
                <span class="stat-value" style="color: var(--accent-green);">連線正常 (DB Sync)</span>
            </div>
        </div>

        <div class="card">
            <h3>💰 現有分錢總覽明細</h3>
            <table>
                <tr>
                    <th>編號</th>
                    <th>成員名稱</th>
                    <th>品項名稱</th>
                    <th>每人實拿金額</th>
                    <th>負責人</th>
                    <th>狀態</th>
                    <th>操作</th>
                </tr>
                {% for row in records %}
                <tr>
                    <td>#{{ row[0] }}</td>
                    <td><b>{{ row[1] }}</b></td>
                    <td>{{ row[2] }}</td>
                    <td><span style="color: var(--accent-gold); font-weight: 600;">{{ "{:,}".format(row[3]|int) }}</span> 元</td>
                    <td>{{ row[4] }}</td>
                    <td>
                        {% if row[5] == 1 %}
                            <span class="status-badge status-paid">已領取</span>
                        {% else %}
                            <span class="status-badge status-unpaid">未領取</span>
                        {% endif %}
                    </td>
                    <td>
                        {% if user %}
                            {% if is_admin or user.username == row[1] or user.global_name == row[1] %}
                                <form action="/toggle/{{ row[0] }}" method="POST" style="margin:0;">
                                    {% if row[5] == 1 %}
                                        <button type="submit" class="btn btn-secondary" style="padding: 6px 12px; font-size: 12px;">改為未領</button>
                                    {% else %}
                                        <button type="submit" class="btn" style="padding: 6px 12px; font-size: 12px;">確認已領</button>
                                    {% endif %}
                                </form>
                            {% else %}
                                <span style="color:var(--text-muted); font-size:12px;">僅限本人/幹部</span>
                            {% endif %}
                        {% else %}
                            <a href="/login" class="btn btn-discord" style="padding: 6px 12px; font-size: 12px; width:auto;">登入修改</a>
                        {% endif %}
                    </td>
                </tr>
                {% else %}
                <tr><td colspan="7" style="text-align:center; color:var(--text-muted); padding: 40px;">目前沒有任何分錢明細記錄。</td></tr>
                {% endfor %}
            </table>
        </div>

        {% elif tab == 'create' %}
        <div class="card">
            <h3>📝 填寫打寶與分紅資訊</h3>
            <form action="/create_loot" method="POST">
                <div class="form-grid">
                    <div class="form-group">
                        <label>開單負責人 (遊戲ID)</label>
                        <input type="text" name="leader_name" value="{{ user.username if user else '' }}" required placeholder="例如：Alex">
                    </div>
                    <div class="form-group">
                        <label>打寶日期</label>
                        <input type="date" name="loot_date" value="{{ today }}" required>
                    </div>
                    <div class="form-group full">
                        <label>打到的物品名稱</label>
                        <input type="text" name="item_name" required placeholder="例如：+10 稀有防具 / 王卡">
                    </div>
                    <div class="form-group full">
                        <label>參與人員 (請用半形逗號分隔)</label>
                        <textarea name="members" rows="4" required placeholder="玩家A, 玩家B, 玩家C..."></textarea>
                    </div>
                    <div class="form-group">
                        <label>售出總金額 (若未售出填 0 則進入待售庫)</label>
                        <input type="number" name="total_price" value="0" required>
                    </div>
                    <div class="form-group">
                        <label>交易所手續費/抽稅 (%)</label>
                        <input type="number" name="tax_rate" value="0" step="0.1">
                    </div>
                </div>
                <div style="margin-top: 25px;">
                    <button type="submit" class="btn">🚀 確認送出並同步</button>
                </div>
            </form>
        </div>

        {% elif tab == 'pending' %}
        <div class="card">
            <h3>⏳ 待售寶物庫（尚未結算）</h3>
            <table>
                <tr>
                    <th>日期</th>
                    <th>負責人</th>
                    <th>物品名稱</th>
                    <th>參與人數</th>
                    <th>快速結算操作</th>
                </tr>
                {% for p in pending_projects %}
                <tr>
                    <td>{{ p[3] }}</td>
                    <td><b>{{ p[1] }}</b></td>
                    <td>{{ p[2] }}</td>
                    <td>{{ p[4].split(',')|length }} 人</td>
                    <td>
                        <form action="/activate/{{ p[0] }}" method="POST" style="display:flex; gap:10px; align-items:center;">
                            <input type="number" name="sold_price" placeholder="輸入實際售出總金額" required style="width: 160px; padding: 8px;">
                            <button type="submit" class="btn" style="padding: 8px 14px; font-size: 13px;">完成售出並分錢</button>
                        </form>
                    </td>
                </tr>
                {% else %}
                <tr><td colspan="5" style="text-align:center; color:var(--text-muted); padding: 40px;">目前沒有待售寶物項目。</td></tr>
                {% endfor %}
            </table>
        </div>
        {% endif %}
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    user = session.get('user')
    is_admin = user and user.get('id') in ADMIN_DISCORD_IDS
    tab = request.args.get('tab', 'dashboard')
    today = datetime.now().strftime('%Y-%m-%d')

    conn = sqlite3.connect("guild_database.db")
    cursor = conn.cursor()

    cursor.execute("SELECT id, leader_name, item_name, loot_date, members FROM loot_projects WHERE status = 'pending'")
    pending_projects = cursor.fetchall()
    pending_count = len(pending_projects)

    cursor.execute("SELECT id, member_name, item_name, total_per_person, leader_name, status FROM split_records ORDER BY id DESC")
    records = cursor.fetchall()
    conn.close()

    return render_template_string(HTML_TEMPLATE, user=user, is_admin=is_admin, tab=tab, today=today, pending_projects=pending_projects, pending_count=pending_count, records=records)

@app.route('/create_loot', methods=['POST'])
def create_loot():
    leader_name = request.form.get('leader_name')
    loot_date = request.form.get('loot_date')
    item_name = request.form.get('item_name')
    members_raw = request.form.get('members', '')
    total_price = float(request.form.get('total_price', 0))
    tax_rate = float(request.form.get('tax_rate', 0))

    members = [m.strip() for m in members_raw.replace('，', ',').split(',') if m.strip()]
    if not members:
        return "請至少輸入一位參與成員！", 400

    conn = sqlite3.connect("guild_database.db")
    cursor = conn.cursor()

    if total_price > 0:
        status = 'active'
        net_price = total_price * (1 - tax_rate / 100)
        per_person = net_price / len(members)

        cursor.execute(
            "INSERT INTO loot_projects (leader_name, item_name, loot_date, members, total_price, tax_rate, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (leader_name, item_name, loot_date, members_raw, total_price, tax_rate, status)
        )
        project_id = cursor.lastrowid

        for m in members:
            cursor.execute(
                "INSERT INTO split_records (project_id, member_name, item_name, total_per_person, leader_name, status) VALUES (?, ?, ?, ?, ?, 0)",
                (project_id, m, item_name, per_person, leader_name)
            )
    else:
        cursor.execute(
            "INSERT INTO loot_projects (leader_name, item_name, loot_date, members, total_price, tax_rate, status) VALUES (?, ?, ?, ?, ?, ?, 'pending')",
            (leader_name, item_name, loot_date, members_raw, 0, tax_rate)
        )

    conn.commit()
    conn.close()
    return redirect(url_for('index', tab='dashboard'))

@app.route('/activate/<int:project_id>', methods=['POST'])
def activate_project(project_id):
    sold_price = float(request.form.get('sold_price', 0))
    
    conn = sqlite3.connect("guild_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT leader_name, item_name, members, tax_rate FROM loot_projects WHERE id = ?", (project_id,))
    proj = cursor.fetchone()
    
    if proj:
        leader_name, item_name, members_raw, tax_rate = proj
        members = [m.strip() for m in members_raw.replace('，', ',').split(',') if m.strip()]
        net_price = sold_price * (1 - tax_rate / 100)
        per_person = net_price / len(members) if members else 0

        cursor.execute("UPDATE loot_projects SET total_price = ?, status = 'active' WHERE id = ?", (sold_price, project_id))

        for m in members:
            cursor.execute(
                "INSERT INTO split_records (project_id, member_name, item_name, total_per_person, leader_name, status) VALUES (?, ?, ?, ?, ?, 0)",
                (project_id, m, item_name, per_person, leader_name)
            )
        conn.commit()
    conn.close()
    return redirect(url_for('index', tab='dashboard'))

@app.route('/toggle/<int:record_id>', methods=['POST'])
def toggle_status(record_id):
    user = session.get('user')
    if not user:
        return redirect(url_for('login'))

    conn = sqlite3.connect("guild_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT member_name, status FROM split_records WHERE id = ?", (record_id,))
    row = cursor.fetchone()
    
    if row:
        member_name, current_status = row
        is_admin = user.get('id') in ADMIN_DISCORD_IDS
        if is_admin or user.get('username') == member_name or user.get('global_name') == member_name:
            new_status = 0 if current_status == 1 else 1
            cursor.execute("UPDATE split_records SET status = ? WHERE id = ?", (new_status, record_id))
            conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/login')
def login():
    return redirect(f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify")

@app.route('/callback')
def callback():
    code = request.args.get('code')
    resp = requests.post("https://discord.com/api/oauth2/token", data={
        'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI
    }, headers={'Content-Type': 'application/x-www-form-urlencoded'}).json()
    
    if 'access_token' in resp:
        user_data = requests.get("https://discord.com/api/users/@me", headers={'Authorization': f"Bearer {resp['access_token']}"}).json()
        session['user'] = {'id': user_data.get('id'), 'username': user_data.get('username'), 'global_name': user_data.get('global_name')}
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
