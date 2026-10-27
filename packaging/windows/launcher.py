"""Windows executable entry point. Persist state outside the installation directory."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import runpy
import shutil
import sys
import tempfile
import traceback


def safe_target(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
        raise ValueError('Invalid payload path')
    target = root.joinpath(*relative.parts)
    node = target
    while node != root.parent:
        if node.is_symlink():
            raise ValueError('A managed application path is a symbolic link')
        if node == root:
            break
        node = node.parent
    return target


def prepare(payload: Path, support: Path) -> Path:
    manifest = json.loads((payload/'payload-manifest.json').read_text(encoding='utf-8'))
    app = support/'app';app.mkdir(parents=True,exist_ok=True)
    for name,digest in manifest['files'].items():
        source = safe_target(payload,name);target = safe_target(app,name)
        if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise ValueError(f'Packaged file failed verification: {name}')
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == digest:
            continue
        target.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent,delete=False,suffix='.installing') as stream:
            staging = Path(stream.name);stream.write(source.read_bytes())
        staging.replace(target)
    # Only obsolete files previously recorded by our launcher are removed.
    previous = app/'.payload-manifest.json'
    if previous.is_file():
        for name in json.loads(previous.read_text(encoding='utf-8')).get('files',{}):
            if name not in manifest['files']:
                old = safe_target(app,name)
                if old.is_file():old.unlink()
    previous.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    for name in ('config','memory','plugins'):(app/name).mkdir(exist_ok=True)
    return app


def smoke_test(app: Path, report: Path):
    # No microphone, camera, browser navigation, or network requests.
    os.environ['QT_QPA_PLATFORM']='offscreen'
    from PyQt6.QtWidgets import QApplication
    from google.genai import types
    from core.action_loader import discover_actions
    from ui import MainWindow
    import main
    import cv2, sounddevice, cryptography
    from playwright.sync_api import sync_playwright
    from memory.config_manager import CONFIG_FILE
    assert CONFIG_FILE.parent.parent == app
    from core.wake_word import is_ready
    assert is_ready(), 'Bundled Friday wake model is unavailable'
    with sync_playwright() as browser_driver:
        assert browser_driver.chromium.name == 'chromium'
    registry=discover_actions(app/'actions',{d['name'] for d in main.TOOL_DECLARATIONS})
    declarations=main.TOOL_DECLARATIONS+registry.get_tool_declarations()
    for declaration in declarations:types.FunctionDeclaration(**declaration)
    if len(declarations)!=25:raise RuntimeError(f'Expected 25 tools, loaded {len(declarations)}')
    q=QApplication.instance() or QApplication([]);w=MainWindow('');w.show();q.processEvents()
    if w._overlay:w._overlay.hide()
    q.processEvents();image=report.with_suffix('.png')
    assert w.grab().save(str(image));w.close()
    report.write_text(json.dumps({'ok':True,'version':'56.0.0','publisher':'techobux','tools':len(declarations),'runtime':str(app),'hud':str(image)},indent=2),encoding='utf-8')


def main():
    smoke='--smoke-test' in sys.argv
    if smoke:
        index=sys.argv.index('--report');report=Path(sys.argv[index+1]).resolve();report.parent.mkdir(parents=True,exist_ok=True)
        support=report.parent/'friday-smoke-state'
    else:
        support=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))/'FRIDAY'
    logs=support/'logs';logs.mkdir(parents=True,exist_ok=True)
    log=(logs/'startup.log').open('a',encoding='utf-8',buffering=1)
    sys.stdout=sys.stderr=log
    try:
        bundle=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
        app=prepare(bundle/'app_payload',support)
        os.environ['FRIDAY_RUNTIME_DIR']=str(app)
        sys.path.insert(0,str(app));os.chdir(app)
        if smoke:smoke_test(app,report)
        else:runpy.run_path(str(app/'main.py'),run_name='__main__')
    except Exception:
        traceback.print_exc()
        if not smoke:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,f'FRIDAY could not start. Details are in:\n{logs / "startup.log"}','FRIDAY',0x10)
        raise SystemExit(1)


if __name__=='__main__':main()
