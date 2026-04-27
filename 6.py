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

def load_db():
    if not os.path.exists(DATA_FILE):
        data = {"target_message_id": "無", "current_emoji": "🤡", "warn_records": {}, "violation_records": {}}
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return data
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "violation_records" not in data: data["violation_records"] = {}
        if "warn_records" not in data: data["warn_records"] = {}
        return data
    except:
        return {"target_message_id": "無", "current_emoji": "🤡", "warn_records": {}, "violation_records": {}}

class RoleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="獲取/移除身分組", style=discord.ButtonStyle.secondary, custom_id="role_btn_v4")
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
        self.db = load_db()

    def save_data(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.db, f, ensure_ascii=False, indent=4)

    async def setup_hook(self):
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
        await self.send_backup("自動備份")

bot = IntegratedBot()

# 核心懲處邏輯
async def check_punishment(member_id: int, reason: str, guild: discord.Guild):
    uid = str(member_id)
    if bot.db["warn_records"].get(uid, 0) >= 4:
        bot.db["warn_records"][uid] = 0
        bot.db["violation_records"][uid] = bot.db["violation_records"].get(uid, 0) + 1
        v_count = bot.db["violation_records"][uid]
        
        member = guild.get_member(member_id)
        log_ch = bot.get_channel(WARN_LOG_CHANNEL_ID)
        
        if v_count >= 3:
            if member: await member.ban(reason=f"累犯滿 3 次。理由：{reason}")
            if log_ch: await log_ch.send(f"🚫 **停權**：用戶 ID `{uid}` 累犯達標。")
        else:
            if member: await member.timeout(datetime.timedelta(days=1), reason=f"滿 4 警告。理由：{reason}")
            if log_ch: await log_ch.send(f"🔇 **禁言**：用戶 ID `{uid}` 禁言 1 天 (累犯 {v_count}/3)。")
        bot.save_data()

# --- Flask 網頁介面 (側邊欄加強版) ---
app = Flask(__name__)
app.secret_key = os.urandom(24)

