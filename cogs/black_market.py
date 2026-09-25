import random
from datetime import datetime, timedelta
import discord
from discord import app_commands
from discord.ext import commands, tasks
from utils import get_wallet_balance, modify_balance
from utils.database import get_db_connection

# 已經根據平衡性調整過價格與時效的黑市道具清單
BLACK_MARKET_ITEMS = {
    "broadcast": {
        "name": "全群廣播 / 大聲公",
        "price": 350,
        "hours": 0,  # 立即性消耗道具，無持續時間
        "type": "broadcast",
        "description": "向全群廣播你的重要訊息（約 1 週產出）",
    },
    "rename_card": {
        "name": "強制改名卡",
        "price": 550,
        "hours": 24,  # 持續 24 小時自動還原
        "type": "rename",
        "description": "強制更改受害者名字 24 小時",
    },
    "debuff_reverse": {
        "name": "發言倒裝句咒語",
        "price": 450,
        "hours": 1,
        "type": "reverse",
        "description": "讓目標 1 小時內發言變成倒裝句",
    },
    "debuff_mosaic": {
        "name": "打碼馬賽克眼鏡",
        "price": 300,
        "hours": 2,
        "type": "mosaic",
        "description": "讓目標 2 小時內發言隨機被馬賽克",
    },
}


def safe_modify_balance(user_id, amount):
  """🛡️ 萬能安全扣款包裝函式：自動相容各種不同的 modify_balance 參數定義"""
  try:
    return modify_balance(user_id, amount)
  except TypeError:
    try:
      return modify_balance(user_id, amount, tx_type="black_market", sender_id="BLACK_MARKET")
    except TypeError:
      try:
        return modify_balance(str(user_id), int(amount))
      except Exception as e:
        print(f"❌ 扣款執行失敗: {e}")
        return False
    except Exception as e:
      print(f"❌ 扣款執行失敗: {e}")
      return False
  except Exception as e:
    print(f"❌ 扣款執行失敗: {e}")
    return False


