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
2. Set `CHAT_CONTROL` to `true` if you want Instagram Live chat to drive game events.
3. Fill in the Instagram/Facebook Graph fields (any one discovery path is enough):
   - `INSTAGRAM_USER_ID`: the IG user ID that owns the live broadcast (preferred when you already know it).
   - `INSTAGRAM_SHADOW_USER_ID`: optional shadow IG user ID returned from the Graph API when your account is linked to a Page.
   - `FACEBOOK_PAGE_ID`: optional Page ID so the game can discover the linked Instagram account automatically.
   - `INSTAGRAM_LIVE_MEDIA_ID`: optional fallback broadcast ID if you want to force a specific live session.
   - `INSTAGRAM_ACCESS_TOKEN`: a long-lived Instagram user token with the permissions required by the Instagram Graph API.
   - Placeholder strings that start with `YOUR_` are ignored by the app to prevent Graph errors—replace them with real IDs/tokens.
4. Adjust the remaining intervals and queue pop timings as desired.

**Note:** The automated scripts (`run.ps1` and `run.sh`) will run the game and restart it in case of unexpected crashes. When you close the game window normally, the script will exit cleanly. This is perfect for unattended streams.

Steps 2 to 4 are **optional**. You can disable the entire Instagram integration by setting the property: `"CHAT_CONTROL": false`.

### Instagram Live setup (using Instagram Login)
The YouTube polling logic has been replaced with Instagram Live comment polling. To wire it up with your Instagram account:

1. Create a Meta app and enable **Instagram Graph API** with Instagram Login for your app, as described in the official guide: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login
2. Ensure your Instagram account is a **Business** or **Creator** account linked to a Facebook Page (required for the Graph API).
3. Obtain a short-lived Instagram user access token via Instagram Login, then exchange it for a **long-lived user token** (valid up to 60 days) using the same guide. Place this token in `INSTAGRAM_ACCESS_TOKEN`.
4. Provide one of the following so the game can discover your IG user ID:
   - **Direct**: call `me?fields=id,username` with your access token and place the ID in `INSTAGRAM_USER_ID`.
   - **Via Facebook Page**: call `/{page-id}?fields=instagram_business_account,instagram_professional_account,connected_instagram_account,shadow_ig_user` using the Graph API explorer (https://developers.facebook.com/docs/graph-api). Copy the returned IG/Shadow IG user ID into either `INSTAGRAM_USER_ID` or `INSTAGRAM_SHADOW_USER_ID`, or simply set `FACEBOOK_PAGE_ID` and let the game resolve it automatically.
5. Start an Instagram Live broadcast. The game will call the Live Media endpoint (https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/live_media/) on **Graph API v24.0** to locate the active broadcast and then poll `/{live_media_id}/live_comments` (falling back to `/comments` when needed) for chat messages.
6. If you prefer to hardcode a specific live media ID instead of auto-detection, copy it from your live session and place it in `INSTAGRAM_LIVE_MEDIA_ID`.

Once configured, every Instagram Live comment will spawn a TNT in-game with the commenter’s display name, message, and profile picture attached. Some comment nodes omit `profile_picture_url`, so the game makes a follow-up call to the IG user node to retrieve the avatar when necessary.

**Instagram Graph troubleshooting**

- If you see an error like `OAuthException code 190 (error_subcode 467)` in the console logs, your access token is expired or revoked. Regenerate a **long-lived user token** with Instagram Login (https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login#exchanging-a-short-lived-token-for-a-long-lived-token) and update `INSTAGRAM_ACCESS_TOKEN`.
- When you only have a Facebook Page ID, you can still resolve the live account through Graph Explorer (https://developers.facebook.com/tools/explorer/) using the **Shadow IG User** endpoints (https://developers.facebook.com/docs/graph-api/reference/shadow-ig-user/):
  1. Query `/{page-id}?fields=instagram_business_account,instagram_professional_account,connected_instagram_account,shadow_ig_user` to retrieve the linked IG/shadow IG user ID.
  2. Query `/{shadow-ig-user-id}/live_media?fields=id,status,title,ingest_streams` to find the active live media.
  3. If needed, call `/{live_media_id}/live_comments?fields=id,text,from{id,username,profile_picture_url},created_time` to verify chat access.
- If the token is invalid, the game will temporarily skip Graph calls until you supply a new token to prevent repeated failures.
- If your Page does not expose a `shadow_ig_user`, use the `connected_instagram_account` or `instagram_business_account`/`instagram_professional_account` IDs from step 1 above. Drop whichever ID you get into `INSTAGRAM_USER_ID` (or keep `FACEBOOK_PAGE_ID` set) and restart the game—the app will resolve and poll that account automatically. Placeholder values like `YOUR_LIVE_MEDIA_ID_OPTIONAL` are skipped so you won’t see GraphMethodException 100 errors when you leave them unchanged.

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

- Instagram chat messages that contain `megatnt` enqueue a MegaTNT with the chatter’s display name, message, and avatar attached.
- Queue processing happens every `QUEUES_POP_INTERVAL_SECONDS` (see `default.config.json` / `config.json`). Polling frequency for Instagram is controlled by `INSTAGRAM_POLL_INTERVAL_SECONDS`.
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
