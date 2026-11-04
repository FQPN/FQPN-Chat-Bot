# -*- mode: python ; coding: utf-8 -*-
# PyInstaller recipe: turns the bot and its libraries into a folder with FQPNsChatBot.exe (no Python needed).
#
# Fewer antivirus false alarms (1.16.0):
#  - no UPX: a compressed program looks like packed malware to antivirus programs, so nothing is compressed
#  - Windows version info (Properties > Details): who made it, what it is, its version
#  - the build on GitHub uses a PyInstaller "starter" (bootloader) compiled there, not the one shared by every
#    PyInstaller program in the world (see .github/workflows/build-installer.yml)
#  - the name has no apostrophe: FQPNsChatBot.exe (it was FQPN'sChatBot.exe; the installer removes the old one)
import datetime
import re

from PyInstaller.utils.hooks import collect_data_files, collect_submodules
from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                 VarFileInfo, VarStruct, VSVersionInfo)

EXE_NAME = "FQPNsChatBot"

# The version comes from ONE place: core/version.py, which the GitHub build fills in from the release tag (v1.16.0).
_text = open("core/version.py", encoding="utf-8").read()
VERSION = re.search(r'VERSION\s*=\s*"([^"]*)"', _text).group(1)
_nums = [int(x) for x in re.findall(r"\d+", VERSION.split("-")[0])][:3]
NUMS = tuple(_nums + [0] * (4 - len(_nums)))            # 1.16.0 -> (1, 16, 0, 0): Windows wants four numbers

version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=NUMS, prodvers=NUMS, mask=0x3F, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
                      date=(0, 0)),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", "FQPN"),
            StringStruct("ProductName", "FQPN's Chat Bot"),
            StringStruct("FileDescription", "FQPN's Chat Bot"),        # the name Task Manager shows
            StringStruct("FileVersion", VERSION),
            StringStruct("ProductVersion", VERSION),
            StringStruct("InternalName", EXE_NAME),
            StringStruct("OriginalFilename", EXE_NAME + ".exe"),
            StringStruct("LegalCopyright", f"Copyright \u00a9 {datetime.date.today().year} FQPN"),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ],
)

hidden = (collect_submodules("twitchio") + collect_submodules("aiohttp")
          + collect_submodules("webview"))
datas = [("core/dashboard.html", "core")] + collect_data_files("twitchio") + collect_data_files("webview")
hidden += collect_submodules("pystray")   # the tray icon (its Windows part is loaded by name at run time)
datas += [("icon.ico", ".")]              # the logo shown in the dashboard and in the tray

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
    name=EXE_NAME,
    console=False,          # the black window: it shows the Twitch code and closing it stops the bot
    icon="icon.ico",        # the app's logo on the exe
    version=version_info,   # Properties > Details
    upx=False,              # never compressed (UPX is a common reason for false alarms)
    strip=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="TwitchChatBot")
