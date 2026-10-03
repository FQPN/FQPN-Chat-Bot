# Changelog

## 1.1.1
- Fixed: starting the app a second time no longer opens a second copy (which also made the bot answer twice in chat). The copy that is already running comes to the front instead.
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
