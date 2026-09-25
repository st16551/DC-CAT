from flask import Flask, render_template_string, request, redirect, url_for, session
import sqlite3
import requests
import csv
import io
import json
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

# Google 試算表公開 CSV 下載網址 ("成員名單" 工作表)
GSHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/12AP1pzhqeskwhYY5piaYGasRNifLdCpgoddjxVM5yg4/gviz/tq?tqx=out:csv&sheet=成員名單"

def fetch_guild_members_from_sheet():
    """從 Google 試算表自動同步最新成員名單（唯讀，絕不修改你的表單）"""
    members = []
    try:
        response = requests.get(GSHEET_CSV_URL)
        if response.status_code == 200:
            decoded_content = response.content.decode('utf-8')
            reader = csv.reader(io.StringIO(decoded_content))
            next(reader, None) # 跳過標題列
            for row in reader:
                if len(row) >= 3:
                    discord_account = row[1].strip() if len(row) > 1 else ""
                    game_name = row[2].strip() if len(row) > 2 else ""
                    job = row[3].strip() if len(row) > 3 else ""
                    display_str = f"{job}-{game_name}({discord_account})" if job and game_name else (game_name or discord_account)
                    if display_str and display_str not in members:
                        members.append(display_str)
    except Exception as e:
        print("讀取 Google 試算表失敗，使用備用名單:", e)
        members = ["聖騎士-高須鼠兒[高須]", "死靈-Pongdog(胖打)"]
    return members

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
            status TEXT DEFAULT 'pending',
            updated_by TEXT,
            updated_at TEXT
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
    
    try:
        cursor.execute("ALTER TABLE loot_projects ADD COLUMN edit_summary TEXT")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()

init_db()

