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
ADMIN_REVIEW_CHANNEL_ID = 1497470602888613918  # 懲處審核頻道
DATA_FILE = "data.json"                 
# =============================================

# --- 懲處按鈕組件 ---
class PunishmentView(discord.ui.View):
    def __init__(self, target_member: discord.Member):
        super().__init__(timeout=None) # 按鈕永久有效直到重啟
        self.target_member = target_member

    @discord.ui.button(label="停權 1 天 (Ban)", style=discord.ButtonStyle.danger)
    async def ban_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await self.target_member.ban(reason="警告超過 4 次（管理員手動執行）", delete_message_days=0)
            await interaction.response.send_message(f"✅ 已由 {interaction.user.mention} 執行：將 {self.target_member.mention} **停權 1 天**。")
            self.stop() # 停用這組按鈕
        except:
            await interaction.response.send_message("❌ 權限不足，無法停權該成員。", ephemeral=True)

    @discord.ui.button(label="禁言 1 天 (Timeout)", style=discord.ButtonStyle.secondary)
    async def timeout_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            duration = datetime.timedelta(days=1)
            await self.target_member.timeout(duration, reason="警告超過 4 次（管理員手動執行）")
            await interaction.response.send_message(f"✅ 已由 {interaction.user.mention} 執行：將 {self.target_member.mention} **禁言 1 天**。")
            self.stop()
        except:
            await interaction.response.send_message("❌ 權限不足，無法禁言該成員。", ephemeral=True)

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all() # 確保開啟所有權限
        super().__init__(command_prefix="!", intents=intents)
        self.target_message_id = None 
        self.current_emoji = "🤡"
        self.warn_records = {}

    def save_all_data(self):
        payload = {"target_message_id": self.target_message_id, "current_emoji": self.current_emoji, "warn_records": self.warn_records}
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=4)

    def load_all_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.target_message_id = data.get("target_message_id")
                    self.current_emoji = data.get("current_emoji", "🤡")
                    self.warn_records = {int(k): v for k, v in data.get("warn_records", {}).items()}
            except: print("⚠️ 載入存檔失敗")

    async def setup_hook(self):
        self.load_all_data()
        guild = discord.Object(id=MY_GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        self.auto_backup_task.start()

    @tasks.loop(hours=6)
    async def auto_backup_task(self):
        await self.wait_until_ready()
        await self.perform_full_backup("自動備份")

    async def perform_full_backup(self, reason):
        channel = self.get_channel(BACKUP_CHANNEL_ID)
        if not channel: return
        self.save_all_data()
        await channel.send(f"📦 **[{reason}]**", files=[discord.File(DATA_FILE)])

bot = MyBot()

# --- 指令區 ---

@bot.tree.command(name="警告", description="記警告，滿 4 次觸發審核")
@app_commands.default_permissions(administrator=True)
async def warn(interaction: discord.Interaction, 成員: discord.Member, 理由: str):
    await interaction.response.defer()
    uid = 成員.id
    bot.warn_records[uid] = bot.warn_records.get(uid, 0) + 1
    count = bot.warn_records[uid]
    bot.save_all_data()

    embed = discord.Embed(title="⚠️ 警告發布", description=f"{成員.mention}\n理由：{理由}\n累計：`{count}` 次", color=0xFF0000)
    await interaction.followup.send(content=成員.mention, embed=embed)

    # 檢查是否滿 4 次
    if count >= 4:
        review_channel = bot.get_channel(ADMIN_REVIEW_CHANNEL_ID)
        if review_channel:
            review_embed = discord.Embed(
                title="🚨 警告達標：懲處審核",
                description=f"成員 {成員.mention} 警告已達 `{count}` 次。\n請管理員選擇處置方式：",
                color=discord.Color.dark_orange()
            )
            await review_channel.send(embed=review_embed, view=PunishmentView(成員))

@bot.tree.command(name="刪除警告", description="清除紀錄")
@app_commands.default_permissions(administrator=True)
async def clear_warn(interaction: discord.Interaction, 成員: discord.Member):
    await interaction.response.defer(ephemeral=True)
    if 成員.id in bot.warn_records:
        del bot.warn_records[成員.id]
        bot.save_all_data()
        await interaction.followup.send(f"✅ 已清除 {成員.mention} 紀錄")
    else:
        await interaction.followup.send("ℹ️ 無紀錄")

@bot.tree.command(name="公告", description="發送並置頂公告")
@app_commands.default_permissions(administrator=True)
async def announcement(interaction: discord.Interaction, 標題: str, 內容: str):
    await interaction.response.defer(ephemeral=True)
    try:
        pins = await interaction.channel.pins()
        for pin in pins:
            if pin.author.id == bot.user.id: await pin.unpin()
    except: pass
    msg = await interaction.channel.send(f"# 📢 {標題}\n\n{內容}\n---")
    await msg.pin()
    await interaction.followup.send("✅ 已發布公告")

@bot.tree.command(name="身分組", description="身分組訊息")
async def roles_setup(interaction: discord.Interaction, 標題: str, 內容: str, 表情: str = "🤡"):
    bot.current_emoji = 表情
    embed = discord.Embed(title=標題, description=內容 + f"\n\n點擊 {表情} 領取", color=0xFFAA00)
    await interaction.response.send_message("處理中...", ephemeral=True)
    msg = await interaction.channel.send(embed=embed)
    bot.target_message_id = msg.id
    bot.save_all_data()
    await msg.add_reaction(表情)

@bot.tree.command(name="備份數據", description="手動備份")
@app_commands.default_permissions(administrator=True)
async def manual_backup(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await bot.perform_full_backup(f"手動執行: {interaction.user.name}")
    await interaction.followup.send("✅ 備份完成")

@bot.tree.command(name="還原", description="還原數據")
@app_commands.default_permissions(administrator=True)
async def restore_all(interaction: discord.Interaction, 數據備份: discord.Attachment):
    await interaction.response.defer(ephemeral=True)
    async with aiohttp.ClientSession() as session:
        async with session.get(數據備份.url) as resp:
            if resp.status == 200:
                data = json.loads(await resp.text())
                bot.target_message_id = data.get("target_message_id")
                bot.current_emoji = data.get("current_emoji", "🤡")
                bot.warn_records = {int(k): v for k, v in data.get("warn_records", {}).items()}
                bot.save_all_data()
                await interaction.followup.send("✅ 還原成功")

# --- 事件監聽 ---
@bot.event
async def on_raw_reaction_add(p):
    if p.message_id == bot.target_message_id and str(p.emoji) == bot.current_emoji:
        g = bot.get_guild(p.guild_id)
        r = g.get_role(ROLE_ID)
        if r and p.member and not p.member.bot: await p.member.add_roles(r)

@bot.event
async def on_raw_reaction_remove(p):
    if p.message_id == bot.target_message_id and str(p.emoji) == bot.current_emoji:
        g = bot.get_guild(p.guild_id)
        r = g.get_role(ROLE_ID)
        try:
            m = await g.fetch_member(p.user_id)
            if r and m and not m.bot: await m.remove_roles(r)
        except: pass

bot.run(TOKEN)
