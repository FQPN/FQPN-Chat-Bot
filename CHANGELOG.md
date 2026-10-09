# Changelog

## 1.5.0
- New Moderation page: Bad words (Arabic and English, hard to dodge), Links, Excess caps, emotes and symbols, Repetitions and Shared chat. Each has an info button with examples and its own settings.
- "Blocked words" moved from the Blocklist into Moderation > Bad words (switched off, so nothing changes until you turn it on).

## 1.4.0
- The app tells its developer which Twitch channel uses it and which app version, about once a day. Nothing else is sent. Settings > App explains exactly what is sent.

## 1.2.0
- **New: Public command list.** Commands → **Public list** gives your channel one short link (for example `…/fqpn_`) to a web page that lists your commands, grouped by who can use them, with search, in English and Arabic. It updates by itself a few seconds after you change a command, and **Use for !cmlist** makes `!cmlist` send that link. It is off until you switch it on.
- Only the names of switched-on commands and who can use them are shared, never the replies. Each command has a new **Show on the public list** switch to keep it off the page. Switching the list off removes it from the website.
- Your Twitch login is sent with the list so the website can check which channel it is; the website does not keep it. If the website is down, the app keeps trying by itself and everything else works as before.
- **Fixed:** the Dashboard's Bot status said "Message is off" instead of "Connected · offline" when you were connected but not live (since 1.1.7).

## 1.1.10
- **Fixed: the variable tooltips were shifted by one.** In 1.1.9, hovering a variable button from $(viewers) to $(raider) showed the explanation and example of the next button (for example $(viewers) explained $(follow)). Each button now shows its own text again, in English and Arabic. $(viewers) is explained as the number of people watching now (in a raid reply, the number of raiders). Replies and commands were never affected, only the help text.

## 1.1.9
- **New variable $(viewers):** how many people are watching right now. Use it in commands and timers, for example a timer with 【 $(viewers) viewers ⏰ $(uptime) 】. It updates with every live check (about once a minute) and shows 0 when you are offline. In a raid reply, $(viewers) still means the number of people who raided you, as before.

## 1.1.7
- **The app is laid out for every window size.** The smallest window is now 1000 x 650 (bigger than a phone screen), and everything from there up to a very large monitor is arranged on purpose. The Commands table uses columns when there is room and tidy cards when there is not, so nothing is squeezed or cut off. On narrower windows the sidebar becomes a slim strip of icons (hover for the name). On very wide windows the content keeps a readable width, centered. Arabic answers line up with the rest, tab rows wrap instead of hiding, and short windows get tighter spacing.
- **One account in the sidebar.** Your avatar opens a small menu with your channel account, the bot account (click it to manage it) and Disconnect.
- **The sidebar is always right.** The red highlight now stays on the page you are on while you drag the window wider or narrower. When the window is too short for the whole menu, it scrolls (no scrollbar) and a soft fade above your account shows that there is more below.
- **Sidebar counts show what is switched on.** Commands, Timers, Events and now Greetings each show how many are active (a switched-off one is not counted), and the numbers follow your switches as you flip them.
- **The owners' names are links.** Hover FQPN_ or 1asoom in the top bar and the name turns your accent colour; click it to open that Twitch channel in your browser.
- **A soft border when you hover a sidebar item**, in your accent colour (it follows the accent you pick in Appearance).
- **Stream messages (Events > Stream).** The bot can say something in your chat when your stream starts, when it comes back after a drop, and when it ends, plus how many new followers you got since your last stream. Each of the four has its own switch, its own text with clickable variables ($(category), $(title), $(channel), $(uptime), $(newfollowers)) and a live preview, and they are all OFF until you switch them on. A short drop is not announced as the end: the stream counts as ended after 2 minutes offline, and if you are back within 15 minutes it is the same stream (the Resume message, and the uptime keeps adding up); both times can be changed. If you open the app in the middle of a stream it does not announce a start that happened hours ago. The messages are sent only while the app runs and the bot is not paused. The bot also learns about the stream going online or offline from Twitch straight away, so the messages are not held up by the live-check interval.
- **The bot keeps itself connected.** "Connected" used to only mean the bot had started: if the link to Twitch died quietly (after your PC slept, or the internet blipped) the bot could stop hearing chat while the app still said Connected. Now a watchdog checks every half minute that Twitch still has the bot's chat connection and that your Twitch login still works, and if that fails twice in a row it reconnects the bot by itself. It does not restart the bot just because the internet is down, it waits for it, and after a few restarts in an hour it stops and tells you instead of looping. It also checks straight away after your PC wakes up.
- **An honest status.** When the bot is reconnecting, the internet is down, your Twitch login has expired or the connection keeps failing, a banner says so (with Connect Twitch or Restart bot buttons where they help) and the Bot status card on the Dashboard shows it instead of "Connected". If the check for whether you're live keeps failing, you are told that timers are waiting. There is also a "Restart bot" row in the menu that opens from your avatar.
- **Calmer scrollbars.** Thin, rounded and quiet, with no arrow buttons. The sidebar has none, and the sideways scrollbar is gone.
- **"Getting started" goes away for good** once all five steps are done, and the tour skips that step then.
- The "Tutorial" row in Settings > App is gone; the Tutorial button at the top does the same.
- The separate phone layout is removed: the window cannot be made smaller than 1000 x 650.

## 1.1.5
- **A guided tour and a "Getting started" checklist.** On the first start the app walks you through everything in plain words (18 short steps, in English and Arabic): the menu, commands, timers, events, greetings, the blocklist, logs, settings, the separate bot account and donations. A "Tutorial" button in the top bar, a row in Settings > App and a button in the checklist replay it any time. The checklist on the Dashboard ticks itself off as you set things up (connect Twitch, make a command, turn on a timer, turn on an event reply, keep the bot on).
- **A tidier sidebar, and every section is its own page.** The menu is now in four groups: Overview, Chat tools, Connections and System. Commands, Timers and Events show a small count (how many commands, active timers and events with a reply on). **Greetings**, **Bot account** and **Donations** are now pages of their own, no longer tabs hidden inside Events and Settings. Settings keeps Appearance, App, Bot (pause and behaviour), Notifications and Logs and data. On a phone, the top menu lists every page.
- **A new app icon** (sidebar, tray, installer and window).

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
