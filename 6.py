import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
import threading
import datetime
from flask import Flask, render_template_string, request, redirect, url_for, session

# ================= 基礎設定區 =================
TOKEN = os.getenv('DISCORD_TOKEN')
WEB_PASSWORD = os.getenv('WEB_PWD', 'admin888') 
MY_GUILD_ID = 1492797387008376852
BACKUP_CHANNEL_ID = 1496886906544324738
ANNOUNCE_CHANNEL_ID = 1492888316809318561 
WARN_LOG_CHANNEL_ID = 1497470602888613918 
DATA_FILE = "data.json"
# =============================================

class IntegratedBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.db = {"warn_records": {}}

    def save_data(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.db, f, ensure_ascii=False, indent=4)

    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    self.db = json.load(f)
            except: print("⚠️ 載入存檔失敗")

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
app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- 網頁 HTML ---
HTML_TPL = """
<!DOCTYPE html>
<html>
<head>
    <title>機器人管理後台</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: sans-serif; background: #2c2f33; color: white; padding: 20px; }
        .card { background: #23272a; padding: 15px; border-radius: 10px; margin-bottom: 20px; border: 1px solid #7289da; }
        input, textarea, button { width: 100%; padding: 12px; margin: 8px 0; border-radius: 5px; border: none; box-sizing: border-box; }
        button { background: #7289da; color: white; font-weight: bold; cursor: pointer; }
        .btn-backup { background: #43b581; }
        .btn-restore { background: #faa61a; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { border-bottom: 1px solid #444; padding: 10px; text-align: left; }
    </style>
</head>
<body>
    <div style="max-width: 600px; margin: auto;">
        {% if not logged_in %}
            <div class="card">
                <h1>🔑 管理員登入</h1>
                <form method="post" action="/login"><input type="password" name="pwd" placeholder="輸入密碼" required><button type="submit">登入</button></form>
            </div>
        {% else %}
            <h1>🛡️ 控制面板 <a href="/logout" style="font-size:14px; color:#f04747;">[登出]</a></h1>
            <div class="card">
                <h3>📢 全大字公告</h3>
                <form action="/announce" method="post">
                    <textarea name="content" rows="3" placeholder="輸入內容..." required></textarea>
                    <button type="submit">發送大字公告</button>
                </form>
            </div>
            <div class="card">
                <h3>💾 備份與還原</h3>
                <form action="/backup" method="post"><button type="submit" class="btn-backup">立即備份 (JSON)</button></form>
                <form action="/restore" method="post" enctype="multipart/form-data">
                    <input type="file" name="file" accept=".json" required><button type="submit" class="btn-restore">上傳 JSON 還原</button>
                </form>
            </div>
            <div class="card">
                <h3>⚠️ 警告管理</h3>
                <form action="/manage" method="post">
                    ID: <input type="text" name="uid" placeholder="成員 ID" required>
                    理由: <input type="text" name="reason" placeholder="理由" required>
                    <div style="display: flex; gap: 5px;">
                        <button type="submit" name="act" value="add">增加</button>
                        <button type="submit" name="act" value="sub" style="background:#faa61a;">減少</button>
                    </div>
                </form>
                <table>
                    <tr><th>ID</th><th>次數</th></tr>
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

# --- 網頁路由邏輯 ---
@app.route('/')
def index(): return render_template_string(HTML_TPL, db=bot.db, logged_in=session.get('user') == 'admin')

@app.route('/login', methods=['POST'])
def login():
    if request.form.get('pwd') == WEB_PASSWORD: session['user'] = 'admin'
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('user', None); return redirect(url_for('index'))

@app.route('/announce', methods=['POST'])
def web_announce():
    if session.get('user') != 'admin': return redirect(url_for('index'))
    content = request.form.get('content')
    ch = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if ch: bot.loop.create_task(ch.send(f"# 📢 公告\n# {content}"))
    return redirect(url_for('index'))

@app.route('/manage', methods=['POST'])
def web_manage():
    if session.get('user') != 'admin': return redirect(url_for('index'))
    uid, act, reason = request.form.get('uid'), request.form.get('act'), request.form.get('reason')
    recs = bot.db["warn_records"]
    if act == "add": recs[uid] = recs.get(uid, 0) + 1
    else: recs[uid] = max(0, recs.get(uid, 0) - 1)
    bot.save_data()
    # 發送 Embed 通知
    log_ch = bot.get_channel(WARN_LOG_CHANNEL_ID)
    if log_ch:
        embed = discord.Embed(title="⚠️ 警告變動 (網頁)", color=0x7289da)
        embed.add_field(name="對象", value=f"<@{uid}>")
        embed.add_field(name="理由", value=reason)
        embed.add_field(name="累計", value=f"{recs[uid]} 支")
        bot.loop.create_task(log_ch.send(embed=embed))
    return redirect(url_for('index'))

@app.route('/backup', methods=['POST'])
def web_backup():
    if session.get('user') == 'admin': bot.loop.create_task(bot.send_backup("網頁備份"))
    return redirect(url_for('index'))

@app.route('/restore', methods=['POST'])
def web_restore():
    if session.get('user') == 'admin':
        file = request.files.get('file')
        if file: bot.db = json.load(file); bot.save_data()
    return redirect(url_for('index'))

# --- Discord 指令區 ---

@bot.tree.command(name="身分組", description="領取身分組訊息")
async def roles_cmd(interaction: discord.Interaction):
    # 使用按鈕或簡單訊息回應，避免「未受回應」
    await interaction.response.send_message("🎭 **身分組領取系統**\n請點擊對應按鈕（按鈕邏輯需依需求撰寫）", ephemeral=False)

@bot.tree.command(name="警告", description="調整警告")
async def warn_cmd(interaction: discord.Interaction, 成員: discord.Member, 理由: str, 動作: str = "增加"):
    uid = str(成員.id)
    recs = bot.db["warn_records"]
    if 動作 == "增加": recs[uid] = recs.get(uid, 0) + 1
    else: recs[uid] = max(0, recs.get(uid, 0) - 1)
    bot.save_data()
    
    # 立即回應 Discord
    await interaction.response.send_message(f"✅ 已處理 {成員.mention}。理由：{理由}", ephemeral=True)
    
    # 發送嵌入訊息到日誌
    log_ch = bot.get_channel(WARN_LOG_CHANNEL_ID)
    if log_ch:
        embed = discord.Embed(title="⚠️ 警告變動 (指令)", color=0xff0000)
        embed.add_field(name="成員", value=成員.mention)
        embed.add_field(name="操作者", value=interaction.user.mention)
        embed.add_field(name="理由", value=理由)
        embed.add_field(name="累計", value=f"{recs[uid]} 支")
        await log_ch.send(embed=embed)

@bot.tree.command(name="公告", description="發送全大字公告")
async def announce_cmd(interaction: discord.Interaction, 內容: str):
    ch = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if ch:
        await ch.send(f"# 📢 公告\n# {內容}")
        await interaction.response.send_message("✅ 公告已發送", ephemeral=True)

@bot.tree.command(name="手動備份", description="備份資料")
async def backup_cmd(interaction: discord.Interaction):
    await bot.send_backup("指令手動備份")
    await interaction.response.send_message("✅ 備份檔已發出", ephemeral=True)

@bot.tree.command(name="還原數據", description="還原最新備份")
async def restore_cmd(interaction: discord.Interaction):
    ch = bot.get_channel(BACKUP_CHANNEL_ID)
    async for m in ch.history(limit=5):
        if m.attachments:
            bot.db = json.loads(await m.attachments[0].read())
            bot.save_data()
            return await interaction.response.send_message("✅ 數據已從備份還原", ephemeral=True)
    await interaction.response.send_message("❌ 找不到檔案", ephemeral=True)

if __name__ == "__main__":
    # Flask 執行在背景
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080))), daemon=True).start()
    bot.run(TOKEN)
