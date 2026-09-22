import asyncio
from datetime import datetime, timedelta
import discord
from discord import app_commands
from discord.ext import commands

active_polls = {}

ROLE_WEIGHTS = {
    "會長": 3,
    "長老": 2,
    "副會長": 2,
    "核心幹部": 2
}

def get_user_vote_weight(member: discord.Member) -> int:
    highest_weight = 1
    for role in member.roles:
        if role.name in ROLE_WEIGHTS:
            if ROLE_WEIGHTS[role.name] > highest_weight:
                highest_weight = ROLE_WEIGHTS[role.name]
    return highest_weight

def generate_poll_embed(poll_data: dict) -> discord.Embed:
    total_weight = sum(sum(v["weight"] for v in voters.values()) for voters in poll_data["votes"].values())
    
    embed = discord.Embed(
        title=f"📊 公會決議：{poll_data['title']}",
        description="請點擊下方按鈕進行投票。（系統會自動計算身分組權重）",
        color=discord.Color.gold()
    )
    
    for idx, option in enumerate(poll_data["options"]):
        option_weight = sum(v["weight"] for v in poll_data["votes"][str(idx)].values())
        percentage = (option_weight / total_weight * 100) if total_weight > 0 else 0
        
        filled_blocks = int(percentage / 10)
        empty_blocks = 10 - filled_blocks
        progress_bar = "█" * filled_blocks + "░" * empty_blocks
        
        embed.add_field(
            name=f"選項 {idx + 1}: {option}",
            value=f"{progress_bar} **{percentage:.1f}%** ({option_weight} 票權)",
            inline=False
        )
        
    embed.set_footer(text=f"總票權數：{total_weight} | 結束時間：{poll_data['end_time'].strftime('%Y-%m-%d %H:%M')}")
    return embed

class PollView(discord.ui.View):
    def __init__(self, poll_id: str, options: list):
        super().__init__(timeout=None)
        self.poll_id = poll_id
        
        for idx, option_text in enumerate(options):
            button = discord.ui.Button(
                label=option_text[:80],
                style=discord.ButtonStyle.primary,
                custom_id=f"vote_{poll_id}_{idx}"
            )
            button.callback = self.create_callback(idx)
            self.add_item(button)
            
    def create_callback(self, option_idx: int):
        async def button_callback(interaction: discord.Interaction):
            poll_data = active_polls.get(self.poll_id)
            if not poll_data:
                return await interaction.response.send_message("❌ 此投票已結束或不存在。", ephemeral=True)
                
            user_id = str(interaction.user.id)
            
            for existing_option, voters in poll_data["votes"].items():
                if user_id in voters:
                    if existing_option == str(option_idx):
                        return await interaction.response.send_message("⚠️ 你已經投過這個選項了！", ephemeral=True)
                    else:
                        del poll_data["votes"][existing_option][user_id]
                        break
                        
            weight = get_user_vote_weight(interaction.user)
            poll_data["votes"][str(option_idx)][user_id] = {"weight": weight}
            
            new_embed = generate_poll_embed(poll_data)
            await interaction.message.edit(embed=new_embed)
            
            await interaction.response.send_message(f"✅ 投票成功！(你的票權為：{weight})", ephemeral=True)
            
        return button_callback

class VotingSystemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
    async def end_poll_task(self, poll_id: str, delay_seconds: int, channel_id: int):
        await asyncio.sleep(delay_seconds)
        
        poll_data = active_polls.pop(poll_id, None)
        if not poll_data:
            return
            
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return
            
        try:
            message = await channel.fetch_message(int(poll_id))
            view = discord.ui.View.from_message(message)
            for child in view.children:
                child.disabled = True
                
            embed = generate_poll_embed(poll_data)
            embed.title = f"🏁 [已結算] 公會決議：{poll_data['title']}"
            embed.color = discord.Color.green()
            
            total_weight = sum(sum(v["weight"] for v in voters.values()) for voters in poll_data["votes"].values())
            if total_weight == 0:
                result_text = "無人參與投票，本次決議無效。"
            else:
                highest_votes = -1
                winners = []
                for idx, option in enumerate(poll_data["options"]):
                    option_weight = sum(v["weight"] for v in poll_data["votes"][str(idx)].values())
                    if option_weight > highest_votes:
                        highest_votes = option_weight
                        winners = [option]
                    elif option_weight == highest_votes:
                        winners.append(option)
                
                if len(winners) == 1:
                    result_text = f"🎉 決議結果：**{winners[0]}** 獲勝！"
                else:
                    result_text = f"⚖️ 決議結果：平手 ({', '.join(winners)})"
                    
            embed.add_field(name="最終結果", value=result_text, inline=False)
            
            await message.edit(embed=embed, view=view)
            await channel.send(f"📢 **投票已自動結算！** 請查看上方 {message.jump_url} 的最終結果。")
            
        except discord.NotFound:
            pass

    @app_commands.command(
        name="發起投票",
        description="[幹部專用] 發起具備身分組權重與自動結算的公會決議"
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        title="投票主題",
        option1="選項 1",
        option2="選項 2",
        option3="選項 3 (選填)",
        option4="選項 4 (選填)",
        duration_hours="投票持續時間(小時)，預設 24 小時"
    )
    async def create_poll(
        self, 
        interaction: discord.Interaction, 
        title: str, 
        option1: str, 
        option2: str, 
        option3: str = None, 
        option4: str = None,
        duration_hours: float = 24.0
    ):
        options = [opt for opt in [option1, option2, option3, option4] if opt]
        
        if len(set(options)) != len(options):
            return await interaction.response.send_message("❌ 選項不能重複！", ephemeral=True)
            
        end_time = datetime.now() + timedelta(hours=duration_hours)
        
        temp_votes = {str(i): {} for i in range(len(options))}
        
        poll_data = {
            "title": title,
            "options": options,
            "votes": temp_votes,
            "end_time": end_time,
            "channel_id": interaction.channel_id
        }
        
        embed = discord.Embed(
            title=f"📊 公會決議：{title}",
            description="正在建立投票系統...",
            color=discord.Color.light_gray()
        )
        await interaction.response.send_message(embed=embed)
        message = await interaction.original_response()
        poll_id = str(message.id)
        
        active_polls[poll_id] = poll_data
        
        final_embed = generate_poll_embed(poll_data)
        view = PollView(poll_id, options)
        await message.edit(embed=final_embed, view=view)
        
        delay_seconds = int(duration_hours * 3600)
        self.bot.loop.create_task(self.end_poll_task(poll_id, delay_seconds, interaction.channel_id))

async def setup(bot):
    await bot.add_cog(VotingSystemCog(bot))
