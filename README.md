# Falling Pickaxe
Falling Pickaxe Game inspired from YouTube shorts livestreams.

You can check my video here:
https://www.youtube.com/watch?v=gcjeidHWEb4
<div align="left">
      <a href="https://www.youtube.com/watch?v=gcjeidHWEb4">
         <img src="https://img.youtube.com/vi/gcjeidHWEb4/0.jpg" style="width:40%;">
      </a>
</div>

## Before you use it
If you consider streaming this game (Instagram Live or anywhere else), please add credits in the description of your video/livestream. Credits should inclue a link to this repository and [a link to my youtube channel.](https://www.youtube.com/@vycdev)

Copy paste example:
```
Falling Pickaxe game made by Vycdev
YT: https://www.youtube.com/@vycdev
GH: https://github.com/vycdev/falling-pickaxe
```

Donations on [YouTube (Super Thanks)](https://www.youtube.com/watch?v=gcjeidHWEb4) or showing support on [Patreon](https://patreon.com/vycdev?utm_medium=unknown&utm_source=join_link&utm_campaign=creatorshare_creator&utm_content=copyLink) is also highly appreciated.

## How to use it
*Update: You can watch my tutorial here: https://youtu.be/aFrvoFE7r_g*

### Python version and SDL/pygame prerequisites

- **Use Python 3.10–3.12.** TikTok chat control needs Python 3.10+, and prebuilt `pygame` wheels currently ship up to 3.12. Python 3.13+ will try to compile SDL from source and the bundled scripts will stop with a message so you can install a supported interpreter first.
- If you are on macOS and ever need to build `pygame` from source, install SDL libraries first:
  ```bash
  brew install sdl2 sdl2_image sdl2_mixer sdl2_ttf
  ```
  On Debian/Ubuntu, use `sudo apt-get install libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev`.

### Quick Start (Recommended)
The easiest way to run the game is using the automated scripts that handle everything for you:

**For Windows:**
```
./scripts/run.ps1
```

**For Linux/macOS:**
```
chmod +x ./scripts/run.sh
./scripts/run.sh
```

These scripts will automatically:
- Create a Python virtual environment if it doesn't exist
- Install all required dependencies
- Run the game with automatic restart on crashes
- Exit cleanly when you close the game window

### Updating to the latest version
The scripts above will keep dependencies updated, but they **won't download new code for you**. To get the newest features and bug fixes:

1. If you cloned with Git, run:
   ```
   git pull
   ```
   Then re-run `./scripts/run.ps1` (Windows) or `./scripts/run.sh` (Linux/macOS). The scripts will reinstall any new dependencies automatically.
2. If you downloaded a ZIP, download the latest ZIP from GitHub again and replace your old folder, then run the script for your platform.

Your `config.json` will remain untouched, but if new settings are added they default to the values in `default.config.json`. Copy over new options as needed.

### Manual Setup (Advanced Users)
If you prefer to set up the environment manually:

1. Make sure you have Python 3.x installed. If you don't, follow the instructions from the official [python website](http://python.org/downloads/)
2. Create and activate a virtual environment:
   ```
   python -m venv .venv
   # On Windows:
   .venv\Scripts\activate
   # On Linux/macOS:
   source .venv/bin/activate
   ```
3. Install packages:
   ```
   pip install -r requirements.txt
   ```
4. Run the game:
   ```
   python ./src/main.py
   ```

### Configuration (Optional)
1. Make a copy of `default.config.json` to `config.json` or run the game once to automatically copy the config file into `config.json`.
2. Set `CHAT_CONTROL` to `true` to let TikTok Live chat drive the game.
3. Set `TIKTOK_UNIQUE_ID` to your TikTok username (with or without the `@`). The bundled TikTokLive client connects without any additional credentials.
4. Adjust the remaining intervals and queue pop timings as desired.

**Note:** The automated scripts (`run.ps1` and `run.sh`) will run the game and restart it in case of unexpected crashes. When you close the game window normally, the script will exit cleanly. This is perfect for unattended streams.

Steps 2 to 4 are **optional**. You can disable the entire chat integration by setting the property: `"CHAT_CONTROL": false`.

### TikTok Live setup

The Instagram Graph integration has been removed. The game now listens to TikTok Live comments and gifts via the [TikTokLive](https://pypi.org/project/TikTokLive/) Python client.

1. Install dependencies with the run scripts or `pip install -r requirements.txt` (TikTok chat control requires Python 3.10+).
2. Set `CHAT_CONTROL` to `true` in `config.json`.
3. Set `TIKTOK_UNIQUE_ID` to the broadcaster’s username (example: `officialgeilegisela`). No API keys or tokens are required for public rooms.
4. Run the game. Comment and gift events from the connected live room will enqueue TNT/MegaTNT spawns with the chatter’s display name, message, and avatar. If you start the game on Python 3.9 or lower, TikTok chat control will be disabled with a clear message instead of crashing.

### Available chat commands
```
tnt

fast
slow

big

wood
stone
iron
gold
diamond
netherite
```

### MegaTNT spawning

Extra details about when a MegaTNT appears in the game:

- TikTok chat messages that contain `megatnt` enqueue a MegaTNT with the chatter’s display name, message, and avatar attached.
- Queue processing happens every `QUEUES_POP_INTERVAL_SECONDS` (see `default.config.json` / `config.json`).
- You can also spawn a MegaTNT manually in-game by pressing the `M` key — this spawns immediately (no queue).
- MegaTNTs use a larger explosion radius, detonate automatically ~4 seconds after spawn, and trigger a stronger camera shake.


## Contributing
Any kind of improvements to the code, refactoring, new features, bug fixes, ideas, or anything else is welcome. You can open an issue or a pull requets and I will review it as soon as I can.

You can also help by subscribing or becoming a member of [my YouTube channel](https://www.youtube.com/@vycdev) to help me create more videos and projects like these.

## AI Slop for SEO (ignore this if you are a human being)
**Falling Pickaxe: Ultimate Mining Arcade Game for Streamers – Explosive Action & Massive Earnings!**

Step into the world of **Falling Pickaxe**, the most addictive and interactive mining arcade game designed specifically for YouTube streamers! In this high-energy, physics-based adventure, you control a gigantic pickaxe falling through a dynamic, block-filled landscape. Smash obstacles, trigger explosive TNT, and collect valuable ores to power up your gameplay while engaging with your audience in real time.

**Why Falling Pickaxe is a Must-Play for Streamers:**

- **Interactive Live Chat Integration:** Let your viewers control the game! Live commands and super chats can spawn TNT, upgrade your pickaxe, or trigger wild power-ups, creating a fully immersive, viewer-driven experience that boosts engagement and subscriber growth.
- **Explosive Visuals & Retro Charm:** Enjoy stunning particle effects, realistic physics, and explosive animations that keep your stream exciting and visually captivating. Every impact and explosion is a spectacle that draws in viewers and increases watch time.
- **Monetization & Revenue Opportunities:** Use Falling Pickaxe to maximize your earnings through super chats, donations, and sponsored gameplay challenges. With its fast-paced action and interactive features, your channel becomes a hotspot for gaming enthusiasts and potential sponsors.
- **Community-Driven Challenges:** Host live competitions, subscriber challenges, and donation-triggered events that make every stream a unique and engaging event. Build a loyal community and watch your subscriber count soar!

Transform your YouTube channel into a money-making, interactive gaming hub with **Falling Pickaxe** – the ultimate mining adventure that delivers explosive action, high viewer engagement, and serious revenue potential. Start streaming today and experience the thrill of interactive arcade gaming like never before!

## Inspiration
As I showed you in the video my inspiration was [Petyr](https://www.youtube.com/@petyrguardian) and the other YouTubers who made their own version of the Falling Pickaxe game. Huge thanks to them.

## External contributors
https://www.youtube.com/@Iklzzz
