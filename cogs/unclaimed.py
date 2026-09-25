from flask import Flask, render_template_string, request, redirect, url_for, session
import sqlite3
import requests
from datetime import datetime

app = Flask(__name__)
app.secret_key = "my_guild_secret_key_abcxyz888_666"

# ==================== 🛠️ Discord OAuth2 設定 ====================
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
    
    # 1. 戰利品專案主表 (支援網頁登記與待售寶物庫)
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
    
    # 2. 個人分錢明細表 (完全相容你的 Discord 領取系統)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS split_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            member_name TEXT,
            item_name TEXT,
            total_per_person REAL,
            leader_name TEXT,
            status INTEGER DEFAULT 0,
            message_id INTEGER DEFAULT NULL,
            channel_id INTEGER DEFAULT NULL,
            FOREIGN KEY(project_id) REFERENCES loot_projects(id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# 整合版前端畫面模板 (包含分頁導覽、登記打寶、待售寶物庫、未領清單查詢)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>SpiritVale 公會打寶與分錢管理系統</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #f8f9fa; margin: 0; padding: 20px; color: #333; }
        .container { max-width: 1150px; margin: auto; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #eaeaea; padding-bottom: 15px; margin-bottom: 20px; }
        h2 { margin: 0; color: #1a1a1a; }
        .user-bar { display: flex; align-items: center; gap: 10px; }
        .btn { padding: 8px 16px; text-decoration: none; border-radius: 6px; background: #2f855a; color: white; border: none; cursor: pointer; font-size: 14px; font-weight: 500; transition: background 0.2s; }
        .btn:hover { background: #276749; }
        .btn-secondary { background: #718096; }
        .btn-secondary:hover { background: #4a5568; }
        .btn-discord { background: #5865F2; }
        .btn-discord:hover { background: #4752c4; }
        .btn-danger { background: #e53e3e; }
        .btn-danger:hover { background: #c53030; }
        .nav-tabs { display: flex; gap: 10px; margin-bottom: 25px; border-bottom: 1px solid #dee2e6; padding-bottom: 10px; }
        .nav-tab { padding: 8px 16px; border-radius: 6px; text-decoration: none; color: #4a5568; background: #edf2f7; font-weight: 500; }
        .nav-tab.active { background: #3182ce; color: white; }
        .card { background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.02); }
        .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 15px; }
        .form-group { display: flex; flex-direction: column; gap: 5px; }
        .form-group.full { grid-column: span 2; }
        label { font-weight: 600; font-size: 13px; color: #4a5568; }
        input, textarea, select { padding: 10px; border: 1px solid #cbd5e0; border-radius: 6px; font-size: 14px; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 12px; border-bottom: 1px solid #edf2f7; text-align: left; font-size: 14px; }
        th { background-color: #f7fafc; color: #2d3748; font-weight: 600; }
        .status-tag { padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }
        .status-0 { background: #fed7d7; color: #9b2c2c; }
        .status-1 { background: #c6f6d5; color: #22543d; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>🛡️ SpiritVale 戰利品與分錢管理系統</h2>
            <div class="user-bar">
                {% if user %}
                    <span>👤 <b>{{ user.username }}</b> {% if is_admin %}<span style="color:red; font-weight:bold;">(幹部)</span>{% endif %}</span>
                    <a href="/logout" class="btn btn-secondary" style="padding: 6px 12px;">登出</a>
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
            <h3>📝 登記新打寶項目</h3>
            <form action="/create_loot" method="POST">
                <div class="form-grid">
                    <div class="form-group">
                        <label>開單負責人 (你的遊戲ID)</label>
                        <input type="text" name="leader_name" value="{{ user.username if user else '' }}" required placeholder="例如：鈴噹、小修">
                    </div>
                    <div class="form-group">
                        <label>打寶日期</label>
                        <input type="date" name="loot_date" value="{{ today }}" required>
                    </div>
                    <div class="form-group full">
                        <label>打到的物品名稱</label>
                        <input type="text" name="item_name" required placeholder="例如：150王團 牧師卡、冰泰坦卡">
                    </div>
                    <div class="form-group full">
                        <label>參與人員 (請用半形或全形逗號分隔名字)</label>
                        <textarea name="members" rows="3" required placeholder="鈴噹, Draumr, 大鯊魚, 哭雲..."></textarea>
                    </div>
                    <div class="form-group">
                        <label>售出總金額 (若尚未售出可填 0 放入待售庫)</label>
                        <input type="number" name="total_price" value="0" required>
                    </div>
                    <div class="form-group">
                        <label>交易所手續費 / 抽稅 (%)</label>
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
                            <input type="number" name="sold_price" placeholder="輸入成交總金額" required style="width: 140px; padding: 6px;">
                            <button type="submit" class="btn" style="padding: 6px 12px;">售出結算並生成分錢</button>
                        </form>
                    </td>
                </tr>
                {% else %}
                <tr><td colspan="5" style="text-align:center; color:#718096; padding: 20px;">目前沒有待售中的寶物。</td></tr>
                {% endfor %}
            </table>
        </div>

        {% else %}
        <div class="card">
            <h3>💰 全體成員分錢與未領狀態總覽</h3>
            <p style="font-size:13px; color:#718096;">這裡列出所有已結算項目的成員分配明細。Discord 玩家打 `/查詢未領` 看到的也是這份資料庫！</p>
            <table>
                <tr>
                    <th>編號</th>
                    <th>成員名稱</th>
                    <th>品項名稱</th>
                    <th>每人實拿金額</th>
                    <th>負責人</th>
                    <th>領取狀態</th>
                    <th>操作</th>
                </tr>
                {% for row in records %}
                <tr>
                    <td>{{ row[0] }}</td>
                    <td><b>{{ row[1] }}</b></td>
                    <td>{{ row[2] }}</td>
                    <td>{{ "{:,}".format(row[3]|int) }} 元</td>
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
                                        <button type="submit" class="btn btn-secondary" style="padding: 4px 8px; font-size:12px;">改回未領</button>
                                    {% else %}
                                        <button type="submit" class="btn" style="padding: 4px 8px; font-size:12px;">設為已領</button>
                                    {% endif %}
                                </form>
                            {% else %}
                                <span style="color:#a0aec0; font-size:12px;">僅限本人或幹部</span>
                            {% endif %}
                        {% else %}
                            <a href="/login" class="btn btn-discord" style="padding: 4px 8px; font-size:12px;">登入修改</a>
                        {% endif %}
                    </td>
                </tr>
                {% else %}
                <tr><td colspan="7" style="text-align:center; color:#718096; padding: 20px;">目前尚無任何分錢紀錄。</td></tr>
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
        net_price = total_price * (1 - tax_rate / 100)
        per_person = net_price / len(members)

        cursor.execute(
            "INSERT INTO loot_projects (leader_name, item_name, loot_date, members, total_price, tax_rate, status) VALUES (?, ?, ?, ?, ?, ?, 'active')",
            (leader_name, item_name, loot_date, members_raw, total_price, tax_rate)
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
async def setup(bot):
    await bot.add_cog(Unclaimed(bot))  # 請確認括號裡的類別名稱是否為 Unclaimed
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
