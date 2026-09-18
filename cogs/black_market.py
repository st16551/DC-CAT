class TargetDebuffModal(discord.ui.Modal):
    target_name = discord.ui.TextInput(
        label="受害者名字或 ID",
        placeholder="請輸入你要施法的成員名稱...",
        max_length=50,
    )

    def __init__(self, cost, debuff_type, item_name, hours):
        super().__init__(title=f"施放【{item_name}】")
        self.cost = cost
        self.debuff_type = debuff_type
        self.item_name = item_name
        self.hours = hours

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        target_str = self.target_name.value.strip()

        if target_str.startswith("<@") and target_str.endswith(">"):
            clean_id = target_str.strip("<@!>")
            target_member = guild.get_member(int(clean_id))
        else:
            target_member = discord.utils.find(
                lambda m: target_str.lower() in m.name.lower() or target_str.lower() in m.display_name.lower(),
                guild.members,
            )

        if not target_member:
            await interaction.followup.send(f"❌ 找不到名為 `{target_str}` 的成員！", ephemeral=True)
            return

        if target_member.bot:
            await interaction.followup.send("❌ 不能對機器人施法！", ephemeral=True)
            return

        user_id = str(interaction.user.id)
        
        # 💡 修正處：補上扣款行為
        modify_balance(user_id, -self.cost, tx_type=f"buy_{self.debuff_type}", sender_id="SHOP_SYSTEM")

        key = f"{guild.id}_{target_member.id}"
        active_debuffs[key] = {
            "guild_id": guild.id,
            "user_id": target_member.id,
            "type": self.debuff_type,
            "expire_at": datetime.now() + timedelta(hours=self.hours),
        }

        await interaction.followup.send(
            f"🎯 施法成功！已對 **{target_member.display_name}** 施加【{self.item_name}】，持續 {self.hours} 小時！",
            ephemeral=True,
        )
        if guild.system_channel:
            await guild.system_channel.send(
                f"🔮 **【黑市詛咒】** {interaction.user.mention} 成功對 **{target_member.display_name}** 施展了 **{self.item_name}**！"
            )
