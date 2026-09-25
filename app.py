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
    # 建立打寶/分錢專案主表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS loot_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            leader_name TEXT,
            item_name TEXT,
            loot_date TEXT,
            members TEXT, -- 以逗號分隔的成員名單
            total_price REAL,
            tax_rate REAL,
            status TEXT DEFAULT 'pending' -- pending(待售), active(分錢中), archived(已歸檔)
        )
    ''')
    # 建立個人領取狀態表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS split_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            member_name TEXT,
            item_name TEXT,
            total_per_person REAL,
            leader_name TEXT,
            status INTEGER DEFAULT 0, -- 0:未領, 1:已領
            FOREIGN KEY(project_id) REFERENCES loot_projects(id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# 網頁前端 HTML 模板 (已改為沉浸式 MMORPG 遊戲風暗黑介面)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>SpiritVale 戰利品管理系統</title>
    <style>
        :root {
            --bg-color: #0b0f19;
            --panel-bg: #131c2e;
            --panel-border: #1e293b;
            --text-main: #f1f5f9;
            --text-muted: #94a3b8;
            --accent-gold: #f59e0b;
            --accent-blue: #3b82f6;
            --accent-green: #10b981;
            --danger-red: #ef4444;
        }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
            background-color: var(--bg-color); 
            margin: 0; 
            padding: 30px; 
            color: var(--text-main); 
        }
        .container { 
            max-width: 1150px; 
            margin: auto; 
            background: var(--panel-bg); 
            padding: 35px; 
            border-radius: 16px; 
            box-shadow: 0 10px 30px rgba(0,0,0,0.5); 
            border: 1px solid rgba(245, 158, 11, 0.2); 
        }
        .header { 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            border-bottom: 1px solid var(--panel-border); 
            padding-bottom: 20px; 
            margin-bottom: 25px; 
        }
        h2 { 
            margin: 0; 
            color: var(--accent-gold); 
            font-size: 22px; 
            letter-spacing: 0.5px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .user-bar { display: flex; align-items: center; gap: 12px; font-size: 14px; color: var(--text-muted); }
        .user-bar b { color: var(--text-main); }
        
        .btn { 
            padding: 9px 18px; 
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
        }
        .btn:hover { transform: translateY(-1px); filter: brightness(1.1); }
        .btn-secondary { background: #334155; box-shadow: none; }
        .btn-secondary:hover { background: #475569; }
        .btn-discord { background: #5865F2; box-shadow: 0 4px 12px rgba(88, 101, 242, 0.3); }
        .btn-discord:hover { background: #4752c4; }
        
        .nav-tabs { display: flex; gap: 12px; margin-bottom: 30px; }
        .nav-tab { 
            padding: 10px 20px; 
            border-radius: 8px; 
            text-decoration: none; 
            color: var(--text-muted); 
            background: #0f172a; 
            font-weight: 600; 
            font-size: 14px;
            border: 1px solid var(--panel-border);
            transition: all 0.2s;
        }
        .nav-tab:hover { color: var(--text-main); border-color: #475569; }
        .nav-tab.active { 
            background: linear-gradient(135deg, #2563eb, #1d4ed8); 
            color: white; 
            border-color: transparent;
            box-shadow: 0 4px 12px rgba(37, 99, 235, 0.4);
        }
        
        .card { 
            background: #0f172a; 
            border: 1px solid var(--panel-border); 
            border-radius: 12px; 
            padding: 25px; 
            margin-bottom: 25px; 
        }
        .card h3 { margin-top: 0; color: #f8fafc; font-size: 18px; margin-bottom: 20px; border-left: 4px solid var(--accent-gold); padding-left: 10px; }
        
        .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }
        .form-group { display: flex; flex-direction: column; gap: 8px; }
        .form-group.full { grid-column: span 2; }
        label { font-weight: 600; font-size: 13px; color: var(--text-muted); }
        
        input, textarea, select { 
            padding: 12px; 
            background: #1e293b; 
            border: 1px solid #334155; 
            border-radius: 8px; 
            color: white; 
            font-size: 14px; 
            outline: none;
            transition: border-color 0.2s;
        }
        input:focus, textarea:focus { border-color: var(--accent-gold); }
        
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 14px; border-bottom: 1px solid var(--panel-border); text-align: left; font-size: 14px; }
        th { background-color: #162032; color: var(--text-muted); font-weight: 600; }
        tr:hover td { background-color: rgba(255, 255, 255, 0.02); }
        
        .status-tag { padding: 5px 10px; border-radius: 6px; font-size: 12px; font-weight: bold; }
        .status-0 { background: rgba(239, 68, 68, 0.15); color: #fca5a5; border: 1px solid rgba(239, 68, 68, 0.3); }
        .status-1 { background: rgba(16, 185, 129, 0.15); color: #6ee7b7; border: 1px solid rgba(16, 185, 129, 0.3); }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>🛡️ SpiritVale 戰利品管理系統</h2>
            <div class="user-bar">
                {% if user %}
                    <span>👤 <b>{{ user.username }}</b> {% if is_admin %}<span style="color:var(--accent-gold);">(幹部)</span>{% endif %}</span>
                    <a href="/logout" class="btn btn-secondary" style="padding: 6px 12px; font-size: 13px;">登出</a>
                {% else %}
                    <a href="/login" class="btn btn-discord">🔐 使用 Discord 登入</a>
                {% endif %}
            </div>
        </div>

        <div class="nav-tabs">
            <a href="/?tab=dashboard" class="nav-tab {% if tab == 'dashboard' %}active{% endif %}">📊 分錢與未領總覽</a>
            <a href="/?tab=create" class="nav-tab {% if tab == 'create' %}active{% endif %}">➕ 登記打寶項目</a>
            <a href="/?tab=pending" class="nav-tab {% if tab == 'pending' %}active{% endif %}">⏳ 待售寶物庫</a>
        </div>

        {% if tab == 'create' %}
        <div class="card">
            <h3>登記新打寶項目</h3>
            <form action="/create_loot" method="POST">
                <div class="form-grid">
                    <div class="form-group">
                        <label>開單負責人 (你的遊戲ID)</label>
                        <input type="text" name="leader_name" value="{{ user.username if user else '' }}" required placeholder="例如：小修、團長A">
                    </div>
                    <div class="form-group">
                        <label>打寶日期</label>
                        <input type="date" name="loot_date" value="{{ today }}" required>
                    </div>
                    <div class="form-group full">
                        <label>打到的物品名稱</label>
                        <input type="text" name="item_name" required placeholder="例如：冰泰坦卡、150王團 牧師卡">
                    </div>
                    <div class="form-group full">
                        <label>參與人員 (請用半形逗號分隔名字)</label>
                        <textarea name="members" rows="3" required placeholder="鈴噹, Draumr, 大鯊魚, 哭雲, 拉姆..."></textarea>
                    </div>
                    <div class="form-group">
                        <label>售出總金額 (若尚未售出可先填 0)</label>
                        <input type="number" name="total_price" value="0" required>
                    </div>
                    <div class="form-group">
                        <label>交易所手續費/抽稅 (%)</label>
                        <input type="number" name="tax_rate" value="0" step="0.1">
                    </div>
                </div>
                <button type="submit" class="btn">確認送出登記</button>
            </form>
        </div>

        {% elif tab == 'pending' %}
        <div class="card">
            <h3>⏳ 待售寶物庫（尚未賣出）</h3>
            <table>
                <tr>
                    <th>日期</th>
                    <th>負責人</th>
                    <th>物品名稱</th>
                    <th>參與人數</th>
                    <th>操作</th>
                </tr>
                {% for p in pending_projects %}
                <tr>
                    <td>{{ p[3] }}</td>
                    <td><b>{{ p[1] }}</b></td>
                    <td>{{ p[2] }}</td>
                    <td>{{ p[4].split(',')|length }} 人</td>
                    <td>
                        <form action="/activate/{{ p[0] }}" method="POST" style="display:inline; display:flex; gap:8px; align-items:center;">
                            <input type="number" name="sold_price" placeholder="輸入售出總金額" required style="width: 140px; padding: 8px;">
                            <button type="submit" class="btn" style="padding: 8px 14px;">售出結算並發放</button>
                        </form>
                    </td>
                </tr>
                {% else %}
                <tr><td colspan="5" style="text-align:center; color:var(--text-muted); padding: 30px;">目前沒有待售寶物。</td></tr>
                {% endfor %}
            </table>
        </div>

        {% else %}
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
                    <td>{{ row[0] }}</td>
                    <td><b>{{ row[1] }}</b></td>
                    <td>{{ row[2] }}</td>
                    <td><span style="color: var(--accent-gold);">{{ "{:,}".format(row[3]|int) }}</span> 元</td>
                    <td>{{ row[4] }}</td>
                    <td>
                        {% if row[5] == 1 %}
                            <span class="status-tag status-1">已領取</span>
                        {% else %}
                            <span class="status-tag status-0">未領取</span>
                        {% endif %}
                    </td>
                    <td>
                        {% if user %}
                            {% if is_admin or user.username == row[1] or user.global_name == row[1] %}
                                <form action="/toggle/{{ row[0] }}" method="POST" style="margin:0;">
                                    {% if row[5] == 1 %}
                                        <button type="submit" class="btn btn-secondary" style="padding: 5px 10px; font-size:12px;">改為未領</button>
                                    {% else %}
                                        <button type="submit" class="btn" style="padding: 5px 10px; font-size:12px;">確認已領</button>
                                    {% endif %}
                                </form>
                            {% else %}
                                <span style="color:var(--text-muted); font-size:12px;">非本人</span>
                            {% endif %}
                        {% else %}
                            <a href="/login" class="btn btn-discord" style="padding: 5px 10px; font-size:12px;">登入修改</a>
                        {% endif %}
                    </td>
                </tr>
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

    cursor.execute("SELECT id, member_name, item_name, total_per_person, leader_name, status FROM split_records ORDER BY id DESC")
    records = cursor.fetchall()
    conn.close()

    return render_template_string(HTML_TEMPLATE, user=user, is_admin=is_admin, tab=tab, today=today, pending_projects=pending_projects, records=records)

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
        # 尚未售出，存入 pending
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
