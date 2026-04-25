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
        except Exception as e: print(f"❌ 存檔失敗: {e}")

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
            except Exception as e: print(f"❌ 讀取失敗: {e}")

    async def setup_hook(self):
        self.load_all_data()
        guild = discord.Object(id=MY_GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        self.auto_backup_task.start() 
        print(f"✅ 機器人上線！備份頻道: {BACKUP_CHANNEL_ID}")

    @tasks.loop(hours=6)
    async def auto_backup_task(self):
        await self.wait_until_ready()
        await self.perform_full_backup("例行 6 小時備份")

    async def perform_full_backup(self, reason):
        channel = self.get_channel(BACKUP_CHANNEL_ID)
        if not channel: return
        guild = self.get_guild(MY_GUILD_ID)
        if not guild: return
        
        # 結構備份
        struct = {
            "server_name": guild.name,
            "backup_time": str(datetime.datetime.now()),
            "roles": [f"{r.name}" for r in guild.roles],
            "categories": [c.name for c in guild.categories]
        }
        with open("server_backup.json", "w", encoding="utf-8") as f:
            json.dump(struct, f, ensure_ascii=False, indent=4)

        self.save_all_data()
        await channel.send(
            f"📦 **[{reason}]**",
            files=[discord.File(DATA_FILE), discord.File("server_backup.json")]
        )

bot = MyBot()

# --- 1. /公告 (新增：自動銷掉舊置頂) ---
@bot.tree.command(name="公告", description="發送新公告，並自動取消機器人的舊置頂公告")
@app_commands.describe(標題="標題", 內容="內容")
@app_commands.default_permissions(administrator=True)
async def announcement(interaction: discord.Interaction, 標題: str, 內容: str):
    await interaction.response.defer(ephemeral=True)
    
    # A. 先找出並取消機器人之前的置頂
    try:
        pins = await interaction.channel.pins()
        for pin in pins:
            if pin.author.id == bot.user.id:
                await pin.unpin()
    except:
        pass # 忽略權限不足或其他錯誤

    # B. 發布新公告
    time_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    msg_content = f"# 📢 {標題}\n\n{內容}\n\n> 🕒 公告時間：{time_str}\n---"
    
    new_msg = await interaction.channel.send(msg_content)
    
    # C. 置頂新公告
    try:
        await new_msg.pin()
        await interaction.followup.send("✅ 舊置頂已撤下，新公告已發布並置頂。")
    except Exception as e:
        await interaction.followup.send(f"⚠️ 公告已發送，但置頂失敗: {e}")

# --- 2. /還原 (數據 + 架構補建) ---
@bot.tree.command(name="還原", description="從備份檔恢復數據與缺失架構")
@app_commands.describe(數據備份="上傳 data.json", 架構備份="上傳 server_backup.json (選填)")
@app_commands.default_permissions(administrator=True)
async def restore_all(interaction: discord.Interaction, 數據備份: discord.Attachment, 架構備份: discord.Attachment = None):
    await interaction.response.defer(ephemeral=True)
    async with aiohttp.ClientSession() as session:
        # 還原數據
        async with session.get(數據備份.url) as resp:
            if resp.status == 200:
                data = json.loads(await resp.text())
                bot.target_message_id = data.get("target_message_id")
                bot.current_emoji = data.get("current_emoji", "🤡")
                bot.warn_records = {int(k): v for k, v in data.get("warn_records", {}).items()}
                bot.save_all_data()
                res = "✅ 數據還原成功！"
            else:
                return await interaction.followup.send("❌ 下載失敗")

        # 補建架構 (分類與身分組)
        if 架構備份:
            async with session.get(架構備份.url) as resp:
                if resp.status == 200:
                    struct = json.loads(await resp.text())
                    guild = interaction.guild
                    exist_roles = [r.name for r in guild.roles]
                    for r_name in struct.get("roles", []):
                        if r_name not in exist_roles and r_name != "@everyone":
                            await guild.create_role(name=r_name)
                    exist_cats = [c.name for c in guild.categories]
                    for c_name in struct.get("categories", []):
                        if c_name not in exist_cats:
                            await guild.create_category(c_name)
                    res += "\n🏗️ 架構已補齊。"
    await interaction.followup.send(res)

# --- 3. /警告 ---
@bot.tree.command(name="警告", description="記警告")
@app_commands.default_permissions(administrator=True) 
async def warn(interaction: discord.Interaction, 成員: discord.Member, 理由: str):
    uid = 成員.id
    bot.warn_records[uid] = bot.warn_records.get(uid, 0) + 1
    bot.save_all_data()
    embed = discord.Embed(title="⚠️ 警告", description=f"{成員.mention}\n理由：{理由}\n累計：`{bot.warn_records[uid]}` 次", color=0xFF0000)
    await interaction.response.send_message(content=成員.mention, embed=embed)

# --- 4. /身分組 ---
@bot.tree.command(name="身分組", description="發送領取訊息")
async def roles_setup(interaction: discord.Interaction, 標題: str, 內容: str, 表情: str = "🤡"):
    bot.current_emoji = 表情
    embed = discord.Embed(title=標題, description=內容 + f"\n\n點擊 {表情} 領取身分組", color=0xFFAA00)
    await interaction.response.send_message("✅ 已發送", ephemeral=True)
    msg = await interaction.channel.send(embed=embed)
    bot.target_message_id = msg.id
    bot.save_all_data()
    try: await msg.add_reaction(表情)
    except: pass

# --- 反應監聽 (身分組) ---
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
            if role and member and not member.bot: await member.remove_roles(role)
        except: pass

bot.run(TOKEN)
