import io
from datetime import datetime, timedelta
import discord
from discord import app_commands
from discord.ext import commands
import asyncio

from utils import custom_configs, save_data, CUSTOM_CONFIG_FILE, temp_voice_rooms
from utils.database import get_db_connection

ROOM_MODES = {
    "雙坦3補爬塔團 (2坦 3補 5DPS 2補位)": {
        "roles": [
            {"name": "坦克", "max": 2},
            {"name": "補師", "max": 3},
            {"name": "輸出", "max": 5},
            {"name": "補位", "max": 2}
        ]
    },
    "自訂/上次記憶模式 (彈出視窗設定)": "CUSTOM"
}

# ===================== 密碼解鎖驗證與自訂配置 Modal =====================
class RaidConfigButtonView(discord.ui.View):
    def __init__(self, host: discord.Member, saved_data):
        super().__init__(timeout=60)
        self.host = host
        self.saved_data = saved_data

    @discord.ui.button(label="📝 點擊填寫自訂出團配置", style=discord.ButtonStyle.success)
    async def open_config_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = RaidConfigModal(self.host)
        if self.saved_data:
            modal.title_input.default = self.saved_data.get("title", "SpiritVale 爬塔出團")
            modal.time_input.default = self.saved_data.get("time", "今晚 21:00")
            default_str = ", ".join([f"{r['name']}:{r['max']}" for r in self.saved_data.get("roles", [])])
            modal.roles_input.default = default_str
        await interaction.response.send_modal(modal)


class RaidAuthModal(discord.ui.Modal, title="解鎖自訂配置權限"):
    password_input = discord.ui.TextInput(
        label="請輸入解鎖密碼",
        placeholder="請輸入通關密語...",
        style=discord.TextStyle.short,
        required=True
    )

    def __init__(self, host: discord.Member):
        super().__init__()
        self.host = host

    async def on_submit(self, interaction: discord.Interaction):
        if self.password_input.value.strip() == "escalation":
            saved = custom_configs.get(str(interaction.guild_id)) if isinstance(custom_configs, dict) else None
            view = RaidConfigButtonView(self.host, saved)
            await interaction.response.send_message("✅ **密碼正確！** 請點擊下方按鈕開啟自訂出團配置視窗：", view=view, ephemeral=True)
        else:
            await interaction.response.send_message("❌ 密碼錯誤！您沒有權限修改自訂出團配置。", ephemeral=True)


class RaidConfigModal(discord.ui.Modal, title="自訂出團爬塔配置"):
    title_input = discord.ui.TextInput(
        label="副本/出團名稱",
        placeholder="例如: 迴響之塔 90層速刷團",
        default="SpiritVale 爬塔出團"
    )
    time_input = discord.ui.TextInput(
        label="預定出團時間",
        placeholder="例如: 今晚 21:00 或 週末下午",
        default="今晚 21:00"
    )
    roles_input = discord.ui.TextInput(
        label="職位與人數配置 (格式: 職位:人數)",
        placeholder="例如: 坦克:2, 補師:3, 輸出:5, 補位:2 (不限總人數)",
        default="坦克:2, 補師:3, 輸出:5, 補位:2",
        style=discord.TextStyle.paragraph
    )

    def __init__(self, host: discord.Member):
        super().__init__()
        self.host = host

    async def on_submit(self, interaction: discord.Interaction):
        parsed_roles = []
        
        try:
            raw_lines = self.roles_input.value.replace("，", ",").split(",")
            for line in raw_lines:
                if ":" in line:
                    r_name, r_max = line.split(":")
                    max_num = int(r_max.strip())
                    if max_num <= 0:
                        await interaction.response.send_message(f"❌ 職位「{r_name.strip()}」的人數必須大於 0！", ephemeral=True)
                        return
                    parsed_roles.append({"name": r_name.strip(), "max": max_num})
                    
            if not parsed_roles:
                raise ValueError("未解析到任何有效職位")
                
        except ValueError:
            await interaction.response.send_message("❌ 職位格式解析失敗！請確保人數是純數字，格式為：`職位名稱:人數`", ephemeral=True)
            return

        if isinstance(custom_configs, dict):
            custom_configs[str(interaction.guild_id)] = {
                "title": self.title_input.value,
                "time": self.time_input.value,
                "roles": parsed_roles
            }
            save_data(CUSTOM_CONFIG_FILE, custom_configs)

        # 建立訊息物件以綁定 message_id
        await interaction.response.defer(ephemeral=True)
        msg = await interaction.channel.send("載入出團面板中...")
        
        view = RaidView(host=self.host, title=self.title_input.value, time_str=self.time_input.value, roles_config=parsed_roles, message_id=msg.id, channel_id=msg.channel.id)
        embed = view._build_embed()
        await msg.edit(content=f"**{self.host.mention} 發起了解鎖自訂配置的爬塔出團招募！**", embed=embed, view=view)
        await interaction.followup.send("✅ 出團面板已成功發起！", ephemeral=True)


