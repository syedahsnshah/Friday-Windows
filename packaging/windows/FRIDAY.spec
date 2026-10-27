# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files

ROOT = Path(SPECPATH).resolve().parents[1]
payload = ROOT/'build/windows/payload'
if not (payload/'payload-manifest.json').is_file():
    raise RuntimeError('Run packaging/windows/build_exe.py to stage the release payload first.')
datas = [(str(payload),'app_payload')]
hidden_imports = ['main','ui','google.genai','google.genai.types','playwright.sync_api','playwright.async_api',
 'uvicorn.logging','uvicorn.loops.auto','uvicorn.protocols.http.auto',
 'uvicorn.protocols.websockets.auto','uvicorn.lifespan.on','win32com.client','win32api','win32gui','win32con']
for folder in ('actions','core','memory','config','dashboard','plugins'):
    for source in (ROOT/folder).rglob('*.py'):
        if '__pycache__' not in source.parts:
            parts=list(source.relative_to(ROOT).with_suffix('').parts)
            if parts[-1]=='__init__':parts.pop()
            if parts:hidden_imports.append('.'.join(parts))
binaries=[]
for package in ('vosk','_sounddevice_data'):
    more_data, more_binaries, more_imports = collect_all(package)
    datas+=more_data;binaries+=more_binaries;hidden_imports+=more_imports
datas+=collect_data_files('playwright')  # Node driver, not a fresh browser/profile.
a=Analysis([str(ROOT/'packaging/windows/launcher.py')],pathex=[str(ROOT)],binaries=binaries,
 datas=datas,hiddenimports=sorted(set(hidden_imports)),hookspath=[],hooksconfig={},runtime_hooks=[],
 excludes=['matplotlib','notebook','pytest'],noarchive=False,optimize=0)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='FRIDAY',debug=False,
 bootloader_ignore_signals=False,strip=False,upx=False,console=False,
 disable_windowed_traceback=False,icon=str(ROOT/'config/friday.ico'))
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='FRIDAY')
