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
                "target_message_id": None, 
                "current_emoji": "🤡", 
                "warn_records": {},
                "violation_records": {}
            }, f, indent=4)

init_data()

class RoleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="獲取/移除身分組", style=discord.ButtonStyle.secondary, custom_id="role_btn_fixed")
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

# --- 懲處邏輯 ---
async def check_punishment(member: discord.Member, reason: str):
    uid = str(member.id)
    if bot.db["warn_records"].get(uid, 0) >= 4:
        bot.db["warn_records"][uid] = 0
        bot.db["violation_records"][uid] = bot.db["violation_records"].get(uid, 0) + 1
        v_count = bot.db["violation_records"][uid]
        
        log_ch = bot.get_channel(WARN_LOG_CHANNEL_ID)
        if v_count >= 3:
            await member.ban(reason=f"累犯達 3 次。最後理由：{reason}")
            if log_ch: await log_ch.send(f"🚫 **停權**：{member.mention} 累犯滿 3 次，永久封鎖。")
        else:
            await member.timeout(datetime.timedelta(days=1), reason=f"警告滿 4 支。理由：{reason}")
            if log_ch: await log_ch.send(f"🔇 **禁言**：{member.mention} 滿 4 警告，禁言 1 天。目前累犯：`{v_count}/3`")
        bot.save_data()

# --- 網頁後台 ---
app = Flask(__name__)
app.secret_key = os.urandom(24)

HTML_TPL = """
<!DOCTYPE html>
<html>
<head>
    <title>管理後台</title>
    <style>
        body { background:#2c2f33; color:white; font-family:sans-serif; padding:20px; }
        .card { background:#23272a; padding:15px; border-radius:10px; border:1px solid #7289da; margin-bottom:15px; }
        input, textarea, button { width:100%; padding:10px; margin:5px 0; border-radius:5px; border:none; box-sizing:border-box; }
        button { background:#7289da; color:white; font-weight:bold; cursor:pointer; }
        .btn-green { background:#43b581; } .btn-orange { background:#faa61a; }
        table { width:100%; border-collapse:collapse; } th, td { border-bottom:1px solid #444; padding:8px; }
    </style>
</head>
<body>
    <div style="max-width:700px; margin:auto;">
        {% if not logged_in %}
            <div class="card"><h1>🔑 登入</h1><form method="post" action="/login"><input type="password" name="pwd"><button type="submit">進入</button></form></div>
        {% else %}
            <h1>🛡️ 控制面板 <a href="/logout" style="color:#f04747; font-size:14px;">[登出]</a></h1>
            <div class="card">
                <h3>📢 發送大字公告</h3>
                <form action="/announce" method="post"><textarea name="content" required></textarea><button type="submit">發送</button></form>
            </div>
            <div class="card">
                <h3>⚠️ 警告管理</h3>
                <form action="/manage" method="post">
                    ID: <input type="text" name="uid" required>
                    理由: <input type="text" name="reason" required>
                    <div style="display:flex; gap:5px;"><button type="submit" name="act" value="add" class="btn-green">增加</button><button type="submit" name="act" value="sub" class="btn-orange">減少</button></div>
                </form>
                <table><tr><th>ID</th><th>警告</th><th>累犯</th></tr>
                    {% for uid, count in db.warn_records.items() %}
                    <tr><td>{{ uid }}</td><td>{{ count }} 支</td><td>{{ db.violation_records.get(uid, 0) }} 次</td></tr>
                    {% endfor %}
                </table>
            </div>
            <div class="card">
                <h3>💾 備份與上傳還原</h3>
                <form action="/backup" method="post"><button type="submit" class="btn-green">立即備份至 Discord</button></form>
                <form action="/restore" method="post" enctype="multipart/form-data"><input type="file" name="file" accept=".json" required><button type="submit" class="btn-orange">上傳 JSON 還原數據</button></form>
            </div>
        {% endif %}
    </div>
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

@app.route('/manage', methods=['POST'])
def web_manage():
    uid, act, reason = request.form.get('uid'), request.form.get('act'), request.form.get('reason')
    if act == "add": bot.db["warn_records"][uid] = bot.db["warn_records"].get(uid, 0) + 1
    else: bot.db["warn_records"][uid] = max(0, bot.db["warn_records"].get(uid, 0) - 1)
    bot.save_data()
    return redirect('/')

@app.route('/backup', methods=['POST'])
def web_backup(): bot.loop.create_task(bot.send_backup("網頁手動備份")); return redirect('/')

@app.route('/restore', methods=['POST'])
def web_restore():
    file = request.files.get('file')
    if file: bot.db = json.load(file); bot.save_data()
    return redirect('/')

# --- Discord 指令 ---
@bot.tree.command(name="身分組")
async def roles_cmd(interaction: discord.Interaction, 標題: str, 內容: str, 表情: str = "🤡"):
    e = discord.Embed(title=標題, description=內容, color=0x7289da)
    v = RoleView(); v.children[0].emoji = 表情
    await interaction.response.send_message(embed=e, view=v)
    msg = await interaction.original_response()
    bot.db["target_message_id"] = msg.id; bot.db["current_emoji"] = 表情; bot.save_data()

@bot.tree.command(name="警告")
async def warn_cmd(interaction: discord.Interaction, 成員: discord.Member, 理由: str, 動作: str = "增加"):
    uid = str(成員.id)
    if 動作 == "增加": bot.db["warn_records"][uid] = bot.db["warn_records"].get(uid, 0) + 1
    else: bot.db["warn_records"][uid] = max(0, bot.db["warn_records"].get(uid, 0) - 1)
    bot.save_data()
    await interaction.response.send_message(f"已處理 {成員.mention}", ephemeral=True)
    if 動作 == "增加": await check_punishment(成員, 理由)

@bot.tree.command(name="手動備份")
async def manual_backup(interaction: discord.Interaction):
    await bot.send_backup("指令手動備份")
    await interaction.response.send_message("✅ 備份已送出", ephemeral=True)

@bot.tree.command(name="還原數據")
async def manual_restore(interaction: discord.Interaction):
    ch = bot.get_channel(BACKUP_CHANNEL_ID)
    async for m in ch.history(limit=5):
        if m.attachments:
            bot.db = json.loads(await m.attachments[0].read()); bot.save_data()
            return await interaction.response.send_message("✅ 數據已還原", ephemeral=True)
    await interaction.response.send_message("❌ 找不到檔案", ephemeral=True)

if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080))), daemon=True).start()
    bot.run(TOKEN)
