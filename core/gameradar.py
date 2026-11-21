"""1.20.0: Game Radar. The app sees which game is open on this PC.

  - $(gameinfo) -> "Playing VALORANT — tactical 5v5 hero shooter" (Arabic: «يلعب VALORANT — شوتر تكتيكي خمسة ضد خمسة»)
    and $(gamename) -> "VALORANT".
  - The Twitch category can follow the game: Off, Ask me (the default) or Automatic. Nothing happens until the same game
    has been open for 2 minutes (a quick look at a game changes nothing), and closing the game never switches back.

How a game is recognised (nothing is sent anywhere; only the running programs' names and folders are looked at):
  1. games the streamer told the app about (Game Radar page) and games seen before (their descriptions can be edited),
  2. a built-in list of popular games (the program's file name, with an English and Arabic description),
  3. games installed with Steam or Epic (the program runs from the game's folder); for Steam games the genres come from
     Steam's store (in English and Arabic) as a description until the streamer writes one,
  4. any other program that stays full screen for a few minutes is asked about once ("Is this a game?").

The list lives in the channel's "game_radar" file: {"switch", "games": {exe: {...}}, "ignored": [exe, ...]}.
Scanning runs every few seconds on a background thread; on other systems than Windows it finds nothing (tests feed it).
"""
import json
import logging
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

log = logging.getLogger("gameradar")

WINDOWS = sys.platform == "win32"
SCAN_SECONDS = 8
SWITCH_AFTER = 120            # the same game open this long before the Twitch category changes (or the app asks)
ASK_AFTER = 180               # an unknown program full screen this long before "Is this a game?"
SWITCH_MODES = ("off", "ask", "auto")
SOURCES = ("builtin", "steam", "epic", "battlenet", "ea", "ubisoft", "gog", "riot", "rockstar", "amazon", "xbox", "you")

