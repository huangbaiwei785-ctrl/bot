import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import sys

# --- 基礎設定 ---
TOKEN = os.getenv("DISCORD_TOKEN")
ROLE_ID = 1492939910641090710 
DEFAULT_CHANNEL_ID = 1492920337283809480 # 你的 CMD 發言預設頻道

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True         
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.target_message_id = 1496871344313471189
        self.current_emoji = "🤡" # 預設改回小丑

    async def setup_hook(self):
        await self.tree.sync()
        self.loop.create_task(self.cmd_listener())
        print(f"✅ 機器人已上線！目前預設表情為：{self.current_emoji}")

    async def cmd_listener(self):
        await self.wait_until_ready()
        while not self.is_closed():
            raw_input = await self.loop.run_in_executor(None, sys.stdin.readline)
            line = raw_input.strip()
            if not line: continue
            parts = line.split(" ", 1)
            target_channel = self.get_channel(int(parts[0])) if parts[0].isdigit() and len(parts[0]) >= 17 else self.get_channel(DEFAULT_CHANNEL_ID)
            msg_to_send = parts[1] if (parts[0].isdigit() and len(parts[0]) >= 17 and len(parts) > 1) else line
            if target_channel and msg_to_send:
                try: await target_channel.send(msg_to_send)
                except: print("❌ CMD 發送失敗")

bot = MyBot()

@bot.tree.command(name="身分組", description="發送身分組領取訊息")
@app_commands.describe(標題="標題", 內容="說明文字", 表情="Emoji (例如 🤡) 或自定義表情格式")
@app_commands.checks.has_permissions(administrator=True)
async def roles_setup(interaction: discord.Interaction, 標題: str, 內容: str, 表情: str = "🤡"):
    bot.current_emoji = 表情 # 更新目前監控的表情
    embed = discord.Embed(title=標題, description=內容 + f"\n\n點擊 {表情} 領取身分組", color=0xFFAA00)
    
    await interaction.response.send_message(f"✅ 已設定，目前監控表情：{表情}", ephemeral=True)
    msg = await interaction.channel.send(embed=embed)
    bot.target_message_id = msg.id
    
    try:
        await msg.add_reaction(表情)
        print(f"🚀 正在監控訊息：{msg.id} | 表情：{表情}")
    except:
        print("❌ 無法加上反應，請確認表情符號是否正確")

@bot.event
async def on_raw_reaction_add(payload):
    # 確保是我們要的那則訊息
    if payload.message_id != bot.target_message_id:
        return

    # 將點擊的表情轉為字串進行比對
    clicked_emoji = str(payload.emoji)
    
    if clicked_emoji == bot.current_emoji:
        guild = bot.get_guild(payload.guild_id)
        role = guild.get_role(ROLE_ID)
        if role and payload.member:
            try:
                # 檢查機器人階級是否高於該身分組
                if role.position < guild.me.top_role.position:
                    await payload.member.add_roles(role)
                    print(f"✅ 已發放身分組給 {payload.member.name}")
                else:
                    print(f"❌ 階級錯誤：請在伺服器設定將機器人拉到 {role.name} 上方")
            except Exception as e:
                print(f"❌ 錯誤: {e}")

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.message_id == bot.target_message_id and str(payload.emoji) == bot.current_emoji:
        guild = bot.get_guild(payload.guild_id)
        role = guild.get_role(ROLE_ID)
        try:
            member = await guild.fetch_member(payload.user_id)
            if role and member:
                await member.remove_roles(role)
                print(f"🗑️ 已移除 {member.name} 的身分組")
        except:
            pass

bot.run(TOKEN)
