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

# 自動創立符合格式的 data.json
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
        if not role: return await interaction.response.send_message("找不到身分組", ephemeral=True)
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"已移除 {role.name}", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"已領取 {role.name}", ephemeral=True)

class IntegratedBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
        self.db = {}
    def save(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.db, f, ensure_ascii=False, indent=4)
    async def setup_hook(self):
        with open(DATA_FILE, "r") as f: self.db = json.load(f)
        self.add_view(RoleView())
        guild = discord.Object(id=MY_GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        self.auto_backup.start()

    @tasks.loop(hours=6)
    async def auto_backup(self):
        await self.wait_until_ready()
        await self.send_backup("自動備份")

    async def send_backup(self, reason):
        ch = self.get_channel(BACKUP_CHANNEL_ID)
        if ch:
            self.save()
            await ch.send(f"📦 **[{reason}]**", file=discord.File(DATA_FILE))

bot = IntegratedBot()
app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- 完整的控制面板 HTML ---
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
        .btn-red { background: #f04747; } .btn-green { background: #43b581; }
        table { width: 100%; margin-top: 10px; border-collapse: collapse; }
        th, td { border-bottom: 1px solid #444; padding: 8px; text-align: left; }
    </style>
</head>
<body>
    <div style="max-width: 600px; margin: auto;">
        {% if not logged_in %}
            <div class="card"><h1>🔑 登入</h1><form method="post" action="/login"><input type="password" name="pwd"><button type="submit">進入</button></form></div>
        {% else %}
            <h1>🛡️ 控制面板 <a href="/logout" style="color:#f04747; font-size:14px;">[登出]</a></h1>
            
            <div class="card">
                <h3>📢 全大字公告</h3>
                <form action="/announce" method="post"><textarea name="content" placeholder="內容..."></textarea><button type="submit">發送</button></form>
            </div>

            <div class="card">
                <h3>⚠️ 警告管理</h3>
                <form action="/manage" method="post">
                    ID: <input type="text" name="uid" required>
                    理由: <input type="text" name="reason" required>
                    <div style="display:flex; gap:5px;">
                        <button type="submit" name="act" value="add" class="btn-green">增加</button>
                        <button type="submit" name="act" value="sub" style="background:#faa61a;">減少</button>
                    </div>
                </form>
                <table><tr><th>ID</th><th>次數</th></tr>
                    {% for uid, count in db.warn_records.items() %}
                    <tr><td>{{ uid }}</td><td>{{ count }}</td></tr>
                    {% endfor %}
                </table>
            </div>

            <div class="card">
                <h3>💾 系統資訊</h3>
                <p>身分組訊息 ID: <code>{{ db.target_message_id }}</code></p>
                <form action="/backup" method="post"><button type="submit">立即手動備份</button></form>
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
    return redirect(url_for('index'))

@app.route('/logout')
def logout(): session.pop('user', None); return redirect(url_for('index'))

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
    bot.save()
    log_ch = bot.get_channel(WARN_LOG_CHANNEL_ID)
    if log_ch:
        e = discord.Embed(title="⚠️ 警告變動 (網頁)", color=0x7289da)
        e.add_field(name="對象", value=f"<@{uid}>"); e.add_field(name="理由", value=reason); e.add_field(name="累計", value=recs[uid])
        bot.loop.create_task(log_ch.send(embed=e))
    return redirect(url_for('index'))

@app.route('/backup', methods=['POST'])
def web_backup():
    bot.loop.create_task(bot.send_backup("網頁手動備份"))
    return redirect(url_for('index'))

@bot.tree.command(name="身分組")
async def roles_cmd(interaction: discord.Interaction, 標題: str, 內容: str, 表情: str = "🤡"):
    e = discord.Embed(title=標題, description=內容, color=0x7289da)
    v = RoleView(); v.children[0].emoji = 表情
    await interaction.response.send_message(embed=e, view=v)
    msg = await interaction.original_response()
    bot.db["target_message_id"] = msg.id; bot.db["current_emoji"] = 表情; bot.save()

@bot.tree.command(name="警告")
async def warn_cmd(interaction, 成員: discord.Member, 理由: str, 動作: str = "增加"):
    uid = str(成員.id)
    if 動作 == "增加": bot.db["warn_records"][uid] = bot.db["warn_records"].get(uid, 0) + 1
    else: bot.db["warn_records"][uid] = max(0, bot.db["warn_records"].get(uid, 0) - 1)
    bot.save(); await interaction.response.send_message(f"已處理 {成員.mention}", ephemeral=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=port), daemon=True).start()
    bot.run(TOKEN)
