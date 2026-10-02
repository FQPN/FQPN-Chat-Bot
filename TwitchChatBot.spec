# -*- mode: python ; coding: utf-8 -*-
# PyInstaller recipe: turns the bot and its libraries into a folder with TwitchChatBot.exe (no Python needed).
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hidden = (collect_submodules("twitchio") + collect_submodules("aiohttp")
          + collect_submodules("webview"))
datas = [("core/dashboard.html", "core")] + collect_data_files("twitchio") + collect_data_files("webview")

a = Analysis(
    ["launcher.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FQPN'sChatBot",
    console=False,          # the black window: it shows the Twitch code and closing it stops the bot
    icon="icon.ico",
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="TwitchChatBot")
