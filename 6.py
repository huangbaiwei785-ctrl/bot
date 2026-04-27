import discord
from discord.ext import commands, tasks
import json
import os
import threading
import datetime
from flask import Flask, render_template_string, request, redirect, session

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
        data = {"target_message_id": None, "current_emoji": "✅", "warn_records": {}, "violation_records": {}}
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return data
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "violation_records" not in data: data["violation_records"] = {}
    return data

class IntegratedBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
        self.db = load_db()

    def save_data(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.db, f, ensure_ascii=False, indent=4)

    async def setup_hook(self):
        guild = discord.Object(id=MY_GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        self.auto_backup.start()

    # --- 反應領取身分組邏輯 ---
    async def on_raw_reaction_add(self, payload):
        if payload.message_id == self.db.get("target_message_id") and str(payload.emoji) == self.db.get("current_emoji"):
            guild = self.get_guild(payload.guild_id)
            role = guild.get_role(ROLE_ID)
            member = guild.get_member(payload.user_id)
            if role and member and not member.bot:
                await member.add_roles(role)

    async def on_raw_reaction_remove(self, payload):
        if payload.message_id == self.db.get("target_message_id") and str(payload.emoji) == self.db.get("current_emoji"):
            guild = self.get_guild(payload.guild_id)
            role = guild.get_role(ROLE_ID)
            member = guild.get_member(payload.user_id)
            if role and member and not member.bot:
                await member.remove_roles(role)

    # --- 備份功能 ---
    async def send_backup(self, reason):
        ch = self.get_channel(BACKUP_CHANNEL_ID) or await self.fetch_channel(BACKUP_CHANNEL_ID)
        if ch:
            self.save_data()
            await ch.send(f"📦 **Gxyn Clan [{reason}]** (時間: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')})", file=discord.File(DATA_FILE))

    @tasks.loop(hours=6)
    async def auto_backup(self):
        await self.wait_until_ready()
        await self.send_backup("自動備份")

bot = IntegratedBot()

# --- 核心通知與處罰邏輯 ---
async def process_warn_and_punishment(member_id: int, reason: str):
    guild = bot.get_guild(MY_GUILD_ID) or await bot.fetch_guild(MY_GUILD_ID)
    uid = str(member_id)
    log_ch = bot.get_channel(WARN_LOG_CHANNEL_ID) or await bot.fetch_channel(WARN_LOG_CHANNEL_ID)
    member = guild.get_member(member_id) or await guild.fetch_member(member_id)
    
    if not log_ch: return

    current_warns = bot.db["warn_records"].get(uid, 0)

    # 1. 如果警告不滿 4 支，發送藍色紀錄通知
    if current_warns < 4:
        embed = discord.Embed(title="⚠️ Gxyn Clan 警告紀錄", color=0x3498db, timestamp=datetime.datetime.now())
        embed.add_field(name="👤 被處罰人", value=f"{member.mention if member else uid}", inline=False)
        embed.add_field(name="📝 理由", value=reason, inline=False)
        embed.add_field(name="🔢 目前警告數", value=f"**{current_warns}** / 4", inline=True)
        await log_ch.send(content=f"{member.mention if member else ''}", embed=embed)
    
    # 2. 如果警告滿 4 支，觸發處罰邏輯
    else:
        bot.db["warn_records"][uid] = 0 # 歸零
        bot.db["violation_records"][uid] = bot.db["violation_records"].get(uid, 0) + 1
        v_count = bot.db["violation_records"][uid]
        bot.save_data()

        if v_count >= 3:
            embed = discord.Embed(title="🚫 Gxyn Clan 永久停權處分", color=0xff0000, timestamp=datetime.datetime.now())
            embed.add_field(name="👤 被處罰人", value=f"{member.mention if member else uid}", inline=False)
            embed.add_field(name="📝 理由", value=reason, inline=False)
            embed.add_field(name="📊 累犯紀錄", value=f"已達 3 次", inline=True)
            if member: await member.ban(reason=f"累犯滿 3 次：{reason}")
            await log_ch.send(content=f"{member.mention if member else ''}", embed=embed)
        else:
            embed = discord.Embed(title="🔇 Gxyn Clan 滿額禁言處置", color=0xffaa00, timestamp=datetime.datetime.now())
            embed.add_field(name="👤 被處罰人", value=f"{member.mention if member else uid}", inline=False)
            embed.add_field(name="📝 理由", value=reason, inline=False)
            embed.add_field(name="📈 累犯進度", value=f"第 {v_count} / 3 次", inline=True)
            embed.add_field(name="⏳ 懲罰", value="禁言 1 天並警告歸零", inline=False)
            if member: await member.timeout(datetime.timedelta(days=1), reason=f"警告滿 4 支：{reason}")
            await log_ch.send(content=f"{member.mention if member else ''}", embed=embed)

# --- Flask 網頁 ---
app = Flask(__name__)
app.secret_key = os.urandom(24)

@app.route('/')
def index():
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>Gxyn Clan Admin</title>
        <style>
            :root { --sidebar-w: 280px; --primary: #4f46e5; --bg: #f3f4f6; }
            body { font-family: sans-serif; margin: 0; display: flex; background: var(--bg); }
            .sidebar { width: var(--sidebar-w); background: white; height: 100vh; border-right: 1px solid #e5e7eb; position: fixed; }
            .main { margin-left: var(--sidebar-w); padding: 40px; width: 100%; box-sizing: border-box; }
            .card { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px; }
            textarea, input, button { width: 100%; padding: 10px; margin: 5px 0; border-radius: 6px; border: 1px solid #d1d5db; box-sizing: border-box; }
            button { background: var(--primary); color: white; border: none; font-weight: bold; cursor: pointer; }
            table { width: 100%; border-collapse: collapse; } th, td { padding: 12px; border-bottom: 1px solid #f3f4f6; text-align: left; }
            .side-title { padding: 25px; font-weight: bold; color: var(--primary); font-size: 20px; border-bottom: 2px solid #f3f4f6; }
        </style>
    </head>
    <body>
    {% if not logged_in %}
        <div style="margin: 100px auto;" class="card"><form method="post" action="/login"><h2>Gxyn 登入</h2><input type="password" name="pwd" required><button type="submit">登入</button></form></div>
    {% else %}
        <div class="sidebar">
            <div class="side-title">Gxyn Clan</div>
            <div style="padding:20px;">
                <p style="font-size:12px; color:gray;">⚠️ 警告處置</p>
                <form action="/quick_warn" method="post">
                    <input type="text" name="uid" placeholder="用戶 ID" required>
                    <input type="text" name="reason" placeholder="原因" required>
                    <button type="submit" name="act" value="add">增加警告 (+)</button>
                    <button type="submit" name="act" value="sub" style="background:#f59e0b;">扣除警告 (-)</button>
                </form>
                <hr style="margin: 20px 0; border: 0; border-top: 1px solid #eee;">
                <form action="/backup" method="post"><button type="submit" style="background:#10b981;">📦 手動備份</button></form>
            </div>
            <a href="/logout" style="display:block; padding:20px; color:red; text-decoration:none;">🚪 登出系統</a>
        </div>
        <div class="main">
            <div class="card">
                <h2>📌 系統狀態</h2>
                <p>身分組訊息 ID: <b>{{ db.target_message_id if db.target_message_id else '未設定' }}</b></p>
                <p>反應表情: <span style="font-size:20px;">{{ db.current_emoji }}</span></p>
            </div>
            <div class="card">
                <h2>📢 發送全大字公告</h2>
                <form action="/announce" method="post"><textarea name="content" rows="3" placeholder="公告內容..." required></textarea><button type="submit">發送至公告頻道</button></form>
            </div>
            <div class="card">
                <h2>⚠️ 紀錄名單</h2>
                <table>
                    <tr><th>用戶 ID</th><th>警告數</th><th>累犯次數</th></tr>
                    {% for uid, count in db.warn_records.items() %}
                    <tr><td><code>{{ uid }}</code></td><td>{{ count }} 支</td><td>{{ db.violation_records.get(uid, 0) }} 次</td></tr>
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
    uid, reason, act = request.form.get('uid'), request.form.get('reason'), request.form.get('act')
    if act == "add": bot.db["warn_records"][uid] = bot.db["warn_records"].get(uid, 0) + 1
    else: bot.db["warn_records"][uid] = max(0, bot.db["warn_records"].get(uid, 0) - 1)
    bot.save_data()
    if act == "add": bot.loop.create_task(process_warn_and_punishment(int(uid), reason))
    return redirect('/')

@app.route('/announce', methods=['POST'])
def web_announce():
    ch = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if ch: bot.loop.create_task(ch.send(f"# 📢 公告\n# {request.form.get('content')}"))
    return redirect('/')

@app.route('/backup', methods=['POST'])
def web_backup():
    bot.loop.create_task(bot.send_backup("網頁手動備份"))
    return redirect('/')

# --- Discord 指令 ---
@bot.tree.command(name="警告")
async def warn_cmd(interaction: discord.Interaction, 成員: discord.Member, 理由: str, 動作: str = "增加", 數量: int = 1):
    uid = str(成員.id)
    if 動作 == "增加": bot.db["warn_records"][uid] = bot.db["warn_records"].get(uid, 0) + 數量
    else: bot.db["warn_records"][uid] = max(0, bot.db["warn_records"].get(uid, 0) - 數量)
    bot.save_data()
    await interaction.response.send_message(f"✅ 已處理 {成員.mention}", ephemeral=True)
    if 動作 == "增加": await process_warn_and_punishment(成員.id, 理由)

@bot.tree.command(name="公告")
async def announce_cmd(interaction, 內容: str):
    ch = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if ch: 
        await ch.send(f"# 📢 公告\n# {內容}")
        await interaction.response.send_message("✅ 公告已發布", ephemeral=True)

@bot.tree.command(name="身分組")
async def roles_cmd(interaction: discord.Interaction, 標題: str, 內容: str, 表情: str = "✅"):
    embed = discord.Embed(title=標題, description=內容, color=0x4f46e5)
    await interaction.response.send_message(embed=embed)
    msg = await interaction.original_response()
    await msg.add_reaction(表情)
    bot.db["target_message_id"] = msg.id
    bot.db["current_emoji"] = 表情
    bot.save_data()

if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080))), daemon=True).start()
    bot.run(TOKEN)
