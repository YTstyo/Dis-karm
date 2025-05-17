# SuperKarmaBot

SuperKarmaBot is a Discord bot that allows users to award and manage karma points, creating a positive and interactive community environment. It supports giving and removing karma, viewing leaderboards, and generating karma distribution graphs. Additionally, it features admin controls and the ability to create kudo boards for public recognition.

## Features

* Award and remove karma points.
* Check a user's karma and recent changes.
* View server-wide karma leaderboards.
* Visualize karma distribution as a graph.
* Admin commands to set karma directly and create kudo boards.
* Automated daily database cleanup.
* Cooldown system to prevent karma spam.
* User level system with customizable emojis.
* Reaction-based karma rewards.
* Kudo boards for special recognition in designated channels.

## Installation

1. **Clone the repository:**

```bash
git clone https://github.com/username/SuperKarmaBot.git
cd SuperKarmaBot
```

2. **Install dependencies:**

```bash
pip install -r requirements.txt
```

3. **Setup Configuration:**
   Create a `config.py` file with the following content:

```python
class Config:
    TOKEN = 'YOUR_DISCORD_BOT_TOKEN'
    OWNER_IDS = [123456789012345678, 987654321098765432]
    PRESENCE_TEXT = 'Managing Karma!'
    DB_PATH = 'karma.db'
    LEVEL_INTERVAL = 10
    COOLDOWN_SECONDS = 60
```

4. **Run the bot:**

```bash
python bot.py
```

## Usage

### User Commands

* `!karma give @user [amount] [reason]` - Award karma.
* `!karma remove @user [amount] [reason]` - Remove karma.
* `!karma check @user` - Check user's karma.
* `!karma leaderboard [limit]` - Show top karma holders.
* `!karma graph` - Visualize karma distribution.

### Admin Commands

* `!karmaadmin set @user [amount] [reason]` - Directly set karma.
* `!karmaadmin createboard #channel [min_karma]` - Create a kudo board.

### Automated Tasks

* **Daily Cleanup:** Removes old karma history entries (older than 30 days).

## Contributing

Feel free to fork the project and submit pull requests. Make sure to write clear commit messages and follow the established code style.

## License

This project is licensed under the MIT License.

## Issues

If you encounter any issues or have suggestions, please open an issue on GitHub.

Happy karma tracking!
