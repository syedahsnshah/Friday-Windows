"""Explicit release payload: application code/assets, never private settings or sessions."""
from pathlib import Path
import hashlib
import json
import shutil

VERSION = '56.0.0'
PUBLISHER = 'techobux'
TOP = ('main.py','ui.py','LICENSE','readme.md','requirements.txt','THIRD_PARTY_NOTICES.md','CHANGELOG.md')
CODE_DIRS = ('actions','core','memory','config','dashboard','plugins')
ASSET_NAMES = {'face_model.obj','prompt.txt','friday.ico'}


def payload_files(root: Path):
    files = [root / name for name in TOP]
    for directory in CODE_DIRS:
        for path in (root / directory).rglob('*'):
            if not path.is_file() or path.is_symlink() or '__pycache__' in path.parts:
                continue
            relative = path.relative_to(root)
            if path.suffix == '.py' or path.name in ASSET_NAMES or (
                relative.parts[:2] == ('dashboard','static') and path.suffix in {'.html','.css','.js','.svg','.png','.ico'}
            ):
                files.append(path)
    model = root/'memory/wake/vosk-model-small-en-us-0.15'
    if not (model/'am/final.mdl').is_file():
        raise FileNotFoundError('The FRIDAY offline wake model must be included before building.')
    files.extend(p for p in model.rglob('*') if p.is_file() and not p.is_symlink())
    return sorted(set(files))


def stage_payload(root: Path, destination: Path):
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    manifest = {}
    for source in payload_files(root):
        relative = source.relative_to(root)
        target = destination/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        manifest[relative.as_posix()] = hashlib.sha256(target.read_bytes()).hexdigest()
    result = {'version':VERSION,'publisher':PUBLISHER,'files':manifest}
    (destination/'payload-manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result