class RaidModeSelect(discord.ui.Select):
    def __init__(self, host: discord.Member):
        self.host = host
        options = [
            discord.SelectOption(label="1. 雙坦3補爬塔團", description="使用經典配置 (2坦 3補 5DPS 2補位)", value="雙坦3補爬塔團 (2坦 3補 5DPS 2補位)"),
            discord.SelectOption(label="2. 自訂配置", description="使用上次記憶的自訂出團設定", value="自訂/上次記憶模式 (彈出視窗設定)"),
            discord.SelectOption(label="3. 密碼解鎖設定", description="輸入密碼驗證，自由調整職位與人數", value="密碼解鎖設定 (自由調整職位與人數)")
        ]
        super().__init__(placeholder="請選擇出團模式...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selection = self.values[0]
        if selection == "密碼解鎖設定 (自由調整職位與人數)":
            await interaction.response.send_modal(RaidAuthModal(self.host))
        elif selection == "自訂/上次記憶模式 (彈出視窗設定)":
            saved = custom_configs.get(str(interaction.guild_id)) if isinstance(custom_configs, dict) else None
            if saved:
                modal = RaidConfigModal(self.host)
                modal.title_input.default = saved.get("title", "SpiritVale 爬塔出團")
                modal.time_input.default = saved.get("time", "今晚 21:00")
                default_str = ", ".join([f"{r['name']}:{r['max']}" for r in saved.get("roles", [])])
                modal.roles_input.default = default_str
                await interaction.response.send_modal(modal)
            else:
                await interaction.response.send_modal(RaidConfigModal(self.host))
        else:
            mode_data = ROOM_MODES[selection]
            await interaction.response.defer(ephemeral=True)
            msg = await interaction.channel.send("載入出團面板中...")
            
            view = RaidView(host=self.host, title=selection, time_str="今晚 21:00", roles_config=mode_data["roles"], message_id=msg.id, channel_id=msg.channel.id)
            embed = view._build_embed()
            
            await msg.edit(content=f"**{self.host.mention} 發起了出團招募！**", embed=embed, view=view)
            await interaction.followup.send("✅ 出團面板已成功發起！", ephemeral=True)


class RaidModeView(discord.ui.View):
    def __init__(self, host: discord.Member):
        super().__init__(timeout=180)
        self.host = host
        self.add_item(RaidModeSelect(host))


# ===================== 出團面板主體 =====================
class RaidView(discord.ui.View):
    def __init__(self, host: discord.Member, title: str, time_str: str, roles_config: list, message_id: int = None, channel_id: int = None):
        super().__init__(timeout=None)
        self.host = host
        self.title = title
        self.time_str = time_str
        self.roles_config = roles_config
        self.signups = {r["name"]: [] for r in roles_config}
        self.is_closed = False
        self.created_voice_channel_id = None
        self.message_id = message_id
        self.channel_id = channel_id
        
        for index, r_info in enumerate(self.roles_config):
            r_name = r_info["name"]
            btn = discord.ui.Button(label=f"加入 {r_name}", style=discord.ButtonStyle.primary, custom_id=f"raid_role_{index}_{r_name}")
            btn.callback = lambda i, n=r_name: asyncio.create_task(self.handle_signup(i, n))
            self.add_item(btn)

        cancel_btn = discord.ui.Button(label="取消報名", style=discord.ButtonStyle.secondary, custom_id="raid_cancel_btn_unique")
        cancel_btn.callback = self.handle_cancel
        self.add_item(cancel_btn)

        notify_members_btn = discord.ui.Button(label="📢 標記現有成員集合", style=discord.ButtonStyle.primary, custom_id="raid_notify_members_btn_unique")
        notify_members_btn.callback = self.handle_notify_members
        self.add_item(notify_members_btn)

        notify_role_btn = discord.ui.Button(label="🔔 通知開團身分組", style=discord.ButtonStyle.secondary, custom_id="raid_notify_role_btn_unique")
        notify_role_btn.callback = self.handle_notify_role
        self.add_item(notify_role_btn)

        voice_btn = discord.ui.Button(label="開通專屬語音房", style=discord.ButtonStyle.success, custom_id="raid_voice_btn_unique")
        voice_btn.callback = self.handle_voice
        self.add_item(voice_btn)

        split_btn = discord.ui.Button(label="💰 結算分錢", style=discord.ButtonStyle.secondary, custom_id="raid_split_btn_unique")
        split_btn.callback = self.handle_split
        self.add_item(split_btn)

        close_btn = discord.ui.Button(label="關閉出團", style=discord.ButtonStyle.danger, custom_id="raid_close_btn_unique")
        close_btn.callback = self.handle_close
        self.add_item(close_btn)

    def _sync_to_db(self):
        """同步目前報名陣容至資料庫"""
        if not self.message_id:
            return
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM raid_records WHERE message_id = ?", (self.message_id,))
            for r_name, m_list in self.signups.items():
                for m in m_list:
                    cursor.execute(
                        "INSERT INTO raid_records (message_id, channel_id, role_name, member_name, leader_name, title) VALUES (?, ?, ?, ?, ?, ?)",
                        (self.message_id, self.channel_id, r_name, m.display_name, self.host.display_name, self.title)
                    )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"❌ 同步出團資料庫失敗：{e}")

    def _build_embed(self) -> discord.Embed:
        status = "[已關閉/出團中]" if self.is_closed else "[出團招募中]"
        color = discord.Color.red() if self.is_closed else discord.Color.gold()
        desc = f"副本名稱：{self.title}\n團長：{self.host.mention}\n預定時間：`{self.time_str}`\n\n目前報名陣容配置：\n"
        for r_info in self.roles_config:
            r_name = r_info["name"]
            r_max = r_info["max"]
            members = self.signups.get(r_name, [])
            m_str = "、".join([m.mention for m in members]) if members else "尚無"
            desc += f"> {r_name} ({len(members)}/{r_max})：{m_str}\n"
        return discord.Embed(title=f"SpiritVale 爬塔出團招募 {status}", description=desc, color=color)

    async def handle_signup(self, interaction: discord.Interaction, role_name: str):
        if self.is_closed:
            await interaction.response.send_message("此出團招募已關閉！", ephemeral=True)
            return
        user = interaction.user
        for r_n, m_list in self.signups.items():
            if user in m_list:
                m_list.remove(user)
        r_max = next((r["max"] for r in self.roles_config if r["name"] == role_name), 99)
        if len(self.signups[role_name]) >= r_max:
            await interaction.response.send_message(f"{role_name} 職位名額已滿！", ephemeral=True)
            return
        self.signups[role_name].append(user)
        self._sync_to_db()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    async def handle_cancel(self, interaction: discord.Interaction):
        if self.is_closed:
            await interaction.response.send_message("此出團招募已關閉！", ephemeral=True)
            return
        user = interaction.user
        removed = False
        for r_n, m_list in self.signups.items():
            if user in m_list:
                m_list.remove(user)
                removed = True
        if removed:
            self._sync_to_db()
            await interaction.response.edit_message(embed=self._build_embed(), view=self)
        else:
            await interaction.response.send_message("您目前並未報名任何職位。", ephemeral=True)

    async def handle_notify_members(self, interaction: discord.Interaction):
        if interaction.user.id != self.host.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("只有團長或管理員可以發送集合通知！", ephemeral=True)
            return
        all_members = [m for m_list in self.signups.values() for m in m_list]
        if not all_members:
            await interaction.response.send_message("目前還沒有任何人報名！", ephemeral=True)
            return
        mentions = " ".join([m.mention for m in all_members])
        await interaction.channel.send(f"📢 **出團集合通知** ({self.title})！\n請以下已報名的夥伴準備集合：\n{mentions}")
        await interaction.response.send_message("已成功標記並發送集合通知！", ephemeral=True)

    async def handle_notify_role(self, interaction: discord.Interaction):
        if interaction.user.id != self.host.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("只有團長或管理員可以發送開團通知！", ephemeral=True)
            return
        member_role = discord.utils.get(interaction.guild.roles, name="成員")
        role_mention = member_role.mention if member_role else "@成員"
        
        await interaction.channel.send(f"🔔 **{role_mention}** 有新的爬塔出團開跑啦！\n**副本：{self.title}**（發起人：{self.host.mention}）\n請大家趕快點擊出團面板進行報名！")
        await interaction.response.send_message("已成功發送身分組開團通知！", ephemeral=True)

    async def handle_voice(self, interaction: discord.Interaction):
        if interaction.user.id != self.host.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("只有團長或管理員可以開通專屬語音房！", ephemeral=True)
            return
        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=True, speak=True),
            self.host: discord.PermissionOverwrite(manage_channels=True, move_members=True, manage_permissions=True)
        }
        for m_list in self.signups.values():
            for m in m_list:
                overwrites[m] = discord.PermissionOverwrite(connect=True, speak=True)
        try:
            room_name = f"{self.title[:10]}專屬房"
            new_channel = await guild.create_voice_channel(name=room_name, category=interaction.channel.category, overwrites=overwrites)
            if isinstance(temp_voice_rooms, dict):
                temp_voice_rooms[new_channel.id] = self.host.id
            if interaction.user.voice and interaction.user.voice.channel:
                try:
                    await interaction.user.move_to(new_channel)
                except Exception:
                    pass
            await interaction.response.send_message(f"專屬語音房已建立：**{new_channel.name}**！", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"建立語音房失敗：{e}", ephemeral=True)

    async def handle_split(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            from cogs.split_system import SPLIT_INSERT_SQL, SplitMoneyView

            unique_names = []
            for m_list in self.signups.values():
                for m in m_list:
                    if m.display_name not in unique_names:
                        unique_names.append(m.display_name)

            if not unique_names:
                await interaction.followup.send("❌ 目前這團沒有任何已報名成員！", ephemeral=True)
                return

            target_channel = discord.utils.get(interaction.guild.text_channels, name="💰-分錢與戰利品歸檔") or interaction.channel
            temp_embed = discord.Embed(title="💰 戰利品分錢面板", description="載入中...", color=discord.Color.gold())
            sent_message = await target_channel.send(embed=temp_embed)

            today_str = datetime.now().strftime("%Y-%m-%d")
            members_str = ", ".join(unique_names)
            project_id = None
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO loot_projects
                (leader_name, leader_discord_id, item_name, loot_date, members, total_price, tax_rate, status)
                VALUES (?, ?, ?, ?, ?, 0, 0, 'pending')
                """,
                (
                    self.host.display_name,
                    self.host.id,
                    "出團戰利品",
                    today_str,
                    members_str,
                ),
            )
            project_id = cursor.lastrowid
            for name in unique_names:
                cursor.execute(
                    SPLIT_INSERT_SQL,
                    (
                        project_id,
                        name,
                        "出團戰利品",
                        0,
                        self.host.display_name,
                        sent_message.id,
                        target_channel.id,
                    ),
                )
            conn.commit()
            conn.close()

            view = SplitMoneyView(
                "出團戰利品",
                0,
                0,
                unique_names,
                self.host,
                message_id=sent_message.id,
                channel_id=target_channel.id,
                project_id=project_id,
            )
            embed = discord.Embed(
                title="💰 戰利品分錢面板",
                description=(
                    f"**物品**：出團戰利品\n**總額**：`0` | **人數**：{len(unique_names)} 人\n"
                    f"**每人分得**：`0`\n\n⚠️ 請點擊下方 **「✏️ 編輯品項/金額」** 按鈕設定正確金額！"
                ),
                color=discord.Color.gold(),
            )
            embed.set_footer(text=f"發起人：{self.host.display_name}")
            await sent_message.edit(embed=embed, view=view)
            await interaction.followup.send(f"✅ 結算分錢面板已發送至 {target_channel.mention}，並已同步至網頁儀表板！", ephemeral=True)

        except Exception as e:
            print(f"❌ 結算功能發生未預期錯誤：{e}")
            await interaction.followup.send(f"❌ 結算功能執行時發生錯誤：`{e}`", ephemeral=True)

    async def handle_close(self, interaction: discord.Interaction):
        if interaction.user.id != self.host.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("只有團長或管理員可以關閉出團！", ephemeral=True)
            return
        try:
            await interaction.response.defer(ephemeral=True)
            if self.message_id:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM raid_records WHERE message_id = ?", (self.message_id,))
                conn.commit()
                conn.close()
            await interaction.message.delete()
            await interaction.followup.send("已關閉出團面板。", ephemeral=True)
        except Exception:
            if not interaction.response.is_done():
                await interaction.response.send_message("關閉出團成功", ephemeral=True)


class RaidSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="出團", description="發起 SpiritVale 爬塔出團招募")
    async def cmd_raid(self, interaction: discord.Interaction):
        view = RaidModeView(host=interaction.user)
        embed = discord.Embed(
            title="⚔️ 選擇出團招募模式",
            description=f"發起人：{interaction.user.mention}\n\n請從下方選單選擇您要使用的出團配置模式：",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(RaidSystem(bot))
