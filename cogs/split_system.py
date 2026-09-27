import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
from utils.database import get_db_connection

# ===================== 資料庫初始化安全檢查 =====================
SPLIT_INSERT_SQL = """
    INSERT INTO split_records
    (project_id, member_name, item_name, total_per_person, leader_name, status, message_id, channel_id)
    VALUES (?, ?, ?, ?, ?, 0, ?, ?)
"""

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

        # 🛠️ 同步更新資料庫：同時更新 loot_projects 與 split_records
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE loot_projects
                SET item_name = ?, total_price = ?, status = 'active'
                WHERE id = ?
                """,
                (self.item_name.value, price_int, self.view_obj.project_id),
            )
            cursor.execute(
                """
                UPDATE split_records
                SET item_name = ?, total_per_person = ?
                WHERE project_id = ? AND status = 0
                """,
                (self.item_name.value, per_person, self.view_obj.project_id),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"❌ 更新網頁連動資料庫失敗：{e}")

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
            conn = get_db_connection()
            cursor = conn.cursor()
            members_str = ", ".join(self.parent_view.members)
            cursor.execute(
                "UPDATE loot_projects SET members = ? WHERE id = ?",
                (members_str, self.parent_view.project_id),
            )
            cursor.execute(
                "DELETE FROM split_records WHERE project_id = ? AND status = 0",
                (self.parent_view.project_id,),
            )
            for name in self.parent_view.members:
                cursor.execute(
                    SPLIT_INSERT_SQL,
                    (
                        self.parent_view.project_id,
                        name,
                        self.parent_view.item_name,
                        self.parent_view.per_person,
                        self.parent_view.leader.display_name,
                        self.parent_view.message_id,
                        self.parent_view.channel_id,
                    ),
                )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"❌ 成員調動同步網頁資料庫失敗：{e}")

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
    def __init__(self, item_name, total, per_person, members, leader, message_id=None, channel_id=None, project_id=None):
        super().__init__(timeout=None)
        self.item_name = item_name
        self.total = total
        self.per_person = per_person
        self.members = members
        self.leader = leader
        self.message_id = message_id
        self.channel_id = channel_id
        self.project_id = project_id
        self.status = {m: False for m in members}
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        
        for member in self.members:
            is_claimed = self.status.get(member, False)
            style = discord.ButtonStyle.success if is_claimed else discord.ButtonStyle.secondary
            label = f"☑ {member} (已領)" if is_claimed else f"☐ {member} (未領)"
            
            # 💡 確保每個成員按鈕都有帶入 project_id 的專屬 custom_id，避免重新整理時 View 關聯失效
            button = SplitButton(member, label, style, self.project_id)
            self.add_item(button)

        voice_grab_btn = discord.ui.Button(label="🎙️ 抓取語音房成員", style=discord.ButtonStyle.success, row=3, custom_id=f"persistent_grab_voice_{self.project_id}")
        voice_grab_btn.callback = self.grab_voice_members
        self.add_item(voice_grab_btn)

        add_member_btn = discord.ui.Button(label="➕ 快速補人/調動", style=discord.ButtonStyle.secondary, row=3, custom_id=f"persistent_add_member_{self.project_id}")
        add_member_btn.callback = self.open_add_member_selector
        self.add_item(add_member_btn)

        edit_btn = discord.ui.Button(label="✏️ 編輯品項/金額", style=discord.ButtonStyle.primary, row=4, custom_id=f"persistent_edit_split_{self.project_id}")
        edit_btn.callback = self.edit_split_info
        self.add_item(edit_btn)

        ping_btn = discord.ui.Button(label="📢 催繳通知未領者", style=discord.ButtonStyle.secondary, row=4, custom_id=f"persistent_ping_unclaimed_{self.project_id}")
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
            conn = get_db_connection()
            cursor = conn.cursor()
            members_str = ", ".join(self.members)
            cursor.execute(
                "UPDATE loot_projects SET members = ? WHERE id = ?",
                (members_str, self.project_id),
            )
            cursor.execute(
                "DELETE FROM split_records WHERE project_id = ? AND status = 0",
                (self.project_id,),
            )
            for name in self.members:
                cursor.execute(
                    SPLIT_INSERT_SQL,
                    (
                        self.project_id,
                        name,
                        self.item_name,
                        self.per_person,
                        self.leader.display_name,
                        self.message_id,
                        self.channel_id,
                    ),
                )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"❌ 語音抓取寫入網頁資料庫失敗：{e}")

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
    def __init__(self, member_name, label, style, project_id):
        super().__init__(label=label, style=style, custom_id=f"split_btn_{project_id}_{member_name}")
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
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE split_records
                SET status = ?
                WHERE member_name = ? AND project_id = ?
                """,
                (new_status, self.member_name, view.project_id),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"❌ 同步更新領取狀態至網頁資料庫失敗：{e}")

        all_claimed = all(view.status.values()) if view.status else False
        if all_claimed:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE loot_projects SET status = 'completed' WHERE id = ?",
                    (view.project_id,),
                )
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"❌ 更新專案完成狀態失敗：{e}")

            await interaction.response.edit_message(content="🎉 **此戰利品所有成員皆已領取完畢，面板已自動關閉！**", embed=None, view=None)
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

        today_str = datetime.now().strftime('%Y-%m-%d')
        members_str = ", ".join(members)

        project_id = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO loot_projects
                (leader_name, leader_discord_id, item_name, loot_date, members, total_price, tax_rate, status)
                VALUES (?, ?, ?, ?, ?, 0, 0, 'pending')
                """,
                (
                    interaction.user.display_name,
                    interaction.user.id,
                    "未命名物品",
                    today_str,
                    members_str,
                ),
            )
            project_id = cursor.lastrowid

            for name in members:
                cursor.execute(
                    SPLIT_INSERT_SQL,
                    (
                        project_id,
                        name,
                        "未命名物品",
                        0,
                        interaction.user.display_name,
                        msg.id,
                        target_channel.id,
                    ),
                )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"❌ 寫入網頁連動資料庫失敗：{e}")

        view = SplitMoneyView(
            item_name="未命名物品 (請點擊下方按鈕編輯)", 
            total=0, 
            per_person=0, 
            members=members, 
            leader=interaction.user,
            message_id=msg.id,
            channel_id=target_channel.id,
            project_id=project_id
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
        await interaction.response.send_message(f"✅ 即時分錢面板已發送至 {target_channel.mention}，並已成功同步至網頁端系統！", ephemeral=True)

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

    @app_commands.command(name="查詢未領", description="查詢目前尚未領取的分錢明細")
    @app_commands.describe(只看自己="只列出你尚未領取的單子（預設列出全部未領）")
    async def query_unclaimed(self, interaction: discord.Interaction, 只看自己: bool = False):
        await interaction.response.defer(ephemeral=True)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, member_name, item_name, total_per_person, leader_name
            FROM split_records
            WHERE status = 0
            ORDER BY id DESC
            LIMIT 40
            """
        )
        rows = cursor.fetchall()
        conn.close()

        display = (interaction.user.display_name or "").strip().lower()
        username = (interaction.user.name or "").strip().lower()
        global_name = (getattr(interaction.user, "global_name", None) or "").strip().lower()
        tokens = [t for t in (display, username, global_name) if t]

        def is_self(member_name):
            hay = (member_name or "").strip().lower()
            return any(t == hay or t in hay for t in tokens)

        if 只看自己:
            rows = [r for r in rows if is_self(r["member_name"])]

        if not rows:
            await interaction.followup.send("🎉 目前沒有未領取的分錢紀錄。", ephemeral=True)
            return

        lines = []
        for row in rows:
            amount = int(row["total_per_person"] or 0)
            lines.append(
                f"`#{row['id']}` **{row['member_name']}**｜{row['item_name']}｜`{amount:,}`｜負責人 {row['leader_name']}"
            )
        embed = discord.Embed(
            title=f"📋 未領取分錢（{len(rows)} 筆）",
            description="\n".join(lines[:25]),
            color=discord.Color.orange(),
        )
        if len(rows) > 25:
            embed.set_footer(text=f"僅顯示前 25 筆，共 {len(rows)} 筆")
        await interaction.followup.send(embed=embed, ephemeral=True)


