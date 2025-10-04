import os
import random
import json
import discord
from discord.ext import commands
from collections import defaultdict
from datetime import datetime, timedelta
from keep_alive import keep_alive
# the newest OpenAI model is "gpt-5" which was released August 7, 2025.
# do not change this unless explicitly requested by the user
from openai import OpenAI

# -----------------------
# Discord Bot 設定
# -----------------------
intents = discord.Intents.all()
intents.message_content = True  # 確保可以讀取訊息內容
bot = commands.Bot(command_prefix="!", intents=intents)

LEVEL_FILE = "levels.json"
WELCOME_CONFIG_FILE = "welcome_config.json"
JOIN_DM_FILE = "join_dm.json"
QA_FILE = "qa.json"
ANTISPAM_FILE = "antispam.json"

# 讀取等級資料
if os.path.exists(LEVEL_FILE):
    with open(LEVEL_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        user_xp = {int(k): v for k, v in data.get("xp", {}).items()}
        user_level = {int(k): v for k, v in data.get("level", {}).items()}
else:
    user_xp = {}
    user_level = {}

# 載入歡迎設定
if os.path.exists(WELCOME_CONFIG_FILE):
    with open(WELCOME_CONFIG_FILE, "r", encoding="utf-8") as f:
        welcome_config = json.load(f)
else:
    welcome_config = {}  # {guild_id: {"channel": channel_id, "message": msg}}

# 載入加入 DM 設定
if os.path.exists(JOIN_DM_FILE):
    with open(JOIN_DM_FILE, "r", encoding="utf-8") as f:
        join_dm_config = json.load(f)
else:
    join_dm_config = {}  # {guild_id: "message"}

# 載入問答設定
if os.path.exists(QA_FILE):
    with open(QA_FILE, "r", encoding="utf-8") as f:
        qa_data = json.load(f)
else:
    qa_data = {}  # {guild_id: {"問題": "回答"}}

# 載入防刷屏設定
if os.path.exists(ANTISPAM_FILE):
    with open(ANTISPAM_FILE, "r", encoding="utf-8") as f:
        antispam_config = json.load(f)
else:
    antispam_config = {}  # {guild_id: {"limit":5, "window":10, "mute":600}}

# 紀錄訊息時間 {guild_id: {user_id: [timestamps]}}
user_messages = defaultdict(lambda: defaultdict(list))

# 儲存等級資料
def save_levels():
    data = {"xp": user_xp, "level": user_level}
    with open(LEVEL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

# 等級系統
def add_xp(user_id, xp_gain=5):
    old_xp = user_xp.get(user_id, 0)
    old_level = user_level.get(user_id, 1)
    new_xp = old_xp + xp_gain
    new_level = old_level
    if new_xp >= old_level * 100:
        new_level += 1
        new_xp = 0
        user_level[user_id] = new_level
        user_xp[user_id] = new_xp
        save_levels()
        return new_level
    user_xp[user_id] = new_xp
    user_level[user_id] = new_level
    save_levels()
    return None

# -----------------------
# Web 伺服器保持 Replit 在線
# -----------------------
keep_alive()

# -----------------------
# Discord Bot 事件
# -----------------------
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ 已登入為 {bot.user}")

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return
    
    guild_id = str(message.guild.id)
    
    # 防刷屏檢測
    if guild_id in antispam_config:
        limit = antispam_config[guild_id]["limit"]
        window = antispam_config[guild_id]["window"]
        mute = antispam_config[guild_id]["mute"]
        
        now = datetime.utcnow()
        user_id = message.author.id
        
        # 紀錄訊息時間戳
        user_messages[guild_id][user_id].append(now)
        
        # 移除過期紀錄
        user_messages[guild_id][user_id] = [
            t for t in user_messages[guild_id][user_id] if (now - t).seconds <= window
        ]
        
        # 偵測刷屏
        if len(user_messages[guild_id][user_id]) >= limit:
            try:
                until = discord.utils.utcnow() + timedelta(seconds=mute)
                await message.author.timeout(until, reason="刷屏/洗版")
                
                await message.channel.send(
                    f"⚠️ {message.author.mention} 因刷屏已被禁言 {mute} 秒。"
                )
            except discord.Forbidden:
                await message.channel.send("❌ 我沒有權限禁言這個成員。")
            
            user_messages[guild_id][user_id].clear()
            await bot.process_commands(message)
            return
    
    # 檢查自定義問答回覆
    if guild_id in qa_data:
        question = message.content.lower().strip()
        if question in qa_data[guild_id]:
            answer = qa_data[guild_id][question]
            await message.channel.send(answer)
            # 如果有匹配的問答，就不再處理其他自動回覆
            await bot.process_commands(message)
            return
    
    # 固定自動回覆
    if "早安" in message.content:
        await message.channel.send("早安呀 🌞 祝你今天順利！")
    if "掰掰" in message.content:
        await message.channel.send("掰掰 👋 下次見！")
    
    # 等級系統
    if not message.author.bot:
        new_level = add_xp(message.author.id, xp_gain=10)
        if new_level:
            await message.channel.send(f"🎉 恭喜 {message.author.mention} 升到 Lv.{new_level}！")
    
    await bot.process_commands(message)

@bot.event
async def on_member_join(member):
    guild_id = str(member.guild.id)
    
    # 發送公開歡迎訊息
    if guild_id in welcome_config:
        channel_id = welcome_config[guild_id]["channel"]
        message = welcome_config[guild_id]["message"]
        
        channel = member.guild.get_channel(channel_id)
        if channel:
            # 允許訊息內使用 {user} 來代表新成員
            await channel.send(message.replace("{user}", member.mention))
    
    # 發送私人 DM 訊息
    if guild_id in join_dm_config:
        dm_message = join_dm_config[guild_id]
        try:
            # 允許訊息中使用 {user} 當作佔位符
            await member.send(dm_message.replace("{user}", member.mention))
        except discord.Forbidden:
            # 成員關閉了 DM 或拒收訊息
            print(f"⚠️ 無法私訊 {member.name}，可能關閉了 DM。")

# -----------------------
# Discord Slash 指令
# -----------------------
@bot.tree.command(name="set_welcome", description="設定伺服器的歡迎訊息與頻道")
async def set_welcome(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    message: str
):
    guild_id = str(interaction.guild.id)
    welcome_config[guild_id] = {"channel": channel.id, "message": message}

    # 存檔
    with open(WELCOME_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(welcome_config, f, ensure_ascii=False, indent=4)

    await interaction.response.send_message(
        f"✅ 已設定加入訊息！\n頻道：{channel.mention}\n訊息：{message}"
    )

@bot.tree.command(name="set_join_dm", description="設定伺服器新成員加入時的私訊")
async def set_join_dm(interaction: discord.Interaction, message: str):
    guild_id = str(interaction.guild.id)
    join_dm_config[guild_id] = message

    # 存檔
    with open(JOIN_DM_FILE, "w", encoding="utf-8") as f:
        json.dump(join_dm_config, f, ensure_ascii=False, indent=4)

    await interaction.response.send_message(f"✅ 已設定加入時的 DM 訊息：{message}")

@bot.tree.command(name="set_antispam", description="設定防刷屏參數")
async def set_antispam(interaction: discord.Interaction, limit: int, window: int, mute: int):
    guild_id = str(interaction.guild.id)
    antispam_config[guild_id] = {"limit": limit, "window": window, "mute": mute}

    with open(ANTISPAM_FILE, "w", encoding="utf-8") as f:
        json.dump(antispam_config, f, ensure_ascii=False, indent=4)

    await interaction.response.send_message(
        f"✅ 防刷屏已設定：{window} 秒內超過 {limit} 則訊息 → 禁言 {mute} 秒"
    )

@bot.tree.command(name="set_answer", description="設定問題的自動回答")
async def set_answer(interaction: discord.Interaction, question: str, answer: str):
    guild_id = str(interaction.guild.id)
    if guild_id not in qa_data:
        qa_data[guild_id] = {}
    qa_data[guild_id][question.lower()] = answer

    with open(QA_FILE, "w", encoding="utf-8") as f:
        json.dump(qa_data, f, ensure_ascii=False, indent=4)

    await interaction.response.send_message(
        f"✅ 已設定 `{question}` 的回答：{answer}"
    )

@bot.tree.command(name="hello", description="跟機器人打招呼")
async def hello(interaction: discord.Interaction):
    await interaction.response.send_message("你好，我是現代 Slash 指令機器人 🤖")

@bot.tree.command(name="ping", description="測試延遲")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! 🏓 延遲 {round(bot.latency * 1000)}ms")

@bot.tree.command(name="say", description="讓機器人說話")
async def say(interaction: discord.Interaction, message: str):
    await interaction.response.send_message(message)

@bot.tree.command(name="repeat", description="重複訊息")
async def repeat(interaction: discord.Interaction, times: int, message: str):
    if times > 5:
        await interaction.response.send_message("⚠️ 不能超過 5 次，避免刷屏！")
        return
    for _ in range(times):
        if interaction.channel and hasattr(interaction.channel, 'send'):
            try:
                await interaction.channel.send(message)
            except (discord.Forbidden, discord.HTTPException):
                pass
    await interaction.response.send_message("✅ 已完成重複")

@bot.tree.command(name="dm", description="私訊伺服器成員")
async def dm(interaction: discord.Interaction, member: discord.Member, message: str):
    try:
        await member.send(message)
        await interaction.response.send_message(f"✅ 已私訊 {member.display_name}")
    except discord.Forbidden:
        await interaction.response.send_message("⚠️ 對方關閉了私訊，無法發送！")

@bot.tree.command(name="dm_user", description="私訊任意 Discord 使用者（非伺服器成員也可）")
async def dm_user(interaction: discord.Interaction, user_id: str, message: str):
    try:
        if not user_id.isdigit():
            await interaction.response.send_message("⚠️ 使用者 ID 必須是數字！")
            return

        try:
            user = await bot.fetch_user(int(user_id))
            if user:
                await user.send(message)
                await interaction.response.send_message(f"✅ 已成功私訊 {user.name}")
            else:
                await interaction.response.send_message("⚠️ 找不到這個使用者！請確認 ID 是否正確。")
        except (discord.NotFound, discord.HTTPException):
            await interaction.response.send_message("⚠️ 找不到這個使用者！請確認 ID 是否正確。")
        except Exception as e:
            await interaction.response.send_message(f"❌ 發生錯誤：{e}")

    except discord.Forbidden:
        await interaction.response.send_message(
            "⚠️ 無法私訊此使用者，可能對方關閉了 DM 或未加好友。"
        )
    except Exception as e:
        await interaction.response.send_message(f"❌ 發生錯誤：{e}")

@bot.tree.command(name="dice", description="擲骰子")
async def dice(interaction: discord.Interaction):
    result = random.randint(1, 6)
    await interaction.response.send_message(f"🎲 你擲出了 **{result}**")

@bot.tree.command(name="choose", description="隨機選一個選項")
async def choose(interaction: discord.Interaction, option1: str, option2: str, option3: str = None):
    options = [option1, option2]
    if option3:
        options.append(option3)
    choice = random.choice(options)
    await interaction.response.send_message(f"🔮 我選擇了：**{choice}**")

@bot.tree.command(name="level", description="查詢等級")
async def level(interaction: discord.Interaction, member: discord.Member = None):
    target_member = member or interaction.user
    lvl = user_level.get(target_member.id, 1)
    xp = user_xp.get(target_member.id, 0)
    await interaction.response.send_message(f"📊 {target_member.display_name} 的等級：Lv.{lvl} (XP: {xp})")

@bot.tree.command(name="rank", description="查看排行榜")
async def rank(interaction: discord.Interaction, top: int = 5):
    if not user_level:
        await interaction.response.send_message("📉 目前還沒有任何數據！")
        return
    ranking = sorted(user_level.keys(), key=lambda uid: (user_level.get(uid,1), user_xp.get(uid,0)), reverse=True)
    top = min(top, len(ranking))
    msg = "🏆 **等級排行榜** 🏆\n"
    for i, uid in enumerate(ranking[:top], start=1):
        guild_member = interaction.guild.get_member(uid) if interaction.guild else None
        name = guild_member.display_name if guild_member else f"未知用戶({uid})"
        lvl = user_level.get(uid, 1)
        xp = user_xp.get(uid, 0)
        msg += f"{i}. {name} — Lv.{lvl} (XP: {xp})\n"
    await interaction.response.send_message(msg)

# -----------------------
# AI 回覆 Slash 指令
# -----------------------
@bot.tree.command(name="ai", description="AI 自動回覆訊息")
async def ai(interaction: discord.Interaction, message: str):
    await interaction.response.defer()  # 表示稍後回覆，避免 Discord 超時
    try:
        # the newest OpenAI model is "gpt-5" which was released August 7, 2025.
        # do not change this unless explicitly requested by the user
        openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = openai_client.chat.completions.create(
            model="gpt-5",
            messages=[
                {"role": "system", "content": "你是一個幽默又友善的 Discord 機器人。"},
                {"role": "user", "content": message}
            ],
            max_tokens=150
        )
        answer = response.choices[0].message.content
        if answer:
            await interaction.followup.send(answer)
        else:
            await interaction.followup.send("AI 沒有回覆內容")
    except Exception as e:
        await interaction.followup.send(f"❌ 發生錯誤：{e}")

# -----------------------
# 啟動 Bot
# -----------------------
if __name__ == "__main__":
    TOKEN = os.environ['DISCORD_TOKEN']
    bot.run(TOKEN)