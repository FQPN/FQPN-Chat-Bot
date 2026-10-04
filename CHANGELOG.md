# Changelog

## 1.1.4
- **Donation alerts.** The bot can thank people in chat when they donate through **Streamlabs** or **StreamElements**. Paste your Streamlabs Socket API token and/or your StreamElements JWT in Settings > Donations (they are stored encrypted on your PC and never shown again), then set the replies in Events > Donation: different replies by amount (cents are allowed), with `{user}`, `{amount}`, `{currency}` and `{message}`. A donation also shows a desktop notification and appears in Logs. The bot only sees donations made while the app is running.
- **Use a separate bot account** (Settings > Bot > Chat account). Pick another Twitch account to write the bot's replies in your chat, while your own account keeps doing what only you can authorise (stream title and game, follows, hype trains). The new section shows both accounts, whether the bot account is a moderator of your channel, a "Send test message" button and a preview of how a reply looks in chat. The bot account is connected with its own Twitch login (use a private window where the bot account is logged in); your own login is not touched. With the option off, everything works exactly as before.

## 1.1.1
- **Fixed a "Not Found" page in the app window** on computers where another program (for example a Flask app) already used port 5000. The app now takes the next free port by itself and never shows an address it doesn't own.
- **Update pop-up:** when a new version is found, a pop-up offers **Update now** or **Update later**, with what's new. If notifications are on you also get a desktop notification, so you notice it even when the app is hidden in the tray.
- **The dashboard only ever opens in the app window, never in a browser.** A second launch waits for the first window and brings it to the front. If the window can't open, a message explains how to install the Microsoft Edge WebView2 Runtime.
- The installer removes the old `FQPN's Chat Bot.exe` left over from the first release and points an existing desktop shortcut at the current program.
- Fixed: starting the app a second time no longer opens a second copy (which also made the bot answer twice in chat). The copy that is already running comes to the front instead.
- **The built-in commands have new names**, so they no longer clash with Nightbot: `!cmlist` (was `!commands`), `!cmadd` (`!addcom`), `!cmedit` (`!editcom`), `!cmdel` (`!delcom`), `!settitle` (`!title`) and `!setgame` (`!game`). The old names do nothing in this bot any more, so only Nightbot answers them.
- Commands > Built-in now has a Status switch for each built-in command, so you can turn `!game`, `!title` and the others off.

## 1.1.0
- **The app updates itself.** It checks GitHub for a new release, downloads it in the background and installs it with one click ("Restart and update"), keeping your data.
- Settings now has five tabs: Appearance, App, Bot, Notifications, Logs and data.
- App: run on startup, start minimized to the tray, keep running in the tray when the window closes, reconnect to Twitch automatically (or press Reconnect).
- Notifications: desktop pop-ups (and an optional sound) for follows, subs, gift subs, raids, hype trains, bits and watch streaks.
- Logs: saved on your computer, kept for 7, 30 or 90 days or forever; optionally includes chat messages.
- Appearance: font size, accent color, compact layout, reduce motion. Start the bot paused or active when the app opens.

## 1.0.0
First release.

- Custom commands with aliases, spaces in names, user levels, cooldowns and variables
- `$(eval)` calculator, `$(urlfetch)`, `$(followage)` and more
- Timers, per-person Greetings (once per stream, random message)
- Twitch events: follows, subscriptions, gift subs, raids, hype trains, bits and watch streaks
- Blocklist, Logs, Pause switch
- Dashboard in English and Arabic, dark and light themes
