# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


datas = [("ui", "ui")]

build_profiles = Path("build_profiles.json")
if build_profiles.exists():
    datas.append((str(build_profiles), "."))

build_metadata = Path("build_metadata.json")
if build_metadata.exists():
    datas.append((str(build_metadata), "."))

injector_jar = Path("injector") / "authlib-injector-1.2.7.jar"
if injector_jar.exists():
    datas.append((str(injector_jar), "injector"))

a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=["webview.platforms.edgechromium"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AiNoCraftLauncher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["ui\\img\\logo.ico"],
)