# (program file names, name, Twitch category, English description, Arabic description). Descriptions: about 5 words.
_BUILTIN = [
    (["valorant-win64-shipping.exe"], "VALORANT", "VALORANT", "tactical 5v5 hero shooter", "شوتر تكتيكي خمسة ضد خمسة"),
    (["minecraft.windows.exe"], "Minecraft", "Minecraft", "block world, build and survive", "عالم مكعبات للبناء والنجاة"),
    (["fortniteclient-win64-shipping.exe"], "Fortnite", "Fortnite", "battle royale, build and fight", "باتل رويال ببناء وقتال"),
    (["cs2.exe"], "Counter-Strike 2", "Counter-Strike", "classic 5v5 tactical shooter", "شوتر تكتيكي كلاسيكي خمسة ضد خمسة"),
    (["gta5.exe", "gta5_enhanced.exe"], "Grand Theft Auto V", "Grand Theft Auto V", "open-world crime in Los Santos", "عالم مفتوح وجريمة في لوس سانتوس"),
    (["robloxplayerbeta.exe"], "Roblox", "Roblox", "millions of player-made games", "ملايين الألعاب من صنع اللاعبين"),
    (["robloxstudiobeta.exe"], "Roblox Studio", "Software and Game Development", "building a Roblox game live", "يصمم لعبة روبلوكس على البث"),
    (["league of legends.exe"], "League of Legends", "League of Legends", "5v5 MOBA, destroy the Nexus", "موبا خمسة ضد خمسة"),
    (["r5apex.exe", "r5apex_dx12.exe"], "Apex Legends", "Apex Legends", "fast squad battle royale", "باتل رويال سريع بفرق"),
    (["rocketleague.exe"], "Rocket League", "Rocket League", "soccer with rocket-powered cars", "كورة بسيارات صواريخ"),
    (["overwatch.exe"], "Overwatch 2", "Overwatch 2", "team hero shooter", "شوتر أبطال جماعي"),
    (["tslgame.exe"], "PUBG: BATTLEGROUNDS", "PUBG: BATTLEGROUNDS", "the original battle royale", "الباتل رويال الأصلي"),
    (["fc25.exe"], "EA SPORTS FC 25", "EA Sports FC 25", "football, Ultimate Team and more", "كورة وألتميت تيم"),
    (["fc26.exe"], "EA SPORTS FC 26", "EA Sports FC 26", "football, Ultimate Team and more", "كورة وألتميت تيم"),
    (["efootball.exe"], "eFootball", "eFootball", "free-to-play football matches", "مباريات كورة مجانية"),
    (["rdr2.exe"], "Red Dead Redemption 2", "Red Dead Redemption 2", "outlaw life in the Wild West", "حياة خارج القانون في الغرب"),
    (["dota2.exe"], "Dota 2", "Dota 2", "deep 5v5 strategy MOBA", "موبا استراتيجية خمسة ضد خمسة"),
    (["rustclient.exe"], "Rust", "Rust", "survive, raid, trust nobody", "انجُ واغزُ ولا تثق بأحد"),
    (["escapefromtarkov.exe"], "Escape from Tarkov", "Escape from Tarkov", "hardcore loot-and-extract shooter", "شوتر صعب: اجمع واطلع حي"),
    (["eldenring.exe"], "ELDEN RING", "ELDEN RING", "brutal open-world fantasy adventure", "مغامرة صعبة في عالم مفتوح"),
    (["rainbowsix.exe", "rainbowsix_vulkan.exe", "rainbowsix_be.exe"], "Rainbow Six Siege", "Tom Clancy's Rainbow Six Siege", "tactical breach-and-defend shooter", "شوتر تكتيكي هجوم ودفاع"),
    (["wow.exe"], "World of Warcraft", "World of Warcraft", "the legendary fantasy MMO", "لعبة أونلاين أسطورية"),
    (["cod.exe"], "Call of Duty", "Call of Duty: Warzone", "fast military shooter", "شوتر عسكري سريع"),
    (["marvel-win64-shipping.exe"], "Marvel Rivals", "Marvel Rivals", "superhero team shooter", "شوتر أبطال مارفل"),
    (["project8.exe"], "Deadlock", "Deadlock", "hero shooter meets MOBA", "شوتر أبطال مع موبا"),
    (["helldivers2.exe"], "HELLDIVERS 2", "HELLDIVERS 2", "co-op bug war for democracy", "حرب تعاونية ضد الحشرات"),
    (["palworld-win64-shipping.exe"], "Palworld", "Palworld", "catch creatures, survive, build", "اصطد مخلوقات وابنِ وانجُ"),
    (["phasmophobia.exe"], "Phasmophobia", "Phasmophobia", "co-op ghost hunting horror", "صيد أشباح رعب جماعي"),
    (["lethal company.exe"], "Lethal Company", "Lethal Company", "co-op horror scrap collecting", "رعب جماعي وجمع خردة"),
    (["repo.exe"], "R.E.P.O.", "R.E.P.O.", "co-op monster loot chaos", "فوضى جماعية ووحوش"),
    (["peak.exe"], "PEAK", "PEAK", "co-op mountain climbing chaos", "تسلق جبل جماعي وفوضى"),
    (["among us.exe"], "Among Us", "Among Us", "find the impostor", "اكتشف الخاين"),
    (["fallguys_client_game.exe"], "Fall Guys", "Fall Guys", "wobbly party obstacle race", "سباق حواجز مضحك"),
    (["deadbydaylight-win64-shipping.exe"], "Dead by Daylight", "Dead by Daylight", "one killer, four survivors", "قاتل واحد ضد أربعة"),
    (["cyberpunk2077.exe"], "Cyberpunk 2077", "Cyberpunk 2077", "neon open-world future RPG", "آر بي جي مستقبلي بعالم مفتوح"),
    (["bg3.exe", "bg3_dx11.exe"], "Baldur's Gate 3", "Baldur's Gate 3", "epic choice-driven fantasy RPG", "آر بي جي خيالي بقرارات مصيرية"),
    (["witcher3.exe"], "The Witcher 3", "The Witcher 3: Wild Hunt", "monster hunter fantasy RPG", "صياد وحوش في عالم خيالي"),
    (["terraria.exe"], "Terraria", "Terraria", "dig, build, fight bosses", "احفر وابنِ وقاتل الزعماء"),
    (["stardew valley.exe", "stardewvalley.exe"], "Stardew Valley", "Stardew Valley", "cozy farming life sim", "حياة مزرعة هادية"),
    (["hearthstone.exe"], "Hearthstone", "Hearthstone", "Warcraft card battles", "معارك بطاقات وواركرافت"),
    (["diablo iv.exe"], "Diablo IV", "Diablo IV", "dark demon-slaying loot RPG", "آر بي جي مظلم ضد الشياطين"),
    (["monsterhunterwilds.exe"], "Monster Hunter Wilds", "Monster Hunter Wilds", "hunt giant monsters together", "اصطد وحوش عملاقة"),
    (["forzahorizon5.exe"], "Forza Horizon 5", "Forza Horizon 5", "open-world racing in Mexico", "سباقات بعالم مفتوح في المكسيك"),
    (["geometrydash.exe"], "Geometry Dash", "Geometry Dash", "rhythm jumping, pure rage", "قفز على الإيقاع ونرفزة"),
    (["brawlhalla.exe"], "Brawlhalla", "Brawlhalla", "free platform fighting brawler", "قتال منصات مجاني"),
    (["discovery.exe"], "THE FINALS", "THE FINALS", "destructible arena game show", "عرض قتالي بساحة تنهدم"),
    (["warframe.x64.exe"], "Warframe", "Warframe", "space ninja looter shooter", "نينجا فضاء وشوتر"),
    (["destiny2.exe"], "Destiny 2", "Destiny 2", "sci-fi looter shooter", "شوتر خيال علمي وغنائم"),
    (["sotgame.exe"], "Sea of Thieves", "Sea of Thieves", "pirate crew adventures", "مغامرات قراصنة مع الطاقم"),
    (["valheim.exe"], "Valheim", "Valheim", "viking survival and building", "نجاة وبناء فايكنج"),
    (["sonsoftheforest.exe"], "Sons Of The Forest", "Sons Of The Forest", "survival horror on an island", "نجاة ورعب في جزيرة"),
    (["7daystodie.exe"], "7 Days to Die", "7 Days to Die", "zombie survival and crafting", "نجاة من الزومبي وصناعة"),
    (["arkascended.exe"], "ARK: Survival Ascended", "ARK: Survival Ascended", "tame dinosaurs, survive", "روّض الديناصورات وانجُ"),
    (["hollow_knight.exe", "hollow knight.exe"], "Hollow Knight", "Hollow Knight", "beautiful hard bug kingdom", "مملكة حشرات صعبة وجميلة"),
    (["hollow knight silksong.exe"], "Hollow Knight: Silksong", "Hollow Knight: Silksong", "Hornet's hard silky adventure", "مغامرة هورنت الصعبة"),
    (["sekiro.exe"], "Sekiro", "Sekiro: Shadows Die Twice", "shinobi sword fights, no mercy", "قتال سيوف شينوبي بلا رحمة"),
    (["darksoulsiii.exe"], "Dark Souls III", "Dark Souls III", "die, learn, try again", "مت وتعلّم وارجع"),
    (["b1-win64-shipping.exe"], "Black Myth: Wukong", "Black Myth: Wukong", "Monkey King action legend", "أكشن أسطورة الملك القرد"),
    (["megabonk.exe"], "Megabonk", "Megabonk", "roguelike horde survival madness", "نجاة من الحشود روغلايك"),
    (["brotato.exe"], "Brotato", "Brotato", "potato with six guns", "بطاطس معها ست أسلحة"),
    (["schedule i.exe"], "Schedule I", "Schedule I", "build a shady business empire", "ابنِ إمبراطورية تجارية"),
    (["content warning.exe"], "Content Warning", "Content Warning", "film monsters, go viral", "صوّر الوحوش وصير ترند"),
    (["balatro.exe"], "Balatro", "Balatro", "poker roguelike, big combos", "بوكر روغلايك وكومبوهات"),
    (["hades.exe"], "Hades", "Hades", "escape the underworld roguelike", "اهرب من العالم السفلي"),
    (["hades2.exe"], "Hades II", "Hades II", "witch roguelike against Time", "ساحرة ضد إله الزمن"),
    (["genshinimpact.exe"], "Genshin Impact", "Genshin Impact", "anime open-world adventure", "مغامرة أنمي بعالم مفتوح"),
    (["starrail.exe"], "Honkai: Star Rail", "Honkai: Star Rail", "space train turn-based RPG", "آر بي جي أدوار بقطار فضائي"),
    (["zenlesszonezero.exe"], "Zenless Zone Zero", "Zenless Zone Zero", "stylish urban action combat", "أكشن حضري بستايل"),
    (["osu!.exe"], "osu!", "osu!", "click circles to the beat", "اضغط الدوائر على الإيقاع"),
    (["re4.exe"], "Resident Evil 4", "Resident Evil 4", "survival horror rescue mission", "رعب ونجاة ومهمة إنقاذ"),
    (["re8.exe"], "Resident Evil Village", "Resident Evil Village", "gothic survival horror", "رعب ونجاة قوطي"),
    (["haloinfinite.exe"], "Halo Infinite", "Halo Infinite", "Master Chief sci-fi shooter", "شوتر ماستر تشيف"),
    (["bf6.exe"], "Battlefield 6", "Battlefield 6", "huge all-out war battles", "حروب ضخمة شاملة"),
    (["bf2042.exe"], "Battlefield 2042", "Battlefield 2042", "huge near-future warfare", "حرب ضخمة في المستقبل"),
    (["pioneergame.exe"], "ARC Raiders", "ARC Raiders", "raid machines, extract alive", "اغزُ الآلات واطلع حي"),
    (["hogwartslegacy.exe"], "Hogwarts Legacy", "Hogwarts Legacy", "wizard life at Hogwarts", "حياة ساحر في هوجوورتس"),
    (["eurotrucks2.exe"], "Euro Truck Simulator 2", "Euro Truck Simulator 2", "chill truck driving across Europe", "سواقة شاحنات في أوروبا"),
    (["acs.exe"], "Assetto Corsa", "Assetto Corsa", "realistic racing simulator", "محاكي سباقات واقعي"),
    (["factorio.exe"], "Factorio", "Factorio", "build the factory, grow it", "ابنِ المصنع وكبّره"),
    (["factorygame-win64-shipping.exe", "factorygamesteam-win64-shipping.exe"], "Satisfactory", "Satisfactory", "3D factory building on alien worlds", "بناء مصانع بكوكب غريب"),
    (["subnautica.exe"], "Subnautica", "Subnautica", "underwater alien ocean survival", "نجاة تحت محيط غريب"),
    (["gmod.exe"], "Garry's Mod", "Garry's Mod", "physics sandbox, anything goes", "ساندبوكس فيزياء بلا حدود"),
    (["dyinglightgame_x64_rwdi.exe"], "Dying Light 2", "Dying Light 2 Stay Human", "parkour through zombie city", "باركور في مدينة زومبي"),
    (["nba2k26.exe"], "NBA 2K26", "NBA 2K26", "basketball, MyCareer and more", "كرة سلة وماي كارير"),
]
BUILTIN: dict = {}
for _exes, _name, _cat, _en, _ar in _BUILTIN:
    for _x in _exes:
        BUILTIN[_x] = {"name": _name, "cat": _cat, "en": _en, "ar": _ar}

