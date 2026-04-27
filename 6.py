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

# 初始化資料，新增 "violation_records" 欄位
def init_data():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "target_message_id": None, 
                "current_emoji": "🤡", 
                "warn_records": {},
                "violation_records": {} # 紀錄累犯次數
            }, f, indent=4)

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
        with open(DATA_FILE, "r") as f: 
            self.db = json.load(f)
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
        await self.send_backup("自動備份")

bot = IntegratedBot()

# --- 核心處理邏輯：警告與懲處 ---
async def process_punishment(member: discord.Member, reason: str):
    uid = str(member.id)
    warn_count = bot.db["warn_records"].get(uid, 0)
    log_ch = bot.get_channel(WARN_LOG_CHANNEL_ID)
    
    if warn_count >= 4:
        # 1. 警告歸零
        bot.db["warn_records"][uid] = 0
        # 2. 累犯紀錄 +1
        bot.db["violation_records"][uid] = bot.db["violation_records"].get(uid, 0) + 1
        violations = bot.db["violation_records"][uid]
        
        if violations >= 3:
            # 累犯 3 次 -> 停權
            await member.ban(reason=f"累犯滿 3 次自動停權。最後事由：{reason}")
            if log_ch:
                await log_ch.send(f"🚫 **停權通知**：{member.mention} 累犯達 3 次，已執行永久停權。")
        else:
            # 滿 4 支 -> 禁言一天
            duration = datetime.timedelta(days=1)
            await member.timeout(duration, reason=f"警告滿 4 支自動禁言。事由：{reason}")
            if log_ch:
                await log_ch.send(f"🔇 **禁言通知**：{member.mention} 警告滿 4 支，已禁言一天。目前累犯次數：`{violations}/3`。")
        
        bot.save_data()

# --- 網頁後台 ---
app = Flask(__name__)
app.secret_key = os.urandom(24)

@app.route('/')
def index():
    return render_template_string("""
    <body style="background:#2c2f33; color:white; font-family:sans-serif; padding:20px;">
        <div style="max-width:600px; margin:auto;">
            <h1>🛡️ 機器人管理後台</h1>
            <div style="background:#23272a; padding:15px; border-radius:10px; border:1px solid #7289da;">
                <h3>⚠️ 警告與累犯紀錄</h3>
                <table style="width:100%; text-align:left;">
                    <tr><th>用戶 ID</th><th>目前警告</th><th>累犯次數</th></tr>
                    {% for uid, count in db.warn_records.items() %}
                    <tr><td>{{ uid }}</td><td>{{ count }} 支</td><td>{{ db.violation_records.get(uid, 0) }} 次</td></tr>
                    {% endfor %}
                </table>
            </div>
            <br>
            <form action="/backup" method="post"><button style="width:100%; padding:10px; background:#43b581; color:white; border:none; border-radius:5px; cursor:pointer;">立即手動備份</button></form>
        </div>
    </body>
    """, db=bot.db)

@app.route('/backup', methods=['POST'])
def web_backup():
    bot.loop.create_task(bot.send_backup("網頁手動備份"))
    return redirect('/')

# --- Discord 指令 ---
@bot.tree.command(name="警告", description="調整成員警告支數")
async def warn_cmd(interaction: discord.Interaction, 成員: discord.Member, 理由: str, 動作: str = "增加"):
    uid = str(成員.id)
    if 動作 == "增加":
        bot.db["warn_records"][uid] = bot.db["warn_records"].get(uid, 0) + 1
    else:
        bot.db["warn_records"][uid] = max(0, bot.db["warn_records"].get(uid, 0) - 1)
    
    bot.save_data()
    await interaction.response.send_message(f"✅ 已處理 {成員.mention}。理由：{理由}", ephemeral=True)
    
    # 檢查是否需要執行懲處
    if 動作 == "增加":
        await process_punishment(成員, 理由)

@bot.tree.command(name="身分組", description="發送身分組領取訊息")
async def roles_cmd(interaction: discord.Interaction, 標題: str, 內容: str, 表情: str = "🤡"):
    e = discord.Embed(title=標題, description=內容, color=0x7289da)
    v = RoleView(); v.children[0].emoji = 表情
    await interaction.response.send_message(embed=e, view=v)
    msg = await interaction.original_response()
    bot.db["target_message_id"] = msg.id; bot.db["current_emoji"] = 表情; bot.save_data()

# 啟動
if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080))), daemon=True).start()
    bot.run(TOKEN)
