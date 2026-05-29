# Installing from package

Install from package when you want Mianotes installed into normal system locations and started by the operating system.

This is the recommended path for people who want to use Mianotes rather than work on the code.

## macOS

Download the latest package:

```text
https://github.com/Mianotes/install/releases/latest/download/mianotes.pkg
```

Open `mianotes.pkg` and follow the installer.

The package installs Mianotes into:

```text
/Library/Application Support/Mianotes/
/Library/LaunchDaemons/com.mianotes.web-service.plist
/Library/LaunchDaemons/com.mianotes.dashboard.plist
/usr/local/bin/mianotes
```

After installation, Mianotes runs as two launchd services:

- `com.mianotes.web-service` on port `8200`
- `com.mianotes.dashboard` on port `8201`

Open Mianotes with:

```bash
mianotes open
```

Run a local health check with:

```bash
mianotes doctor
```

The macOS package creates its own Python virtual environment for Mianotes, but the Mac must already have Python 3.11 or newer available. If the installer cannot find Python, install Python from python.org or Homebrew, then run the package again.

For full search, file parsing, image OCR, and audio/video support, Mianotes can use these local tools when they are available:

```bash
brew install python ripgrep ffmpeg tesseract
```

`mianotes doctor` shows whether those tools are available.

## Ubuntu

Download the latest Debian package:

```text
https://github.com/Mianotes/install/releases/latest/download/mianotes.deb
```

Install it with:

```bash
sudo apt install ./mianotes.deb
```

The package installs Mianotes into:

```text
/opt/mianotes/
/etc/mianotes/mianotes.env
/lib/systemd/system/mianotes-web-service.service
/lib/systemd/system/mianotes-dashboard.service
/usr/bin/mianotes
/var/lib/mianotes/
```

After installation, Mianotes runs as two systemd services:

- `mianotes-web-service` on port `8200`
- `mianotes-dashboard` on port `8201`

The Ubuntu package installs the required system packages for parsing and searching notes, including `ripgrep`, `ffmpeg`, and `tesseract-ocr`.

Open Mianotes with:

```bash
mianotes open
```

Run a local health check with:

```bash
mianotes doctor
```

## Useful commands

```bash
mianotes open
mianotes status
mianotes start
mianotes stop
mianotes doctor
mianotes logs
mianotes uninstall
```

On Ubuntu, `mianotes restart` is also available.

`mianotes uninstall` removes the app services and installed app files.

It keeps your data, environment file, and workspace configuration:

- macOS: `/Library/Application Support/Mianotes/`
- Ubuntu: `/var/lib/mianotes/` and `/etc/mianotes/`

## First run

Open the web app, create the first user, then create or switch workspace.

Read next: [First run](02-first-run.md) and [Configuration options](03-configuration.md).
