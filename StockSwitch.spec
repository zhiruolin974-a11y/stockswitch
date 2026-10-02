"""Windows onedir release build; invoke through scripts/build_windows.ps1."""

from pathlib import Path
import os

root = Path(SPECPATH)
icon = root / "assets" / "StockSwitch.ico"
version_info = root / "build" / "version_info.txt"
debug_build = os.environ.get("STOCKSWITCH_DEBUG_BUILD") == "1"
bundle_name = "StockSwitchDebug" if debug_build else "StockSwitch"

a = Analysis(
    [str(root / "main.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / "config.example.toml"), "."), (str(icon), "assets"),
           (str(root / "THIRD_PARTY_NOTICES.md"), ".")],
    hiddenimports=["zoneinfo", "tzdata"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
# The build host may have Poppler's ICU 78 on PATH. Its icuuc.dll exports
# version-suffixed names, while the PySide6 Qt6Core.dll expects Windows' system
# ICU unversioned entry points. Never place that unrelated DLL at _internal root.
def omit_unneeded(entry):
    destination = str(entry[0]).replace("\\", "/").lower()
    filename = Path(destination).name
    return (filename in {"icuuc.dll", "icudt78.dll"} or
            "virtualkeyboard" in destination or
            filename.startswith("qt6pdf") or "/qtpdf/" in destination)


a.binaries = [entry for entry in a.binaries if not omit_unneeded(entry)]
a.datas = [entry for entry in a.datas if not omit_unneeded(entry)]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name=bundle_name,
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=debug_build, disable_windowed_traceback=False,
    icon=str(icon), version=str(version_info),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=bundle_name)
