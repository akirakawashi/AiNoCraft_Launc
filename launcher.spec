# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

datas = [('ui', 'ui'), ('build_profiles.json', '.'), ('version.json', '.')]
_injector_candidates = [
    Path('injector') / 'authlib-injector-1.2.7.jar',
    Path('authlib-injector-1.2.7.jar'),
]
for _injector_jar in _injector_candidates:
    if _injector_jar.exists():
        _dest = str(_injector_jar.parent) if str(_injector_jar.parent) != '.' else '.'
        datas.append((str(_injector_jar), _dest))
        break

a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
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
    name='AiNoCraftLauncher',
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
    icon=['ui\\img\\logo.ico'],
)
