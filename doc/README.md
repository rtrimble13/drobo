# Drobo Documentation

## Overview

Drobo is a command-line interface for Dropbox that mimics traditional Unix file operations. It allows you to interact with your Dropbox files using familiar commands like `ls`, `cp`, `mv`, and `rm`.

## Features

- **Multiple App Support**: Configure multiple Dropbox apps and switch between them easily
- **Unix-like Commands**: Familiar command syntax that mimics standard Unix tools
- **Token Management**: Automatic refresh of OAuth tokens
- **Detailed Logging**: Comprehensive logging for debugging connection and API issues
- **Verbose Mode**: Optional verbose output for detailed operation information

## Getting Started

1. **Create a Dropbox App**: Visit the [Dropbox App Console](https://www.dropbox.com/developers/apps) to create a new app and get your app key and secret.

2. **Configure drobo**: Copy the example configuration file and update it with your credentials:
   ```bash
   cp etc/droborc.example ~/.droborc
   # Edit ~/.droborc with your app credentials
   ```

3. **Obtain Access Tokens**: Run `drobo <app> auth`. This opens the Dropbox
   OAuth flow, asks you to paste back an authorization code, and writes the
   resulting access and refresh tokens into your configuration file. It needs
   an interactive terminal.

   Once a refresh token is stored, drobo renews the access token on its own --
   you should not need to run `auth` again unless access is revoked.

4. **Start Using drobo**: Once configured, you can start using drobo commands:
   ```bash
   drobo myapp ls //
   ```

## Command Reference

### auth - Authorize an App

```bash
drobo <app> auth
```

Runs the Dropbox OAuth flow for the named app and stores the returned access
and refresh tokens in the configuration file. Requires an interactive
terminal; it will refuse to run (rather than hang) when stdin is not a TTY,
so it is safe to invoke from scripts that may not have one.

```bash
drobo myapp auth
```

### ls - List Directory Contents

```bash
drobo <app> ls [options] [path]
```

Options:
- `-l`: use a long listing format
- `-r, --reverse`: reverse order while sorting
- `-R, --recursive`: list subdirectories recursively
- `-S`: sort by file size, largest first
- `-t`: sort by time, newest first

Examples:
```bash
drobo myapp ls //                 # list the remote root
drobo myapp ls -l //Documents     # long format
drobo myapp ls -ltr //Documents   # long format, sorted by time, reversed
drobo myapp ls -R //              # recursive listing
drobo myapp ls -S //Documents     # sort by file size
```

### cp - Copy Files

```bash
drobo <app> cp [options] SOURCE ... DEST
drobo <app> cp [options] -T SOURCE DEST
drobo <app> cp [options] -t DIRECTORY SOURCE ...
```

Options:
- `-r, --recursive`: Copy directories recursively
- `-T`: Treat DEST as a normal file
- `-t, --target-directory=DIRECTORY`: Copy all SOURCE arguments into DIRECTORY

**Important Notes:**
- Remote paths begin with `//`, local paths follow Linux conventions
- SOURCE files must all be remote or all be local (cannot mix)
- Wildcards are supported in SOURCE (e.g., `*.pdf`, `file?.txt`)
- When copying multiple files, DEST must be a directory
- Local-to-local copies are not supported (use standard `cp` command)

Examples:
```bash
# Upload local file to Dropbox
drobo myapp cp ~/file.txt //remote_file.txt

# Download from Dropbox to local
drobo myapp cp //remote_file.txt ~/local_file.txt

# Copy within Dropbox (remote to remote)
drobo myapp cp //source.txt //destination.txt

# Copy multiple files using wildcards
drobo myapp cp //subdir/*.pdf .
drobo myapp cp ~/Documents/*.txt //backup/

# Recursive directory copy
drobo myapp cp -r //remote_dir ./local_dir

# If local_dir exists, creates ./local_dir/remote_dir/
# If local_dir doesn't exist, creates it and copies contents directly

# Use -t flag to specify target directory first
drobo myapp cp -t //target_dir ~/file1.txt ~/file2.txt

# Use -T flag to treat destination as a file
drobo myapp cp -T //source/file.txt //dest_file.txt
```

### mv - Move/Rename Files

```bash
drobo <app> mv [options] SOURCE ... DEST
drobo <app> mv [options] -t DIRECTORY SOURCE ...
```

Options:
- `-f, --force`: do not raise an error if the destination file already exists
- `-u, --update`: move only when SOURCE is newer than the destination, or the
  destination is missing
- `-t, --target-directory=DIRECTORY`: move all SOURCE arguments into DIRECTORY

Examples:
```bash
# Rename file in Dropbox
drobo myapp mv //old_name.txt //new_name.txt

# Move file to a different directory
drobo myapp mv //file.txt //subfolder/file.txt

# Move multiple files into a directory
drobo myapp mv -t //documents //file1.txt //file2.txt

# Overwrite an existing destination
drobo myapp mv -f //source.txt //existing_dest.txt

# Move only if the source is newer
drobo myapp mv -u //source.txt //dest.txt
```

### rm - Remove Files

```bash
drobo <app> rm [options] <file1> [file2 ...]
```

Options:
- `-f, --force`: ignore nonexistent files and arguments, never prompt
- `-r, --recursive`: remove directories and their contents recursively

Examples:
```bash
# Remove single file
drobo myapp rm //unwanted_file.txt

# Remove multiple files
drobo myapp rm //file1.txt //file2.txt

# Force remove (ignore errors)
drobo myapp rm -f //might_not_exist.txt

# Remove a directory and its contents
drobo myapp rm -r //directory
```

## Configuration File Format

The configuration file uses TOML format and should be located at `~/.droborc`:

```toml
[apps.app_name]
app_key = "your_dropbox_app_key"
app_secret = "your_dropbox_app_secret"
access_token = "your_access_token"
refresh_token = "your_refresh_token"
```

You can define multiple apps in the same file by using different app names.

## Troubleshooting

### Common Issues

1. **"App not found" error**: Check that your app name matches what's defined in `.droborc`
2. **Authentication errors**: Verify your app key, secret, and tokens are correct
3. **Network timeouts**: Check your internet connection and Dropbox service status

### Logging

Drobo logs all operations to `~/.drobo.log`. Use the verbose flag (`-v`) for more detailed output:

```bash
drobo -v myapp ls //
```

### Token Refresh

If your access token expires, drobo refreshes it automatically using the
stored refresh token -- no interaction is required, so this works from cron
and scripts. A refresh token on its own is a complete credential: you may
leave `access_token` empty and drobo will obtain one on first use.

If refresh fails (for example the app's access was revoked), re-authorize
with `drobo <app> auth`.

### Configuration File Permissions

The configuration file holds your app secret and refresh token, so drobo
creates it with mode `0600` (owner read/write only) and keeps it that way
when saving tokens. If an existing file is readable by other users, drobo
warns on startup; fix it with `chmod 600 ~/.droborc`.