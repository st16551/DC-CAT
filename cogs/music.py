import discord
from discord.ext import commands
import wavelink

class MusicControlView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="上一首", style=discord.ButtonStyle.secondary, emoji="⏮️")
    async def prev_song(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 這裡可依需求實作歷史播放紀錄回溯
        await interaction.response.send_message("目前佇列暫無上一首紀錄。", ephemeral=True)

    @discord.ui.button(label="暫停/繼續", style=discord.ButtonStyle.success, emoji="⏯️")
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            return await interaction.response.send_message("機器人目前不在語音頻道中！", ephemeral=True)
        
        if player.paused:
            await player.resume()
            await interaction.response.send_message("▶️ 已經恢復播放！", ephemeral=True)
        else:
            await player.pause()
            await interaction.response.send_message("⏸️ 已經暫停播放！", ephemeral=True)

    @discord.ui.button(label="下一首", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def skip_song(self, interaction: discord.Interaction, button: discord.ui.Button):
        player: wavelink.Player = interaction.guild.voice_client
        if not player or not player.playing:
            return await interaction.response.send_message("目前沒有正在播放的音樂！", ephemeral=True)
        
        await player.skip()
        await interaction.response.send_message("⏭️ 已經跳過目前歌曲！", ephemeral=True)

    @discord.ui.button(label="音量+", style=discord.ButtonStyle.primary, emoji="🔊")
    async def volume_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            return await interaction.response.send_message("機器人尚未連線！", ephemeral=True)
        
        new_vol = min(player.volume + 10, 150)
        await player.set_volume(new_vol)
        await interaction.response.send_message(f"🔊 音量已調整為：{new_vol}%", ephemeral=True)

    @discord.ui.button(label="音量-", style=discord.ButtonStyle.primary, emoji="🔉")
    async def volume_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            return await interaction.response.send_message("機器人尚未連線！", ephemeral=True)
        
        new_vol = max(player.volume - 10, 0)
        await player.set_volume(new_vol)
        await interaction.response.send_message(f"🔉 音量已調整為：{new_vol}%", ephemeral=True)

    @discord.ui.button(label="停止播放", style=discord.ButtonStyle.danger, emoji="⏹️")
    async def stop_player(self, interaction: discord.Interaction, button: discord.ui.Button):
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            return await interaction.response.send_message("機器人不在語音頻道中！", ephemeral=True)
        
        await player.disconnect()
        await interaction.response.send_message("⏹️ 音樂已停止並離開頻道。", ephemeral=True)


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        # 初始化 Lavalink 節點連線
        node = wavelink.Node(uri="http://localhost:2333", password="youshallnotpass")
        await wavelink.Pool.init(nodes=[node], client=self.bot)
        print("Lavalink 節點連線初始化完成。")

    @app_commands.command(name="play", description="播放指定的音樂或加入待播清單")
    @app_commands.describe(search="請輸入歌曲名稱或 YouTube 連結")
    async def play(self, interaction: discord.Interaction, search: str):
        if not interaction.user.voice:
            return await interaction.response.send_message("請先加入一個語音頻道！", ephemeral=True)

        await interaction.response.defer()

        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            player = await interaction.user.voice.channel.connect(cls=wavelink.Player)

        # 搜尋音樂
        tracks = await wavelink.Playable.search(search)
        if not tracks:
            return await interaction.followup.send("找不到相關的音樂或網址無效。")

        track = tracks[0]
        await player.queue.put_wait(track)
        
        if not player.playing:
            await player.play(player.queue.get())

        embed = discord.VeiwEmbed if hasattr(discord, 'Embed') else discord.Embed(
            title="🎵 成功加入音樂",
            description=f"**[{track.title}]({track.uri})**",
            color=discord.Color.green()
        )
        embed.add_field(name="時長", value=f"{int(track.length // 60)}分{int(track.length % 60)}秒", inline=True)
        embed.add_field(name="點播者", value=interaction.user.mention, inline=True)
        embed.add_field(name="目前音量", value=f"{player.volume}%", inline=True)

        await interaction.followup.send(embed=embed, view=MusicControlView(self.bot))

async def setup(bot):
    await bot.add_cog(Music(bot))