class RestoredLeader:
    def __init__(self, user_id, display_name):
        self.id = user_id or 0
        self.display_name = display_name or "未知"


async def restore_open_split_views(bot):
    await bot.wait_until_ready()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT project_id, member_name, item_name, total_per_person, leader_name,
               status, message_id, channel_id
        FROM split_records
        WHERE project_id IS NOT NULL AND message_id IS NOT NULL
        """
    )
    rows = cursor.fetchall()
    cursor.execute(
        "SELECT id, leader_discord_id, total_price, status FROM loot_projects"
    )
    projects = {r["id"]: r for r in cursor.fetchall()}
    conn.close()

    grouped = {}
    for row in rows:
        pid = row["project_id"]
        proj = projects.get(pid)
        if not proj or proj["status"] == "completed":
            continue
        grouped.setdefault(pid, []).append(row)

    for pid, recs in grouped.items():
        first = recs[0]
        members = [r["member_name"] for r in recs]
        claimed = {r["member_name"]: bool(r["status"]) for r in recs}
        leader_id = projects[pid]["leader_discord_id"]
        leader = RestoredLeader(leader_id, first["leader_name"])
        total = int(projects[pid]["total_price"] or 0)
        per_person = int(first["total_per_person"] or 0)
        view = SplitMoneyView(
            item_name=first["item_name"] or "未命名物品",
            total=total,
            per_person=per_person,
            members=members,
            leader=leader,
            message_id=first["message_id"],
            channel_id=first["channel_id"],
            project_id=pid,
        )
        view.status = claimed
        view.update_buttons()
        bot.add_view(view, message_id=first["message_id"])


async def setup(bot):
    await bot.add_cog(SplitSystem(bot))
    bot.loop.create_task(restore_open_split_views(bot))
