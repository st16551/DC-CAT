from flask import Flask, render_template_string, request, redirect, url_for, session
import sqlite3
import requests

app = Flask(__name__)
app.secret_key = "my_guild_secret_key_abcxyz888_666"  # 隨機密鑰

# ==================== 🛠️ 請在這裡填入你的 Discord 設定 ====================
CLIENT_ID = "1549954226937929778"
CLIENT_SECRET = "Mh4hq0GCl5oWSjzHEIPQgKnIw7eddvjg"
REDIRECT_URI = "https://dc-cat.onrender.com"

# 幹部的 Discord ID 清單（擁有最高權限，可以修改任何人狀態）
# 範例: ["123456789012345678", "987654321098765432"]
ADMIN_DISCORD_IDS = [
    "407651643836858388",
]
# =========================================================================

# 網頁前端 HTML 模板
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>公會分錢與戰利品總覽</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #f4f6f9; margin: 0; padding: 20px; }
        .container { max-width: 1050px; margin: auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        h2 { color: #333; display: inline-block; }
        .user-bar { float: right; margin-top: 15px; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { padding: 12px; border: 1px solid #ddd; text-align: center; }
        th { background-color: #007bff; color: white; }
        tr:nth-child(even) { background-color: #f9f9f9; }
        .status-1 { color: green; font-weight: bold; }
        .status-0 { color: red; font-weight: bold; }
        .btn { padding: 6px 12px; text-decoration: none; border-radius: 4px; background: #28a745; color: white; border: none; cursor: pointer; font-size: 14px; }
        .btn-secondary { background: #6c757d; }
        .btn-discord { background: #5865F2; }
        .btn-disabled { background: #ccc; cursor: not-allowed; }
        .notice { background: #e2f0d9; padding: 10px; border-radius: 4px; margin-bottom: 15px; color: #385723; }
    </style>
</head>
<body>
    <div class="container">
        <div>
            <h2>💰 公會戰利品與分錢總覽</h2>
            <div class="user-bar">
                {% if user %}
                    <span>👤 歡迎，<b>{{ user.username }}</b> {% if is_admin %}(幹部){% endif %}</span>
                    <a href="/logout" class="btn btn-secondary" style="margin-left: 10px; padding: 4px 8px;">登出</a>
                {% else %}
                    <a href="/login" class="btn btn-discord">🔐 使用 Discord 登入</a>
                {% endif %}
            </div>
        </div>
        
        <div class="notice">✨ <b>規則說明：</b>任何人皆可自由檢視總表。成員僅能修改「自己的名字」之領取狀態；幹部可修改所有人。</div>
        
        <table>
            <tr>
                <th>編號</th>
                <th>成員名稱</th>
                <th>品項名稱</th>
                <th>每人分得金額</th>
                <th>發起團長</th>
                <th>目前狀態</th>
                <th>操作</th>
            </tr>
            {% for row in records %}
            <tr>
                <td>{{ row[0] }}</td>
                <td><b>{{ row[1] }}</b></td>
                <td>{{ row[2] }}</td>
                <td>{{ row[3] }}</td>
                <td>{{ row[4] }}</td>
                <td>
                    {% if row[5] == 1 %}
                        <span class="status-1">已領取</span>
                    {% else %}
                        <span class="status-0">未領取</span>
                    {% endif %}
                </td>
                <td>
                    {% if user %}
                        {# 判斷權限：如果是幹部，或者是本人（名字相同），才允許點擊修改 #}
                        {% if is_admin or user.username == row[1] or user.global_name == row[1] %}
                            <form action="/toggle/{{ row[0] }}" method="post" style="margin:0;">
                                {% if row[5] == 1 %}
                                    <button type="submit" class="btn btn-secondary">改為未領</button>
                                {% else %}
                                    <button type="submit" class="btn">設為已領</button>
                                {% endif %}
                            </form>
                        {% else %}
                            <button class="btn btn-disabled" disabled title="您只能修改自己的狀態">非本人</button>
                        {% endif %}
                    {% else %}
                        <a href="/login" class="btn btn-discord" style="padding: 4px 8px; font-size: 12px;">登入後修改</a>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </table>
    </div>
</body>
</html>
"""

# 1. 首頁（公開檢視）
@app.route('/')
def dashboard():
    user = session.get('user')
    is_admin = False
    if user and user.get('id') in ADMIN_DISCORD_IDS:
        is_admin = True
        
    conn = sqlite3.connect("guild_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, member_name, item_name, total_per_person, leader_name, status FROM split_records ORDER BY id DESC")
    records = cursor.fetchall()
    conn.close()
    
    return render_template_string(HTML_TEMPLATE, records=records, user=user, is_admin=is_admin)

# 2. 導向 Discord 登入畫面
@app.route('/login')
def login():
    discord_login_url = (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=identify"
    )
    return redirect(discord_login_url)

# 3. Discord 授權回調接收點
@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return "授權失敗，未取得 Code。", 400

    # 用 Code 交換 Access Token
    token_url = "https://discord.com/api/oauth2/token"
    payload = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    
    response = requests.post(token_url, data=payload, headers=headers)
    token_data = response.json()
    
    if 'access_token' not in token_data:
        return f"取得 Token 失敗：{token_data}", 400

    access_token = token_data['access_token']

    # 用 Access Token 取得使用者 Discord 資料
    user_url = "https://discord.com/api/users/@me"
    user_headers = {'Authorization': f'Bearer {access_token}'}
    user_response = requests.get(user_url, headers=user_headers)
    user_data = user_response.json()

    # 將使用者資訊存入 Flask Session
    session['user'] = {
        'id': user_data.get('id'),
        'username': user_data.get('username'),
        'global_name': user_data.get('global_name')
    }

    return redirect(url_for('dashboard'))

# 4. 點擊修改領取狀態（嚴格把關身分）
@app.route('/toggle/<int:record_id>', methods=['POST'])
def toggle_status(record_id):
    user = session.get('user')
    if not user:
        return redirect(url_for('login'))

    conn = sqlite3.connect("guild_database.db")
    cursor = conn.cursor()
    
    # 查詢這筆紀錄是誰的
    cursor.execute("SELECT member_name, status FROM split_records WHERE id = ?", (record_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return "找不到此筆紀錄", 404

    member_name, current_status = row
    is_admin = user.get('id') in ADMIN_DISCORD_IDS

    # 檢查權限：必須是幹部，或者登入者的使用者名稱/全域名稱剛好等於紀錄上的成員名字
    if is_admin or user.get('username') == member_name or user.get('global_name') == member_name:
        new_status = 0 if current_status == 1 else 1
        cursor.execute("UPDATE split_records SET status = ? WHERE id = ?", (new_status, record_id))
        conn.commit()
    else:
        conn.close()
        return "權限不足：您只能修改自己的領取狀態！", 403

    conn.close()
    return redirect(url_for('dashboard'))

# 5. 登出
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
