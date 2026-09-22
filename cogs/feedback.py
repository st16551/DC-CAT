# ==================================================
# 檔案名稱：cogs/feedback.py
# 檔案用途：公會意見回饋箱與幹部審核討論系統（結合 JSON 資料庫）
# ==================================================

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

# 匯入你們專案共用的 JSON 資料庫讀寫核心
from utils.database import load_data, save_data

# 【請設定】相關頻道與身分組 ID
ADMIN_FEEDBACK_CHANNEL_ID = 1548406801488285706  # 意見箱審核專區頻道 ID
DISCUSSION_CHANNEL_ID = 1548406801488285707      # 意見採納後的討論頻道 ID
ADMIN_ROLE_ID = 1529725865024557196              # 要被 @ 叫出來討論的幹部身分組 ID

class FeedbackModal(discord.ui.Modal, title="📬 填寫公會意見回饋"):
    feedback_input = discord.ui.TextInput(
        label="您的寶貴意見或建議",
        placeholder="例如：建議調整週末活動時間、優化倉庫分配機制等...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):
        author = interaction.user
        content = self.feedback_input.value
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. 寫入 data.json 資料庫
        data = load_data()
        if "feedbacks" not in data:
            data["feedbacks"] = {}

        # 產生一組唯一的意見 ID (用時間戳記)
        feedback_id = f"fb_{int(datetime.now().timestamp())}"
        
        feedback_entry = {
            "id": feedback_id,
            "author_id": author.id,
            "author_name": author.display_name,
            "content": content,
            "status": "審核中",          # 狀態: 審核中 / 已採納 / 不合適
            "handler": None,
            "created_at": created_at
        }
        
        data["feedbacks"][feedback_id] = feedback_entry
        save_data(data)

        # 2. 建立精美的具名意見卡片，並把 feedback_id 藏在 Footer 方便對應
        embed = discord.Embed(
            title="📬 【收到新的會員意見】",
            description=content,
            color=discord.Color.blurple()
        )
        embed.set_author(name=author.display_name, icon_url=author.display_avatar.url)
        embed.add_field(name="建議成員", value=author.mention, inline=False)
        embed.set_footer(text=f"意見編號: {feedback_id} | 作者 ID: {author.id}")

        view = FeedbackReviewView()

        # 3. 給填寫的成員私密提示
        await interaction.response.send_message(
            content=f"✅ **{author.mention} 你的意見已成功送交給幹部群，感謝你的回饋！**", 
            ephemeral=True
        )

        # 4. 傳送到幹部審核頻道
        guild = interaction.guild
        feedback_channel = guild.get_channel(ADMIN_FEEDBACK_CHANNEL_ID)

        if not feedback_channel:
            feedback_channel = interaction.channel  # 若找不到則退回當前頻道

        try:
            await feedback_channel.send(embed=embed, view=view)
        except Exception as e:
            print(f"❌ 發送至審核頻道失敗: {e}")


class FeedbackReviewView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # 永久常駐按鈕

    @discord.ui.button(label="🟢 採納（須討論）", style=discord.ButtonStyle.success, custom_id="feedback_accept_btn_v4")
    async def accept_feedback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 只有幹部與管理員可以審核意見！", ephemeral=True)
            return

        embed = interaction.message.embeds[0]
        footer_text = embed.footer.text
        
        # 從 Footer 解析出 feedback_id 與 author_id
        try:
            parts = footer_text.split(" | ")
            feedback_id = parts[0].replace("意見編號: ", "").strip()
            author_id = int(parts[1].replace("作者 ID: ", "").strip())
        except Exception:
            await interaction.response.send_message("❌ 讀取意見編號發生錯誤！", ephemeral=True)
            return

        # 更新 data.json 中的狀態
        data = load_data()
        if "feedbacks" in data and feedback_id in data["feedbacks"]:
            data["feedbacks"][feedback_id]["status"] = "已採納"
            data["feedbacks"][feedback_id]["handler"] = interaction.user.display_name
            save_data(data)

        # 更新 Embed 樣式
        embed.color = discord.Color.green()
        embed.title = "🟢 【意見已採納（須討論）】"
        embed.add_field(name="處理幹部", value=interaction.user.mention, inline=False)

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)

        guild = interaction.guild

        # 5. 自動推送到討論/交辦頻道並 @幹部
        discussion_channel = guild.get_channel(DISCUSSION_CHANNEL_ID)
        if discussion_channel:
            admin_role = guild.get_role(ADMIN_ROLE_ID)
            role_mention = admin_role.mention if admin_role else "@幹部群"
            
            try:
                discussion_embed = discord.Embed(
                    title="🟢 【意見採納 - 開啟討論】",
                    description=embed.description,
                    color=discord.Color.green()
                )
                discussion_embed.set_author(name=embed.author.name, icon_url=embed.author.icon_url)
                for field in embed.fields:
                    discussion_embed.add_field(name=field.name, value=field.value, inline=field.inline)
                discussion_embed.set_footer(text=embed.footer.text)

                await discussion_channel.send(
                    content=f"🔔 {role_mention} 有新的採納意見需要進行後續討論與追蹤：", 
                    embed=discussion_embed
                )
            except Exception as e:
                print(f"❌ 轉發至討論頻道失敗: {e}")

        # 6. 私訊通知原作者
        target_member = guild.get_member(author_id)
        notify_text = f"🟢 **你在公會意見箱提出的建議已被幹部【採納（須討論）】，感謝你對公會的貢獻！**"
        
        if target_member:
            try:
                await target_member.send(notify_text)
            except Exception:
                pass
            await interaction.followup.send(f"✅ 已更新狀態（已同步寫入資料庫），已轉發至討論頻道並私訊通知 {target_member.mention}。", ephemeral=True)
        else:
            await interaction.followup.send(f"✅ 已更新狀態（已同步寫入資料庫），並已轉發至討論頻道。", ephemeral=True)

    @discord.ui.button(label="🔴 綜合評估不合適", style=discord.ButtonStyle.danger, custom_id="feedback_reject_btn_v4")
    async def reject_feedback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 只有幹部與管理員可以審核意見！", ephemeral=True)
            return

        embed = interaction.message.embeds[0]
        footer_text = embed.footer.text
        
        try:
            parts = footer_text.split(" | ")
            feedback_id = parts[0].replace("意見編號: ", "").strip()
            author_id = int(parts[1].replace("作者 ID: ", "").strip())
        except Exception:
            await interaction.response.send_message("❌ 讀取意見編號發生錯誤！", ephemeral=True)
            return

        # 更新 data.json 中的狀態
        data = load_data()
        if "feedbacks" in data and feedback_id in data["feedbacks"]:
            data["feedbacks"][feedback_id]["status"] = "不合適"
            data["feedbacks"][feedback_id]["handler"] = interaction.user.display_name
            save_data(data)

        embed.color = discord.Color.red()
        embed.title = "🔴 【意見綜合評估不合適】"
        embed.add_field(name="處理幹部", value=interaction.user.mention, inline=False)

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)

        # 通知原作者
        guild = interaction.guild
        target_member = guild.get_member(author_id)
        notify_text = f"🔴 **你在公會意見箱提出的建議經幹部綜合評估後暫不合適，感謝你的寶貴回饋！**"
        
        if target_member:
            try:
                await target_member.send(notify_text)
            except Exception:
                pass
            await interaction.followup.send(f"✅ 已更新狀態（已同步寫入資料庫），並已嘗試私訊通知 {target_member.mention}。", ephemeral=True)
        else:
            await interaction.followup.send(f"✅ 已更新狀態（已同步寫入資料庫）。", ephemeral=True)


class PersistentFeedbackView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # 永久常駐面板按鈕

    @discord.ui.button(label="📮 點擊填寫意見箱", style=discord.ButtonStyle.blurple, custom_id="persistent_feedback_btn_main_v4")
    async def open_feedback_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = FeedbackModal()
        await interaction.response.send_modal(modal)


class FeedbackCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # 註冊持久化 View，確保重啟後按鈕依然有效
        self.bot.add_view(PersistentFeedbackView())
        self.bot.add_view(FeedbackReviewView())

    @app_commands.command(name="架設意見箱", description="【管理員】在當前頻道發送常駐的意見箱填寫面板")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_feedback_panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📬 靈谷公會 - 意見回饋箱",
            description="對公會有任何想法、建議或想反映的事項嗎？\n"
                        "請點擊下方按鈕填寫，你的意見將會直接儲存並送交給幹部群進行評估！",
            color=discord.Color.blue()
        )
        view = PersistentFeedbackView()
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ 意見箱常駐面板已成功架設！", ephemeral=True)


async def setup(bot):
    await bot.add_cog(FeedbackCog(bot))