class TargetDebuffModal(discord.ui.Modal):

  def __init__(self, cost, debuff_type, item_name, hours):
    super().__init__(title=f"施放【{item_name}】")

    self.cost = cost
    self.debuff_type = debuff_type
    self.item_name = item_name
    self.hours = hours

    # 依照道具類型建立對應的輸入框
    if debuff_type == "broadcast":
      self.target_name = discord.ui.TextInput(
          label="廣播內容訊息",
          placeholder="請輸入你想向全群廣播公告的內容...",
          style=discord.TextStyle.paragraph,
          max_length=300,
      )
      self.add_item(self.target_name)
    else:
      self.target_name = discord.ui.TextInput(
          label="受害者名字、ID 或 @標註",
          placeholder="例如: @高貴又潔白的會長大人 或 輸入ID",
          max_length=50,
      )
      self.add_item(self.target_name)

      if debuff_type == "rename":
        self.new_nickname = discord.ui.TextInput(
            label="強制改為的新名稱",
            placeholder="請輸入想惡整他的新暱稱...",
            max_length=32,
        )
        self.add_item(self.new_nickname)

  async def on_submit(self, interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    user_id = str(interaction.user.id)

    # 1. 再次檢查錢包餘額
    current_coins = get_wallet_balance(user_id)
    if current_coins < self.cost:
      await interaction.followup.send(
          f"❌ 你的 SU 幣不足！購買【{self.item_name}】需要 `{self.cost} SU幣`，你目前只有 `{current_coins} SU幣`。",
          ephemeral=True,
      )
      return

    guild = interaction.guild

    # 處理「全群廣播」的特殊邏輯
    if self.debuff_type == "broadcast":
      broadcast_content = self.target_name.value.strip()

      success = safe_modify_balance(user_id, -self.cost)
      if not success:
        await interaction.followup.send(
            "❌ 扣款失敗，請稍後再試或聯繫管理員。", ephemeral=True
        )
        return

      await interaction.followup.send(
          f"📢 廣播成功！已消耗 `{self.cost} SU幣` 發送大聲公。",
          ephemeral=True,
      )

      target_channel = interaction.channel
      if target_channel:
        await target_channel.send(
            f"📢 **【黑市大聲公 / 全群廣播】**\n"
            f"來自 {interaction.user.mention} 的重金宣告：\n> {broadcast_content}"
        )
      return

    # 解析並尋找目標成員（強化防呆模糊搜尋）
    target_str = self.target_name.value.strip()
    target_member = None

    if target_str.startswith("<@") and target_str.endswith(">"):
      clean_id = target_str.strip("<@!>")
      if clean_id.isdigit():
        target_member = guild.get_member(int(clean_id))
        if not target_member:
          try:
            target_member = await guild.fetch_member(int(clean_id))
          except Exception:
            pass
    elif target_str.isdigit():
      target_member = guild.get_member(int(target_str))
      if not target_member:
        try:
          target_member = await guild.fetch_member(int(target_str))
        except Exception:
          pass

    if not target_member:
      for m in guild.members:
        m_name = m.name.lower() if m.name else ""
        m_display = m.display_name.lower() if m.display_name else ""
        m_global = m.global_name.lower() if m.global_name else ""
        t_lower = target_str.lower()

        if t_lower in m_name or t_lower in m_display or t_lower in m_global:
          target_member = m
          break

    if not target_member:
      await interaction.followup.send(
          f"❌ 找不到名為或代號為 `{target_str}` 的成員！\n"
          f"💡 **建議：** 請直接使用 `@標註` 該成員，或是輸入對方的 ID 進行施法最為準確！",
          ephemeral=True,
      )
      return

    if target_member.bot:
      await interaction.followup.send("❌ 不能對機器人施法！", ephemeral=True)
      return

    if target_member.id == interaction.user.id and self.debuff_type != "rename":
      await interaction.followup.send("❌ 不能對自己施展詛咒！", ephemeral=True)
      return

    # 2. 執行安全扣款
    success = safe_modify_balance(user_id, -self.cost)
    if not success:
      await interaction.followup.send(
          "❌ 扣款失敗，請稍後再試或聯繫管理員。", ephemeral=True
      )
      return

    old_nick = target_member.display_name

    # 如果是強制改名卡
    if self.debuff_type == "rename":
      new_nick = self.new_nickname.value.strip()
      try:
        await target_member.edit(
            nick=new_nick,
            reason=f"黑市強制改名卡由 {interaction.user} 購買施放",
        )
      except discord.Forbidden:
        await interaction.followup.send(
            "❌ 機器人權限不足或身分組低於對方，無法改名！已全額退款。",
            ephemeral=True,
        )
        safe_modify_balance(user_id, self.cost)
        return
      except discord.HTTPException as e:
        await interaction.followup.send(
            f"❌ 改名失敗 ({e})！已全額退款。", ephemeral=True
        )
        safe_modify_balance(user_id, self.cost)
        return

    # 3. 寫入資料庫記錄狀態（支援跨重啟與背景檢查）
    key = f"{guild.id}_{target_member.id}"
    expire_at_str = (datetime.now() + timedelta(hours=self.hours)).isoformat()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO active_debuffs (id, guild_id, user_id, type, old_nickname, expire_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (
            key,
            guild.id,
            target_member.id,
            self.debuff_type,
            old_nick,
            expire_at_str,
        ),
    )
    conn.commit()
    conn.close()

    if self.debuff_type == "rename":
      await interaction.followup.send(
          f"🎯 施法成功！已將 **{old_nick}** 強制改名為 **{new_nick}**，持續 {self.hours} 小時！已扣除 `{self.cost} SU幣`。",
          ephemeral=True,
      )
      if interaction.channel:
        await interaction.channel.send(
            f"🔀 **【黑市整人】** {interaction.user.mention} 對 **{old_nick}** 使用了 **強制改名卡**！"
        )
      return

    await interaction.followup.send(
        f"🎯 施法成功！已對 **{target_member.display_name}** 施加【{self.item_name}】，持續 {self.hours} 小時！已扣除 `{self.cost} SU幣`。",
        ephemeral=True,
    )

    if interaction.channel:
      await interaction.channel.send(
          f"🔮 **【黑市詛咒】** {interaction.user.mention} 成功對 **{target_member.display_name}** 施展了 **{self.item_name}**！"
      )


class BlackMarketSelect(discord.ui.Select):

  def __init__(self):
    options = [
        discord.SelectOption(
            label=item["name"],
            description=(
                f"售價: {item['price']} SU幣 | {item['description']}"
            ),
            value=key,
        )
        for key, item in BLACK_MARKET_ITEMS.items()
    ]
    super().__init__(
        placeholder="點此選購黑市整人道具...",
        min_values=1,
        max_values=1,
        options=options,
    )

  async def callback(self, interaction: discord.Interaction):
    item_key = self.values[0]
    item = BLACK_MARKET_ITEMS[item_key]
    user_id = str(interaction.user.id)

    current_coins = get_wallet_balance(user_id)
    if current_coins < item["price"]:
      await interaction.response.send_message(
          f"❌ 你的 SU 幣不足！【{item['name']}】售價為 `{item['price']} SU幣`，你目前只有 `{current_coins} SU幣`。",
          ephemeral=True,
      )
      return

    await interaction.response.send_modal(
        TargetDebuffModal(
            cost=item["price"],
            debuff_type=item["type"],
            item_name=item["name"],
            hours=item["hours"],
        )
    )


class BlackMarketView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)
    self.add_item(BlackMarketSelect())


