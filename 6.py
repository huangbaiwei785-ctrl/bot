import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
import datetime
import aiohttp

# ================= 基礎設定區 =================
TOKEN = os.getenv('DISCORD_TOKEN') 
MY_GUILD_ID = 1492797387008376852       
ROLE_ID = 1492939910641090710           
BACKUP_CHANNEL_ID = 1496886906544324738 
DATA_FILE = "data.json"                 
# =============================================

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True         
        intents.message_content = True
        intents.guilds = True 
        super().__init__(command_prefix="!", intents=intents)
        
        self.target_message_id = None 
        self.current_emoji = "🤡"
        self.warn_records = {}

    def save_all_data(self):
        payload = {
            "target_message_id": self.target_message_id,
            "current_emoji": self.current_emoji,
            "warn_records": self.warn_records
        }
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"❌ 存檔失敗: {e}")

    def load_all_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.target_message_id = data.get("target_message_id")
                    self.current_emoji = data.get("current_emoji", "🤡")
                    raw_warns = data.get("warn_records", {})
                    self.warn_records = {int(k): v for k, v in raw_warns.items()}
                print("📁 數據已載入")
            except Exception as e:
                print(f"❌ 讀取失敗: {e}")

    async def setup_hook(self):
        self.load_all_data()
        guild = discord.Object(id=MY_GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        self.auto_backup_task.start() 
        print(f"✅ 機器人上線！自動備份設定：每 6 小時一次")

    @tasks.loop(hours=6) # 👈 修改為 6 小時
    async def auto_backup_task(self):
        await self.wait_until_ready()
        await self.perform_full_backup("系統 6 小時例行備份")

    async def perform_full_backup(self, reason):
        channel = self.get_channel(BACKUP_CHANNEL_ID)
        if not channel: return
        guild = self.get_guild(MY_GUILD_ID)
        if not guild: return

        structure = {
            "server_name": guild.name,
            "backup_time": str(datetime.datetime.now()),
            "roles": [f"{r.name} (ID: {r.id})" for r in guild.roles],
            "channels": [f"#{ch.name} ({ch.type})" for ch in guild.channels]
        }
        struct_file = "server_backup.json"
        with open(struct_file, "w", encoding="utf-8") as f:
            json.dump(structure, f, ensure_ascii=False, indent=4)

        self.save_all_data()
        await channel.send(
            f"📦 **[{reason}]**\n📅 時間：{datetime.datetime.now().strftime('%m/%d %H:%M')}",
            files=[discord.File(DATA_FILE), discord.File(struct_file)]
        )

bot = MyBot()

# --- 1. /警告 ---
@bot.tree.command(name="警告", description="記警告")
@app_commands.describe(成員="對象", 理由="原因")
@app_commands.default_permissions(administrator=True) 
async def warn(interaction: discord.Interaction, 成員: discord.Member, 理由: str):
    user_id = 成員.id
    bot.warn_records[user_id] = bot.warn_records.get(user_id, 0) + 1
    bot.save_all_data()
    embed = discord.Embed(title="⚠️ 警告", description=f"{成員.mention}\n理由：{理由}\n累計：`{bot.warn_records[user_id]}` 次", color=0xFF0000)
    await interaction.response.send_message(content=成員.mention, embed=embed)

# --- 2. /還原 (核心新功能) ---
@bot.tree.command(name="還原", description="從上傳的 data.json 檔案恢復數據")
@app_commands.describe(備份檔="請拖入備份頻道中的 data.json 檔案")
@app_commands.default_permissions(administrator=True)
async def restore_data(interaction: discord.Interaction, 備份檔: discord.Attachment):
    if not 備份檔.filename.endswith(".json"):
        await interaction.response.send_message("❌ 請上傳正確的 `.json` 格式檔案。", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(備份檔.url) as resp:
                if resp.status == 200:
                    content = await resp.text()
                    data = json.loads(content)
                    
                    # 覆蓋目前記憶體中的數據
                    bot.target_message_id = data.get("target_message_id")
                    bot.current_emoji = data.get("current_emoji", "🤡")
                    raw_warns = data.get("warn_records", {})
                    bot.warn_records = {int(k): v for k, v in raw_warns.items()}
                    
                    # 立即寫入本地磁碟
                    bot.save_all_data()
                    await interaction.followup.send("✅ 數據還原成功！警告紀錄與身分組 ID 已更新。")
                else:
                    await interaction.followup.send("❌ 無法下載檔案。")
    except Exception as e:
        await interaction.followup.send(f"❌ 還原過程發生錯誤：{e}")

# --- 3. /備份數據 ---
@bot.tree.command(name="備份數據", description="手動執行備份")
@app_commands.default_permissions(administrator=True)
async def manual_backup(interaction: discord.Interaction):
    await interaction.response.send_message("⌛ 備份中...", ephemeral=True)
    await bot.perform_full_backup(f"手動執行: {interaction.user.name}")

# --- 4. /身分組 ---
@bot.tree.command(name="身分組", description="發送領取訊息")
async def roles_setup(interaction: discord.Interaction, 標題: str, 內容: str, 表情: str = "🤡"):
    bot.current_emoji = 表情
    embed = discord.Embed(title=標題, description=內容 + f"\n\n點擊 {表情} 領取身分組", color=0xFFAA00)
    await interaction.response.send_message(f"✅ 已產生", ephemeral=True)
    msg = await interaction.channel.send(embed=embed)
    bot.target_message_id = msg.id
    bot.save_all_data()
    try: await msg.add_reaction(表情)
    except: pass

# --- 反應監聽 (不變) ---
@bot.event
async def on_raw_reaction_add(payload):
    if payload.message_id == bot.target_message_id and str(payload.emoji) == bot.current_emoji:
        guild = bot.get_guild(payload.guild_id)
        role = guild.get_role(ROLE_ID)
        if role and payload.member and not payload.member.bot:
            try: await payload.member.add_roles(role)
            except: pass

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.message_id == bot.target_message_id and str(payload.emoji) == bot.current_emoji:
        guild = bot.get_guild(payload.guild_id)
        role = guild.get_role(ROLE_ID)
        try:
            member = await guild.fetch_member(payload.user_id)
            if role and member and not member.bot:
                await member.remove_roles(role)
        except: pass

if TOKEN:
    bot.run(TOKEN)
