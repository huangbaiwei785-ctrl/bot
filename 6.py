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

class RoleView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None) # 永不到期
        self.bot = bot

    @discord.ui.button(label="獲取/移除身分組", style=discord.ButtonStyle.secondary, custom_id="persistent_role_button")
    async def toggle_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 從資料庫獲取當前設定的表情 (雖然按鈕顯示是寫死的，但這確保逻辑一致)
        role = interaction.guild.get_role(ROLE_ID)
        if not role:
            return await interaction.response.send_message("❌ 找不到身分組設定", ephemeral=True)
        
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"✅ 已移除 {role.name}", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"✅ 已領取 {role.name}", ephemeral=True)

class IntegratedBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        # 初始化資料格式
        self.db = {
            "target_message_id": None,
            "current_emoji": "🤡",
            "warn_records": {}
        }

    def save_data(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.db, f, ensure_ascii=False, indent=4)

    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    self.db = json.load(f)
            except: print("⚠️ 載入存檔失敗")

    async def setup_hook(self):
        self.load_data()
        # 註冊持久化視圖
        self.add_view(RoleView(self))
        
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

# --- Discord 指令 ---

@bot.tree.command(name="身分組", description="發送身分組領取嵌入訊息")
async def roles_cmd(interaction: discord.Interaction, 標題: str, 內容: str, 表情: str = "🤡"):
    # 建立嵌入訊息 (欠入)
    embed = discord.Embed(
        title=標題,
        description=內容,
        color=0x7289da,
        timestamp=datetime.datetime.now()
    )
    embed.set_footer(text="點擊下方按鈕領取")
    
    # 發送訊息
    view = RoleView(bot)
    # 動態更改按鈕表情
    view.children[0].emoji = 表情
    
    await interaction.response.send_message(embed=embed, view=view)
    
    # 獲取發送後的訊息並寫入資料庫
    msg = await interaction.original_response()
    bot.db["target_message_id"] = msg.id
    bot.db["current_emoji"] = 表情
    bot.save_data()

@bot.tree.command(name="警告", description="調整警告支數")
async def warn_cmd(interaction: discord.Interaction, 成員: discord.Member, 動作: str, 理由: str, 數量: int = 1):
    uid = str(成員.id)
    if 動作 == "增加":
        bot.db["warn_records"][uid] = bot.db["warn_records"].get(uid, 0) + 數量
    else:
        bot.db["warn_records"][uid] = max(0, bot.db["warn_records"].get(uid, 0) - 數量)
    
    bot.save_data() # 存檔會包含警告與身分組 ID
    await interaction.response.send_message(f"✅ 已處理 {成員.mention}。目前累計：`{bot.db['warn_records'][uid]}` 支", ephemeral=True)
    
    # 發送 Log
    log_ch = bot.get_channel(WARN_LOG_CHANNEL_ID)
    if log_ch:
        e = discord.Embed(title="⚠️ 警告變動", color=0xff0000)
        e.add_field(name="對象", value=成員.mention)
        e.add_field(name="理由", value=理由)
        e.add_field(name="總計", value=f"{bot.db['warn_records'][uid]} 支")
        await log_ch.send(embed=e)

# --- (其餘 Flask 網頁與備份指令保持與前版相同) ---
# ... (此處省略 Flask 啟動與 backup_cmd 代碼) ...

if __name__ == "__main__":
    app = Flask(__name__) # 這裡需補上 Flask 實例化以便執行
    # (Flask 路由建議參考前幾次回答補齊)
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=8080), daemon=True).start()
    bot.run(TOKEN)
