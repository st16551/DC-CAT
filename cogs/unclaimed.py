import sqlite3
import discord
from discord import app_commands
from discord.ext import commands

class ClaimSelectMenu(discord.ui.Select):
    def __init__(self, records: list):
        options = []
        for row_id, item, amount, leader in records:
            leader_str = leader if leader else "團長"
            label = f"{item} ({amount:,}元) - 找:{leader_str}"
            options.append(discord.SelectOption(label=label[:100], value=str(row_id)))

        super().__init__(
            placeholder="🔘 請選擇想要先領取的特定項目（可複選）...",
            min_values=1,
            max_values=len(options),
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()


class FlexibleClaimView(discord.ui.View):
    def __init__(self, bot, member_name: str, records: list):
        super().__init__(timeout=120)
        self.bot = bot
        self.member_name = member_name
        self.records = records  
        
        self.select_menu = ClaimSelectMenu(records)
        self.add_item(self.select_menu)

    async def process_claims_and_sync(self, row_ids):
        """處理領取、刪除資料庫紀錄，並檢查對應面板是否該自動刪除"""
        try:
            conn = sqlite3.connect("guild_database.db")
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            affected_message_ids = set()

            for r_id in row_ids:
                cursor.execute("SELECT message_id, channel_id, leader_name, item_name FROM split_records WHERE id = ?", (int(r_id),))
                row = cursor.fetchone()
                if row and row["message_id"]:
                    affected_message_ids.add((row["message_id"], row["channel_id"]))

                cursor.execute("DELETE FROM split_records WHERE id = ?", (int(r_id),))
            
            conn.commit()

            for msg_id, ch_id in affected_message_ids:
                cursor.execute("SELECT COUNT(*) as cnt FROM split_records WHERE message_id = ?", (msg_id,))
                res = cursor.fetchone()
                remaining_count = res["cnt"] if res else 0

                if remaining_count == 0:
                    channel = self.bot.get_channel(ch_id)
                    if not channel:
                        try:
                            channel = await self.bot.fetch_channel(ch_id)
                        except Exception:
                            continue
                    try:
                        message = await channel.fetch_message(msg_id)
                        if message:
                            await message.delete()
                    except Exception as ex:
                        print(f"❌ 自動刪除已完結面板訊息失敗 ({msg_id}): {ex}")
                else:
                    channel = self.bot.get_channel(ch_id)
                    if not channel:
                        try:
                            channel = await self.bot.fetch_channel(ch_id)
                        except Exception:
                            continue
                    try:
                        message = await channel.fetch_message(msg_id)
                        if message and message.view:
                            view = message.view
                            if self.member_name in view.status:
                                view.status[self.member_name] = True
                                view.update_buttons()
                                embed = discord.Embed(
                                    title="💰 戰利品分錢面板",
                                    description=f"**物品**：{view.item_name}\n**總額**：`{view.total:,}` | **每人分得**：`{view.per_person:,}`",
                                    color=discord.Color.gold()
                                )
                                embed.set_footer(text=f"發起人：{view.leader.display_name}")
                                await message.edit(embed=embed, view=view)
                    except Exception as ex:
                        print(f"❌ 更新實體訊息面板失敗 ({msg_id}): {ex}")

            conn.close()
        except Exception as e:
            print(f"❌ 查詢並同步分錢面板發生錯誤：{e}")

    @discord.ui.button(label="☑️ 領取選定項目", style=discord.ButtonStyle.primary, row=1)
    async def claim_selected_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        selected_ids = self.select_menu.values
        if not selected_ids:
            await interaction.response.send_message("❌ 請先在下方的下拉選單中勾選您要領取的項目！", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await self.process_claims_and_sync(selected_ids)

        await interaction.followup.send(f"✅ 成功領取選定的 **{len(selected_ids)}** 項戰利品！已自動清理資料庫與對應面板。", ephemeral=True)
        
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

    @discord.ui.button(label="💰 一鍵領取全部未領", style=discord.ButtonStyle.success, row=1)
    async def claim_all_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        all_row_ids = [row_id for row_id, _, _, _ in self.records]
        await self.process_claims_and_sync(all_row_ids)

        for child in self.children:
            child.disabled = True

        embed = discord.Embed(
            title=f"✅ {self.member_name} 全部領取成功！",
            description="您的所有未領清單已全數領取完畢、對應的主面板若皆已清空則會自動刪除！請記得跟對應的團長核對領取遊戲幣。",
            color=discord.Color.green()
        )
        await interaction.message.edit(embed=embed, view=self)
        await interaction.followup.send("✅ 已全數領取完畢！", ephemeral=True)


class UnclaimedCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="查詢未領", description="查詢自己的未領戰利品（顯示單一金額、全部金額與負責人）")
    async def check_unclaimed(self, interaction: discord.Interaction):
        target_name = interaction.user.display_name

        try:
            conn = sqlite3.connect("guild_database.db")
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT id, item_name, total_per_person, leader_name FROM split_records WHERE member_name = ? AND status = 0", 
                (target_name,)
            )
            rows = cursor.fetchall()
            conn.close()
        except Exception as e:
            await interaction.response.send_message("🎉 目前系統尚未檢測到分錢紀錄表，或您目前沒有未領項目！", ephemeral=True)
            return

        if not rows:
            await interaction.response.send_message(f"🎉 太神啦！**{target_name}** 目前沒有任何未領取的戰利品分錢！", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"💰 {target_name} 的未領分錢清單",
            color=discord.Color.gold()
        )
        
        total_money = 0
        desc = "以下是您目前尚未領取的項目明細與負責人：\n\n"
        
        formatted_records = []
        for idx, row in enumerate(rows, 1):
            row_id = row["id"]
            item = row["item_name"]
            amount = row["total_per_person"] if row["total_per_person"] is not None else 0
            leader = row["leader_name"]
            
            formatted_records.append((row_id, item, amount, leader))
            
            leader_str = leader if leader else "未指定"
            desc += f"{idx}. **{item}**\n" \
                    f"    └ 單項金額：`{amount:,}` 元 ｜ 負責人：**{leader_str}**\n"
            total_money += amount

        desc += f"\n-------------------\n🔹 **全部未領總金額**：`{total_money:,}` 元"
        embed.description = desc
        embed.set_footer(text="可利用下方選單勾選部分項目分開領取，或點擊按鈕一次領完（領完後自動清除）！")

        view = FlexibleClaimView(self.bot, target_name, formatted_records)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(UnclaimedCog(bot))
