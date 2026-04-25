import discord
from discord import app_commands
from discord.ext import commands
import os

# ================= 基礎設定區 =================
TOKEN = os.getenv("DISCORD_TOKEN")
ROLE_ID = 1492939910641090710           # 領取身分組的 ID
MY_GUILD_ID = 1492797387008376852        # 你的伺服器 ID
# =============================================

# 暫時紀錄警告次數 {user_id: count}
warn_records = {}

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True         
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.target_message_id = None 
        self.current_emoji = "🤡"

    async def setup_hook(self):
        # 強制同步至指定伺服器
        guild = discord.Object(id=MY_GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        print(f"🚀 指令已強制同步至伺服器: {MY_GUILD_ID}")
        print(f"✅ 機器人已上線，CMD 發言功能已關閉。")

bot = MyBot()

# --- 1. /警告 ---
@bot.tree.command(name="警告", description="對成員記一次警告")
@app_commands.describe(成員="要警告的對象", 理由="警告原因")
@app_commands.checks.has_permissions(administrator=True)
async def warn(interaction: discord.Interaction, 成員: discord.Member, 理由: str):
    user_id = 成員.id
    warn_records[user_id] = warn_records.get(user_id, 0) + 1
    count = warn_records[user_id]

    embed = discord.Embed(
        title="⚠️ 成員警告單",
        description=f"**被警告者：** {成員.mention}\n**理由：** {理由}\n**目前累計警告：** `{count}` 次",
        color=discord.Color.red()
    )
    embed.set_footer(text="請遵守伺服器規範")
    
    await interaction.response.send_message(content=成員.mention, embed=embed)

# --- 2. /刪除警告 ---
@bot.tree.command(name="刪除警告", description="歸零特定成員的警告紀錄")
@app_commands.describe(成員="要清除紀錄的對象")
@app_commands.checks.has_permissions(administrator=True)
async def clear_warn(interaction: discord.Interaction, 成員: discord.Member):
    user_id = 成員.id
    if user_id in warn_records:
        del warn_records[user_id]
        await interaction.response.send_message(f"✅ 已清除 {成員.mention} 的所有警告紀錄。")
    else:
        await interaction.response.send_message(f"ℹ️ {成員.mention} 本來就沒有警告紀錄。", ephemeral=True)

# --- 3. /身分組 ---
@bot.tree.command(name="身分組", description="發送身分組領取訊息")
@app_commands.describe(標題="標題", 內容="內容", 表情="預設為 🤡")
async def roles_setup(interaction: discord.Interaction, 標題: str, 內容: str, 表情: str = "🤡"):
    bot.current_emoji = 表情
    embed = discord.Embed(title=標題, description=內容 + f"\n\n點擊 {表情} 領取身分組", color=0xFFAA00)
    
    await interaction.response.send_message(f"✅ 身分組訊息已產生", ephemeral=True)
    msg = await interaction.channel.send(embed=embed)
    bot.target_message_id = msg.id
    try:
        await msg.add_reaction(表情)
    except:
        print("❌ 無法加上反應，請檢查表情符號是否正確")

# --- 反應監聽：領取身分組 ---
@bot.event
async def on_raw_reaction_add(payload):
    if payload.message_id == bot.target_message_id and str(payload.emoji) == bot.current_emoji:
        guild = bot.get_guild(payload.guild_id)
        role = guild.get_role(ROLE_ID)
        if role and payload.member and not payload.member.bot:
            try:
                await payload.member.add_roles(role)
                print(f"✅ 已發放身分組給 {payload.member.name}")
            except:
                print("❌ 權限階級不足")

# --- 反應監聽：移除身分組 ---
@bot.event
async def on_raw_reaction_remove(payload):
    if payload.message_id == bot.target_message_id and str(payload.emoji) == bot.current_emoji:
        guild = bot.get_guild(payload.guild_id)
        role = guild.get_role(ROLE_ID)
        try:
            member = await guild.fetch_member(payload.user_id)
            if role and member and not member.bot:
                await member.remove_roles(role)
                print(f"🗑️ 已從 {member.name} 身上移除身分組")
        except:
            pass

bot.run(TOKEN)