# 儀表板 HTML 模板
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
        }
        .nav-menu { display: flex; flex-direction: column; gap: 8px; flex-grow: 1; }
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
        .nav-item:hover { color: var(--text-main); background: rgba(255, 255, 255, 0.03); }
        .nav-item.active { color: white; background: linear-gradient(135deg, #2563eb, #1d4ed8); }
        
        .user-panel { background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border-color); padding: 15px; border-radius: 12px; font-size: 13px; }
        .user-info { margin-bottom: 10px; color: var(--text-muted); word-break: break-all; }
        .user-info b { color: var(--text-main); }
        
        .main-content { flex-grow: 1; padding: 40px; overflow-y: auto; max-width: calc(100vw - 260px); }
        .top-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; }
        .top-bar h1 { margin: 0; font-size: 24px; font-weight: 700; }
        
        .stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px; display: flex; flex-direction: column; gap: 5px; }
        .stat-label { font-size: 13px; color: var(--text-muted); font-weight: 600; }
        .stat-value { font-size: 22px; font-weight: 700; color: var(--accent-gold); }
        
        .card { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 14px; padding: 25px; margin-bottom: 25px; box-shadow: 0 8px 24px rgba(0,0,0,0.3); }
        .card h3 { margin-top: 0; font-size: 16px; color: var(--text-main); margin-bottom: 20px; display: flex; align-items: center; justify-content: space-between; }
        
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
        input:focus, textarea:focus { border-color: var(--accent-gold); }
        
        .member-picker-box { background: #0b101d; border: 1px solid var(--border-color); border-radius: 8px; padding: 12px; margin-top: 8px; }
        .member-search-input { width: 100%; margin-bottom: 10px; }
        .member-suggestions { display: flex; flex-wrap: wrap; gap: 6px; max-height: 140px; overflow-y: auto; padding: 4px; }
        .chip { background: #1e293b; border: 1px solid #334155; color: #f1f5f9; padding: 5px 10px; border-radius: 6px; font-size: 12px; cursor: pointer; transition: all 0.15s; }
        .chip:hover { background: var(--accent-gold); color: black; border-color: var(--accent-gold); }
        
        .selected-tags { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; min-height: 45px; background: #07090e; padding: 10px; border-radius: 8px; border: 1px solid var(--border-color); }
        .selected-tag { background: #2563eb; color: white; padding: 5px 10px; border-radius: 6px; font-size: 12px; display: inline-flex; align-items: center; gap: 6px; }
        .selected-tag .remove-btn { cursor: pointer; font-weight: bold; color: #fca5a5; }
        .selected-tag .remove-btn:hover { color: white; }

        .btn { 
            padding: 10px 20px; text-decoration: none; border-radius: 8px; background: linear-gradient(135deg, #059669, #047857); 
            color: white; border: none; cursor: pointer; font-size: 14px; font-weight: 600; transition: all 0.2s; 
            box-shadow: 0 4px 12px rgba(5, 150, 105, 0.3); display: inline-flex; align-items: center; justify-content: center; gap: 8px;
        }
        .btn:hover { transform: translateY(-1px); filter: brightness(1.1); }
        .btn-secondary { background: #334155; box-shadow: none; }
        .btn-secondary:hover { background: #475569; }
        .btn-discord { background: #5865F2; box-shadow: 0 4px 12px rgba(88, 101, 242, 0.3); width: 100%; }
        
        table { width: 100%; border-collapse: collapse; margin-top: 5px; }
        th, td { padding: 14px 16px; border-bottom: 1px solid var(--border-color); text-align: left; font-size: 14px; }
        th { background-color: #0b101d; color: var(--text-muted); font-weight: 600; }
        tr:hover td { background-color: rgba(255, 255, 255, 0.01); }
        
        .status-badge { padding: 6px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; display: inline-block; }
        .status-unpaid { background: rgba(239, 68, 68, 0.1); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.2); }
        .status-paid { background: rgba(16, 185, 129, 0.1); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.2); }
        .change-summary { color: #38bdf8; font-size: 13px; line-height: 1.5; }
    </style>
</head>
<body>
    <div class="sidebar">
        <div>
            <div class="brand"><span>🛡️</span> SpiritVale 管理</div>
            <div class="nav-menu">
                <a href="/?tab=dashboard" class="nav-item {% if tab == 'dashboard' %}active{% endif %}"><span>📊</span> 分錢明細總覽</a>
                <a href="/?tab=create" class="nav-item {% if tab == 'create' %}active{% endif %}"><span>➕</span> 登記打寶項目</a>
                <a href="/?tab=pending" class="nav-item {% if tab == 'pending' %}active{% endif %}"><span>⏳</span> 待售寶物庫</a>
                <a href="/?tab=logs" class="nav-item {% if tab == 'logs' %}active{% endif %}"><span>📜</span> 修改紀錄</a>
            </div>
        </div>
        <div class="user-panel">
            {% if user %}
                <div class="user-info">登入身分：<br><b>{{ user.global_name or user.username }}</b> {% if is_admin %}<span style="color:var(--accent-gold);">(幹部)</span>{% endif %}</div>
                <a href="/logout" class="btn btn-secondary" style="width: 100%; padding: 8px; font-size: 13px;">登出系統</a>
            {% else %}
                <div class="user-info" style="margin-bottom: 12px;">尚未透過 Discord 驗證</div>
                <a href="/login" class="btn btn-discord" style="padding: 10px; font-size: 13px;">🔐 Discord 登入</a>
            {% endif %}
        </div>
    </div>

    <div class="main-content">
        <div class="top-bar">
            <h1>
                {% if tab == 'create' %}登記打寶項目
                {% elif tab == 'pending' %}待售寶物庫管理
                {% elif tab == 'logs' %}系統編輯修改紀錄
                {% else %}分錢與領取狀態總覽{% endif %}
            </h1>
        </div>

        {% if tab == 'dashboard' %}
        <div class="stats-grid">
            <div class="stat-card"><span class="stat-label">總分發紀錄筆數</span><span class="stat-value">{{ records|length }} 筆</span></div>
            <div class="stat-card"><span class="stat-label">待售寶物數量</span><span class="stat-value" style="color: var(--accent-blue);">{{ pending_count }} 件</span></div>
            <div class="stat-card"><span class="stat-label">試算表成員連線</span><span class="stat-value" style="color: var(--accent-green);">已同步 (Live)</span></div>
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
                                <form action="/toggle/{{ row[0] }}" method="POST" style="margin:0; display:inline;">
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
            <h3>
                <span>📝 填寫打寶與分紅資訊</span>
                <button type="button" class="btn btn-secondary" style="padding: 6px 12px; font-size: 12px;" onclick="copyLastForm()">📋 複製上一次表單</button>
            </h3>
            <form action="/create_loot" method="POST" id="lootForm" onsubmit="return saveFormState()">
                <div class="form-grid">
                    <div class="form-group">
                        <label>開單負責人</label>
                        <input type="text" id="leader_name" name="leader_name" value="{{ user.global_name if user and user.global_name else (user.username if user else '') }}" required placeholder="負責人名稱">
                    </div>
                    <div class="form-group">
                        <label>打寶日期</label>
                        <input type="date" id="loot_date" name="loot_date" value="{{ today }}" required>
                    </div>
                    <div class="form-group full">
                        <label>打到的物品名稱</label>
                        <input type="text" id="item_name" name="item_name" required placeholder="例如：+10 稀有防具 / 王卡">
                    </div>
                    
                    <div class="form-group full">
                        <label>參與人員 (輸入關鍵字快速搜尋並點選，點擊負號可移除)</label>
                        <div class="member-picker-box">
                            <input type="text" id="memberSearch" class="member-search-input" placeholder="🔍 搜尋試算表成員 (例如: 聖騎士、高須、死靈)..." onkeyup="filterMembers()">
                            <div class="member-suggestions" id="memberSuggestions"></div>
                        </div>
                        <div class="selected-tags" id="selectedTagsContainer">
                            <span style="color: var(--text-muted); font-size: 12px;" id="placeholderText">尚未選擇任何成員，請從上方搜尋點選...</span>
                        </div>
                        <input type="hidden" name="members" id="membersHiddenInput" required>
                    </div>

                    <div class="form-group">
                        <label>售出總金額 (若未售出填 0 則進入待售庫)</label>
                        <input type="number" id="total_price" name="total_price" value="0" required>
                    </div>
                    <div class="form-group">
                        <label>交易所手續費 (%)</label>
                        <input type="number" id="tax_rate" name="tax_rate" value="0" step="0.1">
                    </div>
                </div>
                <div style="margin-top: 25px;">
                    <button type="submit" class="btn">🚀 直接送出登記</button>
                </div>
            </form>
        </div>

        <script>
            const allMembers = {{ members_json | safe }};
            let selectedMembers = [];

            function renderSuggestions(filter = "") {
                const container = document.getElementById("memberSuggestions");
                container.innerHTML = "";
                const filtered = allMembers.filter(m => m.toLowerCase().includes(filter.toLowerCase()) && !selectedMembers.includes(m));
                
                filtered.forEach(name => {
                    const chip = document.createElement("div");
                    chip.className = "chip";
                    chip.innerText = "+ " + name;
                    chip.onclick = () => addMember(name);
                    container.appendChild(chip);
                });
            }

            function renderTags() {
                const container = document.getElementById("selectedTagsContainer");
                const hiddenInput = document.getElementById("membersHiddenInput");
                container.innerHTML = "";

                if (selectedMembers.length === 0) {
                    container.innerHTML = '<span style="color: var(--text-muted); font-size: 12px;">尚未選擇任何成員，請從上方搜尋點選...</span>';
                    hiddenInput.value = "";
                    return;
                }

                selectedMembers.forEach(name => {
                    const tag = document.createElement("div");
                    tag.className = "selected-tag";
                    tag.innerHTML = `${name} <span class="remove-btn" onclick="removeMember('${name}')">✕</span>`;
                    container.appendChild(tag);
                });

                hiddenInput.value = selectedMembers.join(", ");
            }

            function addMember(name) {
                if (!selectedMembers.includes(name)) {
                    selectedMembers.push(name);
                    renderTags();
                    filterMembers();
                }
            }

            function removeMember(name) {
                selectedMembers = selectedMembers.filter(m => m !== name);
                renderTags();
                filterMembers();
            }

            function filterMembers() {
                const query = document.getElementById("memberSearch").value;
                renderSuggestions(query);
            }

            function saveFormState() {
                const formData = {
                    item_name: document.getElementById("item_name").value,
                    tax_rate: document.getElementById("tax_rate").value,
                    members: selectedMembers
                };
                localStorage.setItem("last_loot_form", JSON.stringify(formData));
                return true;
            }

            function copyLastForm() {
                const saved = localStorage.getItem("last_loot_form");
                if (!saved) {
                    alert("找不到上一次的開單紀錄！");
                    return;
                }
                const data = JSON.parse(saved);
                document.getElementById("item_name").value = data.item_name || "";
                document.getElementById("tax_rate").value = data.tax_rate || 0;
                selectedMembers = data.members || [];
                renderTags();
                filterMembers();
            }

            renderSuggestions();
        </script>

        {% elif tab == 'pending' %}
        <div class="card">
            <h3>⏳ 待售寶物庫（尚未結算）</h3>
            <table>
                <tr>
                    <th>日期</th>
                    <th>負責人</th>
                    <th>物品名稱</th>
                    <th>參與人數</th>
                    <th>操作與編輯</th>
                </tr>
                {% for p in pending_projects %}
                <tr>
                    <td>{{ p[3] }}</td>
                    <td><b>{{ p[1] }}</b></td>
                    <td>{{ p[2] }}</td>
                    <td>{{ p[4].split(',')|length }} 人</td>
                    <td>
                        <div style="display: flex; gap: 8px; align-items: center;">
                            <form action="/activate/{{ p[0] }}" method="POST" style="display:flex; gap:6px; align-items:center;">
                                <input type="number" name="sold_price" placeholder="售出金額" required style="width: 110px; padding: 6px;">
                                <button type="submit" class="btn" style="padding: 6px 10px; font-size: 12px;">結算</button>
                            </form>
                            {% if user and (is_admin or user.username == p[1] or user.global_name == p[1]) %}
                                <a href="/edit/{{ p[0] }}" class="btn btn-secondary" style="padding: 6px 10px; font-size: 12px; text-decoration:none;">編輯</a>
                            {% endif %}
                        </div>
                    </td>
                </tr>
                {% else %}
                <tr><td colspan="5" style="text-align:center; color:var(--text-muted); padding: 40px;">目前沒有待售寶物項目。</td></tr>
                {% endfor %}
            </table>
        </div>

        {% elif tab == 'logs' %}
        <div class="card">
            <h3>📜 系統編輯修改紀錄總覽 (公開透明查閱)</h3>
            <table>
                <tr>
                    <th>專案編號</th>
                    <th>原開單負責人</th>
                    <th>物品名稱</th>
                    <th>詳細異動內容</th>
                    <th>最後修改人</th>
                    <th>修改時間</th>
                </tr>
                {% for log in edit_logs %}
                <tr>
                    <td>#{{ log[0] }}</td>
                    <td><b>{{ log[1] }}</b></td>
                    <td>{{ log[2] }}</td>
                    <td class="change-summary">{{ log[10] if log[10] else "未記錄變更細節" }}</td>
                    <td><span style="color: var(--accent-gold); font-weight: 600;">{{ log[8] }}</span></td>
                    <td>{{ log[9] }}</td>
                </tr>
                {% else %}
                <tr><td colspan="6" style="text-align:center; color:var(--text-muted); padding: 40px;">目前尚無任何修改紀錄。</td></tr>
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

    guild_members = fetch_guild_members_from_sheet()

    conn = sqlite3.connect("guild_database.db")
    cursor = conn.cursor()

    cursor.execute("SELECT id, leader_name, item_name, loot_date, members FROM loot_projects WHERE status = 'pending'")
    pending_projects = cursor.fetchall()
    pending_count = len(pending_projects)

    cursor.execute("SELECT id, member_name, item_name, total_per_person, leader_name, status FROM split_records ORDER BY id DESC")
    records = cursor.fetchall()

    try:
        cursor.execute("SELECT id, leader_name, item_name, loot_date, members, total_price, tax_rate, status, updated_by, updated_at, edit_summary FROM loot_projects WHERE updated_by IS NOT NULL ORDER BY updated_at DESC")
        edit_logs = cursor.fetchall()
    except sqlite3.OperationalError:
        edit_logs = []

    conn.close()

    members_json = json.dumps(guild_members, ensure_ascii=False)

    return render_template_string(HTML_TEMPLATE, user=user, is_admin=is_admin, tab=tab, today=today, pending_projects=pending_projects, pending_count=pending_count, records=records, edit_logs=edit_logs, members_json=members_json)

# 升級後的編輯頁面路由 (含智慧標籤點選與移除機制)
@app.route('/edit/<int:project_id>', methods=['GET', 'POST'])
def edit_project(project_id):
    user = session.get('user')
    if not user:
        return redirect(url_for('login'))

    conn = sqlite3.connect("guild_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, leader_name, item_name, loot_date, members, total_price, tax_rate, status, updated_by, updated_at FROM loot_projects WHERE id = ?", (project_id,))
    proj = cursor.fetchone()

    if not proj:
        conn.close()
        return "找不到該筆打寶記錄！", 404

    is_admin = user.get('id') in ADMIN_DISCORD_IDS
    leader_name = proj[1]

    if not is_admin and user.get('username') != leader_name and user.get('global_name') != leader_name:
        conn.close()
        return "權限不足：您不是此筆打寶記錄的開單負責人或幹部，無法進行編輯！", 403

    guild_members = fetch_guild_members_from_sheet()
    members_json = json.dumps(guild_members, ensure_ascii=False)
    
    # 取得原本已選的成員名單
    existing_members = [m.strip() for m in proj[4].replace('，', ',').split(',') if m.strip()]
    existing_members_json = json.dumps(existing_members, ensure_ascii=False)

    if request.method == 'POST':
        item_name = request.form.get('item_name')
        members_raw = request.form.get('members', '')
        tax_rate = float(request.form.get('tax_rate', 0))
        
        old_item = proj[2]
        old_tax = float(proj[6])
        
        old_members_set = set(existing_members)
        new_members_set = set([m.strip() for m in members_raw.replace('，', ',').split(',') if m.strip()])
        
        added_members = new_members_set - old_members_set
        removed_members = old_members_set - new_members_set
        
        change_messages = []
        if old_item != item_name:
            change_messages.append(f"物品更名:「{old_item}」➔「{item_name}」")
        if added_members:
            change_messages.append(f"新增人員: {', '.join(added_members)}")
        if removed_members:
            change_messages.append(f"移除人員: {', '.join(removed_members)}")
        if old_tax != tax_rate:
            change_messages.append(f"手續費: {old_tax}% ➔ {tax_rate}%")
            
        change_summary = "；".join(change_messages)
        if not change_summary:
            change_summary = "單純更新，無實質內容變更"
            
        editor_name = user.get('global_name') or user.get('username')
        now_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute("UPDATE loot_projects SET item_name = ?, members = ?, tax_rate = ?, updated_by = ?, updated_at = ?, edit_summary = ? WHERE id = ?", 
                       (item_name, members_raw, tax_rate, editor_name, now_time, change_summary, project_id))
        conn.commit()
        conn.close()
        return redirect(url_for('index', tab='pending'))

    conn.close()
    
    # 升級版的編輯頁面模板（完美整合智慧標籤選擇器）
    EDIT_TEMPLATE = """
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"><title>編輯打寶項目</title>
    <style>
        :root {
            --bg-body: #07090e;
            --bg-card: #131b2e;
            --border-color: #1e293b;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent-gold: #f59e0b;
        }
        body { background: var(--bg-body); color: var(--text-main); font-family: sans-serif; padding: 40px; }
        .card { background: var(--bg-card); border: 1px solid var(--border-color); padding: 30px; border-radius: 12px; max-width: 700px; margin: auto; box-shadow: 0 8px 24px rgba(0,0,0,0.3); }
        input, textarea { width: 100%; padding: 12px; background: #0b101d; border: 1px solid var(--border-color); color: white; border-radius: 8px; margin-top: 6px; margin-bottom: 20px; outline: none; }
        input:focus, textarea:focus { border-color: var(--accent-gold); }
        label { font-weight: 600; font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; display: block; margin-bottom: 4px; }
        
        .member-picker-box { background: #0b101d; border: 1px solid var(--border-color); border-radius: 8px; padding: 12px; margin-top: 6px; margin-bottom: 15px; }
        .member-search-input { width: 100%; margin-bottom: 10px; }
        .member-suggestions { display: flex; flex-wrap: wrap; gap: 6px; max-height: 140px; overflow-y: auto; padding: 4px; }
        .chip { background: #1e293b; border: 1px solid #334155; color: #f1f5f9; padding: 5px 10px; border-radius: 6px; font-size: 12px; cursor: pointer; transition: all 0.15s; }
        .chip:hover { background: var(--accent-gold); color: black; border-color: var(--accent-gold); }
        
        .selected-tags { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 20px; min-height: 45px; background: #07090e; padding: 10px; border-radius: 8px; border: 1px solid var(--border-color); }
        .selected-tag { background: #2563eb; color: white; padding: 5px 10px; border-radius: 6px; font-size: 12px; display: inline-flex; align-items: center; gap: 6px; }
        .selected-tag .remove-btn { cursor: pointer; font-weight: bold; color: #fca5a5; }
        .selected-tag .remove-btn:hover { color: white; }

        .btn { padding: 10px 20px; background: linear-gradient(135deg, #059669, #047857); color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; text-decoration: none; display: inline-flex; align-items: center; gap: 8px; }
        .btn:hover { filter: brightness(1.1); }
        .btn-secondary { background: #334155; }
    </style>
    </head>
    <body>
        <div class="card">
            <h2>✏️ 編輯打寶項目 (#{{ proj[0] }})</h2>
            {% if proj[8] %}
                <p style="font-size: 12px; color: #94a3b8; margin-bottom: 20px;">最後修改紀錄：由 <b>{{ proj[8] }}</b> 於 {{ proj[9] }} 進行修改</p>
            {% endif %}
            
            <form method="POST">
                <label>物品名稱</label>
                <input type="text" name="item_name" value="{{ proj[2] }}" required>
                
                <label>參與人員 (搜尋並點選加入，點擊 ✕ 移除)</label>
                <div class="member-picker-box">
                    <input type="text" id="memberSearch" class="member-search-input" placeholder="🔍 搜尋試算表成員 (例如: 聖騎士、高須、死靈)..." onkeyup="filterMembers()">
                    <div class="member-suggestions" id="memberSuggestions"></div>
                </div>
                <div class="selected-tags" id="selectedTagsContainer"></div>
                <input type="hidden" name="members" id="membersHiddenInput" required>

                <label>交易所手續費 (%)</label>
                <input type="number" name="tax_rate" value="{{ proj[6] }}" step="0.1">

                <div style="display: flex; gap: 10px; margin-top: 10px;">
                    <button type="submit" class="btn">直接儲存修改</button>
                    <a href="/?tab=pending" class="btn btn-secondary" style="line-height: normal;">取消返回</a>
                </div>
            </form>
        </div>

        <script>
            const allMembers = {{ members_json | safe }};
            let selectedMembers = {{ existing_members_json | safe }};

            function renderSuggestions(filter = "") {
                const container = document.getElementById("memberSuggestions");
                container.innerHTML = "";
                const filtered = allMembers.filter(m => m.toLowerCase().includes(filter.toLowerCase()) && !selectedMembers.includes(m));
                
                filtered.forEach(name => {
                    const chip = document.createElement("div");
                    chip.className = "chip";
                    chip.innerText = "+ " + name;
                    chip.onclick = () => addMember(name);
                    container.appendChild(chip);
                });
            }

            function renderTags() {
                const container = document.getElementById("selectedTagsContainer");
                const hiddenInput = document.getElementById("membersHiddenInput");
                container.innerHTML = "";

                if (selectedMembers.length === 0) {
                    container.innerHTML = '<span style="color: var(--text-muted); font-size: 12px;">尚未選擇任何成員...</span>';
                    hiddenInput.value = "";
                    return;
                }

                selectedMembers.forEach(name => {
                    const tag = document.createElement("div");
                    tag.className = "selected-tag";
                    tag.innerHTML = `${name} <span class="remove-btn" onclick="removeMember('${name}')">✕</span>`;
                    container.appendChild(tag);
                });

                hiddenInput.value = selectedMembers.join(", ");
            }

            function addMember(name) {
                if (!selectedMembers.includes(name)) {
                    selectedMembers.push(name);
                    renderTags();
                    filterMembers();
                }
            }

            function removeMember(name) {
                selectedMembers = selectedMembers.filter(m => m !== name);
                renderTags();
                filterMembers();
            }

            function filterMembers() {
                const query = document.getElementById("memberSearch").value;
                renderSuggestions(query);
            }

            renderTags();
            renderSuggestions();
        </script>
    </body>
    </html>
    """
    return render_template_string(EDIT_TEMPLATE, proj=proj, members_json=members_json, existing_members_json=existing_members_json)

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
        is_admin = user.get('id'] in ADMIN_DISCORD_IDS
        if is_admin or user.get('username'] == member_name or user.get('global_name') == member_name:
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
        'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'grant_type': 'authorization_code',
        'code': code, 'redirect_uri': REDIRECT_URI
    })
    
    token = resp.json().get('access_token')
    if token:
        user_resp = requests.get("https://discord.com/api/users/@me", headers={'Authorization': f'Bearer {token}'})
        session['user'] = user_resp.json()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
