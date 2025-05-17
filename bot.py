import logging
import random
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import discord
from discord import app_commands
from discord.ext import commands, tasks
import aiosqlite
import matplotlib.pyplot as plt
from io import BytesIO
from config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("karma.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("SuperKarmaBot")

class KarmaEmojis:
    UP = "🔼"
    DOWN = "🔽"
    TOP = "🏆"
    LEVELS = ["⭐", "🌟", "✨", "💫", "☄️"]
    REACTIONS = ["👍", "❤️", "🎉", "🔥", "👏"]

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

class SuperKarmaBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
            activity=discord.Game(name=Config.PRESENCE_TEXT),
            owner_ids=Config.OWNER_IDS
        )
        self.db_pool = None
        self.cooldowns = {}
        self.karma_events = []
        self.start_time = datetime.now()
        
    async def setup_hook(self):
        self.db_pool = await aiosqlite.connect(Config.DB_PATH)
        await self.init_db()
        await self.load_cogs()
        await self.tree.sync()
        self.cleanup_task.start()
        logger.info("SuperKarmaBot initialized!")

    async def init_db(self):
        await self.db_pool.execute("""
            CREATE TABLE IF NOT EXISTS karma (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                karma INTEGER NOT NULL DEFAULT 0,
                last_updated TEXT,
                PRIMARY KEY (user_id, guild_id)
            )
        """)
        await self.db_pool.execute("""
            CREATE TABLE IF NOT EXISTS karma_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                change INTEGER NOT NULL,
                reason TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self.db_pool.execute("""
            CREATE TABLE IF NOT EXISTS kudo_boards (
                channel_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                min_karma INTEGER DEFAULT 1
            )
        """)
        await self.db_pool.commit()

    async def load_cogs(self):
        await self.load_extension("jishaku")

    async def close(self):
        self.cleanup_task.cancel()
        if self.db_pool:
            await self.db_pool.close()
        await super().close()

    @tasks.loop(hours=24)
    async def cleanup_task(self):
        await self.db_pool.execute("DELETE FROM karma_history WHERE timestamp < datetime('now', '-30 days')")
        await self.db_pool.commit()
        logger.info("Performed daily database cleanup")

bot = SuperKarmaBot()

class KarmaManager:
    @staticmethod
    async def get_karma(user_id: int, guild_id: int) -> Dict:
        async with bot.db_pool.execute(
            """SELECT karma, last_updated FROM karma 
               WHERE user_id = ? AND guild_id = ?""",
            (user_id, guild_id)
        ) as cursor:
            row = await cursor.fetchone()
            return {
                "karma": row[0] if row else 0,
                "last_updated": row[1] if row else None
            }

    @staticmethod
    async def update_karma(user_id: int, guild_id: int, delta: int, reason: str = None) -> Dict:
        async with bot.db_pool.execute(
            """INSERT INTO karma (user_id, guild_id, karma, last_updated)
               VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT(user_id, guild_id) DO UPDATE SET
               karma = karma + excluded.karma,
               last_updated = excluded.last_updated
               RETURNING karma""",
            (user_id, guild_id, delta)
        ) as cursor:
            result = await cursor.fetchone()
            await bot.db_pool.execute(
                """INSERT INTO karma_history 
                   (user_id, guild_id, change, reason)
                   VALUES (?, ?, ?, ?)""",
                (user_id, guild_id, delta, reason)
            )
            await bot.db_pool.commit()
            
            return {
                "new_karma": result[0],
                "level": await KarmaManager.calculate_level(result[0])
            }

    @staticmethod
    async def calculate_level(karma: int) -> int:
        return min(karma // Config.LEVEL_INTERVAL, len(KarmaEmojis.LEVELS)-1)

    @staticmethod
    async def get_leaderboard(guild_id: int, limit: int = 10) -> List[Dict]:
        async with bot.db_pool.execute(
            """SELECT user_id, karma FROM karma
            WHERE guild_id = ?
            ORDER BY karma DESC
            LIMIT ?""",
            (guild_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            return [{"user_id": row[0], "karma": row[1]} for row in rows]

    @staticmethod
    async def get_history(user_id: int, guild_id: int, limit: int = 5) -> List[Dict]:
        async with bot.db_pool.execute(
            """SELECT change, reason, timestamp FROM karma_history
               WHERE user_id = ? AND guild_id = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (user_id, guild_id, limit)
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    @staticmethod
    async def create_kudo_board(channel_id: int, guild_id: int, min_karma: int = 1):
        await bot.db_pool.execute(
            """INSERT OR REPLACE INTO kudo_boards
               (channel_id, guild_id, min_karma)
               VALUES (?, ?, ?)""",
            (channel_id, guild_id, min_karma)
        )
        await bot.db_pool.commit()

def is_owner():
    async def predicate(interaction: discord.Interaction):
        if interaction.user.id not in Config.OWNER_IDS:
            raise commands.NotOwner("Only bot owners can use this command")
        return True
    return app_commands.check(predicate)

def check_cooldown(user_id: int) -> Optional[timedelta]:
    last_action = bot.cooldowns.get(user_id)
    if not last_action:
        return None
    elapsed = datetime.now() - last_action
    if elapsed < (cooldown := timedelta(seconds=Config.COOLDOWN_SECONDS)):
        return cooldown - elapsed
    return None

karma_group = app_commands.Group(name="karma", description="Karma management commands")

@karma_group.command(name="give", description="Award karma to a user")
@app_commands.describe(
    user="The user to recognize",
    amount="Karma amount (default: 1)",
    reason="Reason for giving karma"
)
async def karma_give(
    interaction: discord.Interaction,
    user: discord.Member,
    amount: app_commands.Range[int, 1, 10] = 1,
    reason: Optional[str] = None
):
    if user.id == interaction.user.id:
        return await interaction.response.send_message(
            "❌ You cannot give yourself karma",
            ephemeral=True
        )

    if remaining := check_cooldown(interaction.user.id):
        return await interaction.response.send_message(
            f"⏳ Please wait {remaining.seconds}s before giving karma again",
            ephemeral=True
        )

    result = await KarmaManager.update_karma(
        user.id, interaction.guild_id, amount, reason)
    bot.cooldowns[interaction.user.id] = datetime.now()

    level_emoji = KarmaEmojis.LEVELS[result["level"]]
    embed = discord.Embed(
        title=f"{KarmaEmojis.UP} Karma Given",
        description=f"Awarded {amount} karma to {user.mention}",
        color=discord.Color.green()
    )
    embed.add_field(name="New Total", value=f"{result['new_karma']} {level_emoji}")
    if reason:
        embed.add_field(name="Reason", value=reason, inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@karma_group.command(name="remove", description="Remove karma from a user")
@app_commands.describe(
    user="The user to remove karma from",
    amount="Karma amount (default: 1)",
    reason="Reason for removal"
)
async def karma_remove(
    interaction: discord.Interaction,
    user: discord.Member,
    amount: app_commands.Range[int, 1, 10] = 1,
    reason: Optional[str] = None
):
    if user.id == interaction.user.id:
        return await interaction.response.send_message(
            "❌ You cannot remove your own karma",
            ephemeral=True
        )

    if remaining := check_cooldown(interaction.user.id):
        return await interaction.response.send_message(
            f"⏳ Please wait {remaining.seconds}s before modifying karma again",
            ephemeral=True
        )

    result = await KarmaManager.update_karma(
        user.id, interaction.guild_id, -amount, reason)
    bot.cooldowns[interaction.user.id] = datetime.now()

    level_emoji = KarmaEmojis.LEVELS[result["level"]]
    embed = discord.Embed(
        title=f"{KarmaEmojis.DOWN} Karma Removed",
        description=f"Removed {amount} karma from {user.mention}",
        color=discord.Color.orange()
    )
    embed.add_field(name="New Total", value=f"{result['new_karma']} {level_emoji}")
    if reason:
        embed.add_field(name="Reason", value=reason, inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@karma_group.command(name="check", description="Check a user's karma")
@app_commands.describe(user="User to check (defaults to you)")
async def karma_check(
    interaction: discord.Interaction,
    user: Optional[discord.Member] = None
):
    target = user or interaction.user
    karma_data = await KarmaManager.get_karma(target.id, interaction.guild_id)
    level = await KarmaManager.calculate_level(karma_data["karma"])
    level_emoji = KarmaEmojis.LEVELS[level]
    
    history = await KarmaManager.get_history(target.id, interaction.guild_id)
    
    embed = discord.Embed(
        title=f"{level_emoji} {target.display_name}'s Karma",
        color=discord.Color.blurple()
    )
    embed.add_field(name="Total Karma", value=karma_data["karma"])
    embed.add_field(name="Level", value=f"{level} {level_emoji}")
    
    if history:
        recent_changes = "\n".join(
            f"{'+' if change['change'] > 0 else ''}{change['change']} - {change['reason'] or 'No reason'}"
            for change in history
        )
        embed.add_field(name="Recent Changes", value=recent_changes, inline=False)
    
    embed.set_thumbnail(url=target.display_avatar.url)
    await interaction.response.send_message(embed=embed)

@karma_group.command(name="leaderboard", description="Show server karma leaders")
@app_commands.describe(limit="Number of users to show (max 25)")
async def karma_leaderboard(
    interaction: discord.Interaction,
    limit: app_commands.Range[int, 1, 25] = 10
):
    records = await KarmaManager.get_leaderboard(interaction.guild_id, limit)
    if not records:
        return await interaction.response.send_message(
            "No karma records yet in this server!",
            ephemeral=True
        )

    leaderboard = []
    for idx, record in enumerate(records, 1):
        user = interaction.guild.get_member(record["user_id"]) or f"User {record['user_id']}"
        level = await KarmaManager.calculate_level(record["karma"])
        leaderboard.append(
            f"{idx}. {getattr(user, 'display_name', user)} - "
            f"{record['karma']} {KarmaEmojis.LEVELS[level]}"
        )

    embed = discord.Embed(
        title=f"{KarmaEmojis.TOP} Karma Leaderboard",
        description="\n".join(leaderboard),
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"Top {limit} users")
    await interaction.response.send_message(embed=embed)

@karma_group.command(name="graph", description="Visualize karma distribution")
async def karma_graph(interaction: discord.Interaction):
    records = await KarmaManager.get_leaderboard(interaction.guild_id, 10)
    if not records:
        return await interaction.response.send_message(
            "Not enough data to generate graph",
            ephemeral=True
        )

    users = []
    karma_values = []
    for record in records:
        user = interaction.guild.get_member(record["user_id"])
        users.append(getattr(user, 'display_name', f"User {record['user_id']}"))
        karma_values.append(record["karma"])

    plt.figure(figsize=(10, 6))
    bars = plt.bar(users, karma_values, color='skyblue')
    plt.title('Top Karma Holders')
    plt.ylabel('Karma Points')
    plt.xticks(rotation=45, ha='right')
    
    # Add value labels
    for bar in bars:
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height,
                f'{int(height)}',
                ha='center', va='bottom')

    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    plt.close()
    
    file = discord.File(buf, filename="karma_graph.png")
    embed = discord.Embed(title="Karma Distribution", color=discord.Color.blue())
    embed.set_image(url="attachment://karma_graph.png")
    await interaction.response.send_message(file=file, embed=embed)

admin_group = app_commands.Group(name="karmaadmin", description="Admin karma controls", default_permissions=discord.Permissions(manage_guild=True))

@admin_group.command(name="set", description="Set a user's karma directly")
@app_commands.describe(
    user="User to modify",
    amount="New karma value",
    reason="Reason for change"
)
async def admin_set(
    interaction: discord.Interaction,
    user: discord.Member,
    amount: int,
    reason: Optional[str] = None
):
    current = await KarmaManager.get_karma(user.id, interaction.guild_id)
    delta = amount - current["karma"]
    
    result = await KarmaManager.update_karma(
        user.id, interaction.guild_id, delta, reason or "Admin adjustment")
    
    embed = discord.Embed(
        title="⚡ Admin Karma Adjustment",
        description=f"Set {user.mention}'s karma to {amount}",
        color=discord.Color.purple()
    )
    embed.add_field(name="Change", value=f"{delta:+d}")
    if reason:
        embed.add_field(name="Reason", value=reason, inline=False)
    
    await interaction.response.send_message(embed=embed)

@admin_group.command(name="createboard", description="Create a kudo board channel")
@app_commands.describe(
    channel="Channel to make a kudo board",
    min_karma="Minimum karma needed to give recognition"
)
async def create_board(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    min_karma: app_commands.Range[int, 1, 10] = 1
):
    await KarmaManager.create_kudo_board(channel.id, interaction.guild_id, min_karma)
    
    embed = discord.Embed(
        title="📌 Kudo Board Created",
        description=f"{channel.mention} is now a kudo board!",
        color=discord.Color.green()
    )
    embed.add_field(
        name="Requirements",
        value=f"Minimum {min_karma} karma to give recognition"
    )
    await interaction.response.send_message(embed=embed)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    
    async with bot.db_pool.execute(
        "SELECT min_karma FROM kudo_boards WHERE channel_id = ?",
        (message.channel.id,)
    ) as cursor:
        board = await cursor.fetchone()
        if board:
            if not message.content.startswith(("+rep", "!rep", "/rep")):
                await message.delete()
                try:
                    await message.author.send(
                        f"Only kudo messages are allowed in {message.channel.mention}.\n"
                        "Use `+rep @user [reason]` to give recognition."
                    )
                except discord.Forbidden:
                    pass
            return
    
    await bot.process_commands(message)

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if str(payload.emoji) in KarmaEmojis.REACTIONS:
        channel = bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        
        if payload.user_id == message.author.id:
            return
            
        result = await KarmaManager.update_karma(
            message.author.id, payload.guild_id, 1,
            f"Received {payload.emoji} reaction"
        )
        
        new_level = await KarmaManager.calculate_level(result["new_karma"])
        old_level = new_level - 1 if result["new_karma"] > 1 else 0
        
        if new_level > old_level:
            user = await bot.fetch_user(message.author.id)
            await user.send(
                f"🎉 You leveled up to {KarmaEmojis.LEVELS[new_level]} "
                f"Karma Level {new_level}!"
            )

@bot.event
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"⏳ Command on cooldown. Try again in {error.retry_after:.1f}s",
            ephemeral=True
        )
    elif isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "🔒 You don't have permission to use this command",
            ephemeral=True
        )
    else:
        logger.error(f"Command error: {error}", exc_info=True)
        await interaction.response.send_message(
            "⚠️ An error occurred while executing this command",
            ephemeral=True
        )

bot.tree.add_command(karma_group)
bot.tree.add_command(admin_group)

@bot.event
async def on_ready():
    logger.info(f"SuperKarmaBot ready! Logged in as {bot.user}")
    logger.info(f"Servers: {len(bot.guilds)}")
    logger.info(f"Latency: {bot.latency*1000:.2f}ms")

if __name__ == "__main__":
    if not Config.TOKEN:
        logger.critical("Missing bot token in config.py")
        exit(1)
    bot.run(Config.TOKEN)