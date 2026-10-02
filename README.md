# Twitch Chat Bot

A Twitch chat bot you run on your own computer, with a web dashboard to manage it.
The dashboard is in English and Arabic.

## What it does
- **Commands:** names with or without a symbol (`!discord`, `hello there`), aliases, user levels, cooldowns
- **Variables:** `$(user)`, `$(touser)`, `$(count)`, `$(game)`, `$(uptime)`, `$(followage)`, `$(urlfetch ...)`, `$(eval ...)` and more
- **Timers:** messages on a schedule, only while you are live
- **Greetings:** greet chosen people once per stream, with one of several random messages
- **Twitch events:** follows, subscriptions, gift subs, raids, hype trains, bits and watch streaks, each with its own reply
- **Blocklist, Logs and a Pause switch**

## Install (Windows, no Python needed)
1. Open the **Releases** page of this project and download **FQPN-Chat-Bot-Setup-x.y.z.exe**.
2. Run it and follow the steps. It installs for your user only; no administrator rights are needed.
3. Start **FQPN's Chat Bot** from the Start menu (or the desktop shortcut).

Windows may show a blue **"Windows protected your PC"** box because the installer is not signed.
Click **More info**, then **Run anyway**.

Your commands, timers and Twitch login are saved in `%APPDATA%\TwitchChatBot`, outside the program folder.
Installing a newer version over the old one, or uninstalling, never deletes them. The file `bot.log` in that folder
shows what the bot printed, which helps when asking for help.

To update: download the newest Setup.exe from Releases and run it. It upgrades in place.

## Install from source (Windows, for developers)
1. Install [Python](https://www.python.org/downloads/) (3.10 or newer). Tick **Add Python to PATH** in the installer.
2. Download this project (green **Code** button, then **Download ZIP**) and unzip it.
3. Double-click **run.bat**. The first run sets everything up and may take a minute.

## First start
1. The bot asks you to connect Twitch: the dashboard shows a short code and an **Open Twitch** button.
2. Open the link, enter the code and click **Authorize**. You only do this once.
3. The dashboard is at **http://localhost:5000** (it opens by itself). It is reachable from this computer only.

## Twitch permissions the bot asks for
`user:read:chat`, `user:write:chat`, `moderator:manage:announcements`, `channel:manage:broadcast`,
`moderator:read:followers`, `channel:read:hype_train`

## Your data
Everything you set up is saved on your computer:

| Folder | What is in it |
|---|---|
| `data/` | commands, timers, greetings, events, settings |
| `authentication/` | your Twitch login (**never share or upload this folder**) |

Both folders are ignored by Git, so they are never uploaded.

## Updating
- **With Git:** double-click **update.bat**.
- **With a ZIP:** download the new ZIP, copy its files over the old ones, and keep your `data` and `authentication` folders.

## Troubleshooting
- A red banner says the bot can't be reached: check that the black window from `run.bat` is still open.
- Follows or hype trains don't work: they need the extra permissions above. Disconnect and connect Twitch again from the account menu.
- Anything else: look at the black window; it prints the reason.

## License
Add a license file (MIT is a common choice for a project like this).
