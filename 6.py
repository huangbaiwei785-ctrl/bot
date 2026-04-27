import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import threading
from flask import Flask, render_template_string, request, redirect, url_for

# ================= 基礎設定區 =================
TOKEN = os.getenv('DISCORD_TOKEN')
WEB_PASSWORD = os.getenv('WEB_PWD', 'admin888') 
MY_GUILD_ID = 1492797387008376852
DATA_FILE = "warn_data.json"
# =============================================

class WarnBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.warn_records = {}

    def save_data(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.warn_records, f, ensure_ascii=False, indent=4)

    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.warn_records = {str(k): int(v) for k, v in data.items()}
            except: print("⚠️ 載入存檔失敗")

    async def setup_hook(self):
        self.load_data()
        guild = discord.Object(id=MY_GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

bot = WarnBot()

# --- Flask 網頁控制面板 ---
app = Flask(__name__)

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>警告管理控制台</title>
    <style>
        body { font-family: 'Segoe UI', sans-serif; background: #2c2f33; color: white; padding: 20px; text-align: center; }
        .container { max-width: 600px; margin: auto; background: #23272a; padding: 25px; border-radius: 15px; border: 1px solid #7289da; }
        input { width: 80%; padding: 10px; margin: 10px 0; background: #40444b; border: 1px solid #202225; color: white; border-radius: 5px; }
        .btn-group { display: flex; justify-content: space-around; margin-top: 15px; }
        button { padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; font-weight: bold; }
        .add { background: #43b581; color: white; }
        .sub { background: #faa61a; color: white; }
        .clear { background: #f04747; color: white; }
        table { width: 100%; margin-top: 20px; border-collapse: collapse; }
        th, td { padding: 10px; border-bottom: 1px solid #444; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚠️ 警告管理後台</h1>
        <form action="/manage" method="post">
            <input type="password" name="pwd" placeholder="管理密碼" required><br>
            <input type="text" name="uid" placeholder="成員 ID (例如: 123456789)"><br>
            <input type="number" name="amount" value="1" min="1" style="width: 50px;"> 支
            <div class="btn-group">
                <button type="submit" name="action" value="add" class="add">增加警告</button>
                <button type="submit" name="action" value="sub" class="sub">減少警告</button>
                <button type="submit" name="action" value="clear" class="clear">清除紀錄</button>
            </div>
        </form>
        <table>
            <tr><th>成員 ID</th><th>警告支數</th></tr>
            {% for uid, count in warns.items() %}
            <tr><td>{{ uid }}</td><td>{{ count }}</td></tr>
            {% endfor %}
        </table>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_PAGE, warns=bot.warn_records)

@app.route('/manage', methods=['POST'])
def manage():
    pwd = request.form.get('pwd')
    uid = request.form.get('uid')
    amount = int(request.form.get('amount', 1))
    action = request.form.get('action')

    if pwd != WEB_PASSWORD: return "❌ 密碼錯誤", 403
    
    if uid:
        if action == "add":
            bot.warn_records[uid] = bot.warn_records.get(uid, 0) + amount
        elif action == "sub":
            bot.warn_records[uid] = max(0, bot.warn_records.get(uid, 0) - amount)
        elif action == "clear":
            if uid in bot.warn_records: del bot.warn_records[uid]
        bot.save_data()
    return redirect(url_for('index'))

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- Discord 指令 ---
@bot.tree.command(name="警告", description="調整成員警告支數")
@app_commands.describe(動作="增加/減少/清除", 數量="調整的支數 (預設 1)")
@app_commands.choices(動作=[
    app_commands.Choice(name="增加 (+)", value="add"),
    app_commands.Choice(name="減少 (-)", value="sub"),
    app_commands.Choice(name="清除 (歸零)", value="clear")
])
async def warn_cmd(interaction: discord.Interaction, 成員: discord.Member, 動作: str, 數量: int = 1):
    uid = str(成員.id)
    if 動作 == "add":
        bot.warn_records[uid] = bot.warn_records.get(uid, 0) + 數量
        m = f"✅ 已為 {成員.mention} 增加 `{數量}` 支警告。"
    elif 動作 == "sub":
        bot.warn_records[uid] = max(0, bot.warn_records.get(uid, 0) - 數量)
        m = f"✅ 已為 {成員.mention} 減少 `{數量}` 支警告。"
    else:
        if uid in bot.warn_records: del bot.warn_records[uid]
        m = f"🔥 已歸零 {成員.mention} 的紀錄。"
    
    bot.save_data()
    await interaction.response.send_message(f"{m}\n目前累計：`{bot.warn_records.get(uid, 0)}` 支")

if __name__ == "__main__":
    t = threading.Thread(target=run_web)
    t.start()
    bot.run(TOKEN)
