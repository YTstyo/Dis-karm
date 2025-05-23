class Config:
    TOKEN = "YOUR_DISCORD_BOT_TOKEN"
    OWNER_IDS = [123456789012345678]

    COOLDOWN_SECONDS = 60
    LEVEL_INTERVAL = 50  
    MAX_KARMA_PER_DAY = 100 

    DB_PATH = "karma.db"

    LEADERBOARD_LIMIT = 10

    PRESENCE_TEXT = "/karma help"

    REACTION_KARMA_ENABLED = True
    REACTION_COOLDOWN = 3600 

    DEFAULT_MIN_KARMA = 3
