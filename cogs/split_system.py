import sqlite3
import discord
from discord import app_commands
from discord.ext import commands

# ===================== 資料庫初始化安全檢查 =====================
def init_db():
    try:
        conn = sqlite3.connect("guild_database.db")
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS split_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_name TEXT,
                item_name TEXT,
                total_per_person INTEGER,
                leader_name TEXT,
                status INTEGER DEFAULT 0,
                message_id INTEGER,
                channel_id INTEGER
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ 初始化分錢資料庫失敗：{e}")

init_db()

# ===================== 分錢系統相關 Modal 與 View =====================

class EditSplitModal(discord.ui.Modal, title="設定/修改戰利品分錢資訊"):
    item_name = discord.ui.TextInput(
        label="掉落物品名稱",
        placeholder="例如：狂戰王卡 / 稀有神裝",
        required=True,
        max_length=100
    )
    total_price = discord.ui.TextInput(
        label="總金額 (數字)",
        placeholder="例如：270000000",
        required=True,
        max_length=20
    )

    def __init__(self, view_obj):
        super().__init__()
        self.view_obj = view_obj
        if view_obj.item_name != "未命名物品 (請點擊下方按鈕編輯)" and view_obj.item_name != "出團戰利品":
            self.item_name.default = view_obj.item_name
        if view_obj.total > 0:
            self.total_price.default = str(view_obj.total)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            price_int = int(self.total_price.value.replace(",", "").replace("_", ""))
        except ValueError:
            await interaction.response.send_message("❌ 金額必須是純數字！", ephemeral=True)
            return

        members = self.view_obj.members
        if not members:
            await interaction.response.send_message("❌ 目前這團沒有任何已設定的成員可以分錢！", ephemeral=True)
            return

        per_person = price_int // len(members)

        self.view_obj.item_name = self.item_name.value
        self.view_obj.total = price_int
        self.view_obj.per_person = per_person
        self.view_obj.update_buttons()

        # 🛠️ 修正：直接以 message_id 與 leader_name 為錨點同步更新資料庫，不管舊名稱是什麼都能正確寫入
        try:
            conn = sqlite3.connect("guild_database.db")
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE split_records 
                SET item_name = ?, total_per_person = ? 
                WHERE leader_name = ? AND status = 0 AND message_id = ?
                """,
                (self.item_name.value, per_person, self.view_obj.leader.display_name, self.view_obj.message_id)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"❌ 更新分錢資料庫失敗：{e}")

        embed = discord.Embed(
            title="💰 戰利品分錢面板",
            description=f"**物品**：{self.view_obj.item_name}\n**總額**：`{price_int:,}` | **人數**：{len(members)} 人\n**每人分得**：`{per_person:,}`",
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"發起人：{self.view_obj.leader.display_name}")

        await interaction.response.edit_message(embed=embed, view=self.view_obj)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ 已取消操作。", ephemeral=True)
        except Exception:
            pass


class AddMemberSelectView(discord.ui.View):
    def __init__(self, parent_view):
        super().__init__(timeout=180)
        self.parent_view = parent_view
        
        self.user_select = discord.ui.UserSelect(
            placeholder="🔍 請在選單中打字搜尋並勾選要【加入】的新成員...",
            min_values=1,
            max_values=25
        )
        self.user_select.callback = self.select_callback
        self.add_item(self.user_select)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.parent_view.leader.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 只有此分錢面板的發起人或管理員才能執行成員調動！", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        selected_names = [u.display_name for u in self.user_select.values]
        
        added_count = 0
        for name in selected_names:
            if name not in self.parent_view.members:
                self.parent_view.members.append(name)
                self.parent_view.status[name] = False
                added_count += 1

        if self.parent_view.total > 0 and self.parent_view.members:
            self.parent_view.per_person = self.parent_view.total // len(self.parent_view.members)

        self.parent_view.update_buttons()

        try:
            conn = sqlite3.connect("guild_database.db")
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM split_records WHERE leader_name = ? AND message_id = ? AND status = 0",
                (self.parent_view.leader.display_name, self.parent_view.message_id)
            )
            for name in self.parent_view.members:
                cursor.execute(
                    "INSERT INTO split_records (member_name, item_name, total_per_person, leader_name, status, message_id, channel_id) VALUES (?, ?, ?, ?, 0, ?, ?)",
                    (name, self.parent_view.item_name, self.parent_view.per_person, self.parent_view.leader.display_name, self.parent_view.message_id, self.parent_view.channel_id)
                )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"❌ 成員調動同步資料庫失敗：{e}")

        embed = discord.Embed(
            title="💰 戰利品分錢面板",
            description=f"**物品**：{self.parent_view.item_name}\n**總額**：`{self.parent_view.total:,}` | **人數**：{len(self.parent_view.members)} 人\n**每人分得**：`{self.parent_view.per_person:,}`",
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"發起人：{self.parent_view.leader.display_name}")

        try:
            channel = interaction.guild.get_channel(self.parent_view.channel_id) or interaction.channel
            msg = await channel.fetch_message(self.parent_view.message_id)
            await msg.edit(embed=embed, view=self.parent_view)
        except Exception:
            pass

        await interaction.followup.send(f"✅ 成功追加 `{added_count}` 位新成員！目前總人數：`{len(self.parent_view.members)}` 人。", ephemeral=True)


class SplitMoneyView(discord.ui.View):
    def __init__(self, item_name, total, per_person, members, leader, message_id=None, channel_id=None):
        super().__init__(timeout=None)
        self.item_name = item_name
        self.total = total
        self.per_person = per_person
        self.members = members
        self.leader = leader
        self.message_id = message_id
        self.channel_id = channel_id
        self.status = {m: False for m in members}
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        
        for member in self.members:
            is_claimed = self.status.get(member, False)
            style = discord.ButtonStyle.success if is_claimed else discord.ButtonStyle.secondary
            label = f"☑ {member} (已領)" if is_claimed else f"☐ {member} (未領)"
            
            button = SplitButton(member, label, style)
            self.add_item(button)

        voice_grab_btn = discord.ui.Button(label="🎙️ 抓取語音房成員", style=discord.ButtonStyle.success, row=3, custom_id="persistent_grab_voice_btn")
        voice_grab_btn.callback = self.grab_voice_members
        self.add_item(voice_grab_btn)

        add_member_btn = discord.ui.Button(label="➕ 快速補人/調動", style=discord.ButtonStyle.secondary, row=3, custom_id="persistent_add_member_btn")
        add_member_btn.callback = self.open_add_member_selector
        self.add_item(add_member_btn)

        edit_btn = discord.ui.Button(label="✏️ 編輯品項/金額", style=discord.ButtonStyle.primary, row=4, custom_id="persistent_edit_split_btn")
        edit_btn.callback = self.edit_split_info
        self.add_item(edit_btn)

        ping_btn = discord.ui.Button(label="📢 催繳通知未領者", style=discord.ButtonStyle.secondary, row=4, custom_id="persistent_ping_unclaimed_btn")
        ping_btn.callback = self.ping_unclaimed
        self.add_item(ping_btn)

    async def grab_voice_members(self, interaction: discord.Interaction):
        if interaction.user.id != self.leader.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 只有此分錢面板的發起人或管理員才能抓取語音房！", ephemeral=True)
            return

        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("❌ 您目前不在任何語音頻道中！請先進入要結算的語音房再點擊此按鈕。", ephemeral=True)
            return

        voice_channel = interaction.user.voice.channel
        voice_members = voice_channel.members

        added_count = 0
        for m in voice_members:
            m_name = m.display_name
            if m_name not in self.members:
                self.members.append(m_name)
                self.status[m_name] = False
                added_count += 1

        if self.total > 0 and self.members:
            self.per_person = self.total // len(self.members)

        try:
            conn = sqlite3.connect("guild_database.db")
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM split_records WHERE leader_name = ? AND message_id = ? AND status = 0",
                (self.leader.display_name, self.message_id)
            )
            for name in self.members:
                cursor.execute(
                    "INSERT INTO split_records (member_name, item_name, total_per_person, leader_name, status, message_id, channel_id) VALUES (?, ?, ?, ?, 0, ?, ?)",
                    (name, self.item_name, self.per_person, self.leader.display_name, self.message_id, self.channel_id)
                )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"❌ 語音抓取寫入資料庫失敗：{e}")

        self.update_buttons()

        embed = discord.Embed(
            title="💰 戰利品分錢面板",
            description=f"**物品**：{self.item_name}\n**總額**：`{self.total:,}` | **人數**：{len(self.members)} 人\n**每人分得**：`{self.per_person:,}`",
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"發起人：{self.leader.display_name}")

        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(f"🎙️ 成功從語音房 **【{voice_channel.name}】** 抓取並新增 `{added_count}` 位成員！", ephemeral=True)

    async def open_add_member_selector(self, interaction: discord.Interaction):
        if interaction.user.id != self.leader.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 只有此分錢面板的發起人或管理員才能進行成員調動！", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        view = AddMemberSelectView(self)
        await interaction.followup.send("👥 請在下方選單中**打字搜尋並勾選**要加入的新成員：", view=view, ephemeral=True)

    async def edit_split_info(self, interaction: discord.Interaction):
        if interaction.user.id != self.leader.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 只有此分錢面板的發起人或管理員才能編輯品項與金額！", ephemeral=True)
            return
        await interaction.response.send_modal(EditSplitModal(self))

    async def ping_unclaimed(self, interaction: discord.Interaction):
        unclaimed = [m for m, claimed in self.status.items() if not claimed]
        if not unclaimed:
            await interaction.response.send_message("🎉 太神啦！所有人都已經領完錢了！", ephemeral=True)
            return
        
        ping_texts = []
        for name in unclaimed:
            member_obj = discord.utils.get(interaction.guild.members, display_name=name) or discord.utils.get(interaction.guild.members, name=name)
            if member_obj:
                ping_texts.append(member_obj.mention)
            else:
                ping_texts.append(name)

        msg = f"📢 **【分錢通知】** 還有以下成員尚未領取 **{self.item_name}** 的款項 (`{self.per_person:,}`)：\n" + " ".join(ping_texts)
        await interaction.channel.send(msg)
        if not interaction.response.is_done():
            await interaction.response.send_message("✅ 已成功發送催繳通知！", ephemeral=True)


class SplitButton(discord.ui.Button):
    def __init__(self, member_name, label, style):
        super().__init__(label=label, style=style, custom_id=f"split_btn_{member_name}")
        self.member_name = member_name

    async def callback(self, interaction: discord.Interaction):
        view: SplitMoneyView = self.view
        
        is_owner = (interaction.user.id == view.leader.id)
        is_admin = interaction.user.guild_permissions.administrator

        if not (is_owner or is_admin):
            await interaction.response.send_message(f"❌ 您無法變更 `{self.member_name}` 的領取狀態！只有此面板的發起人或伺服器管理員可以操作。", ephemeral=True)
            return

        view.status[self.member_name] = not view.status.get(self.member_name, False)
        view.update_buttons()

        new_status = 1 if view.status[self.member_name] else 0
        try:
            conn = sqlite3.connect("guild_database.db")
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE split_records 
                SET status = ? 
                WHERE member_name = ? AND leader_name = ? AND message_id = ?
                """,
                (new_status, self.member_name, view.leader.display_name, view.message_id)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"❌ 同步更新領取狀態資料庫失敗：{e}")

        all_claimed = all(view.status.values()) if view.status else False
        if all_claimed:
            try:
                conn = sqlite3.connect("guild_database.db")
                cursor = conn.cursor()
                cursor.execute("DELETE FROM split_records WHERE message_id = ?", (view.message_id,))
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"❌ 刪除已完成面板資料失敗：{e}")

            await interaction.response.edit_message(content="🎉 **此戰利品所有成員皆已領取完畢，面板已自動關閉並清除！**", embed=None, view=None)
            try:
                await interaction.message.delete()
            except Exception:
                pass
        else:
            embed = discord.Embed(
                title="💰 戰利品分錢面板",
                description=f"**物品**：{view.item_name}\n**總額**：`{view.total:,}` | **每人分得**：`{view.per_person:,}`",
                color=discord.Color.gold()
            )
            await interaction.response.edit_message(embed=embed, view=view)


class SplitSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="即時分錢", description="建立一個帶有快速補人與權限鎖的戰利品分錢面板")
    @app_commands.describe(initial_member="初始成員 (可選填一位，支援打字自動跳出伺服器成員)")
    async def cmd_instant_split(self, interaction: discord.Interaction, initial_member: str = None):
        members = [interaction.user.display_name]
        if initial_member and initial_member not in members:
            members.append(initial_member)
        
        target_channel = discord.utils.get(interaction.guild.text_channels, name="💰-分錢與戰利品歸檔") or interaction.channel
        
        temp_embed = discord.Embed(
            title="💰 戰利品分錢面板",
            description="載入中...",
            color=discord.Color.gold()
        )
        msg = await target_channel.send(embed=temp_embed)

        view = SplitMoneyView(
            item_name="未命名物品 (請點擊下方按鈕編輯)", 
            total=0, 
            per_person=0, 
            members=members, 
            leader=interaction.user,
            message_id=msg.id,
            channel_id=target_channel.id
        )
        
        embed = discord.Embed(
            title="💰 戰利品分錢面板",
            description=(
                f"**物品**：尚未設定\n"
                f"**總額**：`0` | **人數**：{len(members)} 人\n"
                f"**每人分得**：`0`\n\n"
                f"**分錢名單**：\n" + ", ".join([f"`{m}`" for m in members]) + "\n\n"
                f"⚠️ 請點擊下方 **「✏️ 編輯品項/金額」** 按鈕來輸入掉落物與總金額！"
            ),
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"發起人：{interaction.user.display_name}")

        await msg.edit(embed=embed, view=view)

        try:
            conn = sqlite3.connect("guild_database.db")
            cursor = conn.cursor()
            for name in members:
                cursor.execute(
                    "INSERT INTO split_records (member_name, item_name, total_per_person, leader_name, status, message_id, channel_id) VALUES (?, ?, ?, ?, 0, ?, ?)",
                    (name, "未命名物品", 0, interaction.user.display_name, msg.id, target_channel.id)
                )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"❌ 寫入資料庫失敗：{e}")

        await interaction.response.send_message(f"✅ 即時分錢面板已發送至 {target_channel.mention}！", ephemeral=True)

    @cmd_instant_split.autocomplete("initial_member")
    async def instant_split_autocomplete(self, interaction: discord.Interaction, current: str):
        guild = interaction.guild
        if not guild:
            return []
        
        member_names = set()
        for m in guild.members:
            if m.display_name:
                member_names.add(m.display_name)
            if m.name:
                member_names.add(m.name)
        
        filtered = [
            app_commands.Choice(name=name, value=name)
            for name in sorted(member_names)
            if current.lower() in name.lower()
        ]
        return filtered[:25]

async def setup(bot):
    await bot.add_cog(SplitSystem(bot))
