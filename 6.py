import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
import threading
import datetime
from flask import Flask, render_template_string, request, redirect, url_for

# ================= 基礎設定區 =================
TOKEN = os.getenv('DISCORD_TOKEN')
WEB_PASSWORD = os.getenv('WEB_PWD', 'admin888') 
MY_GUILD_ID = 1492797387008376852
BACKUP_CHANNEL_ID = 1496886906544324738  # 備份頻道
ANNOUNCE_CHANNEL_ID = 1492909029780095200 # 公告預設發送頻道
DATA_FILE = "warn_data.json"
# =============================================

class WarnBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.warn_records = {}

    def save_data(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.warn_records, f, ensure_ascii=False, indent=4)

    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.warn_records = {str(k): int(v) for k, v in data.items()}
            except: print("⚠️ 載入存檔失敗")

    async def setup_hook(self):
        self.load_data()
        guild = discord.Object(id=MY_GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        self.auto_backup.start() # 啟動自動備份

    @tasks.loop(hours=6)
    async def auto_backup(self):
        """自動將警告數據備份到指定頻道"""
        await self.wait_until_ready()
        channel = self.get_channel(BACKUP_CHANNEL_ID)
        if channel:
            self.save_data()
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            await channel.send(f"📦 **警告系統數據自動備份**\n時間：`{timestamp}`", file=discord.File(DATA_FILE))

bot = WarnBot()
app = Flask(__name__)

# --- 網頁後台介面 ---
HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>警告與公告系統</title>
    <style>
        body { font-family: sans-serif; background: #2c2f33; color: white; padding: 20px; }
        .card { background: #23272a; padding: 20px; border-radius: 10px; margin-bottom: 20px; border: 1px solid #7289da; }
        input, textarea, button { width: 100%; padding: 10px; margin: 10px 0; border-radius: 5px; border: none; box-sizing: border-box; }
        button { background: #7289da; color: white; font-weight: bold; cursor: pointer; }
        .danger { background: #f04747; }
        table { width: 100%; margin-top: 10px; border-collapse: collapse; }
        th, td { border-bottom: 1px solid #444; padding: 8px; text-align: left; }
    </style>
</head>
<body>
    <div style="max-width: 600px; margin: auto;">
        <h1>🛡️ 管理員控制台</h1>
        
        <div class="card">
            <h2>📢 發送公告</h2>
            <form action="/announce" method="post">
                密碼: <input type="password" name="pwd" required>
                內容: <textarea name="content" rows="3" placeholder="輸入公告內容..."></textarea>
                <button type="submit">發送至公告頻道</button>
            </form>
        </div>

        <div class="card">
            <h2>⚠️ 警告管理</h2>
            <form action="/manage" method="post">
                密碼: <input type="password" name="pwd" required>
                成員 ID: <input type="text" name="uid" placeholder="貼上 ID">
                數量: <input type="number" name="amount" value="1">
                <button type="submit" name="action" value="add">增加警告</button>
                <button type="submit" name="action" value="sub" style="background: #faa61a;">減少警告</button>
                <button type="submit" name="action" value="clear" class="danger">清除該員紀錄</button>
            </form>
        </div>

        <div class="card">
            <h3>📊 目前統計</h3>
            <table>
                <tr><th>成員 ID</th><th>警告數</th></tr>
                {% for uid, count in warns.items() %}
                <tr><td>{{ uid }}</td><td>{{ count }}</td></tr>
                {% endfor %}
            </table>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_PAGE, warns=bot.warn_records)

@app.route('/manage', methods=['POST'])
def manage():
    if request.form.get('pwd') != WEB_PASSWORD: return "密碼錯誤", 403
    uid, amount, action = request.form.get('uid'), int(request.form.get('amount', 1)), request.form.get('action')
    if uid:
        if action == "add": bot.warn_records[uid] = bot.warn_records.get(uid, 0) + amount
        elif action == "sub": bot.warn_records[uid] = max(0, bot.warn_records.get(uid, 0) - amount)
        elif action == "clear": bot.warn_records.pop(uid, None)
        bot.save_data()
    return redirect(url_for('index'))

@app.route('/announce', methods=['POST'])
def announce():
    if request.form.get('pwd') != WEB_PASSWORD: return "密碼錯誤", 403
    content = request.form.get('content')
    if content:
        channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
        if channel:
            bot.loop.create_task(channel.send(f"📢 **【公告】**\n{content}"))
    return redirect(url_for('index'))

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- Discord 指令 ---
@bot.tree.command(name="警告", description="調整警告支數")
@app_commands.describe(動作="add/sub/clear", 數量="調整支數")
@app_commands.choices(動作=[
    app_commands.Choice(name="增加", value="add"),
    app_commands.Choice(name="減少", value="sub"),
    app_commands.Choice(name="清除", value="clear")
])
async def warn_cmd(interaction: discord.Interaction, 成員: discord.Member, 動作: str, 數量: int = 1):
    uid = str(成員.id)
    if 動作 == "add": bot.warn_records[uid] = bot.warn_records.get(uid, 0) + 數量
    elif 動作 == "sub": bot.warn_records[uid] = max(0, bot.warn_records.get(uid, 0) - 數量)
    else: bot.warn_records.pop(uid, None)
    bot.save_data()
    await interaction.response.send_message(f"✅ 更新成功。目前累計：`{bot.warn_records.get(uid, 0)}` 支")

if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    bot.run(TOKEN)
