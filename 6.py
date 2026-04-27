import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
import threading
import datetime
import io
from flask import Flask, render_template_string, request, redirect, url_for, session

# ================= 基礎設定區 =================
TOKEN = os.getenv('DISCORD_TOKEN')
WEB_PASSWORD = os.getenv('WEB_PWD', 'admin888') 
MY_GUILD_ID = 1492797387008376852
BACKUP_CHANNEL_ID = 1496886906544324738  
ANNOUNCE_CHANNEL_ID = 1492909029780095200 
DATA_FILE = "data.json"
# =============================================

class IntegratedBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.db = {"warn_records": {}, "target_message_id": None, "current_emoji": "🤡"}

    def save_data(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.db, f, ensure_ascii=False, indent=4)

    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    self.db = json.load(f)
            except: print("⚠️ 載入失敗")

    async def setup_hook(self):
        self.load_data()
        guild = discord.Object(id=MY_GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        self.auto_backup.start()

    @tasks.loop(hours=6)
    async def auto_backup(self):
        await self.wait_until_ready()
        await self.send_backup("系統定時自動備份")

    async def send_backup(self, reason):
        channel = self.get_channel(BACKUP_CHANNEL_ID)
        if channel:
            self.save_data()
            now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            await channel.send(f"📦 **[{reason}]**\n時間：`{now}`", file=discord.File(DATA_FILE))

bot = IntegratedBot()

# --- Flask 網頁後台 (免重複輸密碼版) ---
app = Flask(__name__)
app.secret_key = os.urandom(24) # Session 加密密鑰

HTML_TPL = """
<!DOCTYPE html>
<html>
<head>
    <title>機器人管理後台</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: sans-serif; background: #2c2f33; color: white; padding: 20px; }
        .card { background: #23272a; padding: 15px; border-radius: 10px; margin-bottom: 20px; border: 1px solid #7289da; }
        input, textarea, button { width: 100%; padding: 10px; margin: 8px 0; border-radius: 5px; border: none; box-sizing: border-box; }
        button { background: #7289da; color: white; font-weight: bold; cursor: pointer; }
        .btn-backup { background: #43b581; }
        .btn-restore { background: #faa61a; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { border-bottom: 1px solid #444; padding: 8px; text-align: left; }
    </style>
</head>
<body>
    <div style="max-width: 600px; margin: auto;">
        {% if not logged_in %}
            <div class="card">
                <h1>🔑 管理員登入</h1>
                <form method="post" action="/login">
                    <input type="password" name="pwd" placeholder="輸入管理密碼" required>
                    <button type="submit">登入</button>
                </form>
            </div>
        {% else %}
            <h1>🛡️ 機器人控制面板 <a href="/logout" style="font-size:14px; color:#f04747;">[登出]</a></h1>
            
            <div class="card">
                <h3>📢 發送公告</h3>
                <form action="/announce" method="post">
                    <textarea name="content" rows="2" placeholder="輸入公告內容..." required></textarea>
                    <button type="submit">發送至公告頻道</button>
                </form>
            </div>

            <div class="card">
                <h3>💾 備份與還原</h3>
                <form action="/backup" method="post"><button type="submit" class="btn-backup">立即手動備份到 Discord</button></form>
                <hr style="border: 0.5px solid #444;">
                <form action="/restore" method="post" enctype="multipart/form-data">
                    還原檔案: <input type="file" name="file" accept=".json" required>
                    <button type="submit" class="btn-restore">上傳並覆蓋現有數據</button>
                </form>
            </div>

            <div class="card">
                <h3>⚠️ 警告管理</h3>
                <form action="/manage" method="post">
                    ID: <input type="text" name="uid" placeholder="ID">
                    數量: <input type="number" name="amount" value="1">
                    <div style="display: flex; gap: 5px;">
                        <button type="submit" name="act" value="add">增加</button>
                        <button type="submit" name="act" value="sub" style="background:#faa61a;">減少</button>
                    </div>
                </form>
                <table>
                    <tr><th>ID</th><th>警告支數</th></tr>
                    {% for uid, count in db.warn_records.items() %}
                    <tr><td>{{ uid }}</td><td>{{ count }}</td></tr>
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
    return render_template_string(HTML_TPL, db=bot.db, logged_in=session.get('user') == 'admin')

@app.route('/login', methods=['POST'])
def login():
    if request.form.get('pwd') == WEB_PASSWORD:
        session['user'] = 'admin'
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))

@app.route('/manage', methods=['POST'])
def web_manage():
    if session.get('user') != 'admin': return redirect(url_for('index'))
    uid, amount, act = request.form.get('uid'), int(request.form.get('amount', 1)), request.form.get('act')
    if uid:
        recs = bot.db["warn_records"]
        if act == "add": recs[uid] = recs.get(uid, 0) + amount
        elif act == "sub": recs[uid] = max(0, recs.get(uid, 0) - amount)
        bot.save_data()
    return redirect(url_for('index'))

@app.route('/announce', methods=['POST'])
def web_announce():
    if session.get('user') != 'admin': return redirect(url_for('index'))
    content = request.form.get('content')
    if content:
        ch = bot.get_channel(ANNOUNCE_CHANNEL_ID)
        if ch: bot.loop.create_task(ch.send(f"📢 **公告**\n{content}"))
    return redirect(url_for('index'))

@app.route('/backup', methods=['POST'])
def web_backup():
    if session.get('user') != 'admin': return redirect(url_for('index'))
    bot.loop.create_task(bot.send_backup("管理員網頁手動備份"))
    return "✅ 備份成功！<a href='/'>返回</a>"

@app.route('/restore', methods=['POST'])
def web_restore():
    if session.get('user') != 'admin': return redirect(url_for('index'))
    file = request.files.get('file')
    if file and file.filename.endswith('.json'):
        bot.db = json.load(file)
        bot.save_data()
        return "✅ 還原成功！<a href='/'>返回</a>"
    return "❌ 檔案不正確"

# --- Discord 指令區 ---

@bot.tree.command(name="警告", description="調整成員警告支數")
async def warn_cmd(interaction: discord.Interaction, 成員: discord.Member, 動作: str, 數量: int = 1):
    uid = str(成員.id)
    if 動作 == "增加": bot.db["warn_records"][uid] = bot.db["warn_records"].get(uid, 0) + 數量
    elif 動作 == "減少": bot.db["warn_records"][uid] = max(0, bot.db["warn_records"].get(uid, 0) - 數量)
    bot.save_data()
    await interaction.response.send_message(f"✅ 更新成功。目前累計：`{bot.db['warn_records'].get(uid, 0)}` 支")

@bot.tree.command(name="公告", description="發送公告至指定頻道")
@app_commands.default_permissions(administrator=True)
async def announce_cmd(interaction: discord.Interaction, 內容: str):
    channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if channel:
        await channel.send(f"📢 **公告**\n{內容}")
        await interaction.response.send_message("✅ 公告已發送", ephemeral=True)

@bot.tree.command(name="手動備份", description="立即將 data.json 備份到 Discord 頻道")
@app_commands.default_permissions(administrator=True)
async def backup_cmd(interaction: discord.Interaction):
    await bot.send_backup("管理員指令手動備份")
    await interaction.response.send_message("✅ 備份檔案已發送到日誌頻道", ephemeral=True)

@bot.tree.command(name="還原數據", description="從最後一則備份檔案中還原數據")
@app_commands.default_permissions(administrator=True)
async def restore_cmd(interaction: discord.Interaction):
    channel = bot.get_channel(BACKUP_CHANNEL_ID)
    async for message in channel.history(limit=5):
        if message.attachments:
            file = message.attachments[0]
            if file.filename.endswith('.json'):
                content = await file.read()
                bot.db = json.loads(content)
                bot.save_data()
                return await interaction.response.send_message("✅ 成功從 Discord 備份還原最新數據！")
    await interaction.response.send_message("❌ 找不到有效的備份檔案")

if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080))), daemon=True).start()
    bot.run(TOKEN)
