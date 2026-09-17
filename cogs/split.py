import sqlite3
import discord
from discord import app_commands
from discord.ext import commands

# ===================== 資料庫初始化 =====================
def init_split_db():
    try:
        conn = sqlite3.connect("guild_database.db")
        cursor = conn.cursor()
        # 分錢與未領紀錄表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS split_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_name TEXT,
                item_name TEXT,
                total_per_person INTEGER,
                leader_name TEXT,
                status INTEGER DEFAULT 0
            )
        """)
        # 統一的打寶/待售總表 (splits)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS splits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                leader TEXT,
                item_name TEXT,
                total_price INTEGER,
                per_person INTEGER,
                status TEXT
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ 初始化分錢資料庫失敗：{e}")

init_split_db()

# ===================== 登記/開單 Modal =====================
class SplitModal(discord.ui.Modal, title="登記打寶與即時分錢"):
    item_name = discord.ui.TextInput(
        label="掉落物品名稱",
        placeholder="例如：ECHO / 稀有神裝",
        required=True,
        max_length=100
    )
    total_price = discord.ui.TextInput(
        label="總金額 (數字，若待售可先填 0)",
        placeholder="例如：210000000 或 0",
        required=True,
        max_length=20
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            price_int = int(self.total_price.value.replace(",", "").replace("_", ""))
        except ValueError:
            await interaction.response.send_message("❌ 金額必須是純數字！", ephemeral=True)
            return

        # 預設把當前發起人加入名單
        members = [interaction.user.display_name]
        per_person = price_int // len(members) if price_int > 0 else 0
        status_str = "active" if price_int > 0 else "pending" # 金額為0歸類為待售寶物庫

        from datetime import datetime
        now_date = datetime.now().strftime("%Y-%m-%d %H:%M")

        try:
            conn = sqlite3.connect("guild_database.db")
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO splits (date, leader, item_name, total_price, per_person, status) VALUES (?, ?, ?, ?, ?, ?)",
                (now_date, interaction.user.display_name, self.item_name.value, price_int, per_person, status_str)
            )
            for m in members:
                cursor.execute(
                    "INSERT INTO split_records (member_name, item_name, total_per_person, leader_name, status) VALUES (?, ?, ?, ?, 0)",
                    (m, self.item_name.value, per_person, interaction.user.display_name)
                )
            conn.commit()
            conn.close()
        except Exception as e:
            await interaction.response.send_message(f"❌ 寫入資料庫失敗：{e}", ephemeral=True)
            return

        view = SplitMoneyView(
            item_name=self.item_name.value,
            total=price_int,
            per_person=per_person,
            members=members,
            leader=interaction.user
        )

        embed = discord.Embed(
            title="💰 戰利品分錢面板" if price_int > 0 else "📦 待售寶物登錄成功",
            description=(
                f"**物品**：{self.item_name.value}\n"
                f"**總額**：`{price_int:,}` | **人數**：{len(members)} 人\n"
                f"**每人分得**：`{per_person:,}`\n\n"
                f"**分錢名單**：\n" + ", ".join([f"`{m}`" for m in members]) + "\n\n"
                f"📌 狀態：{'🟢 進行中分錢' if price_int > 0 else '🟡 尚未售出 (已放入待售寶物庫)'}"
            ),
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"發起人：{interaction.user.display_name}")

        target_channel = discord.utils.get(interaction.guild.text_channels, name="💰-分錢與戰利品歸檔") or interaction.channel
        await target_channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"✅ 成功建立分錢/寶物面板並發送至 {target_channel.mention}！", ephemeral=True)


class EditSplitModal(discord.ui.Modal, title="設定/修改戰利品分錢資訊"):
    item_name = discord.ui.TextInput(
        label="掉落物品名稱",
        placeholder="例如：ECHO / 稀有神裝",
        required=True,
        max_length=100
    )
    total_price = discord.ui.TextInput(
        label="總金額 (數字)",
        placeholder="例如：210000000",
        required=True,
        max_length=20
    )

    def __init__(self, view_obj):
        super().__init__()
        self.view_obj = view_obj
        if view_obj.item_name != "未命名物品":
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
        old_item_name = self.view_obj.item_name
        self.view_obj.item_name = self.item_name.value
        self.view_obj.total = price_int
        self.view_obj.per_person = per_person
        self.view_obj.update_buttons()

        try:
            conn = sqlite3.connect("guild_database.db")
            cursor = conn.cursor()
            for member_name in members:
                cursor.execute(
                    """
                    UPDATE split_records 
                    SET item_name = ?, total_per_person = ? 
                    WHERE member_name = ? AND leader_name = ? AND item_name = ? AND status = 0
                    """,
                    (self.item_name.value, per_person, member_name, self.view_obj.leader.display_name, old_item_name)
                )
            cursor.execute(
                "UPDATE splits SET item_name = ?, total_price = ?, per_person = ?, status = 'active' WHERE leader = ? AND item_name = ?",
                (self.item_name.value, price_int, per_person, self.view_obj.leader.display_name, old_item_name)
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


class AddMemberSelectView(discord.ui.View):
    def __init__(self, parent_view):
        super().__init__(timeout=180)
        self.parent_view = parent_view
        
        self.user_select = discord.ui.UserSelect(
            placeholder="請勾選要保留或加入的成員...",
            min_values=0,
            max_values=25
        )
        self.user_select.callback = self.select_callback
        self.add_item(self.user_select)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.parent_view.leader.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 只有發起人或管理員才能調動成員！", ephemeral=True)
            return

        selected_names = [u.display_name for u in self.user_select.values]
        self.parent_view.members = selected_names
        
        if self.parent_view.total > 0 and self.parent_view.members:
            self.parent_view.per_person = self.parent_view.total // len(self.parent_view.members)
        elif not self.parent_view.members:
            self.parent_view.per_person = 0

        self.parent_view.update_buttons()

        try:
            conn = sqlite3.connect("guild_database.db")
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM split_records WHERE leader_name = ? AND item_name = ? AND status = 0",
                (self.parent_view.leader.display_name, self.parent_view.item_name)
            )
            for name in self.parent_view.members:
                cursor.execute(
                    "INSERT INTO split_records (member_name, item_name, total_per_person, leader_name, status) VALUES (?, ?, ?, ?, 0)",
                    (name, self.parent_view.item_name, self.parent_view.per_person, self.parent_view.leader.display_name)
                )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"❌ 成員調動同步失敗：{e}")

        embed = discord.Embed(
            title="💰 戰利品分錢面板",
            description=f"**物品**：{self.parent_view.item_name}\n**總額**：`{self.parent_view.total:,}` | **人數**：{len(self.parent_view.members)} 人\n**每人分得**：`{self.parent_view.per_person:,}`",
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"發起人：{self.parent_view.leader.display_name}")

        await interaction.message.edit(embed=embed, view=self.parent_view)
        await interaction.response.send_message(f"✅ 成員調動完成！現有成員：{len(self.parent_view.members)} 人", ephemeral=True)


class SplitMoneyView(discord.ui.View):
    def __init__(self, item_name, total, per_person, members, leader):
        super().__init__(timeout=None)
        self.item_name = item_name
        self.total = total
        self.per_person = per_person
        self.members = members
        self.leader = leader
        self.status = {m: False for m in members}
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        for member in self.members:
            is_claimed = self.status.get(member, False)
            style = discord.ButtonStyle.success if is_claimed else discord.ButtonStyle.secondary
            label = f"☑ {member} (已領)" if is_claimed else f"☐ {member} (未領)"
            self.add_item(SplitButton(member, label, style))

        voice_grab_btn = discord.ui.Button(label="🎙️ 抓取語音房", style=discord.ButtonStyle.success, row=3)
        voice_grab_btn.callback = self.grab_voice_members
        self.add_item(voice_grab_btn)

        add_member_btn = discord.ui.Button(label="➕ 快速補人", style=discord.ButtonStyle.secondary, row=3)
        add_member_btn.callback = self.open_add_member_selector
        self.add_item(add_member_btn)

        edit_btn = discord.ui.Button(label="✏️ 編輯品項/金額", style=discord.ButtonStyle.primary, row=4)
        edit_btn.callback = self.edit_split_info
        self.add_item(edit_btn)

        ping_btn = discord.ui.Button(label="📢 催繳通知", style=discord.ButtonStyle.secondary, row=4)
        ping_btn.callback = self.ping_unclaimed
        self.add_item(ping_btn)

    async def grab_voice_members(self, interaction: discord.Interaction):
        if interaction.user.id != self.leader.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 只有發起人或管理員才能抓取語音房！", ephemeral=True)
            return

        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("❌ 您目前不在任何語音頻道中！", ephemeral=True)
            return

        voice_channel = interaction.user.voice.channel
        added_count = 0
        for m in voice_channel.members:
            m_name = m.display_name
            if m_name not in self.members:
                self.members.append(m_name)
                self.status[m_name] = False
                added_count += 1
                try:
                    conn = sqlite3.connect("guild_database.db")
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO split_records (member_name, item_name, total_per_person, leader_name, status) VALUES (?, ?, ?, ?, 0)",
                        (m_name, self.item_name, self.per_person, self.leader.display_name)
                    )
                    conn.commit()
                    conn.close()
                except Exception as e:
                    print(f"❌ 語音抓取寫入資料庫失敗：{e}")

        if self.total > 0 and self.members:
            self.per_person = self.total // len(self.members)

        self.update_buttons()
        embed = discord.Embed(
            title="💰 戰利品分錢面板",
            description=f"**物品**：{self.item_name}\n**總額**：`{self.total:,}` | **人數**：{len(self.members)} 人\n**每人分得**：`{self.per_person:,}`",
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"發起人：{self.leader.display_name}")
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(f"🎙️ 從語音 **【{voice_channel.name}】** 抓取了 `{added_count}` 位成員！", ephemeral=True)

    async def open_add_member_selector(self, interaction: discord.Interaction):
        if interaction.user.id != self.leader.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 權限不足！", ephemeral=True)
            return
        await interaction.response.send_message("👥 請在下方選單中勾選成員：", view=AddMemberSelectView(self), ephemeral=True)

    async def edit_split_info(self, interaction: discord.Interaction):
        if interaction.user.id != self.leader.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 權限不足！", ephemeral=True)
            return
        await interaction.response.send_modal(EditSplitModal(self))

    async def ping_unclaimed(self, interaction: discord.Interaction):
        unclaimed = [m for m, claimed in self.status.items() if not claimed]
        if not unclaimed:
            await interaction.response.send_message("🎉 所有人都已經領完錢了！", ephemeral=True)
            return
        ping_texts = [discord.utils.get(interaction.guild.members, display_name=n).mention if discord.utils.get(interaction.guild.members, display_name=n) else n for n in unclaimed]
        msg = f"📢 **【分錢通知】** 還有以下成員尚未領取 **{self.item_name}** (`{self.per_person:,}`)：\n" + " ".join(ping_texts)
        await interaction.channel.send(msg)
        if not interaction.response.is_done():
            await interaction.response.defer()


class SplitButton(discord.ui.Button):
    def __init__(self, member_name, label, style):
        super().__init__(label=label, style=style, custom_id=f"split_btn_{member_name}")
        self.member_name = member_name

    async def callback(self, interaction: discord.Interaction):
        view: SplitMoneyView = self.view
        view.status[self.member_name] = not view.status.get(self.member_name, False)
        view.update_buttons()

        new_status = 1 if view.status[self.member_name] else 0
        try:
            conn = sqlite3.connect("guild_database.db")
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE split_records SET status = ? WHERE member_name = ? AND leader_name = ? AND item_name = ?",
                (new_status, self.member_name, view.leader.display_name, view.item_name)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"❌ 更新領取狀態失敗：{e}")

        all_claimed = all(view.status.values()) if view.status else False
        color = discord.Color.green() if all_claimed else discord.Color.gold()
        title = "💰 戰利品分錢面板 [已全數領取]" if all_claimed else "💰 戰利品分錢面板"
        
        embed = discord.Embed(
            title=title,
            description=f"**物品**：{view.item_name}\n**總額**：`{view.total:,}` | **每人分得**：`{view.per_person:,}`",
            color=color
        )
        await interaction.response.edit_message(embed=embed, view=view)


class SplitSystemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="即時分錢", description="建立一個帶有快速補人與權限鎖的戰利品分錢面板")
    async def cmd_instant_split(self, interaction: discord.Interaction):
        await interaction.response.send_modal(SplitModal())

async def setup(bot):
    await bot.add_cog(SplitSystemCog(bot))
