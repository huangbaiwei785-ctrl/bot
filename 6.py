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

# 初始化資料檔
def init_data():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "target_message_id": "無", 
                "current_emoji": "🤡", 
                "warn_records": {},
                "violation_records": {}
            }, f, indent=4)

init_data()

class RoleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="獲取/移除身分組", style=discord.ButtonStyle.secondary, custom_id="role_btn_final")
    async def toggle(self, interaction, button):
        role = interaction.guild.get_role(ROLE_ID)
        if not role: return await interaction.response.send_message("❌ 找不到身分組", ephemeral=True)
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"✅ 已移除：{role.name}", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"✅ 已領取：{role.name}", ephemeral=True)

class IntegratedBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
        self.db = {}

    def save_data(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.db, f, ensure_ascii=False, indent=4)

    async def setup_hook(self):
        with open(DATA_FILE, "r") as f: self.db = json.load(f)
        if "violation_records" not in self.db: self.db["violation_records"] = {}
        self.add_view(RoleView())
        guild = discord.Object(id=MY_GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        self.auto_backup.start()

    async def send_backup(self, reason):
        ch = self.get_channel(BACKUP_CHANNEL_ID)
        if ch:
            self.save_data()
            await ch.send(f"📦 **[{reason}]**", file=discord.File(DATA_FILE))

    @tasks.loop(hours=6)
    async def auto_backup(self):
        await self.wait_until_ready()
        await self.send_backup("定時自動備份")

bot = IntegratedBot()

# 懲處邏輯
async def check_punishment(member: discord.Member, reason: str):
    uid = str(member.id)
    if bot.db["warn_records"].get(uid, 0) >= 4:
        bot.db["warn_records"][uid] = 0
        bot.db["violation_records"][uid] = bot.db["violation_records"].get(uid, 0) + 1
        v_count = bot.db["violation_records"][uid]
        log_ch = bot.get_channel(WARN_LOG_CHANNEL_ID)
        if v_count >= 3:
            await member.ban(reason=f"累犯滿 3 次自動停權。事由：{reason}")
            if log_ch: await log_ch.send(f"🚫 **停權**：{member.mention} 累犯滿 3 次。")
        else:
            await member.timeout(datetime.timedelta(days=1), reason=f"警告滿 4 支自動禁言。事由：{reason}")
            if log_ch: await log_ch.send(f"🔇 **禁言**：{member.mention} 滿 4 支警告，禁言 1 天。累犯：`{v_count}/3`")
        bot.save_data()

# --- Flask 網頁 ---
app = Flask(__name__)
app.secret_key = os.urandom(24)

HTML_TPL = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Gryn Clan 管理後台</title>
    <style>
        :root { --sidebar-width: 240px; --primary: #4f46e5; --bg: #f9fafb; }
        body { font-family: sans-serif; margin: 0; display: flex; background: var(--bg); color: #1f2937; }
        .sidebar { width: var(--sidebar-width); background: white; height: 100vh; border-right: 1px solid #e5e7eb; position: fixed; display: flex; flex-direction: column; }
        .sidebar-header { padding: 25px; font-size: 20px; font-weight: bold; color: var(--primary); border-bottom: 1px solid #f3f4f6; }
        .sidebar-menu { padding: 15px; flex-grow: 1; }
        .menu-item { padding: 12px; text-decoration: none; color: #4b5563; display: block; border-radius: 8px; margin-bottom: 5px; transition: 0.2s; }
        .menu-item:hover { background: #f3f4f6; color: var(--primary); }
        .main-content { margin-left: var(--sidebar-width); padding: 40px; width: calc(100% - var(--sidebar-width)); }
        .card { background: white; padding: 25px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 25px; }
        h2 { margin-top: 0; border-left: 4px solid var(--primary); padding-left: 10px; font-size: 1.2rem; }
        input, textarea, button { width: 100%; padding: 12px; margin: 8px 0; border-radius: 6px; border: 1px solid #d1d5db; box-sizing: border-box; }
        button { background: var(--primary); color: white; border: none; font-weight: bold; cursor: pointer; }
        table { width: 100%; border-collapse: collapse; } th, td { padding: 12px; border-bottom: 1px solid #f3f4f6; text-align: left; }
    </style>
</head>
<body>
{% if not logged_in %}
    <div style="display:flex; justify-content:center; align-items:center; height:100vh; width:100%;">
        <div class="card" style="width:350px; text-align:center;">
            <h1>🔑 登入系統</h1>
            <form method="post" action="/login"><input type="password" name="pwd" required><button type="submit">登入</button></form>
        </div>
    </div>
{% else %}
    <div class="sidebar">
        <div class="sidebar-header">機器人管理</div>
        <nav class="sidebar-menu">
            <a href="/" class="menu-item">📌 系統狀態</a>
            <a href="/logout" class="menu-item" style="color:#ef4444; margin-top:20px;">🚪 登出系統</a>
        </nav>
    </div>
    <div class="main-content">
        <div class="card">
            <h2>📌 目前狀態</h2>
            <p>訊息 ID：<b>{{ db.target_message_id }}</b></p>
            <p>目前表情：<span style="font-size:24px;">{{ db.current_emoji }}</span></p>
        </div>
        <div class="card">
            <h2>📢 發送公告</h2>
            <form action="/announce" method="post"><textarea name="content" placeholder="公告內容..." required></textarea><button type="submit">發送</button></form>
        </div>
        <div class="card">
            <h2>⚠️ 警告與累犯名單</h2>
            <table>
                <tr><th>用戶 ID</th><th>警告</th><th>累犯</th></tr>
                {% for uid, count in db.warn_records.items() %}
                <tr><td><code>{{ uid }}</code></td><td>{{ count }} 支</td><td>{{ db.violation_records.get(uid, 0) }} 次</td></tr>
                {% endfor %}
            </table>
        </div>
        <div class="card">
            <h2>💾 備份管理</h2>
            <form action="/backup" method="post"><button type="submit">立即備份至 Discord</button></form>
            <form action="/restore" method="post" enctype="multipart/form-data"><input type="file" name="file" accept=".json" required><button type="submit" style="background:#f59e0b;">上傳 JSON 還原</button></form>
        </div>
    </div>
{% endif %}
</body>
</html>
"""

@app.route('/')
def index(): return render_template_string(HTML_TPL, db=bot.db, logged_in=session.get('user') == 'admin')

@app.route('/login', methods=['POST'])
def login():
    if request.form.get('pwd') == WEB_PASSWORD: session['user'] = 'admin'
    return redirect('/')

@app.route('/logout')
def logout(): session.pop('user', None); return redirect('/')

@app.route('/announce', methods=['POST'])
def web_announce():
    ch = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if ch: bot.loop.create_task(ch.send(f"# 📢 公告\n# {request.form.get('content')}"))
    return redirect('/')

@app.route('/backup', methods=['POST'])
def web_backup(): bot.loop.create_task(bot.send_backup("網頁手動備份")); return redirect('/')

@app.route('/restore', methods=['POST'])
def web_restore():
    file = request.files.get('file')
    if file: bot.db = json.load(file); bot.save_data()
    return redirect('/')

# --- Discord 指令 ---
@bot.tree.command(name="公告", description="發送全大字公告")
async def announce_cmd(interaction: discord.Interaction, 內容: str):
    ch = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if ch:
        await ch.send(f"# 📢 公告\n# {內容}")
        await interaction.response.send_message("✅ 公告已發送", ephemeral=True)

@bot.tree.command(name="身分組", description="發送領取訊息")
async def roles_cmd(interaction: discord.Interaction, 標題: str, 內容: str, 表情: str = "🤡"):
    e = discord.Embed(title=標題, description=內容, color=0x4f46e5)
    v = RoleView(); v.children[0].emoji = 表情
    await interaction.response.send_message(embed=e, view=v)
    msg = await interaction.original_response()
    bot.db["target_message_id"] = msg.id; bot.db["current_emoji"] = 表情; bot.save_data()

@bot.tree.command(name="警告", description="增加/減少警告")
async def warn_cmd(interaction: discord.Interaction, 成員: discord.Member, 理由: str, 動作: str = "增加"):
    uid = str(成員.id)
    if 動作 == "增加": bot.db["warn_records"][uid] = bot.db["warn_records"].get(uid, 0) + 1
    else: bot.db["warn_records"][uid] = max(0, bot.db["warn_records"].get(uid, 0) - 1)
    bot.save_data()
    await interaction.response.send_message(f"已處理 {成員.mention}", ephemeral=True)
    if 動作 == "增加": await check_punishment(成員, 理由)

@bot.tree.command(name="手動備份")
async def m_backup(interaction: discord.Interaction):
    await bot.send_backup("指令備份"); await interaction.response.send_message("✅ 已備份", ephemeral=True)

@bot.tree.command(name="還原數據")
async def m_restore(interaction: discord.Interaction):
    ch = bot.get_channel(BACKUP_CHANNEL_ID)
    async for m in ch.history(limit=5):
        if m.attachments:
            bot.db = json.loads(await m.attachments[0].read()); bot.save_data()
            return await interaction.response.send_message("✅ 數據已還原", ephemeral=True)
    await interaction.response.send_message("❌ 找不到檔案", ephemeral=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=port), daemon=True).start()
    bot.run(TOKEN)
