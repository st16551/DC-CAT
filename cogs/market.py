# ==================================================
# 檔案名稱：cogs/market.py
# 檔案用途：市集買賣與私密討論房系統（支援持久化常駐按鈕）
# ==================================================

import asyncio
import discord
from discord import app_commands
from discord.ext import commands


class TradeRoomView(discord.ui.View):
    def __init__(
        self,
        owner: discord.Member,
        buyer: discord.Member,
        item_name: str,
        trade_type: str,
        note: str = None,
        market_message: discord.Message = None,
    ):
        super().__init__(timeout=None)  # 永久常駐，重啟後按鈕仍然有效
        self.owner = owner
        self.buyer = buyer
        self.item_name = item_name
        self.trade_type = trade_type
        self.note = note
        self.market_message = market_message

    @discord.ui.button(label="完成交易", style=discord.ButtonStyle.success, custom_id="market_complete_trade_btn_v1")
    async def complete_trade(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id not in [self.owner.id, self.buyer.id]:
            await interaction.response.send_message(
                "❌ 只有交易雙方可以操作此按鈕！", ephemeral=True
            )
            return

        button.disabled = True
        await interaction.response.edit_message(view=self)

        # 自動刪除原本在市場頻道中的刊登訊息
        if self.market_message:
            try:
                await self.market_message.delete()
            except Exception as e:
                print(f"❌ 刪除市場刊登訊息失敗: {e}")

        msg = await interaction.channel.send(
            "✅ 交易完成！本私密討論房將在 **10 秒後自動刪除**..."
        )
        for i in range(9, -1, -1):
            await asyncio.sleep(1)
            try:
                await msg.edit(
                    content=f"✅ 交易完成！本私密討論房將在 **{i} 秒後自動刪除**..."
                )
            except discord.HTTPException:
                break
                
        try:
            await interaction.channel.delete()
        except Exception as e:
            print(f"❌ 刪除討論房頻道失敗: {e}")


class MarketCardView(discord.ui.View):
    def __init__(
        self,
        owner: discord.Member,
        item_name: str,
        amount: str,
        trade_type: str,
        note: str = None,
    ):
        super().__init__(timeout=None)  # 永久常駐
        self.owner = owner
        self.item_name = item_name
        self.amount = amount
        self.trade_type = trade_type
        self.note = note

        btn_label = "我要購買" if trade_type == "SELL" else "我要出售"
        btn_style = (
            discord.ButtonStyle.primary
            if trade_type == "SELL"
            else discord.ButtonStyle.success
        )
        # 給定一個固定的 custom_id 確保持久化運作
        custom_id_val = f"market_card_action_{trade_type.lower()}"
        
        btn = discord.ui.Button(label=btn_label, style=btn_style, custom_id=custom_id_val)
        btn.callback = self.on_click
        self.add_item(btn)

    async def on_click(self, interaction: discord.Interaction):
        if interaction.user.id == self.owner.id:
            await interaction.response.send_message(
                "❌ 你不能與自己發起的刊登進行交易！", ephemeral=True
            )
            return

        guild = interaction.guild
        buyer = interaction.user
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            self.owner: discord.PermissionOverwrite(
                read_messages=True, send_messages=True
            ),
            buyer: discord.PermissionOverwrite(
                read_messages=True, send_messages=True
            ),
            guild.me: discord.PermissionOverwrite(
                read_messages=True, send_messages=True
            ),
        }

        action_name = "購買" if self.trade_type == "SELL" else "出售"
        # 簡易過濾頻道名稱非法字元
        safe_item_name = "".join(c for c in self.item_name if c.isalnum() or c in (" ", "-", "_")).strip()
        safe_item_name = safe_item_name.replace(" ", "-")[:15]
        channel_name = f"交易-{safe_item_name}-{buyer.name[:4]}"
        
        try:
            trade_channel = await guild.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                category=interaction.channel.category,
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ 建立私密討論房失敗: {e}", ephemeral=True)
            return

        description = (
            f"歡迎 {self.owner.mention} 與 {buyer.mention}！\n\n"
            f"📦 交易物品：**{self.item_name}**\n"
            f"🔢 數量：**{self.amount}**\n"
        )
        if self.note:
            description += f"📝 備註：{self.note}\n"

        description += (
            "\n請雙方在此溝通細節，完成交易後點擊下方按鈕即可關閉此頻道。"
        )

        embed = discord.Embed(
            title=f"🔒 私密交易討論房 ({action_name})",
            description=description,
            color=discord.Color.gold(),
        )

        market_msg = interaction.message
        room_view = TradeRoomView(
            self.owner,
            buyer,
            self.item_name,
            self.trade_type,
            self.note,
            market_message=market_msg,
        )

        await trade_channel.send(
            content=f"{self.owner.mention} {buyer.mention}",
            embed=embed,
            view=room_view,
        )
        await interaction.response.send_message(
            f"✅ 已為您建立私密討論房：{trade_channel.mention}", ephemeral=True
        )


class MarketCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # 註冊持久化 Views，防止機器人重啟後按鈕失效
        self.bot.add_view(TradeRoomView(None, None, "", ""))
        self.bot.add_view(MarketCardView(None, "", "", "SELL"))
        self.bot.add_view(MarketCardView(None, "", "", "BUY"))

    @app_commands.command(name="賣", description="刊登賣單（出售卡片或道具，可附圖）")
    @app_commands.describe(
        物品名稱="請輸入要賣的物品或卡片名稱",
        數量="請輸入數量 (例如: 1張)",
        備註="選填：想補充的說明、價格或面交地點等",
        圖片="選填：點擊此欄位或直接貼上/上傳圖片",
    )
    async def sell_item(
        self,
        interaction: discord.Interaction,
        物品名稱: str,
        數量: str,
        備註: str = None,
        圖片: discord.Attachment = None,
    ):
        embed = discord.Embed(title="🏷️ 【公會市集】出售刊登", color=discord.Color.blue())
        embed.add_field(name="物品名稱", value=物品名稱, inline=True)
        embed.add_field(name="數量", value=數量, inline=True)
        if 備註:
            embed.add_field(name="備註", value=備註, inline=False)
        embed.add_field(name="賣家", value=interaction.user.mention, inline=False)

        if 圖片:
            embed.set_image(url=圖片.url)

        embed.set_footer(text="點擊下方按鈕將建立私密討論房談價與面交！")

        view = MarketCardView(
            owner=interaction.user,
            item_name=物品名稱,
            amount=數量,
            trade_type="SELL",
            note=備註,
        )
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="收", description="刊登徵求單（收購卡片或道具，可附圖）")
    @app_commands.describe(
        物品名稱="請輸入想要收購的物品或卡片名稱",
        數量="請輸入徵求數量 (例如: 1張)",
        備註="選填：想補充的說明、預算或收購條件等",
        圖片="選填：點擊此欄位或直接貼上/上傳圖片",
    )
    async def buy_item(
        self,
        interaction: discord.Interaction,
        物品名稱: str,
        數量: str,
        備註: str = None,
        圖片: discord.Attachment = None,
    ):
        embed = discord.Embed(title="🛒 【公會市集】徵求刊登", color=discord.Color.green())
        embed.add_field(name="物品名稱", value=物品名稱, inline=True)
        embed.add_field(name="數量", value=數量, inline=True)
        if 備註:
            embed.add_field(name="備註", value=備註, inline=False)
        embed.add_field(name="買家", value=interaction.user.mention, inline=False)

        if 圖片:
            embed.set_image(url=圖片.url)

        embed.set_footer(text="點擊下方按鈕將建立私密討論房談價與面交！")

        view = MarketCardView(
            owner=interaction.user,
            item_name=物品名稱,
            amount=數量,
            trade_type="BUY",
            note=備註,
        )
        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(MarketCog(bot))
