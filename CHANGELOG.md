# Changelog

## 1.17.1

- Events: replies to the **Falkorie** bot. When Falkorie writes that a viewer reached a new level («auk78 is now level 6!») or shows a viewer's streak after !streak («FQPN_ has watched 112 streams in a row!»), the bot answers with your reply. Two new tabs on the Events page, **Falkorie level** and **Falkorie streak**, with {user}, {level} / {streak} and different replies by level or streak (on by default, with ready replies, like «Huge level 6, auk78»). Only real messages from Falkorie count, and the same streak gets one answer. Try them in Test chat with Pretend an event. A tour step shows where they are. The website's Variables page mentions Falkorie for $(level) and $(streak).
- Event replies tag the viewer: {user} (or $(user)) in any Events reply now shows as @name (@fqpn_ instead of fqpn_), so the viewer gets a notification. A reply that already has @{user} isn't doubled; a viewer with an Arabic display name is tagged by their Twitch login; donors whose name has a space (not a Twitch name) aren't tagged. A tour step shows it.

## 1.17.0

- Import commands (Commands page) from **StreamElements**, two ways: paste your StreamElements key (JWT Token: all commands, also hidden ones, and your timers; used once and never saved) or type your channel (the commands on its public page). Their other names come along, and ${user}-style variables become $(user) or from **Nightbot**, two ways: **Sign in with Nightbot** (approve once in the browser: all your commands, also mod-only ones, their $(count) numbers, and your timers, which come switched off), or **Just type the channel** (no sign-in: the commands on Nightbot's public commands page). You see every command first: reply, user level and cooldown carry over, Nightbot variables that only look different are changed ($(customapi) → $(urlfetch), $(twitch $(channel) "{{uptimeLength}}") → $(uptime)…), and a command using something the app doesn't have comes in switched off, with a note. For a name you already have (also "!discord" vs "discord"): skip, replace yours, or import it under another name. Nightbot aliases become other names. Command history has "Undo the whole import".
- New **Labs** tab in Settings: beta features you can try early, off until you switch them on there. Voice commands is the first: switched on, the Voice page (with its Beta tag) shows in the sidebar; switched off, voice stops and the page leaves the sidebar. (If you already had Voice on, it stays on.) Links to Labs on fqpnbot.com and to Support for feedback. The website gets a Labs section too, and Hotkeys joins its features.
- Voice commands (Beta), on their own Voice page in the sidebar, off by default. Hold a push-to-talk key (any key or a mouse side button) and say what the bot should do, in Arabic or English: timeout or ban someone (it asks first and shows the closest names in chat: say 1 / 2 / 3, yes or no), unban, reset a counter, start a mini game, change the title or game, or say something in chat («قول هلا والله تعجب» → it shows «هلا والله!» and sends it when you say yes, 1, 2 or 3; «تعجب» is !, «استفهام» is ؟: after a word «when استفهام» → when?, said first «تعجب when» → !when; a command like !when is sent from your own account so the bot answers it). Arabic, English or both mixed, in any word order; a word heard slightly wrong is matched to the nearest command word or game name. Games are known by every name: the short one («حروف»), the card's name («الكلمة المقلوبة», "Quick math"), English, your own game commands, and the usual mishearings («حروب» → حروف); «عكس الكلمة» is Opposites, not Backwards. Built-in «كنسل» / "cancel" takes back the last voice command (lifts the timeout or ban, gives the counter its number back, stops the game, puts the title or game back). Tick what voice may do. Switching it on downloads the free speech engine (whisper.cpp) and its model once (about 200 MB) into the app's folder; Remove the model frees the space.
- Voice: a third speech model, **Best** (Whisper large-v3, about 1.1 GB, checked after the download): the most accurate for Arabic, English and both mixed, slower than Accurate. Faster understanding: the engine only looks at as much audio as you recorded (not a full 30 seconds every time), and weighs a few readings of what you said (5 on Fast, 3 on Accurate, 2 on Best; 5 on a graphics card). New **Use my graphics card (NVIDIA)** switch (only shown with an NVIDIA card): about 280 MB once, commands understood in about a second; if it doesn't start on that PC, voice goes back to the processor by itself. The Voice page shows how long the last command took. With Arabic + English, when what it heard isn't a command (and it was quick) it listens to the same recording once more in the other language and keeps the reading that is one.
- New **Hotkeys** page in the sidebar (always there, not a beta): press a key anywhere, even in a game, to add 1 to a counter, take 1 off, send a message or command (a command like !discord is sent from your account so the bot answers it), or start a mini game (one you pick or a random one). Up to 12. Combos work: hold up to 4 keys together (Ctrl + Shift + F5, Mouse 4 + Q, F1 + F2) and let go to set it; letters and numbers need Ctrl, Alt, an F key or a mouse button with them, so typing doesn't set them off. They have their own switch and work without voice commands and without the download; the corner pop-up and the sound show what happened. The voice examples now use فقبن / FQPN.
- New sounds for voice commands and hotkeys: soft and short instead of the loud Windows beep (a rising "bloop" when voice heard you, a two-note chime when it's done, a low soft tone when it didn't work), made by the app itself. **Hear it** buttons on the Voice and Hotkeys pages, and Hotkeys have their own Sound switch.
- Nothing runs until the key is pressed: the microphone stays closed and the speech engine isn't started. It starts on the first press (a second or two), stops after 5 minutes without use, and speech is turned into text on the PC (nothing is sent anywhere).
- A small mic in a corner of the screen while you talk (✓ / ✕ after), click-through, any corner; a beep when it heard you; a Test button for the microphone; the last voice command; questions also show in the app with buttons. Every voice change to commands is in Command history ("you (voice)").
- New **Overlays** page (sidebar): one link for OBS (http://127.0.0.1:5000/overlay, a Browser Source of 1920×1080, see-through) for all your overlays, in a slim pill look. Switch on each counter and **First in chat** (who wrote first this stream, with their Twitch picture, a gold 1 and their streak), then on the big preview (a see-through checkerboard like OBS, with a Full screen button) click one to select it, drag it to move it, and drag a corner to make it bigger or smaller: OBS follows right away. Select more than one with Ctrl or Shift + click, or by drawing a box, then move or resize them together; arrow keys nudge (Shift for bigger steps). They're solid: one can't be dragged into another (it slides along it instead), and a new one that would land on another finds a free spot. Selecting one no longer makes the others jump to the corner. The OBS page reloads by itself when the app is updated. A one-line tip under the preview shows how to use it. Solid backgrounds, so nothing behind shows through. **Back to the corner** puts them all back. The ones not moved stack in the corner in the order they were switched on (a new one goes at the bottom, in the list too), in your accent color. Numbers roll when they change, +1 pops out, a reset spins to 0; it follows chat, the app, voice and mods' resets. The screen button next to a counter on the Counters page still shows it on stream too.
- Mini games > Leaderboard: a pencil next to each winner changes their wins in each game (all of them 0 takes them off), and **+ Add a winner** puts back a viewer whose wins were lost (a new PC, no backup): type their Twitch name and their wins.
- Website (public commands page): the Mini games list shows one card per game action instead of one per command: all its commands (like حروف؟ and !حروف) as small chips on top, then what it does and who can use it, in an even grid (one column on a phone). The count is the number of cards. Each command keeps its own direction, and an Arabic game name inside an English description no longer jumbles it.
- Website: new **Variables** page (fqpnbot.com/variables): all 36 variables in the app's groups, each with one line about it, an example command and what chat would show (sample values), a **Try it** box and a search, in English and Arabic. Linked from a button at the top of the home page, a card under the features, and **All variables** in the app's command editor (with a tour step).
- Built-in replies have no emojis anymore.

## 1.16.0

- Command history: every change to a command is kept: from the app, from mods in chat (!cmadd, !cmedit, !cmdel), the editor link or a backup restore, with who did it and when. Commands > History (or History in a command's edit window) shows what changed (before and after) and undoes it; a deleted command comes back with Bring back. The last 300 changes are kept.
- Undo: right after you save or delete a command, an Undo button shows at the bottom for 8 seconds.
- Counters: mods can reset counters from chat with the command + reset, like !deaths reset. It works with any command whose reply uses a counter ($(count name), $(getcount name) or $(count)), whatever its name or language, and resets every counter in that reply. Viewers who type it get the normal reply; the cooldown never blocks a mod's reset; it shows in Logs. In Commands > Counters: a switch (on by default) and who can reset (moderators and the streamer, or the streamer only); each counter shows its reset command, and Last change says who reset it ("reset by sami (mod)").
- Tutorial: 2 more steps (History, Reset from chat).
- Fewer antivirus false alarms: the program is no longer compressed with UPX, it has Windows version info (Properties > Details: FQPN, FQPN's Chat Bot, the version, copyright), and the GitHub build compiles its own PyInstaller bootloader instead of the shared ready-made one. The version comes from one place: the release tag.
- The program is now FQPNsChatBot.exe (it was FQPN'sChatBot.exe: an apostrophe in a program's name can trip up scripts and shortcuts). Updating removes the old one, makes the Start menu shortcut again and points an existing desktop shortcut and "Start with Windows" at the new name. A shortcut pinned to the taskbar by hand needs pinning again once.

  ## 1.15.0

- Four new mini games, so there are 11: «الدخيل» (odd one out: 4 words, 3 belong together; write the one that doesn't. Easy = clearly different groups, Hard = close ones; writing one of the other three locks you out of that round, and the winner's message says what the other three have in common), «ضد» (write the opposite word: about 130 pairs, Easy = everyday words, Hard = harder ones; every fair opposite counts), «لغز» (about 90 easy Arabic riddles, every fair answer counts, a hint halfway, 45 seconds) and «ترجم» (translate a word: Easy or Hard, the direction is random every round, or always English → Arabic or Arabic → English; every fair translation counts). Each has a hint halfway and its own leaderboard tab on the commands page.
- «سؤال» has about 270 questions now (it had about 100), in three difficulties: Easy, Medium and Hard, or Mixed (all of them). "How viewers answer" (only the question, or with 4 choices) is its own setting.
- Bot account: choose what the bot account sends (command replies, mini games, timers, events, greetings, stream messages, giveaways, moderation warnings). Anything switched off comes from your own account. On the Bot accounts page, for one channel or several. Deleting messages, timeouts and the test message always use the bot account.
- Counters: in Commands > Custom, a Commands | Counters switch next to the search shows every counter ($(count name) / $(getcount name)) with its number (never below 0), − / + buttons, an exact number box, which commands add to it or show it, and its last change ("+1 by chat · 3 min ago"). Reset one or all, rename one (your commands are updated to the new name) or delete one nothing uses. New counter can also make the two commands for you (one adds 1 for moderators, one shows the number for everyone).
- Dashboard: a Counters card with − / + for each counter, to fix a count in one click during the stream.
- Mini games: every game can now be started by everyone (set once, with this update). Change it in a game's ⚙ if you want moderators only: it stays the way you set it.
- Mini games: every game starts two ways by default, like «حروف؟» or «!حروف» (added for you where you kept the old command), and the new «العاب؟» / «games?» command lists the commands of the games that are on.
- Timers work like Nightbot's: “Chat lines” counts the chat messages of the last 5 minutes, and a timer that's due while chat is too quiet skips that time instead of posting the moment chat wakes up (so timers no longer pile up). Two timer messages are never sent within a minute of each other: the one that has waited longest goes first. New timers wait for 2 messages, and every timer that had Chat lines off is set to 2 once, with this update (turn it off again and it stays off).
- Leaderboards: All time, This week (starting on Sunday) and This month, in the app and on the commands page; «!الأوائل أسبوع» / «!الأوائل شهر» in chat, and «!فوز» shows this week and month too. Every win counts in all three; all-time wins are never touched. The app's leaderboard now also has tabs for «لغز», «ترجم» and «ضد».
- New variable $(clip): makes a Twitch clip of the last moments of the stream and gives its link (only while live), with a ready-made «!كليب» recipe (mods, 60 s cooldown). Clips need Twitch reconnected once; nobody is logged out by the update. In Test chat it's a pretend link.
- Blocklist: block someone for 1 to 99 minutes or hours, or permanently. A temporary block shows the time left with a bar and ends on its own (also when the app was closed); Make permanent keeps it. Your current blocked users stay permanent.
- Tutorial: 14 more steps (counters: the Commands | Counters switch, changing a counter, New counter and the Dashboard card; Stream stats, finding a command, who can use it and its cooldown, announcements, all-games settings, the leaderboard, recipes, giveaway settings, pausing the bot, backups). Each step shows the page and where you are on it («Mini games · 2 of 3»), and Skip this page jumps to the next page.
- Backup & restore: restoring a backup always failed with "This isn't a FQPN's Chat Bot backup" (the file was sent in a way the app refuses). Fixed, and any other problem now says what it was.
- Several channels: one of your channels can send the replies of another (account 1 for account 2, and the other way round). Choose it in “Who sends the replies” on the Bot accounts page: no new sign-in, and it uses the channel's own login. Signing in a channel as a bot account now explains this instead of only refusing.
- Mini games: in English, the « » around the game names and the start command on each card now read the right way on every PC.
- The commands page no longer says «سؤال» has 4 choices.
- Commands: Aliases are chips, like Trigger words: type a name and press Enter (or a comma); × removes one. Pasting "a, b, c" adds all three. Saved aliases are kept as they are.
- Sidebar: a gear for Settings, and a thin line between the sections. "Bot account(s)" keeps the same name before and after you open it.
- Fixed: disconnecting one of your channels (with several channels) stopped the whole app: every channel's bot and the app's pages froze. Now only that channel stops, and its background work stops with it.

## 1.14.0
   - The app is much faster and much lighter on your PC: it no longer keeps the graphics card and the CPU busy while it's open (also behind a game), its stats are counted in memory and saved once a minute, and nothing on the page moves after a few seconds.
   - The built-in commands (!cmlist, !title, !game, !cmadd, !cmedit, !cmdel, «app?») answer in Arabic when the app is in Arabic.
   - New variables $(count name) and $(getcount name): a counter with a name, shared by several commands (!death adds 1 with $(count deaths), !deaths shows it with $(getcount deaths)).
   - Variables about someone else: $(followage $(touser)), $(followdate $(touser)), $(follow $(touser)), $(firststreak $(touser)) and $(firststreakpeak $(touser)) are about the person mentioned (!followage @FQPN); alone they stay about the viewer, so your commands work as before. !wins @name shows that person's wins and leaderboard place. The !followage, !me and !first recipes use it, and a new !vs compares two people.
   - !game finds the game you mean: short and Arabic names (gta, جاتا, valo, فالو, ماين, ببجي, fc, سوالف…), the closest name, and what's popular on Twitch right now (GTA V rather than San Andreas).
   - Backup & restore in Settings > App: save your whole setup in one file, or bring it back from one (on a new PC, or to undo changes). Before restoring, your current setup is saved in the data folder, so a restore can be undone. Your Twitch logins, donation keys and the editor link are never in the file.
   - The public command list is switched on for every channel (once, with this update), and !cmlist sends its link. If you don't want it, switch it off in Commands > Public list: it stays off.
   - Dashboard: Stream stats for this stream, 7 or 30 days (messages, chatters, new chatters, commands used, followers, top commands, top chatters, top Twitch emotes with their pictures), and your commands page link with Copy. Counted on your PC and saved once a minute.
   - Commands: Public list and Editor link are under one Share button.
   - Commands: each command shows how often it was used in the last 30 days and when it was last used.
   - Mini games: one switch turns all games off or on again; each game keeps its own setting.
   - Timers can wait for chat: they post only after a few new chat messages (2 to 50, off at first).
   - Fixed: the narrow sidebar showed grey blocks between its parts instead of thin lines, and «app?» was squeezed in small windows.
   - Five new mini games: «ايموجي» (guess the word from simple emoji puzzles like 🐝🍯 → عسل; over 120 built in, add your own), «عكس» (write a backwards word the right way), «احسب» (a quick sum in Western digits, like 7 × 8: easy, normal or hard), «سلم» (the fastest to write 3 different words starting with a letter; 2 to 5 words in its settings) and «سؤال» (over 100 easy questions; viewers write the answer itself, like مسقط. Hard, the start: only the question, with a hint halfway. Easy: the 4 choices are shown too, and a wrong choice means no second try that round). Start them with !ايموجي, !عكس, !احسب, !سلم and !سؤال; «لعبه؟» starts a random game.
   - «رتب» is easier: only everyday words, 3 to 5 letters by default (up to 7 in its settings).
   - !top sends the link to your games leaderboard (when your public command list is on); the leaderboard has a tab for every game.
   - The website: how many streamers use the app, next to the Download button; one card for each chat tool, and the comparison has "Runs 100% locally", "No account required" and "No subscription". (Publish web/worker.js.)
   - Fixed: the app could keep the graphics card and the CPU busy (fans spinning, the PC slow or freezing) as long as its window was open, also behind a game: three animations never stopped (the background glow, the status dot, the sidebar sparkles). They are short now, and pause while you use another window. A small health log (perf.log in the data folder, one line a minute) helps find any other cause.
   - Fixed: the bot could keep disconnecting ("CERTIFICATE_VERIFY_FAILED") on PCs where an antivirus HTTPS scanning / web shield, a VPN or a network filter checks secure connections. Secure connections are now checked the way Windows does (truststore). If something still blocks Twitch, a clear warning says what to do.
   - A new look for the Test chat: lines like Twitch chat (time, small role tags), one-click roles, a random viewer, a Live/Offline pill, and a Commands tab with every command of your channel (search, filters, Send, Edit). Type ! in the message box to pick a command; ↑ brings back your last messages.
   - New recipes in Test chat > Recipes: 27 ready-made commands that together use every variable a command can use, each showing which variables it uses.
   - Developers' Users page: who is live right now (with viewers and game, from Twitch), a Watch button, and a Public list button for channels that have one. (Publish web/worker.js.)
   - The Blocklist in the menu shows how many users are blocked.
   - Pin first message: only counts in the first minutes of the stream (5 by default); if nobody writes the word by then, the streak is broken. You're never first on your own stream, "!first", "first?", "اول؟" or the name of one of your commands don't count, and it can just count the streak without pinning. New variable $(firststreakpeak): a viewer's best streak ever.

  ## 1.13.0
   - Editor link (Commands > Editor link): give someone you trust a link and a password; they can change your Commands, Timers, Events, Greetings, Blocklist, Moderation and Mini games from the website, on the app's own pages, and read the Logs.
   - A new password every time, the link ends after 24 hours, and you can cancel it at any moment. Every change is checked by your app and written in the Logs.
   - Your public command page has a Games leaderboard tab (the top 10 of each game) and uses your accent color. Hide the leaderboard in Commands > Public list.
   - Reply to the sender: a new switch on every command (off at first). Off, the bot writes a normal message, also from a bot account (it used to reply to every message); on, it replies to the viewer's message.
   - New variables, grouped by type in the command editor: $(accountage), $(random.chatter), $(followers), $(firststreak), $(weather city) and $(time city). Their "New" tag goes away once you've looked at one (hover it, use it, or try it in the Test chat).
   - New command type, Pin first message: the first viewer of the stream to write a word like first or اول gets their message pinned in chat (until the stream ends or 30 s to 30 min), with an optional reply and a streak.
   - Fixed: the app window could stay partly above the top of the screen (the 1.9.1 fix was missing). It now moves back as soon as you let go of it or open it again.
   - Fixed: a bot account's login could show "expired or missing" every few hours (two copies of its login were renewed in turn, and Twitch refused one), and timers were sometimes posted twice when Twitch answered the bot account too slowly. In most cases an affected login repairs itself.
   - New Test chat page (Chat tools > Test chat): write as any viewer (viewer, sub, VIP, mod, you) and see what the bot answers, with commands, games, filters, greetings and Pin first message; pretend any event or donation. Nothing is sent to Twitch and nothing real changes. With ready-made command recipes, every variable to try, a "try a response" box and a short how-to. The command editor has a Test button for unsaved commands.
   - Event replies can show totals with {total} (all the subs someone gifted, all their Bits, all their donations in that currency, or the months subscribed). The default sub, gift, Bits and donation replies use it; replies you changed stay as you wrote them.
   - New Giveaways page (Chat tools > Giveaways), like Nightbot's: draw a random active chatter (last 5 to 60 minutes), let viewers join by typing a keyword (open, close by hand or after N minutes, draw), or have them guess a secret number (the first right guess wins). Who can enter (user level), followers only, subscriber luck 1x-5x; never the bot, you or people on the Blocklist. Reroll, the winner's messages after the draw, the last 20 winners, saved across a restart. Practice it in the Test chat.
   - Your public command page shows a short example of what each command says (example names in place of the variables; links inside $(urlfetch) are never shown) and your mini games' commands in their own group, with what each one and each built-in command does. Commands > Public list can switch the examples off. (Publish web/worker.js.)
   - The window's top bar takes the app's colors (Windows 11: the exact dark or light color; Windows 10: dark or light). The Advanced variables are always shown.

## 1.12.0
   - Several channels in one app: each with its own commands, timers, greetings, moderation, games and settings, all running at once.
   - Bot accounts: one bot account can send for several channels; see which bot sends for which channel, and whether it can.
   - Safer data: atomic saves, damaged files never overwritten, a backup before moving your data to its channel folder.
   - New built-in command: «app?» / «برنامج؟» answers with the app's website.
   - After an update, Got it shows the new things with a short tour.

## 1.10.1
- The website is now fqpnbot.com. Your public command list link is fqpnbot.com/<your channel>, and it moves there by itself.
- Fixed: after the website address changed, the app never sent the command list to the new address.

## 1.10.0
- «رتب» shows the category of the word (like حيوان or بلاد), so it is much easier to guess. You can switch it off.
- Choose which categories are played, and give your own words a category of your own (like فواكه).
- New website address: commands.fqpnbot.workers.dev. Public command list links move there by themselves.
- New installs start with the public command list switched on. If you already use the app, nothing changes.
- Fixed: the category checkboxes in the mini game settings sat above their names.

## 1.9.0
- New mini game «رتب»: the bot shuffles the letters of a word (!رتب) and the first viewer to write it wins. A hint gives the first letter halfway through; 700+ built-in words, and you can add your own.
- Leaderboards per game: the Mini games page has tabs for All games, حروف and رتب, and "Reset this game". In chat, !فوز shows your wins per game and "!الأوائل رتب" shows one game's top 5.
- While a round runs, its card shows the letter or the shuffled letters and the time left.
- Only one round of any game runs at a time; automatic rounds of the two games take turns.
- Everyone's earlier wins are kept, as «اسم، جماد، نبات، حيوان، بلاد» wins.
- New "All games" settings under the game cards on the Mini games page. The wins and top 5 commands moved there from the «اسم، جماد، نبات، حيوان، بلاد» settings, because they work for every game.
- Rounds per stream (0 = no limit): every round counts, from chat or automatic, in any game. It refills when the next stream starts; a short drop or an app restart doesn't refill it. When it runs out, chat is told.
- Cooldown between rounds (0 to 3600 seconds, for every game): after a round ends, the next one waits; chat is told how long. Automatic rounds wait too. The broadcaster can always start a round.
- Every game command can have up to 5 names (aliases), like an Arabic and an English one. New defaults: !فوز and !wins, !الأوائل and !top. Names you had already changed stay as they are, and !wins / !top are only added where they don't clash with your own commands.
- A game command and one of your own commands can no longer have the same name (the game would answer first and your command would stop working): the save is refused and says which, from the app and from chat (!addcom).
- Lighter while you play: the app runs at "below normal" priority on Windows, so games get the CPU first. The dashboard sleeps while it is minimized or in the tray (no refreshing, no animations), looks less often while another program has the focus, and reloads your settings and logs only when something changed (it used to download all of them every 6 seconds).
- Fixed: the bot reconnected far more often than needed. The connection check now reads Twitch's whole list (old entries from earlier connections used to hide the live one, and each needless reconnect added another), never reconnects while chat messages are arriving, doesn't reconnect a quiet chat when Twitch confirms the connection, and a missing Twitch permission no longer counts as a broken login.
- Fixed: in the mini game settings, the note under the command box overlapped the box.
- Fixed: the app window could end up off the screen after being minimized (or after a monitor was unplugged or the resolution changed), where it couldn't be seen or moved. It now always comes back onto a screen.

## 1.8.0
- A "What's new" window after every update, in English and Arabic side by side.
- Commands are listed A to Z (Arabic أ to ي), with pages at the bottom: show 10, 25, 50 or 100.
- In Arabic, the sidebar stays on the left, like in English.

## 1.7.0
- The bot heals itself when Twitch rejects its login (it used to go silent until restarted), warns when two copies of the app are running, and reconnects if chat goes completely quiet while you're live.
- No Twitch login keys in bot.log any more.
- Shortcuts can use $(query): a !g command with $(query) makes "!g Valorant" change the game.
- $(eval) now understands Nightbot-style code (variables, lists, text).
- $(followage) shows the full time: years, months, days, hours, minutes and seconds.
- Fixed: the "new followers since the last stream" message.
- New Mini games page with «اسم، جماد، نبات، حيوان، بلاد» (!حروف, !صح, !فوز, !الأوائل).
- The tour shows Mini games.

## 1.6.0
- Logs now has three tabs: Activity, Moderation (the bot's filters and your mods' actions) and Bot (everything the bot said, and why), with search, counts and repeated rows grouped.
- Fixed: the "developer" tag on the Users page showed as a big red bar.
- The Users page is in its own Developer group in the sidebar.
- Events no longer show Twitch permission names.
- Moderation logs need six new read-only Twitch permissions: reconnect once when the app asks.

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
