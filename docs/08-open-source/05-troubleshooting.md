# Troubleshooting

This page collects common development issues caused by local machine setup.

## Issue: macOS audio uploads fail with `Bad CPU type`

Mianotes uses MarkItDown to convert uploaded files into Markdown. For audio files, MarkItDown calls local audio tools such as `ffprobe`, `ffmpeg`, `flac`, and `metaflac`.

On Apple Silicon Macs, audio uploads can fail if old Intel binaries in `/usr/local/bin` are found before Apple Silicon Homebrew binaries in `/opt/homebrew/bin`.

The Jobs console may show errors like:

```text
AudioConverter threw OSError with message: [Errno 86] Bad CPU type in executable: 'ffprobe'
```

or:

```text
AudioConverter threw OSError with message: [Errno 86] Bad CPU type in executable: '/usr/local/bin/flac'
```

Follow these steps in order.

### Step 1: Check which binaries are being used

Run this from the same shell that starts Mianotes:

```bash
which ffprobe ffmpeg flac metaflac
file "$(which ffprobe)" "$(which ffmpeg)" "$(which flac)" "$(which metaflac)"
```

A broken Apple Silicon setup usually points to `/usr/local/bin` and reports `x86_64` binaries:

```text
/usr/local/bin/ffprobe:  Mach-O 64-bit executable x86_64
/usr/local/bin/ffmpeg:   Mach-O 64-bit executable x86_64
/usr/local/bin/flac:     Mach-O 64-bit executable x86_64
/usr/local/bin/metaflac: Mach-O 64-bit executable x86_64
```

A healthy setup should point to `/opt/homebrew/bin` and report `arm64` binaries:

```text
/opt/homebrew/bin/ffprobe
/opt/homebrew/bin/ffmpeg
/opt/homebrew/bin/flac
/opt/homebrew/bin/metaflac
```

### Step 2: Reinstall the Apple Silicon audio tools

Install or reinstall the required packages with Homebrew:

```bash
brew reinstall ffmpeg flac
```

Then temporarily put Apple Silicon Homebrew first in your current shell:

```bash
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:$PATH"
hash -r
```

Check the binaries again:

```bash
which ffprobe ffmpeg flac metaflac
file "$(which ffprobe)" "$(which ffmpeg)" "$(which flac)" "$(which metaflac)"
```

If the output now points to `/opt/homebrew/bin` and reports `arm64`, restart Mianotes from the same shell.

### Step 3: Fix your shell startup file

If the problem comes back in a new terminal, your shell startup file is probably putting `/usr/local/bin` before `/opt/homebrew/bin`.

Inspect your startup files:

```bash
grep -n "PATH\\|path" ~/.bash_profile ~/.bashrc ~/.profile ~/.zshrc ~/.zprofile 2>/dev/null
```

Look for a line like this:

```bash
export PATH="/usr/local/bin:/usr/local/sbin:$PATH"
```

That line can shadow Apple Silicon tools if it runs after the `/opt/homebrew/bin` line.

For zsh, use this order:

```bash
export PATH="$HOME/.bun/bin:$PATH"
export PATH="/usr/local/bin:/usr/local/sbin:$PATH"
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:$PATH"
```

The important part is that the `/opt/homebrew/bin` line runs after any line that prepends `/usr/local/bin`.

Reload the shell:

```bash
source ~/.zshrc
hash -r
```

Then check again:

```bash
which ffprobe ffmpeg flac metaflac
file "$(which ffprobe)" "$(which ffmpeg)" "$(which flac)" "$(which metaflac)"
```

### Step 4: Check bash as well if Mianotes starts through bash

Some terminals, editor tasks, or scripts may start Mianotes through bash instead of zsh.

If the service is started from bash, add the Homebrew path to `~/.bash_profile` or `~/.bashrc` as well:

```bash
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:$PATH"
```

Then reload bash:

```bash
source ~/.bash_profile 2>/dev/null || source ~/.bashrc
hash -r
```

### Step 5: Start Mianotes again

After fixing `PATH`, restart Mianotes from a shell where the checks show `/opt/homebrew/bin` and `arm64`.

For development:

```bash
./start-dev.sh
```

For normal local use:

```bash
./start.sh
```

For a temporary one-command test, you can start Mianotes with the corrected `PATH` inline:

```bash
PATH="/opt/homebrew/bin:/opt/homebrew/sbin:$PATH" ./start-dev.sh
```

If that fixes audio uploads, make the `PATH` change permanent in the shell startup file used to launch Mianotes.