# Minecraft Java runs as javaw.exe (like other Java programs): only a window titled "Minecraft…" counts.
BY_TITLE = {"javaw.exe": [("minecraft", "Minecraft")], "java.exe": [("minecraft", "Minecraft")]}

# Never a game (never asked about either): Windows, browsers, streaming and chat apps, players, launchers.
NEVER = {
    "explorer.exe", "dwm.exe", "applicationframehost.exe", "searchhost.exe", "shellexperiencehost.exe", "startmenuexperiencehost.exe",
    "textinputhost.exe", "lockapp.exe", "systemsettings.exe", "taskmgr.exe", "cmd.exe", "powershell.exe", "pwsh.exe",
    "windowsterminal.exe", "conhost.exe", "chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "opera_gx.exe", "brave.exe",
    "vivaldi.exe", "arc.exe", "obs64.exe", "obs32.exe", "streamlabs obs.exe", "streamlabs desktop.exe", "twitch studio.exe",
    "discord.exe", "discordptb.exe", "discordcanary.exe", "telegram.exe", "whatsapp.exe", "slack.exe", "teams.exe", "ms-teams.exe",
    "zoom.exe", "spotify.exe", "vlc.exe", "mpc-hc64.exe", "mpc-be64.exe", "potplayermini64.exe", "wmplayer.exe", "video.ui.exe",
    "steam.exe", "steamwebhelper.exe", "epicgameslauncher.exe", "eadesktop.exe", "battle.net.exe", "riotclientservices.exe",
    "riotclientux.exe", "leagueclient.exe", "leagueclientux.exe", "ubisoftconnect.exe", "upc.exe", "galaxyclient.exe",
    "code.exe", "devenv.exe", "notepad.exe", "notepad++.exe", "winword.exe", "excel.exe", "powerpnt.exe", "outlook.exe",
    "photoshop.exe", "premiere pro.exe", "afterfx.exe", "resolve.exe", "blender.exe", "nvidia app.exe", "nvidia share.exe",
    "nvcontainer.exe", "msiafterburner.exe", "rtss.exe", "medal.exe", "overwolf.exe", "fqpn's chat bot.exe", "twitchchatbot.exe",
    "python.exe", "pythonw.exe", "javaw.exe", "java.exe", "steam_monitor.exe", "crashreportclient.exe", "unitycrashhandler64.exe",
    "easyanticheat.exe", "beservice.exe", "vgtray.exe", "vgc.exe",
    # 1.20.0: programs that run beside games but aren't games (some are sold on Steam)
    "wallpaper32.exe", "wallpaper64.exe", "webwallpaper32.exe", "wallpaperservice32.exe", "ui32.exe", "lively.exe",
    "soundpad.exe", "losslessscaling.exe", "vrserver.exe", "vrmonitor.exe", "vrcompositor.exe", "vrdashboard.exe",
    "voicemeeter.exe", "voicemeeterpro.exe", "voicemeeter8.exe", "voicemeeter8x64.exe", "fpsmonitor.exe", "rainmeter.exe",
    "streamerbot.exe", "streamer.bot.exe", "mixitup.exe", "touchportal.exe", "elgato stream deck.exe", "streamdeck.exe",
    "voicemod.exe", "voicemoddesktop.exe", "nvidia broadcast.exe", "krisp.exe", "displayfusion.exe", "translucenttb.exe",
    # 1.20.0: the launchers' own helpers
    "eabackgroundservice.exe", "ealocalhostsvc.exe", "eaconnect_microsoft.exe", "eacefsubprocess.exe", "uplaywebcore.exe",
    "ubisoftconnect.exe", "uplayservice.exe", "upc_crashreporter.exe", "battle.net helper.exe", "blizzard error.exe",
    "blizzardbrowser.exe", "riotclientcrashhandler.exe", "riotclientuxrender.exe", "rockstarservice.exe", "socialclubhelper.exe",
    "playgtav.exe", "galaxycommunication.exe", "gog galaxy notifications renderer.exe", "amazon games ui.exe",
    "amazongamesui.exe", "xboxpcapp.exe", "xboxapp.exe", "gamebar.exe", "gamingservices.exe", "xboxpcappft.exe",
}
_SYS_DIRS = ("\\windows\\", "/windows/")
# 1.20.0: the small helpers that run beside a game, from its own folder (codcrashhandler.exe, UnityCrashHandler64.exe,
# EasyAntiCheat_EOS.exe, ...): never the game itself, or the radar jumps between the game and its helper
_HELPER = re.compile(r"crash|handler|report|helper|anticheat|anti-cheat|battleye|beservice|updater|uninstall|setup|install"
                     r"|cefprocess|webhelper|subprocess|bootstrap|redist|vc_redist|dxsetup|service|launcherpatcher", re.I)


def is_helper(exe: str) -> bool:
    return bool(_HELPER.search(str(exe or "")))


def _clean(t, n=60) -> str:
    return " ".join(str(t or "").split())[:n]


def builtin_of(exe: str, title: str = ""):
    exe = str(exe or "").lower()
    hit = BUILTIN.get(exe)
    if hit:
        return dict(hit, src="builtin")
    for word, name in BY_TITLE.get(exe, []):
        if word in str(title or "").lower():
            b = next((v for v in BUILTIN.values() if v["name"] == name), None)
            return dict(b or {"name": name, "cat": name, "en": "", "ar": ""}, src="builtin")
    return None


