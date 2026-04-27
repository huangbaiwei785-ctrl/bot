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
        data = {"target_message_id": "無", "current_emoji": "✅", "warn_records": {}, "violation_records": {}}
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return data
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "violation_records" not in data: data["violation_records"] = {}
    return data

class RoleView(discord.ui.View):
    def __init__(self, emoji="✅"):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(style=discord.ButtonStyle.secondary, emoji=emoji, custom_id="role_emoji_btn"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data.get("custom_id") == "role_emoji_btn":
            role = interaction.guild.get_role(ROLE_ID)
            if not role: return await interaction.response.send_message("❌ 找不到身分組", ephemeral=True)
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role)
                await interaction.response.send_message(f"✅ 已移除身分組", ephemeral=True)
            else:
                await interaction.user.add_roles(role)
                await interaction.response.send_message(f"✅ 已領取身分組", ephemeral=True)
        return True

class IntegratedBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
        self.db = load_db()

    def save_data(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.db, f, ensure_ascii=False, indent=4)

    async def setup_hook(self):
        self.add_view(RoleView(self.db.get("current_emoji", "✅")))
        guild = discord.Object(id=MY_GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        self.auto_backup.start()

    async def send_backup(self, reason):
        ch = self.get_channel(BACKUP_CHANNEL_ID) or await self.fetch_channel(BACKUP_CHANNEL_ID)
        if ch:
            self.save_data()
            await ch.send(f"📦 **Gxyn Clan [{reason}]**", file=discord.File(DATA_FILE))

    @tasks.loop(hours=6)
    async def auto_backup(self):
        await self.wait_until_ready()
        await self.send_backup("自動備份")

bot = IntegratedBot()

# --- 處罰通知邏輯 ---
async def process_punishment(member_id: int, reason: str):
    guild = bot.get_guild(MY_GUILD_ID) or await bot.fetch_guild(MY_GUILD_ID)
    uid = str(member_id)
    
    if bot.db["warn_records"].get(uid, 0) >= 4:
        bot.db["warn_records"][uid] = 0
        bot.db["violation_records"][uid] = bot.db["violation_records"].get(uid, 0) + 1
        v_count = bot.db["violation_records"][uid]
        bot.save_data()
        
        member = guild.get_member(member_id) or await guild.fetch_member(member_id)
        log_ch = bot.get_channel(WARN_LOG_CHANNEL_ID) or await bot.fetch_channel(WARN_LOG_CHANNEL_ID)
        
        if not log_ch: return

        if v_count >= 3:
            embed = discord.Embed(title="🚫 Gxyn Clan 永久停權", color=0xff0000, timestamp=datetime.datetime.now())
            embed.add_field(name="👤 被處罰人", value=f"{member.mention if member else uid}", inline=False)
            embed.add_field(name="📝 理由", value=reason, inline=False)
            embed.add_field(name="📊 累犯次數", value=f"第 **{v_count}** 次", inline=True)
            if member: await member.ban(reason=f"累犯滿 3 次：{reason}")
            await log_ch.send(content=f"{member.mention if member else ''}", embed=embed)
        else:
            embed = discord.Embed(title="🔇 Gxyn Clan 禁言處分", color=0xffaa00, timestamp=datetime.datetime.now())
            embed.add_field(name="👤 被處罰人", value=f"{member.mention if member else uid}", inline=False)
            embed.add_field(name="📝 理由", value=reason, inline=False)
            embed.add_field(name="📈 累犯進度", value=f"第 **{v_count}** / 3 次", inline=True)
            embed.add_field(name="⏳ 懲罰", value="禁言 1 天", inline=True)
            if member: await member.timeout(datetime.timedelta(days=1), reason=f"警告滿 4 支：{reason}")
            await log_ch.send(content=f"{member.mention if member else ''}", embed=embed)

# --- Flask 網頁 (增加理由輸入框) ---
app = Flask(__name__)
app.secret_key = os.urandom(24)

@app.route('/')
def index():
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Gxyn Clan Admin</title>
        <style>
            :root { --sidebar-w: 280px; --primary: #4f46e5; --bg: #f3f4f6; }
            body { font-family: sans-serif; margin: 0; display: flex; background: var(--bg); }
            .sidebar { width: var(--sidebar-w); background: white; height: 100vh; border-right: 1px solid #e5e7eb; position: fixed; }
            .side-title { padding: 25px; font-size: 22px; font-weight: bold; color: var(--primary); border-bottom: 2px solid var(--primary); }
            .side-section { padding: 15px 20px; border-bottom: 1px solid #f3f4f6; }
            .main { margin-left: var(--sidebar-w); padding: 40px; width: 100%; box-sizing: border-box; }
            .card { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px; }
            input, textarea, button { width: 100%; padding: 10px; margin: 5px 0; border-radius: 6px; border: 1px solid #d1d5db; box-sizing: border-box; }
            button { background: var(--primary); color: white; border: none; font-weight: bold; cursor: pointer; }
            table { width: 100%; border-collapse: collapse; } th, td { padding: 12px; border-bottom: 1px solid #f3f4f6; text-align: left; }
            h3 { font-size: 0.9rem; color: #6b7280; margin-bottom: 10px; }
        </style>
    </head>
    <body>
    {% if not logged_in %}
        <div style="margin: 100px auto;" class="card"><h2>登入 Gxyn</h2><form method="post" action="/login"><input type="password" name="pwd" required><button type="submit">登入</button></form></div>
    {% else %}
        <div class="sidebar">
            <div class="side-title">Gxyn Clan</div>
            <div class="side-section">
                <h3>⚠️ 警告處置</h3>
                <form action="/quick_warn" method="post">
                    <input type="text" name="uid" placeholder="用戶 ID" required>
                    <input type="number" name="amount" value="1" min="1" title="增加數量">
                    <input type="text" name="reason" placeholder="輸入處罰理由..." required>
                    <button type="submit" name="act" value="add">增加警告 (+)</button>
                    <button type="submit" name="act" value="sub" style="background:#f59e0b;">扣除警告 (-)</button>
                </form>
            </div>
            <div class="side-section">
                <h3>📥 數據還原</h3>
                <form action="/restore" method="post" enctype="multipart/form-data"><input type="file" name="file" required><button type="submit">匯入 JSON</button></form>
            </div>
            <a href="/logout" style="display:block; padding:20px; color:red; text-decoration:none;">🚪 登出系統</a>
        </div>
        <div class="main">
            <div class="card"><h2>📢 發送全大字公告</h2><form action="/announce" method="post"><textarea name="content" placeholder="公告內容..." required></textarea><button type="submit">發送</button></form></div>
            <div class="card">
                <h2>⚠️ 警告紀錄</h2>
                <table>
                    <tr><th>用戶 ID</th><th>警告數</th><th>累犯</th></tr>
                    {% for uid, count in db.warn_records.items() %}
                    <tr><td><code>{{ uid }}</code></td><td>{{ count }}</td><td>{{ db.violation_records.get(uid, 0) }}</td></tr>
                    {% endfor %}
                </table>
            </div>
        </div>
    {% endif %}
    </body>
    </html>
    """, db=bot.db, logged_in=session.get('user') == 'admin')

@app.route('/login', methods=['POST'])
def login():
    if request.form.get('pwd') == WEB_PASSWORD: session['user'] = 'admin'
    return redirect('/')

@app.route('/logout')
def logout(): session.pop('user', None); return redirect('/')

@app.route('/quick_warn', methods=['POST'])
def quick_warn():
    uid, amount, reason = request.form.get('uid'), int(request.form.get('amount', 1)), request.form.get('reason')
    act = request.form.get('act')
    if act == "add": bot.db["warn_records"][uid] = bot.db["warn_records"].get(uid, 0) + amount
    else: bot.db["warn_records"][uid] = max(0, bot.db["warn_records"].get(uid, 0) - amount)
    bot.save_data()
    if act == "add": bot.loop.create_task(process_punishment(int(uid), reason))
    return redirect('/')

@app.route('/restore', methods=['POST'])
def web_restore():
    file = request.files.get('file')
    if file: bot.db = json.load(file); bot.save_data()
    return redirect('/')

@app.route('/announce', methods=['POST'])
def web_announce():
    ch = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if ch: bot.loop.create_task(ch.send(f"# 📢 公告\n# {request.form.get('content')}"))
    return redirect('/')

# --- Discord 指令 ---
@bot.tree.command(name="警告")
async def warn_cmd(interaction: discord.Interaction, 成員: discord.Member, 理由: str, 動作: str = "增加", 數量: int = 1):
    uid = str(成員.id)
    if 動作 == "增加": bot.db["warn_records"][uid] = bot.db["warn_records"].get(uid, 0) + 數量
    else: bot.db["warn_records"][uid] = max(0, bot.db["warn_records"].get(uid, 0) - 數量)
    bot.save_data()
    await interaction.response.send_message(f"✅ 已處理 {成員.mention}", ephemeral=True)
    if 動作 == "增加": await process_punishment(成員.id, 理由)

@bot.tree.command(name="身分組")
async def roles_cmd(interaction: discord.Interaction, 標題: str, 內容: str, 表情: str = "✅"):
    e = discord.Embed(title=標題, description=內容, color=0x4f46e5)
    await interaction.response.send_message(embed=e, view=RoleView(表情))
    msg = await interaction.original_response()
    bot.db["target_message_id"] = msg.id; bot.db["current_emoji"] = 表情; bot.save_data()

if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080))), daemon=True).start()
    bot.run(TOKEN)
