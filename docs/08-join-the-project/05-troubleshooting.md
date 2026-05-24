# Troubleshooting

This page collects development issues that usually come from local machine setup.

## macOS audio uploads fail with Bad CPU type

Mianotes uses MarkItDown to convert uploaded files into Markdown. For audio files,
MarkItDown calls local audio tools such as `ffprobe`, `ffmpeg`, `flac`, and
`metaflac`.

On Apple Silicon Macs, audio parsing can fail when old Intel binaries in
`/usr/local/bin` appear before the Apple Silicon Homebrew binaries in
`/opt/homebrew/bin`.

The Jobs console may show errors like:

```text
AudioConverter threw OSError with message: [Errno 86] Bad CPU type in executable: 'ffprobe'
```

or:

```text
AudioConverter threw OSError with message: [Errno 86] Bad CPU type in executable: '/usr/local/bin/flac'
```

Check which binaries the service shell is using:

```bash
which ffprobe ffmpeg flac metaflac
file "$(which ffprobe)" "$(which ffmpeg)" "$(which flac)" "$(which metaflac)"
```

Broken Apple Silicon setup usually looks like this:

```text
/usr/local/bin/ffprobe:  Mach-O 64-bit executable x86_64
/usr/local/bin/ffmpeg:   Mach-O 64-bit executable x86_64
/usr/local/bin/flac:     Mach-O 64-bit executable x86_64
/usr/local/bin/metaflac: Mach-O 64-bit executable x86_64
```

Install or reinstall the Apple Silicon packages:

```bash
brew reinstall ffmpeg flac
```

Make sure Apple Silicon Homebrew is first in the shell that starts Mianotes:

```bash
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:$PATH"
hash -r
```

Check again:

```bash
which ffprobe ffmpeg flac metaflac
file "$(which ffprobe)" "$(which ffmpeg)" "$(which flac)" "$(which metaflac)"
```

Healthy output should point to `/opt/homebrew/bin` and report `arm64` binaries.

```text
/opt/homebrew/bin/ffprobe
/opt/homebrew/bin/ffmpeg
/opt/homebrew/bin/flac
/opt/homebrew/bin/metaflac
```

Restart the Mianotes service from the same shell after fixing `PATH`.

## PATH keeps choosing /usr/local/bin

If `/usr/local/bin` still appears first, inspect your shell startup files:

```bash
grep -n "PATH\\|path" ~/.bash_profile ~/.bashrc ~/.profile ~/.zshrc ~/.zprofile 2>/dev/null
```

If you see a later line like this:

```bash
export PATH=/usr/local/bin:/usr/local/sbin:$PATH
```

it can shadow the Apple Silicon tools. Put the Apple Silicon Homebrew line after
it, or remove the `/usr/local/bin` prepend if you do not need it.

For zsh, a safe order is:

```bash
export PATH="$HOME/.bun/bin:$PATH"
export PATH="/usr/local/bin:/usr/local/sbin:$PATH"
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:$PATH"
```

Then reload the shell:

```bash
source ~/.zshrc
hash -r
```

If the current terminal is using bash, update `~/.bash_profile` or `~/.bashrc`
as well, or run the temporary `export PATH=...` command before starting the
service.
