"""Run on Windows: exercise both the bundle and the silently installed application."""
from pathlib import Path
import json
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2]
DIST=ROOT/'dist/windows'


def smoke(exe,report):
    subprocess.run([str(exe),'--smoke-test','--report',str(report)],check=True,timeout=180)
    result=json.loads(report.read_text(encoding='utf-8'))
    assert result['ok'] and result['tools']==25 and result['publisher']=='techobux'
    print(json.dumps(result))


def main():
    if sys.platform!='win32':raise SystemExit('Installer validation requires Windows.')
    reports=ROOT/'build/windows/acceptance';reports.mkdir(parents=True,exist_ok=True)
    smoke(DIST/'FRIDAY/FRIDAY.exe',reports/'bundle.json')
    target=reports/'installed';installer=DIST/'FRIDAY_Setup_56.0.0_x64.exe'
    subprocess.run([str(installer),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-',
                    f'/DIR={target}',f'/LOG={reports / "installer.log"}'],check=True,timeout=180)
    smoke(target/'FRIDAY.exe',reports/'installed.json')
    subprocess.run([str(target/'unins000.exe'),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART'],check=True,timeout=180)
    assert not (target/'FRIDAY.exe').exists(),'Uninstallation did not remove the application'
    (reports/'acceptance.json').write_text(json.dumps({'ok':True,'bundle':True,'installation':True,'installed_smoke':True,'uninstallation':True},indent=2))

if __name__=='__main__':main()
