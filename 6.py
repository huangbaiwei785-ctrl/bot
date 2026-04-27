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
ROLE_ID = 1492939910641090710 
# =============================================

# 自動初始化資料格式
def init_data():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({"target_message_id": None, "current_emoji": "🤡", "warn_records": {}}, f, indent=4)

init_data()

class RoleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="獲取/移除身分組", style=discord.ButtonStyle.secondary, custom_id="role_btn")
    async def toggle(self, interaction, button):
        role = interaction.guild.get_role(ROLE_ID)
        if not role: return await interaction.response.send_message("❌ 找不到身分組", ephemeral=True)
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"✅ 已移除身分組：{role.name}", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"✅ 已領取身分組：{role.name}", ephemeral=True)

class IntegratedBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
        self.db = {}

    def save_data(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.db, f, ensure_ascii=False, indent=4)

    async def setup_hook(self):
        with open(DATA_FILE, "r") as f: self.db = json.load(f)
        self.add_view(RoleView()) # 註冊持久化按鈕
        guild = discord.Object(id=MY_GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        self.auto_backup.start()

    @tasks.loop(hours=6)
    async def auto_backup(self):
        await self.wait_until_ready()
        await self.send_backup("系統定時自動備份")

    async def send_backup(self, reason):
        ch = self.get_channel(BACKUP_CHANNEL_ID)
        if ch:
            self.save_data()
            await ch.send(f"📦 **[{reason}]**\n時間：`{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`", file=discord.File(DATA_FILE))

bot = IntegratedBot()
app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- 控制面板 HTML (含檔案上傳功能) ---
HTML_TPL = """
<!DOCTYPE html>
<html>
<head>
    <title>管理後台</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: sans-serif; background: #2c2f33; color: white; padding: 20px; }
        .card { background: #23272a; padding: 15px; border-radius: 10px; margin-bottom: 15px; border: 1px solid #7289da; }
        input, textarea, button { width: 100%; padding: 10px; margin: 5px 0; border-radius: 5px; border: none; box-sizing: border-box; }
        button { background: #7289da; color: white; font-weight: bold; cursor: pointer; }
        .btn-green { background: #43b581; } .btn-orange { background: #faa61a; }
        table { width: 100%; margin-top: 10px; border-collapse: collapse; }
        th, td { border-bottom: 1px solid #444; padding: 8px; text-align: left; }
    </style>
</head>
<body>
    <div style="max-width: 600px; margin: auto;">
        {% if not logged_in %}
            <div class="card"><h1>🔑 登入</h1><form method="post" action="/login"><input type="password" name="pwd" placeholder="密碼" required><button type="submit">登入</button></form></div>
        {% else %}
            <h1>🛡️ 控制面板 <a href="/logout" style="color:#f04747; font-size:14px;">[登出]</a></h1>
            
            <div class="card">
                <h3>📢 全大字公告</h3>
                <form action="/announce" method="post"><textarea name="content" placeholder="公告內容..." required></textarea><button type="submit">發送大字公告</button></form>
            </div>

            <div class="card">
                <h3>💾 備份與還原</h3>
                <form action="/backup" method="post"><button type="submit" class="btn-green">立即手動備份至 Discord</button></form>
                <hr style="border: 0.5px solid #444; margin: 15px 0;">
                <form action="/restore_file" method="post" enctype="multipart/form-data">
                    <label>上傳備份檔 (JSON):</label>
                    <input type="file" name="file" accept=".json" required>
                    <button type="submit" class="btn-orange">上傳並還原數據</button>
                </form>
            </div>

            <div class="card">
                <h3>⚠️ 警告管理</h3>
                <form action="/manage" method="post">
                    ID: <input type="text" name="uid" placeholder="成員 ID" required>
                    理由: <input type="text" name="reason" placeholder="理由" required>
                    <div style="display:flex; gap:5px;">
                        <button type="submit" name="act" value="add" class="btn-green">增加 (+)</button>
                        <button type="submit" name="act" value="sub" class="btn-orange">減少 (-)</button>
                    </div>
                </form>
                <table><tr><th>用戶 ID</th><th>次數</th></tr>
                    {% for uid, count in db.warn_records.items() %}
                    <tr><td>{{ uid }}</td><td>{{ count }} 支</td></tr>
                    {% endfor %}
                </table>
            </div>

            <div class="card">
                <h3>ℹ️ 身分組訊息資訊</h3>
                <p>訊息 ID: <code>{{ db.target_message_id }}</code></p>
                <p>目前表情: <code>{{ db.current_emoji }}</code></p>
            </div>
        {% endif %}
    </div>
</body>
</html>
"""

# --- 網頁路由 ---
@app.route('/')
def index(): return render_template_string(HTML_TPL, db=bot.db, logged_in=session.get('user') == 'admin')

@app.route('/login', methods=['POST'])
def login():
    if request.form.get('pwd') == WEB_PASSWORD: session['user'] = 'admin'
    return redirect(url_for('index'))

@app.route('/logout')
def logout(): session.pop('user', None); return redirect(url_for('index'))

@app.route('/restore_file', methods=['POST'])
def web_restore_file():
    if session.get('user') != 'admin': return redirect(url_for('index'))
    file = request.files.get('file')
    if file and file.filename.endswith('.json'):
        bot.db = json.load(file)
        bot.save_data()
    return redirect(url_for('index'))

@app.route('/announce', methods=['POST'])
def web_announce():
    content = request.form.get('content')
    ch = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if ch: bot.loop.create_task(ch.send(f"# 📢 公告\n# {content}"))
    return redirect(url_for('index'))

@app.route('/manage', methods=['POST'])
def web_manage():
    uid, act, reason = request.form.get('uid'), request.form.get('act'), request.form.get('reason')
    recs = bot.db["warn_records"]
    if act == "add": recs[uid] = recs.get(uid, 0) + 1
    else: recs[uid] = max(0, recs.get(uid, 0) - 1)
    bot.save_data()
    log_ch = bot.get_channel(WARN_LOG_CHANNEL_ID)
    if log_ch:
        e = discord.Embed(title="⚠️ 警告變動 (網頁)", color=0x7289da)
        e.add_field(name="對象", value=f"<@{uid}>"); e.add_field(name="理由", value=reason); e.add_field(name="累計", value=f"{recs[uid]} 支")
        bot.loop.create_task(log_ch.send(embed=e))
    return redirect(url_for('index'))

@app.route('/backup', methods=['POST'])
def web_backup():
    bot.loop.create_task(bot.send_backup("網頁手動備份"))
    return redirect(url_for('index'))

# --- Discord 指令區 ---
@bot.tree.command(name="手動備份", description="立即將數據備份至 Discord 頻道")
async def backup_cmd(interaction: discord.Interaction):
    await bot.send_backup("指令手動備份")
    await interaction.response.send_message("✅ 備份完成！檔案已送至日誌頻道。", ephemeral=True)

@bot.tree.command(name="還原數據", description="從日誌頻道最後一個備份檔還原數據")
async def restore_cmd(interaction: discord.Interaction):
    ch = bot.get_channel(BACKUP_CHANNEL_ID)
    async for m in ch.history(limit=10):
        if m.attachments:
            content = await m.attachments[0].read()
            bot.db = json.loads(content)
            bot.save_data()
            return await interaction.response.send_message("✅ 數據已成功從 Discord 備份還原！", ephemeral=True)
    await interaction.response.send_message("❌ 找不到有效的備份檔案。", ephemeral=True)

@bot.tree.command(name="身分組", description="發送身分組領取嵌入訊息")
async def roles_cmd(interaction: discord.Interaction, 標題: str, 內容: str, 表情: str = "🤡"):
    e = discord.Embed(title=標題, description=內容, color=0x7289da)
    v = RoleView(); v.children[0].emoji = 表情
    await interaction.response.send_message(embed=e, view=v)
    msg = await interaction.original_response()
    bot.db["target_message_id"] = msg.id; bot.db["current_emoji"] = 表情; bot.save_data()

@bot.tree.command(name="警告", description="調整成員警告支數")
async def warn_cmd(interaction: discord.Interaction, 成員: discord.Member, 理由: str, 動作: str = "增加"):
    uid = str(成員.id)
    if 動作 == "增加": bot.db["warn_records"][uid] = bot.db["warn_records"].get(uid, 0) + 1
    else: bot.db["warn_records"][uid] = max(0, bot.db["warn_records"].get(uid, 0) - 1)
    bot.save_data()
    await interaction.response.send_message(f"✅ 已處理 {成員.mention}。理由：{理由}", ephemeral=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=port), daemon=True).start()
    bot.run(TOKEN)
