# drobo
A Dropbox CLI

## Installation

```bash
pip install -e .
```

## Configuration

Create a `.droborc` file in your home directory with your Dropbox app configuration:

```toml
[apps.myapp]
app_key = "your_dropbox_app_key_here"
app_secret = "your_dropbox_app_secret_here"
access_token = "your_access_token"
refresh_token = "your_refresh_token"
```

## Usage

```bash
drobo <app name> <command> [options]
```

### Commands

- `ls`: List remote target contents (mimics Linux ls command)
- `cp`: Copy contents from one location to another (mimics Linux cp command)
- `mv`: Move contents from one location to another (mimics Linux mv command)
- `rm`: Remove remote files and folders (mimics Linux rm command)

### Options

- `--verbose, -v`: Enable verbose output
- `--version`: Show version and exit

### Examples

```bash
# List contents of root directory
drobo myapp ls /

# List with detailed output
drobo myapp ls -l /Documents

# Copy local file to Dropbox
drobo myapp cp local_file.txt /remote_file.txt

# Copy Dropbox file to local
drobo myapp cp /remote_file.txt local_file.txt

# Move file within Dropbox
drobo myapp mv /old_location.txt /new_location.txt

# Move multiple files to a directory
drobo myapp mv //file1.txt //file2.txt //documents/

# Move files using wildcards
drobo myapp mv //subdir/*.pdf //target_dir/

# Move with target directory option
drobo myapp mv -t //documents/ //file1.txt //file2.txt

# Force move (overwrite if destination exists)
drobo myapp mv -f //source.txt //existing_dest.txt

# Move only if source is newer (update)
drobo myapp mv -u //source.txt //dest.txt

# Remove file from Dropbox
drobo myapp rm /unwanted_file.txt

# Remove with force flag (ignore errors)
drobo myapp rm -f /might_not_exist.txt
```

## Development

```bash
# Install dependencies
make install

# Run tests
make test

# Run linting
make fmt

# Build package
make build

# Build documentation
make doc

# Create distribution
make dist

# Clean build artifacts
make clean
```
