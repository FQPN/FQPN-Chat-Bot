# FQPN's Chat Bot

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

The app updates itself: with **Check for updates automatically** on (Settings > App) it finds a new release, downloads it quietly and offers **Restart and update**. If you would rather do it by hand, run the newest Setup.exe from Releases; it upgrades in place. Your commands and Twitch login are always kept.

## Install from source (Windows, for developers)
1. Install [Python](https://www.python.org/downloads/) (3.10 or newer). Tick **Add Python to PATH** in the installer.
2. Download this project (green **Code** button, then **Download ZIP**) and unzip it.
3. Double-click **run.bat**. The first run sets everything up and may take a minute.

## First start
1. The bot asks you to connect Twitch: the dashboard shows a short code and an **Open Twitch** button.
2. Open the link, enter the code and click **Authorize**. You only do this once.
3. The dashboard opens in the app window by itself. It uses a free local port (usually 5000; if another program already uses it, the next free one). It is reachable from this computer only.

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
- Windows says **"An Application Control policy has blocked this file"** (error 4551): Smart App Control blocks programs that are not digitally signed. Until the installer is signed (see *Code signing policy* below), either turn Smart App Control off in **Windows Security > App & browser control**, or run the bot from source with Python (see *Install from source*).
- A red banner says the bot can't be reached: check that the black window from `run.bat` is still open.
- Follows or hype trains don't work: they need the extra permissions above. Disconnect and connect Twitch again from the account menu.
- Anything else: look at the black window; it prints the reason.

## Code signing policy
Free code signing provided by [SignPath.io](https://about.signpath.io/), certificate by [SignPath Foundation](https://signpath.org/).

**Status:** an application to the SignPath Foundation is pending. Until it is accepted, the Windows installer is **not** signed.
After it is accepted, only installers built by this project's public GitHub Actions workflow from the source in this repository will be signed.

Team roles:
- Committers and reviewers: [FQPN](https://github.com/FQPN)
- Approvers: [FQPN](https://github.com/FQPN)

All contributors with write access use multi-factor authentication on GitHub.

## Privacy policy
This program will not transfer any information to other networked systems unless specifically requested by the user or the person installing or operating it.

In detail:
- The bot connects to **Twitch** because that is its purpose: it reads your chat and events and sends your replies. Your Twitch login is stored only on your computer, in `%APPDATA%\TwitchChatBot\authentication`.
- `$(urlfetch ...)` in a command contacts the web address the streamer wrote in that command, and only when the command is used.
- The dashboard page loads its fonts (Outfit and Tajawal) from Google Fonts.
- Commands, timers, greetings, events and settings are stored only on your computer, in `%APPDATA%\TwitchChatBot\data`.
- There is no telemetry and no analytics. If **Check for updates automatically** is on (Settings > App, you can switch it off), the app asks GitHub for the newest release now and then and downloads its installer from this project's GitHub releases.
- Pop-ups, the tray icon and the saved logs work entirely on your computer. Chat messages are only saved if you switch on **Log chat messages**.

## License
[MIT](LICENSE)