class BlackMarketCog(commands.Cog):

  def __init__(self, bot):
    self.bot = bot
    self.check_debuffs_loop.start()

  def cog_unload(self):
    self.check_debuffs_loop.cancel()

  @tasks.loop(minutes=1)
  async def check_debuffs_loop(self):
    """每分鐘自動檢查並解除過期的詛咒與強制改名狀態"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
      cursor.execute("SELECT id, guild_id, user_id, type, old_nickname, expire_at FROM active_debuffs")
      rows = cursor.fetchall()
    except Exception:
      conn.close()
      return

    now = datetime.now()
    for row in rows:
      row_id, guild_id, user_id, debuff_type, old_nickname, expire_at_str = row
      try:
        expire_at = datetime.fromisoformat(expire_at_str)
      except Exception:
        expire_at = now

      if now >= expire_at:
        guild = self.bot.get_guild(guild_id)
        if guild:
          member = guild.get_member(user_id)
          if not member:
            try:
              member = await guild.fetch_member(user_id)
            except Exception:
              member = None

          if member and debuff_type == "rename":
            try:
              await member.edit(nick=old_nickname, reason="黑市強制改名時間到期自動還原")
              if guild.system_channel:
                await guild.system_channel.send(
                    f"✨ **【黑市解除】** **{old_nickname}** 的強制改名時間已到期，已自動恢復原本暱稱！"
                )
            except Exception:
              pass

        cursor.execute("DELETE FROM active_debuffs WHERE id = ?", (row_id,))
        conn.commit()

    conn.close()

  @check_debuffs_loop.before_loop
  async def before_check_debuffs(self):
    await self.bot.wait_until_ready()

  @app_commands.command(
      name="黑市", description="開啟地下黑市，購買整人與詛咒道具"
  )
  async def black_market(self, interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    embed = discord.Embed(
        title="🏴‍☠️ 地下黑市道具坊",
        description=(
            "歡迎來到見不得光的黑市！這裡的道具可以對其他人施加惡整詛咒或發布全群廣播。\n購買時將直接從你的"
            " **SU 幣錢包** 中扣款，請謹慎使用！"
        ),
        color=0x2b2d31,
    )
    embed.add_field(
        name="目前黑市商品",
        value=(
            "• **📢 全群廣播 / 大聲公** (350 SU幣 / 立即生效)\n"
            "• **🔀 強制改名卡** (550 SU幣 / 24小時自動還原)\n"
            "• **🔀 發言倒裝句咒語** (450 SU幣 / 1小時)\n"
            "• **🧩 打碼馬賽克眼鏡** (300 SU幣 / 2小時)"
        ),
        inline=False,
    )
    view = BlackMarketView()
    await interaction.followup.send(embed=embed, view=view, ephemeral=True)


async def setup(bot):
  await bot.add_cog(BlackMarketCog(bot))