def info_text(g, lang: str) -> str:
    """$(gameinfo)."""
    ar = lang == "ar"
    if not g:
        return "ما يلعب شي الحين" if ar else "Not playing anything right now"
    name = g.get("name") or "?"
    desc = (g.get("ar") if ar else g.get("en")) or g.get("en") or g.get("ar") or ""
    head = f"يلعب {name}" if ar else f"Playing {name}"
    return f"{head} — {desc}" if desc else head


def name_text(g, lang: str) -> str:
    """$(gamename)."""
    if g:
        return g.get("name") or "?"
    return "(ما فيه لعبة مفتوحة)" if lang == "ar" else "(no game open)"


def clean(data) -> dict:
    """The "game_radar" file, checked (Backup & restore): bad entries are dropped, never the whole list."""
    if not isinstance(data, dict):
        raise ValueError("The Game Radar list is invalid.")
    games = {}
    for exe, g in list((data.get("games") or {}).items())[:500] if isinstance(data.get("games"), dict) else []:
        exe = _clean(exe, 120).lower()
        if not exe or not isinstance(g, dict):
            continue
        e = {k: _clean(g.get(k, ""), 80) for k in ("name", "cat", "en", "ar")}
        e["name"] = e["name"] or exe.rsplit(".", 1)[0]
        e["src"] = g.get("src") if g.get("src") in SOURCES else "you"
        if g.get("demo_choice") in ("yes", "keep"):
            e["demo_choice"] = g["demo_choice"]
        if g.get("dsrc") in ("en", "ar"):
            e["dsrc"] = g["dsrc"]
        if g.get("checked") is True:
            e["checked"] = True
        if str(g.get("appid") or "").isdigit():
            e["appid"] = str(g["appid"])
        if g.get("off") is True:
            e["off"] = True
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(g.get("last") or "")):
            e["last"] = g["last"]
        games[exe] = e
    ignored = [_clean(x, 120).lower() for x in (data.get("ignored") or []) if isinstance(x, str) and x.strip()][:500] if isinstance(data.get("ignored"), list) else []
    return {"switch": data.get("switch") if data.get("switch") in SWITCH_MODES else "ask", "games": games, "ignored": ignored}


# ---------------------------------------------------------------- Steam and Epic (installed games and their folders)

def _vdf_values(text: str, key: str) -> list:
    return [v.replace("\\\\", "\\") for v in re.findall(r'"%s"\s+"([^"]*)"' % re.escape(key), text, re.I)]


