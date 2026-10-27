# FRIDAY Windows installer — techobux

The customer deliverable is **FRIDAY_Setup_56.0.0_x64.exe**. Customers install it through the setup wizard and launch FRIDAY from the Start Menu or optional desktop shortcut. They do not install Python or run source files.

The installer targets Windows 10 build 19041 or later and Windows 11, with an x64 Python bundle. It installs for the current user without requesting administrator rights. Settings, credentials, memories and jobs live separately under `%LOCALAPPDATA%\FRIDAY\app`; uninstalling the program preserves them. First launch uses FRIDAY's existing in-app setup. Service credentials and browser sessions are never shipped inside the installer.

The original HUD and voice flow remain. The offline Friday wake recognizer and model, audio libraries, document tools and Playwright's Node driver are bundled. No new Chromium installation or browser profile is created by the installer.

## Build in GitHub Actions

Push the application source and `.github/workflows/build-windows-exe.yml` to the repository's `main` or `master` branch, or run **Build Windows Executable & Installer** manually in Actions. The workflow uses a Windows x64 runner and Python 3.11. It downloads the official offline wake model with a pinned SHA-256 checksum, builds the executable, builds Inno Setup, tests a silent installation and an offline application launch, and tests uninstallation.

Download the `FRIDAY-56.0.0-Windows-Setup` artifact after the workflow succeeds. It contains the setup executable, SHA-256 checksum and a build manifest. The diagnostics artifact contains the tool/HUD acceptance reports. A green build is not a live microphone, browser-account or ecommerce acceptance test; test those on a real customer-style Windows machine before distributing widely.

## Build on a Windows PC

Build prerequisites (for the developer only): Python 3.11 x64 and Inno Setup 6 or newer. Run `packaging\windows\build.bat`, or run `packaging\windows\build.ps1` from PowerShell. It creates an isolated `.venv-windows` and builds once. Missing compiler or dependency failures stop the build rather than reporting a successful setup.

Manual commands:

```
python -m pip install -r requirements.txt "pyinstaller>=6.16,<7"
python packaging/windows/fetch_wake_model.py
python packaging/windows/build_exe.py --installer
python packaging/windows/validate_installer.py
```

Output: `dist/windows/FRIDAY_Setup_56.0.0_x64.exe`.

## Build boundaries

PyInstaller must run on Windows for a Windows binary; [PyInstaller documents the platform requirement](https://www.pyinstaller.org/en/stable/). The source allowlist excludes private configuration, accounts, sessions, certificates, memories, generated videos and developer environments. The payload is hashed and copied to a user-writable runtime on launch, preserving personal state during upgrades. Third-party license notices remain included.

This pipeline creates an unsigned installer. A trusted publisher signature requires a separate code-signing certificate; the manifest reports `signed: false`. No signing or notarization is claimed by a successful compilation.
