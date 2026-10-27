"""Fetch the official, checksum-pinned offline wake model before a clean build."""
import hashlib
from pathlib import Path
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
MODEL = 'vosk-model-small-en-us-0.15'
URL = f'https://alphacephei.com/vosk/models/{MODEL}.zip'
SHA256 = '30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498'


def main():
    destination = ROOT / 'memory' / 'wake'
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        archive = Path(temporary) / 'model.zip'
        urllib.request.urlretrieve(URL, archive)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
            raise RuntimeError('Official wake model checksum mismatch')
        with zipfile.ZipFile(archive) as source:
            for item in source.infolist():
                path = Path(item.filename)
                if path.is_absolute() or '..' in path.parts or path.parts[0] != MODEL:
                    raise RuntimeError('Unsafe wake model archive entry')
            source.extractall(destination)
    if not (destination / MODEL / 'am' / 'final.mdl').is_file():
        raise RuntimeError('Wake model is incomplete')
    print('Official offline Friday wake model verified.')


if __name__ == '__main__':
    main()