def steam_root():
    if not WINDOWS:
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            p = Path(winreg.QueryValueEx(k, "SteamPath")[0])
            if p.is_dir():
                return p
    except OSError:
        pass
    for p in (Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam", Path(r"C:\Steam")):
        if p.is_dir():
            return p
    return None


def steam_games(root=None) -> list:
    """[{"appid", "name", "dir"}] for every installed Steam game (all libraries)."""
    root = root or steam_root()
    if not root:
        return []
    libs = [Path(root)]
    try:
        libs += [Path(p) for p in _vdf_values((Path(root) / "steamapps" / "libraryfolders.vdf").read_text("utf-8", "ignore"), "path")]
    except OSError:
        pass
    out, seen = [], set()
    for lib in libs:
        apps = lib / "steamapps"
        try:
            files = list(apps.glob("appmanifest_*.acf"))
        except OSError:
            continue
        for f in files:
            try:
                t = f.read_text("utf-8", "ignore")
                appid, name, folder = (_vdf_values(t, "appid") or [""])[0], (_vdf_values(t, "name") or [""])[0], (_vdf_values(t, "installdir") or [""])[0]
            except (OSError, IndexError):
                continue
            if not appid or not folder or appid in seen or "steamworks" in name.lower() or "redistributable" in name.lower():
                continue
            seen.add(appid)
            out.append({"appid": appid, "name": _plain_name(name), "dir": str((apps / "common" / folder)).lower()})
    return out


def epic_games(folder=None) -> list:
    """[{"name", "dir"}] for every installed Epic game."""
    folder = Path(folder) if folder else Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    out = []
    try:
        files = list(folder.glob("*.item"))
    except OSError:
        return out
    for f in files:
        try:
            d = json.loads(f.read_text("utf-8", "ignore"))
        except (OSError, ValueError):
            continue
        if d.get("bIsApplication") is False or not d.get("InstallLocation") or not d.get("DisplayName"):
            continue
        cats = [str(c).lower() for c in d.get("AppCategories") or []]
        if cats and "games" not in cats:
            continue
        out.append({"name": _plain_name(d["DisplayName"]), "dir": str(d["InstallLocation"]).lower()})
    return out


# 1.20.0: games from the other launchers. Windows keeps an "installed programs" record for each (the list in Settings >
# Apps): a record counts when it comes from one of these launchers, and its folder is where the game runs from.
LAUNCHERS = [   # (source, what the record's publisher / uninstaller / folder contains)
    ("battlenet", ("blizzard entertainment", "battle.net")),
    ("ea", ("electronic arts", "eadesktop", "ea desktop", "\\ea games\\")),
    ("ubisoft", ("ubisoft", "uplay", "upc.exe")),
    ("gog", ("gog.com", "gog sp. z o.o", "\\gog galaxy\\games\\", "\\gog games\\")),
    ("riot", ("riot games",)),
    ("rockstar", ("rockstar games",)),
    ("amazon", ("amazon games", "amazon.com services")),
]
# the launchers themselves and the extras they install are not games
_NOT_GAMES = ("ea app", "origin", "ubisoft connect", "uplay", "battle.net", "gog galaxy", "riot client", "riot vanguard",
              "rockstar games launcher", "social club", "amazon games", "redistributable", "directx", "easy anti-cheat",
              "easyanticheat", "battleye", "punkbuster", "visual c++", "uninstall", "launcher", "crash report", "vc_redist")


def _plain_name(n: str) -> str:
    return " ".join(re.sub(r"[\u2122\u00ae\u00a9]", "", str(n or "")).split())[:60]


def classify(records) -> list:
    """[{"name", "dir", "src"}] from Windows' installed-program records: only games from the launchers above."""
    out, seen = [], set()
    for r in records or []:
        name = _plain_name(r.get("DisplayName"))
        folder = str(r.get("InstallLocation") or "").strip().strip('"').rstrip("\\/")
        if not name or not folder:
            continue
        parts = [x for x in re.split(r"[\\/]", folder.lower()) if x]
        if len(parts) < 2 or parts[-1] in ("program files", "program files (x86)", "games", "steamapps", "common"):
            continue                    # (a folder this wide would catch other programs too)
        low = name.lower()
        if any(w in low for w in _NOT_GAMES):
            continue
        hay = " ".join(str(r.get(k) or "") for k in ("Publisher", "UninstallString", "InstallLocation", "Key")).lower()
        src = next((src for src, marks in LAUNCHERS if any(m in hay for m in marks)), None)
        if not src or folder.lower() in seen:
            continue
        seen.add(folder.lower())
        out.append({"name": name, "dir": folder.lower(), "src": src})
    return out


def _uninstall_records() -> list:
    if not WINDOWS:
        return []
    import winreg
    out = []
    spots = [(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", winreg.KEY_WOW64_64KEY),
             (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", winreg.KEY_WOW64_32KEY),
             (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", 0)]
    for root, path, view in spots:
        try:
            with winreg.OpenKey(root, path, 0, winreg.KEY_READ | view) as k:
                n = winreg.QueryInfoKey(k)[0]
                for i in range(min(n, 3000)):
                    try:
                        sub = winreg.EnumKey(k, i)
                        with winreg.OpenKey(k, sub) as e:
                            r = {"Key": sub}
                            for f in ("DisplayName", "InstallLocation", "Publisher", "UninstallString"):
                                try:
                                    r[f] = str(winreg.QueryValueEx(e, f)[0])
                                except OSError:
                                    pass
                            out.append(r)
                    except OSError:
                        continue
        except OSError:
            continue
    return out


def launcher_games() -> list:
    try:
        return classify(_uninstall_records())
    except Exception:
        log.exception("Launcher games not read")
        return []


# Xbox / Game Pass and Amazon games run from a folder named after the game
_BY_FOLDER = [("xbox", r"\\xboxgames\\([^\\]+)\\"), ("xbox", r"\\modifiablewindowsapps\\([^\\]+)\\"),
              ("amazon", r"\\amazon games\\library\\([^\\]+)\\")]


def by_folder(path: str):
    p = str(path or "").lower().replace("/", "\\")
    for src, pat in _BY_FOLDER:
        m = re.search(pat, p)
        if m and m.group(1) not in ("gamesave", "content"):
            return src, m.group(1)
    return None


def folder_name(path: str, src: str) -> str:
    """The game's name as its folder writes it (original capitals): ...\\XboxGames\\Forza Horizon 5\\Content\\..."""
    p = str(path or "").replace("/", "\\")
    for s, pat in _BY_FOLDER:
        if s == src:
            m = re.search(pat, p, re.I)
            if m:
                return _plain_name(m.group(1).replace("_", " "))
    return ""


DEMO = re.compile(r"(\bdemo\b|\bplaytest\b|\(demo\)|ديمو)", re.I)
DEMO_CAT = "Games + Demos"


def is_demo(name: str) -> bool:
    return bool(DEMO.search(str(name or "")))


_AR = re.compile(r"[\u0600-\u06FF]")


def lang_of(text: str) -> str:
    return "ar" if _AR.search(str(text or "")) else "en"


def translate(text: str, to: str) -> str:
    """1.20.0: one description, the other language made from it (MyMemory's free translation service, once when it is
    saved; never while chatting). "" when it can't (no internet, the daily free amount used up...)."""
    text = _clean(text, 80)
    src = lang_of(text)
    if not text or src == to:
        return text
    url = "https://api.mymemory.translated.net/get?" + urllib.parse.urlencode({"q": text, "langpair": f"{src}|{to}"})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "FQPN-Chat-Bot"}), timeout=8) as r:
            data = json.loads(r.read().decode("utf-8", "ignore"))
        out = _clean(((data.get("responseData") or {}).get("translatedText")) or "", 80)
        if int(data.get("responseStatus") or 0) != 200 or not out or "MYMEMORY" in out.upper() or lang_of(out) != to:
            return ""
        return out
    except Exception as e:
        log.info("Description not translated: %r", e)
        return ""


# Steam's genres for programs that aren't games (Animation & Modeling, Design & Illustration, Utilities, Video / Audio
# Production, Photo Editing, Web Publishing, Education, Software Training, Game Development, Accounting): Wallpaper Engine,
# Lossless Scaling, Soundpad... are on Steam but are not games.
SOFTWARE_GENRES = {str(n) for n in range(50, 61)}
NOT_GAME_TYPES = {"application", "music", "video", "series", "episode", "hardware", "advertising"}


def is_software(info: dict) -> bool:
    if str(info.get("type") or "").lower() in NOT_GAME_TYPES:
        return True
    return any(str(g.get("id")) in SOFTWARE_GENRES for g in info.get("genres") or [] if isinstance(g, dict))


def steam_genres(appid: str) -> dict:
    """{"en": "action, adventure", "ar": "أكشن، مغامرة", "app": False} from Steam's store, or {} (no internet...).
    "app": True when Steam says it's a program, not a game (its type, or a software genre)."""
    out = {}
    for lang, code, sep in (("en", "english", ", "), ("ar", "arabic", "، ")):
        q = {"appids": appid, "l": code} if lang == "en" else {"appids": appid, "l": code, "filters": "genres"}
        url = "https://store.steampowered.com/api/appdetails?" + urllib.parse.urlencode(q)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "FQPN-Chat-Bot"}), timeout=8) as r:
                data = json.loads(r.read().decode("utf-8", "ignore"))
            info = (data.get(str(appid)) or {}).get("data") or {}
            if lang == "en" and info:
                out["app"] = is_software(info)
            genres = [g.get("description", "") for g in info.get("genres") or []]
            genres = [g for g in genres if g and g.lower() not in ("free to play", "early access", "indie")] or genres
            if genres:
                out[lang] = sep.join(genres[:3]).lower() if lang == "en" else sep.join(genres[:3])
        except Exception as e:          # (no internet, Steam busy: no description, never an error)
            log.info("Steam genres for %s not read: %r", appid, e)
    return out


# ---------------------------------------------------------------- the running programs (Windows)

def _processes() -> list:
    """[{"pid", "exe" (file name, lowercase), "path" (lowercase), "start"}] of the running programs (not Windows' own)."""
    try:
        import psutil
    except ImportError:
        return []
    out, alive = [], set()
    for p in psutil.process_iter(["pid", "name", "create_time"]):
        name = str(p.info.get("name") or "").lower()
        if not name.endswith(".exe") or name in NEVER:
            continue
        key = (p.info["pid"], p.info.get("create_time"))
        alive.add(key)
        path = _PATHS.get(key)
        if path is None:                   # (read once per program: the scan stays light while a game runs)
            try:
                path = p.exe() or ""
            except Exception:
                path = ""
            _PATHS[key] = path
        if any(d in path.lower() for d in _SYS_DIRS):
            continue
        out.append({"pid": p.info["pid"], "exe": name, "path": path.lower(), "raw": path, "start": p.info.get("create_time") or 0})
    for k in [k for k in _PATHS if k not in alive]:
        _PATHS.pop(k, None)
    return out


_PATHS: dict = {}


