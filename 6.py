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
ROLE_ID = 1492939910641090710 # 目標身分組
# =============================================

# --- 自動初始化 data.json ---
def init_data_file():
    if not os.path.exists(DATA_FILE):
        default_data = {
            "target_message_id": None,
            "current_emoji": "🤡",
            "warn_records": {}
        }
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(default_data, f, ensure_ascii=False, indent=4)
        print(f"✅ 已自動建立 {DATA_FILE}")

init_data_file()

# --- 持久化按鈕類別 ---
class RoleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="獲取/移除身分組", style=discord.ButtonStyle.secondary, custom_id="persistent_role_button")
    async def toggle_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = interaction.guild.get_role(ROLE_ID)
        if not role:
            return await interaction.response.send_message("❌ 找不到身分組設定", ephemeral=True)
        
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"✅ 已移除身分組：{role.name}", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"✅ 已領取身分組：{role.name}", ephemeral=True)

class IntegratedBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.db = {}

    def save_data(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.db, f, ensure_ascii=False, indent=4)

    def load_data(self):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            self.db = json.load(f)

    async def setup_hook(self):
        self.load_data()
        self.add_view(RoleView()) # 註冊按鈕
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

# --- 網頁 HTML 模板 ---
HTML_TPL = """
<!DOCTYPE html>
<html>
<head>
    <title>機器人管理後台</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: sans-serif; background: #2c2f33; color: white; padding: 20px; }
        .card { background: #23272a; padding: 15px; border-radius: 10px; margin-bottom: 20px; border: 1px solid #7289da; }
        button { width: 100%; padding: 12px; background: #7289da; color: white; border: none; border-radius: 5px; cursor: pointer; font-weight: bold; }
        input { width: 100%; padding: 10px; margin: 5px 0; box-sizing: border-box; }
        table { width: 100%; border-collapse: collapse; }
        th, td { border-bottom: 1px solid #444; padding: 8px; text-align: left; }
    </style>
</head>
<body>
    <div style="max-width: 600px; margin: auto;">
        {% if not logged_in %}
            <div class="card">
                <h1>🔑 管理員登入</h1>
                <form method="post" action="/login"><input type="password" name="pwd" required><button type="submit">登入</button></form>
            </div>
        {% else %}
            <h1>🛡️ 控制面板 <a href="/logout" style="font-size:12px; color:#f04747;">登出</a></h1>
            <div class="card">
                <h3>⚠️ 警告紀錄</h3>
                <table>
                    <tr><th>用戶 ID</th><th>警告次數</th></tr>
                    {% for uid, count in db.warn_records.items() %}
                    <tr><td>{{ uid }}</td><td>{{ count }} 支</td></tr>
                    {% endfor %}
                </table>
            </div>
            <div class="card">
                <h3>💾 數據備份</h3>
                <form action="/backup" method="post"><button type="submit">立即發送備份檔案</button></form>
            </div>
        {% endif %}
    </div>
</body>
</html>
"""

# --- Flask 路由修復 ---
@app.route('/')
def index():
    return render_template_string(HTML_TPL, db=bot.db, logged_in=session.get('user') == 'admin')

@app.route('/login', methods=['POST'])
def login():
    if request.form.get('pwd') == WEB_PASSWORD: session['user'] = 'admin'
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('user', None); return redirect(url_for('index'))

@app.route('/backup', methods=['POST'])
def web_backup():
    if session.get('user') == 'admin': bot.loop.create_task(bot.send_backup("網頁手動備份"))
    return redirect(url_for('index'))

# --- Discord 指令 ---
@bot.tree.command(name="身分組", description="發送身分組領取訊息 (Embed)")
async def roles_cmd(interaction: discord.Interaction, 標題: str, 內容: str, 表情: str = "🤡"):
    embed = discord.Embed(title=標題, description=內容, color=0x7289da)
    view = RoleView()
    view.children[0].emoji = 表情
    await interaction.response.send_message(embed=embed, view=view)
    
    # 儲存訊息資訊到 data.json
    msg = await interaction.original_response()
    bot.db["target_message_id"] = msg.id
    bot.db["current_emoji"] = 表情
    bot.save_data()

# --- 啟動程序 ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=port), daemon=True).start()
    bot.run(TOKEN)
