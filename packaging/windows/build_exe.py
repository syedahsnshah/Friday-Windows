"""Build and check the native Windows application and Inno Setup installation file."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
DIST=ROOT/'dist/windows'
sys.path.insert(0,str(HERE))
from payload import VERSION, PUBLISHER, stage_payload


def require_windows():
    if sys.platform!='win32':
        raise SystemExit('Build the Windows .exe on a Windows x64 runner/PC; PyInstaller cannot cross-compile it from macOS.')
    if sys.version_info[:2]!=(3,11) or platform.architecture()[0]!='64bit':
        raise SystemExit('Use 64-bit Python 3.11 to build FRIDAY.')


def build_pyinstaller(clean=True):
    require_windows()
    stage_payload(ROOT,ROOT/'build/windows/payload')
    cmd=[sys.executable,'-m','PyInstaller','--noconfirm']
    if clean:cmd.append('--clean')
    cmd += ['--distpath',str(DIST),'--workpath',str(ROOT/'build/windows/pyinstaller'),str(HERE/'FRIDAY.spec')]
    subprocess.run(cmd,cwd=ROOT,check=True)
    app=DIST/'FRIDAY'
    if not (app/'FRIDAY.exe').is_file():raise RuntimeError('PyInstaller did not produce FRIDAY.exe')
    return app


def build_inno_setup(app_dir):
    paths=[os.environ.get('ISCC_PATH'),shutil.which('iscc'),shutil.which('ISCC'),
           r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',r'C:\Program Files\Inno Setup 6\ISCC.exe']
    for base in (os.environ.get('ProgramFiles(x86)'),os.environ.get('ProgramFiles')):
        if base:paths.extend(str(p) for p in Path(base).glob('Inno Setup*/ISCC.exe'))
    iscc=next((p for p in paths if p and Path(p).is_file()),None)
    if not iscc:raise RuntimeError('Inno Setup 6 compiler is required for Setup.exe. Set ISCC_PATH if it is installed elsewhere.')
    subprocess.run([iscc,f'/DAppSourceDir={app_dir}',f'/DOutputDir={DIST}',str(HERE/'setup_installer.iss')],check=True,cwd=HERE)
    installer=DIST/f'FRIDAY_Setup_{VERSION}_x64.exe'
    if not installer.is_file():raise RuntimeError('The installer compiler returned without creating Setup.exe')
    receipt={'version':VERSION,'publisher':PUBLISHER,'file':installer.name,'bytes':installer.stat().st_size,
             'sha256':hashlib.sha256(installer.read_bytes()).hexdigest(),'signed':False}
    (DIST/'installer-manifest.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    (DIST/'SHA256SUMS.txt').write_text(f'{receipt["sha256"]}  {installer.name}\n',encoding='utf-8')
    return installer


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installer',action='store_true')
    parser.add_argument('--installer-only',action='store_true',help='Package an already built dist/windows/FRIDAY folder')
    parser.add_argument('--no-clean',action='store_true')
    args=parser.parse_args();require_windows();DIST.mkdir(parents=True,exist_ok=True)
    app=DIST/'FRIDAY' if args.installer_only else build_pyinstaller(not args.no_clean)
    print(build_inno_setup(app) if args.installer or args.installer_only else app)

if __name__=='__main__':main()