def _foreground():
    """{"pid", "title", "full"}: the window in front, and whether it covers its whole screen."""
    if not WINDOWS:
        return None
    try:
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        h = u.GetForegroundWindow()
        if not h:
            return None
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(pid))
        n = u.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(h, buf, n + 1)
        r = wintypes.RECT()
        u.GetWindowRect(h, ctypes.byref(r))

        class MI(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
        mi = MI()
        mi.cbSize = ctypes.sizeof(MI)
        mon = u.MonitorFromWindow(h, 2)
        full = False
        if mon and u.GetMonitorInfoW(mon, ctypes.byref(mi)):
            m = mi.rcMonitor
            full = r.left <= m.left and r.top <= m.top and r.right >= m.right and r.bottom >= m.bottom
        cls = ctypes.create_unicode_buffer(64)
        u.GetClassNameW(h, cls, 64)
        if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd"):     # the desktop itself
            full = False
        return {"pid": int(pid.value), "title": buf.value, "full": full}
    except Exception:
        log.exception("Foreground window not read")
        return None


def _windows() -> list:
    """[{"pid", "title"}] of the visible windows with a title (for "Pick from open programs")."""
    if not WINDOWS:
        return []
    try:
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        out = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def each(h, _):
            if u.IsWindowVisible(h):
                n = u.GetWindowTextLengthW(h)
                if n:
                    buf = ctypes.create_unicode_buffer(n + 1)
                    u.GetWindowTextW(h, buf, n + 1)
                    pid = wintypes.DWORD()
                    u.GetWindowThreadProcessId(h, ctypes.byref(pid))
                    out.append({"pid": int(pid.value), "title": buf.value})
            return True
        u.EnumWindows(each, 0)
        return out
    except Exception:
        log.exception("Windows not listed")
        return []


def _under(path: str, folder: str) -> bool:
    base = str(folder or "").lower().replace("/", "\\").rstrip("\\")
    return bool(base) and str(path or "").lower().replace("/", "\\").startswith(base + "\\")


# ---------------------------------------------------------------- the radar

class Radar:
    def __init__(self):
        self.lock = threading.Lock()
        self.store = None                  # the channel's settings (set by the dashboard; changes with the channel)
        self.procs = _processes            # (tests replace these)
        self.front = _foreground
        self.windows = _windows
        self.steam = steam_games
        self.epic = epic_games
        self.launchers = launcher_games
        self.genres = steam_genres
        self.translate = translate
        self.clock = time.time
        self.now = None                    # the game open now: {exe, name, cat, en, ar, src, since}
        self.ask = None                    # "Is this a game?": {exe, title, since}
        self.prompt = None                 # "Switch the Twitch category?" (Ask me): {exe, name, cat, from}
        self.result = None                 # the last category change: {ok, name, cat, at, why}
        self.twitch_cat = ""               # the Twitch category, as last read
        self._handled = set()              # games (exe + start time) whose category question is settled
        self._installed = (0, [], [], [])  # (when read, Steam games, Epic games, other launchers' games)
        self._full_since = {}              # exe -> when it went full screen (unknown programs)
        self._genre_busy = set()
        self._genre_try = {}
        self._later = set()                # "Ask me later": not asked again until the app restarts
        self._thread = None
        self._stop = threading.Event()

    # ---- settings
    def data(self) -> dict:
        d = self.store.get("game_radar") if self.store else None
        d = dict(d) if isinstance(d, dict) else {}
        d["switch"] = d.get("switch") if d.get("switch") in SWITCH_MODES else "ask"
        d["games"] = dict(d.get("games") or {})
        d["ignored"] = list(d.get("ignored") or [])
        return d

    def _save(self, d: dict) -> None:
        if self.store:
            self.store.save("game_radar", d)

    # ---- scanning
    def start(self) -> None:
        if self._thread and self._thread.is_alive() and not self._stop.is_set():
            return
        if self._thread and self._thread.is_alive():
            self._thread.join(1)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="game-radar", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self.lock:                  # (switched off: nothing is open as far as the app knows)
            self.now = self.ask = self.prompt = None

    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.scan()
            except Exception:
                log.exception("Game Radar scan failed")
            self._stop.wait(SCAN_SECONDS)

    def _installed_games(self):
        when, steam, epic, other = self._installed
        if self.clock() - when > 600:
            got = []
            for fn in (self.steam, self.epic, self.launchers):
                try:
                    got.append(fn() or [])
                except Exception:
                    log.exception("Installed games not read")
                    got.append([])
            steam, epic, other = got
            self._installed = (self.clock(), steam, epic, other)
        return steam, epic, other

    def identify(self, p: dict, d: dict, title: str = ""):
        """What this running program is: a game dict, or None."""
        exe, path = p.get("exe", ""), p.get("path", "")
        if exe in d["ignored"]:
            return None
        mine = d["games"].get(exe)
        if is_helper(exe) and not (mine and mine.get("src") == "you") and exe not in BUILTIN:
            return None
        if mine and not mine.get("off"):
            return dict(mine)
        b = builtin_of(exe, title)
        if b:
            return b
        if not path:
            return None
        steam, epic, other = self._installed_games()
        for g in steam:
            if _under(path, g["dir"]):
                return {"name": g["name"], "cat": g["name"], "en": "", "ar": "", "src": "steam", "appid": g["appid"]}
        for g in epic:
            if _under(path, g["dir"]):
                return {"name": g["name"], "cat": g["name"], "en": "", "ar": "", "src": "epic"}
        best = None
        for g in other:                    # (the deepest folder wins: a game inside another record's folder)
            if _under(path, g["dir"]) and (not best or len(g["dir"]) > len(best["dir"])):
                best = g
        if best:
            return {"name": best["name"], "cat": best["name"], "en": "", "ar": "", "src": best["src"]}
        hit = by_folder(path)
        if hit:
            name = folder_name(p.get("raw") or path, hit[0]) or hit[1].title()
            return {"name": name, "cat": name, "en": "", "ar": "", "src": hit[0]}
        return None

    def scan(self) -> None:
        d = self.data()
        procs = self.procs() or []
        front = self.front() or {}
        found = []
        for p in procs:
            g = self.identify(p, d, front.get("title", "") if front.get("pid") == p.get("pid") else "")
            if g:
                g["demo"] = is_demo(g.get("name"))
                found.append((p.get("pid") == front.get("pid"), p.get("start") or 0, p, g))
        # found only through a store's folder (Steam, Epic, the launchers, Xbox): it must have a window you can see. A program
        # that only sits in the tray (Wallpaper Engine) is not a game being played. Yours and the built-in ones need no window.
        if any(x[3].get("src") not in ("you", "builtin") and not x[0] for x in found):
            try:
                shown = {w.get("pid") for w in (self.windows() or [])}
            except Exception:
                shown = set()
            found = [x for x in found if x[3].get("src") in ("you", "builtin") or x[0] or x[2].get("pid") in shown]
        now = self.clock()
        with self.lock:
            if found:
                cur = self.now.get("key") if self.now else None
                rank = {"you": 2, "builtin": 2}
                # the one in front, then the one already shown (alt-tabbing to the app doesn't move it), then yours /
                # built-in (cod.exe over a Steam folder match), then the newest
                found.sort(key=lambda x: (x[0], f"{x[2]['exe']}|{int(x[1])}" == cur, rank.get(x[3].get("src"), 1), x[1]), reverse=True)
                _, start, p, g = found[0]
                key = f"{p['exe']}|{int(start)}"
                if not self.now or self.now.get("key") != key:
                    since = start if start and start <= now else now
                    self.now = dict(g, exe=p["exe"], key=key, since=since, seen=now)
                    log.info("Game Radar: %s (%s)", g.get("name"), p["exe"])
                else:
                    self.now.update({k: g.get(k, self.now.get(k)) for k in ("name", "cat", "en", "ar", "src", "demo", "demo_choice", "dsrc")}, seen=now)
                fresh = self.data()                       # (read again inside the lock: an edit made meanwhile is kept)
                if self._remember(fresh, p["exe"], g):
                    self._save(fresh)
            else:
                if self.now:
                    log.info("Game Radar: %s closed", self.now.get("name"))
                self.now = None
                if self.prompt:
                    self.prompt = None
            # an unknown program full screen for a few minutes: ask once
            if front.get("full") and not found:
                exe = next((p["exe"] for p in procs if p.get("pid") == front.get("pid")), "")
                if exe and exe not in d["ignored"] and exe not in d["games"] and exe not in self._later:
                    t0 = self._full_since.setdefault(exe, now)
                    if now - t0 >= ASK_AFTER and (not self.ask or self.ask.get("exe") != exe):
                        self.ask = {"exe": exe, "title": _clean(front.get("title"), 80), "mins": int((now - t0) // 60)}
                else:
                    self._full_since.clear()
            else:
                self._full_since.clear()
        g = self.now
        if (g and g.get("src") == "steam" and g.get("appid") and not g.get("checked") and g["appid"] not in self._genre_busy
                and now - self._genre_try.get(g["appid"], -1e9) > 600):      # (no internet: tried again 10 minutes later)
            self._genre_try[g["appid"]] = now
            self._genre_busy.add(g["appid"])
            threading.Thread(target=self._fetch_genres, args=(g["exe"], g["appid"]), daemon=True).start()
        elif not self._genre_busy:            # a Steam program saved earlier and never checked (one at a time)
            for exe, e in self.data()["games"].items():
                aid = str(e.get("appid") or "")
                if e.get("src") == "steam" and aid and not e.get("checked") and not e.get("off") and now - self._genre_try.get(aid, -1e9) > 600:
                    self._genre_try[aid] = now
                    self._genre_busy.add(aid)
                    threading.Thread(target=self._fetch_genres, args=(exe, aid), daemon=True).start()
                    break

    def _remember(self, d: dict, exe: str, g: dict) -> bool:
        """Every game seen is kept in the list (so its description and category can be edited). True = changed."""
        old = d["games"].get(exe)
        if old:
            if time.strftime("%Y-%m-%d") != old.get("last"):
                old["last"] = time.strftime("%Y-%m-%d")
                return True
            return False
        d["games"][exe] = {k: g.get(k, "") for k in ("name", "cat", "en", "ar", "src")} | ({"appid": g["appid"]} if g.get("appid") else {})
        d["games"][exe]["last"] = time.strftime("%Y-%m-%d")
        return True

    def _fetch_genres(self, exe: str, appid: str) -> None:
        """Once per Steam program: is it a game at all (Wallpaper Engine is not), and its genres as a description."""
        try:
            self._check_steam(exe, appid)
        finally:
            self._genre_busy.discard(appid)

    def _check_steam(self, exe: str, appid: str) -> None:
        got = {}
        try:
            got = self.genres(appid) or {}
        except Exception:
            log.exception("Steam genres failed")
        if not got:                                  # (no internet: tried again on a later scan)
            return
        if got.get("app"):
            g = (self.data()["games"].get(exe) or {})
            if g.get("src") != "you":                # (the streamer said it's a game: theirs stays)
                log.info("Game Radar: %s is a program on Steam, not a game", exe)
                self.not_a_game(exe)
                return
        with self.lock:
            d = self.data()
            g = d["games"].get(exe)
            if not g:
                return
            g["checked"] = True
            if not (g.get("en") or g.get("ar")):      # (the streamer wrote one meanwhile: theirs stays)
                g["en"], g["ar"] = _clean(got.get("en"), 80), _clean(got.get("ar"), 80)
            self._save(d)
            if self.now and self.now.get("exe") == exe:
                self.now.update(en=g["en"], ar=g["ar"])

    # ---- what the rest of the app reads
    def current(self):
        with self.lock:
            return dict(self.now) if self.now else None

    def view(self, full: bool = True) -> dict:
        d = self.data()
        now = self.current()
        out = {"now": now and {k: now.get(k) for k in ("exe", "name", "cat", "en", "ar", "src", "since", "dsrc")},
               "switch": d["switch"], "ask": self.ask, "prompt": self.prompt, "result": self.result,
               "twitch_cat": self.twitch_cat, "windows": WINDOWS, "server_time": self.clock(), "demo": self.demo_question()}
        if full:
            out["games"] = sorted(({"exe": k, **{f: v.get(f, "") for f in ("name", "cat", "en", "ar", "src", "last", "dsrc")}} for k, v in d["games"].items()
                                   if not v.get("off") and not (is_helper(k) and v.get("src") != "you" and k not in BUILTIN)),
                                  key=lambda g: (g.get("last") or ""), reverse=True)
            out["ignored"] = d["ignored"]
        return out

    def demo_question(self):
        """A demo is open and its category isn't settled: suggest Twitch's "Games + Demos". {exe, name, cat} or None."""
        g = self.now
        if not g or not g.get("demo") or g.get("demo_choice") or str(g.get("cat", "")).casefold() == DEMO_CAT.casefold():
            return None
        return {"exe": g["exe"], "name": g.get("name", ""), "cat": g.get("cat", "")}

    def answer_demo(self, yes: bool) -> None:
        q = self.demo_question()
        if not q:
            return
        with self.lock:
            d = self.data()
            e = d["games"].get(q["exe"]) or {k: self.now.get(k, "") for k in ("name", "cat", "en", "ar", "src")}
            e["demo_choice"] = "yes" if yes else "keep"
            if yes:
                e["cat"] = DEMO_CAT
            d["games"][q["exe"]] = e
            self._save(d)
            if self.now and self.now.get("exe") == q["exe"]:
                self.now.update(demo_choice=e["demo_choice"], cat=e["cat"])

    # ---- the streamer's answers and edits
    def set_switch(self, mode: str) -> None:
        if mode in SWITCH_MODES:
            with self.lock:
                d = self.data()
                d["switch"] = mode
                self._save(d)
                if mode != "ask":
                    self.prompt = None

    def edit(self, exe: str, fields: dict) -> bool:
        exe = str(exe or "").strip().lower()
        if not exe:
            return False
        with self.lock:
            d = self.data()
            g = dict(d["games"].get(exe) or builtin_of(exe) or {"name": exe.rsplit(".", 1)[0], "cat": "", "en": "", "ar": "", "src": "you"})
            g.pop("off", None)
            for k, n in (("name", 60), ("cat", 80), ("en", 80), ("ar", 80)):
                if k in fields:
                    g[k] = _clean(fields[k], n)
            if fields.get("dsrc") in ("en", "ar"):
                g["dsrc"] = fields["dsrc"]
            if "cat" in fields and is_demo(g.get("name")):
                g["demo_choice"] = "yes" if g.get("cat", "").casefold() == DEMO_CAT.casefold() else "keep"
            if not g.get("name"):
                g["name"] = exe.rsplit(".", 1)[0]
            if not g.get("cat"):
                g["cat"] = g["name"]
            g.setdefault("last", time.strftime("%Y-%m-%d"))
            g["src"] = g.get("src") or "you"
            d["games"][exe] = g
            if exe in d["ignored"]:
                d["ignored"].remove(exe)
            self._save(d)
            if self.now and self.now.get("exe") == exe:
                self.now.update({k: g.get(k, "") for k in ("name", "cat", "en", "ar", "dsrc")}, demo=is_demo(g.get("name")), demo_choice=g.get("demo_choice"))
            if self.ask and self.ask.get("exe") == exe:
                self.ask = None
        return True

    def describe(self, exe: str, text: str) -> bool:
        """One description in either language: it is kept as written and the other language is translated from it
        (blocking: the dashboard runs it on a worker thread)."""
        text = _clean(text, 80)
        src = lang_of(text)
        other = "en" if src == "ar" else "ar"
        made = self.translate(text, other) if text else ""
        return self.edit(exe, {src: text, other: made, "dsrc": src})

    def not_a_game(self, exe: str) -> None:
        exe = str(exe or "").strip().lower()
        if not exe:
            return
        with self.lock:
            d = self.data()
            if exe not in d["ignored"]:
                d["ignored"].append(exe)
            g = d["games"].get(exe)
            if g:
                g["off"] = True             # (kept, not deleted: "It's a game" brings it back with its descriptions)
            self._save(d)
            if self.now and self.now.get("exe") == exe:
                self.now = None
                self.prompt = None
            if self.ask and self.ask.get("exe") == exe:
                self.ask = None

    def later(self) -> None:
        with self.lock:
            if self.ask:
                self._later.add(self.ask["exe"])
            self.ask = None

    def unignore(self, exe: str) -> None:
        exe = str(exe or "").strip().lower()
        with self.lock:
            d = self.data()
            if exe in d["ignored"]:
                d["ignored"].remove(exe)
            g = d["games"].get(exe)
            if g:
                g.pop("off", None)
            self._save(d)

    def programs(self) -> list:
        """The open programs with a window (not Windows' own, not known non-games), for "Pick from open programs"."""
        procs = {p["pid"]: p for p in (self.procs() or [])}
        out, seen = [], set()
        for w in self.windows() or []:
            p = procs.get(w.get("pid"))
            if not p or p["exe"] in seen:
                continue
            seen.add(p["exe"])
            out.append({"exe": p["exe"], "title": _clean(w.get("title"), 80)})
        if not out and not WINDOWS:          # (tests: no windows, so every program)
            for p in procs.values():
                if p["exe"] not in seen:
                    seen.add(p["exe"])
                    out.append({"exe": p["exe"], "title": ""})
        return out[:40]

    # ---- the Twitch category
    def due(self):
        """The game whose category should change now (open 2 minutes, not settled yet), or None."""
        g = self.current()
        if not g or not g.get("cat") or g["key"] in self._handled:
            return None
        if self.demo_question():          # (the demo answer decides the category first)
            return None
        if self.clock() - (g.get("since") or 0) < SWITCH_AFTER:
            return None
        return g

    def settle(self, g, how: str, **result) -> None:
        self._handled.add(g["key"])
        if self.prompt and self.prompt.get("key") == g["key"]:
            self.prompt = None
        if result:
            self.result = dict(result, at=self.clock())

    def answer_prompt(self, yes: bool):
        """The streamer's answer to "Switch the Twitch category?": the game to switch to (yes), else None."""
        p = self.prompt
        if not p:
            return None
        self._handled.add(p["key"])
        self.prompt = None
        return p if yes else None


RADAR = Radar()


_told = set()


def _tell(key: str, en: tuple, ar: tuple) -> None:
    """A desktop pop-up (once per question): the streamer is in the game, not looking at the app."""
    if key in _told:
        return
    _told.add(key)
    try:
        from . import notify
        st = RADAR.store
        lang = (st.get("ui") or {}).get("language") if st else "en"
        title, msg = ar if lang == "ar" else en
        notify.send(st.get("prefs") if st else {}, title, msg)
    except Exception:
        log.exception("Game Radar pop-up failed")


async def tick(bot) -> None:
    """Every few seconds (dashboard): the Twitch category follows the game (Ask me / Automatic)."""
    R = RADAR
    a = R.ask
    if a:
        _tell("ask:" + a["exe"], ("Is this a game?", f"{a['exe']} has been full screen for a while. Open the app to answer."),
              ("هذي لعبة؟", f"{a['exe']} مفتوح بشاشة كاملة من فترة. افتح البرنامج وجاوب."))
    if bot is None or not getattr(bot, "connected", False):
        return
    if R.now:                       # the page shows the Twitch category next to the game (read every 20 s at most)
        try:
            R.twitch_cat = str((await bot._channel_info()).game_name or "")
        except Exception:
            log.info("Twitch category not read", exc_info=True)
    q = R.demo_question()
    if q:
        _tell("demo:" + q["exe"], (f"{q['name']} looks like a demo", "Twitch wants demos in “Games + Demos”. Open the app to choose."),
              (f"{q['name']} شكله ديمو", "تويتش يبي الديمو في «Games + Demos». افتح البرنامج واختر."))
    g = R.due()
    if not g:
        return
    mode = R.data()["switch"]
    if mode == "off":
        R.settle(g, "off")
        return
    try:
        cur = str((await bot._channel_info()).game_name or "")
        R.twitch_cat = cur
    except Exception:
        log.exception("Twitch category not read")
        return
    if cur.strip().casefold() == str(g["cat"]).strip().casefold():
        R.settle(g, "same")
        return
    if mode == "ask":
        if not R.prompt or R.prompt.get("key") != g["key"]:
            R.prompt = {"key": g["key"], "exe": g["exe"], "name": g["name"], "cat": g["cat"], "from": cur}
            _tell("cat:" + g["key"], (f"You're playing {g['name']}", f"Your Twitch category is {cur or '(none)'}. Open the app to switch it."),
                  (f"تلعب {g['name']}", f"تصنيفك في تويتش {cur or '(فاضي)'}. افتح البرنامج وغيّره."))
        return
    R.settle(g, "auto")
    await switch(bot, g)


async def switch(bot, g) -> dict:
    """Changes the Twitch category to the game's. Never says anything in chat."""
    R = RADAR
    try:
        got = await bot.radar_category(g["cat"])
    except Exception:
        log.exception("Category change failed")
        got = None
    if got and got.get("ok"):
        R.twitch_cat = got["name"]
        R.result = {"ok": True, "name": g["name"], "cat": got["name"], "at": R.clock()}
    else:
        R.result = {"ok": False, "name": g["name"], "cat": g["cat"], "why": (got or {}).get("why", "failed"), "at": R.clock()}
    return R.result