HTML_TPL = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Gryn Clan Admin</title>
    <style>
        :root { --sidebar-w: 260px; --primary: #4f46e5; --bg: #f3f4f6; }
        body { font-family: sans-serif; margin: 0; display: flex; background: var(--bg); color: #1f2937; }
        .sidebar { width: var(--sidebar-w); background: white; height: 100vh; border-right: 1px solid #e5e7eb; position: fixed; display: flex; flex-direction: column; }
        .side-title { padding: 25px; font-size: 20px; font-weight: bold; color: var(--primary); border-bottom: 1px solid #f3f4f6; }
        .side-section { padding: 20px; border-bottom: 1px solid #f3f4f6; }
        .side-section h3 { font-size: 0.9rem; margin-bottom: 10px; color: #6b7280; }
        .main { margin-left: var(--sidebar-w); padding: 40px; width: 100%; box-sizing: border-box; }
        .card { background: white; padding: 25px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 25px; }
        h2 { margin: 0 0 15px 0; font-size: 1.1rem; color: #111827; }
        textarea, input, button { width: 100%; padding: 10px; margin: 5px 0; border-radius: 6px; border: 1px solid #d1d5db; box-sizing: border-box; }
        button { background: var(--primary); color: white; border: none; font-weight: bold; cursor: pointer; transition: 0.2s; }
        button:hover { opacity: 0.8; }
        .btn-orange { background: #f59e0b; }
        table { width: 100%; border-collapse: collapse; } th, td { padding: 12px; border-bottom: 1px solid #f3f4f6; text-align: left; }
    </style>
</head>
<body>
{% if not logged_in %}
    <div style="display:flex; justify-content:center; align-items:center; height:100vh; width:100%;">
        <div class="card" style="width:320px; text-align:center;">
            <h2>管理員登入</h2>
            <form method="post" action="/login"><input type="password" name="pwd" required><button type="submit">登入</button></form>
        </div>
    </div>
{% else %}
    <div class="sidebar">
        <div class="side-title">Gryn Admin</div>
        
        <div class="side-section">
            <h3>⚠️ 快速調整警告</h3>
            <form action="/quick_warn" method="post">
                <input type="text" name="uid" placeholder="用戶 ID" required>
                <input type="number" name="amount" value="1" min="1" placeholder="數量">
                <button type="submit" name="act" value="add">增加 (+)</button>
                <button type="submit" name="act" value="sub" class="btn-orange">減少 (-)</button>
            </form>
        </div>
        
        <div style="flex-grow:1;">
            <a href="/" style="padding:15px 25px; text-decoration:none; color:#4b5563; display:block;">🏠 系統首頁</a>
        </div>
        <a href="/logout" style="padding:15px 25px; text-decoration:none; color:#ef4444; border-top:1px solid #f3f4f6;">🚪 登出系統</a>
    </div>

    <div class="main">
        <div class="card">
            <h2>📌 目前狀態</h2>
            <p>身分組訊息 ID: <b>{{ db.target_message_id }}</b> | 按鈕表情: <span style="font-size:24px;">{{ db.current_emoji }}</span></p>
        </div>
        <div class="card">
            <h2>📢 發送公告</h2>
            <form action="/announce" method="post"><textarea name="content" placeholder="輸入公告內容..." required></textarea><button type="submit">發送大字公告</button></form>
        </div>
        <div class="card">
            <h2>⚠️ 警告紀錄名單</h2>
            <table>
                <tr><th>用戶 ID</th><th>警告數</th><th>累犯次數</th></tr>
                {% for uid, count in db.warn_records.items() %}
                <tr><td><code>{{ uid }}</code></td><td><b>{{ count }}</b> 支</td><td>{{ db.violation_records.get(uid, 0) }} 次</td></tr>
                {% endfor %}
            </table>
        </div>
        <div class="card">
            <h2>💾 數據管理</h2>
            <form action="/backup" method="post"><button type="submit">發送備份檔案</button></form>
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

@app.route('/quick_warn', methods=['POST'])
def quick_warn():
    uid = request.form.get('uid')
    amount = int(request.form.get('amount', 1))
    act = request.form.get('act')
    
    if act == "add":
        bot.db["warn_records"][uid] = bot.db["warn_records"].get(uid, 0) + amount
    else:
        bot.db["warn_records"][uid] = max(0, bot.db["warn_records"].get(uid, 0) - amount)
    
    bot.save_data()
    # 觸發懲處檢查
    guild = bot.get_guild(MY_GUILD_ID)
    if act == "add" and guild:
        bot.loop.create_task(check_punishment(int(uid), "網頁後台調整", guild))
    return redirect('/')

@app.route('/announce', methods=['POST'])
def web_announce():
    ch = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if ch: bot.loop.create_task(ch.send(f"# 📢 公告\n# {request.form.get('content')}"))
    return redirect('/')

@app.route('/backup', methods=['POST'])
def web_backup(): bot.loop.create_task(bot.send_backup("網頁手動備份")); return redirect('/')

# --- Discord 指令 ---

@bot.tree.command(name="警告", description="調整成員警告支數")
async def warn_cmd(interaction: discord.Interaction, 成員: discord.Member, 理由: str, 動作: str = "增加", 數量: int = 1):
    uid = str(成員.id)
    if 動作 == "增加":
        bot.db["warn_records"][uid] = bot.db["warn_records"].get(uid, 0) + 數量
    else:
        bot.db["warn_records"][uid] = max(0, bot.db["warn_records"].get(uid, 0) - 數量)
    
    bot.save_data()
    await interaction.response.send_message(f"✅ 已處理 {成員.mention} (調整數量: {數量})", ephemeral=True)
    if 動作 == "增加":
        await check_punishment(成員.id, 理由, interaction.guild)

@bot.tree.command(name="公告")
async def announce_cmd(interaction, 內容: str):
    ch = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if ch: await ch.send(f"# 📢 公告\n# {內容}"); await interaction.response.send_message("✅ 已發送", ephemeral=True)

@bot.tree.command(name="身分組")
async def roles_cmd(interaction, 標題: str, 內容: str, 表情: str = "🤡"):
    e = discord.Embed(title=標題, description=內容, color=0x4f46e5)
    v = RoleView(); v.children[0].emoji = 表情
    await interaction.response.send_message(embed=e, view=v)
    msg = await interaction.original_response()
    bot.db["target_message_id"] = msg.id; bot.db["current_emoji"] = 表情; bot.save_data()

if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080))), daemon=True).start()
    bot.run(TOKEN)
