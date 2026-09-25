import random
import re
import discord
from discord.ext import commands

# 包含各種經典口語、台語粗口與情緒用詞的精準黑名單辭庫
BAD_WORDS = [
    "幹", "淦", "干", "操", "譟", "靠", "耖",
    "靠北", "靠杯", "靠腰", "靠夭", "靠北沙小", "靠北三小",
    "三小", "沙小", "供三小", "講三小", "工三小", "派沙小", "殺小", "衝殺小",
    "媽的", "他媽的", "馬的", "你媽死了", "耖你媽",
    "機掰", "雞掰", "擊敗", "GY", "機歪", "雞巴",
    "白爛", "白癡", "北七", "87", "腦殘", "智障", "惱羞", "破麻", "滾蛋", "去死", "傻逼", "弱智",
    "SB", "sb", "nmsl", "NMSL", "Fuck"
]

# 🛡️ 白名單辭庫：包含這些詞彙的訊息將「絕對不會」被誤殺過濾
WHITE_LIST_WORDS = [
    "幹部", "幹話", "操作", "靠近", "依靠", "主幹", "幹嘛", "乾脆"
]

# 被攔截後，隨機挑選一句模仿他本人講出來的溫馨／搞笑話語庫
REPLACE_MESSAGES = [
    "我愛你",
    "今天天氣真好，大家辛苦了！",
    "其實我超喜歡摸魚的 >_<",
    "會長我大哥！",
    "我今天又肚子餓了，有人要吃宵夜嗎？",
    "祝大家抽卡都十連雙金！",
    "不好意思，我剛剛手指抽筋了",
    "superidol的笑容都没你的甜",
    "本來應該從從容容、游刃有餘",
    "唉呦，我老爸得了MVP!!",
    "其實我是個大好人",
    "你可曾在雪山救過一隻狐狸?！",
]

class WordFilterCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # 快取每個頻道的 Webhook，避免每次都要重複查詢與建立
        self.webhook_cache = {}

    def contains_bad_words(self, content: str) -> bool:
        """精準過濾檢查：排除網址、白名單，並確切比對字詞"""
        # 1. 如果包含網址 (http:// 或 https:// 或 www.)，直接放行，絕不誤殺！
        if re.search(r'https?://|www\.', content, re.IGNORECASE):
            return False

        # 2. 檢查白名單，若命中則放行
        for white_word in WHITE_LIST_WORDS:
            if white_word in content:
                return False

        # 3. 逐一檢查黑名單
        for word in BAD_WORDS:
            # 如果是短英文（如 sb, gy），要求獨立成單字或符合邊界，避免英文字母內嵌被誤殺
            if word.ascii and len(word) <= 3:
                pattern = rf'\b{re.escape(word)}\b'
                if re.search(pattern, content, re.IGNORECASE):
                    return True
            else:
                if word in content:
                    return True
        return False

    async def get_or_create_webhook(self, channel):
        """取得或建立專用 Webhook（帶快取機制，防止超出 Discord 頻道 Webhook 數量上限）"""
        if channel.id in self.webhook_cache:
            webhook = self.webhook_cache[channel.id]
            try:
                # 驗證 webhook 是否還存在
                if webhook and webhook.channel.id == channel.id:
                    return webhook
            except Exception:
                pass

        try:
            webhooks = await channel.webhooks()
            webhook = discord.utils.get(webhooks, name="SystemTextReplacer")
            
            if not webhook:
                webhook = await channel.create_webhook(name="SystemTextReplacer")
            
            self.webhook_cache[channel.id] = webhook
            return webhook
        except Exception as e:
            print(f"❌ 獲取/建立 Webhook 失敗: {e}")
            return None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # 忽略機器人自己發出的訊息
        if message.author.bot:
            return

        content = message.content

        # 透過精準過濾邏輯檢查是否觸發
        if not self.contains_bad_words(content):
            return

        # 觸發後處理
        try:
            await message.delete()
        except discord.HTTPException:
            pass

        try:
            webhook = await self.get_or_create_webhook(message.channel)
            if not webhook:
                # 如果沒有 Webhook 權限或建失敗，改用普通文字備用
                await message.channel.send(f"{message.author.mention} 剛剛不小心講了好話：我愛你")
                return

            avatar_url = message.author.avatar.url if message.author.avatar else message.author.default_avatar.url
            display_name = message.author.display_name
            selected_text = random.choice(REPLACE_MESSAGES)

            await webhook.send(
                content=selected_text,
                username=display_name,
                avatar_url=avatar_url,
            )

        except Exception as e:
            print(f"❌ 導正訊息發生錯誤：{e}")
            await message.channel.send(f"{message.author.mention} 剛剛不小心講了好話：我愛你")

async def setup(bot):
    await bot.add_cog(WordFilterCog(bot))
