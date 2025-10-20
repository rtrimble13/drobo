"""
Main CLI module for drobo.
"""

import logging
import sys
from pathlib import Path

import click

from drobo import __version__
from drobo.commands import setup_commands
from drobo.config import ConfigManager


def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.ERROR
    format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    logging.basicConfig(
        level=level,
        format=format_str,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(Path.home() / ".drobo.log"),
        ],
    )


def print_version(ctx, param, value):
    """Print version and exit."""
    if not value or ctx.resilient_parsing:
        return
    click.echo(f"drobo version {__version__}")
    ctx.exit()


@click.group()
@click.argument("app_name")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option(
    "--version",
    is_flag=True,
    expose_value=False,
    is_eager=True,
    callback=print_version,
    help="Show version and exit",
)
@click.pass_context
def cli(ctx, app_name: str, verbose: bool) -> None:
    """
    Drobo - A Dropbox CLI

    Usage: drobo <app name> <command> [options]

    App names are aliases configured in ~/.droborc
    """
    setup_logging(verbose)

    # Store app context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["app_name"] = app_name
    ctx.obj["verbose"] = verbose


def get_command_handler(ctx):
    """Get command handler, initializing if needed."""
    if "command_handler" not in ctx.obj:
        try:
            config_manager = ConfigManager()
            app_config = config_manager.get_app_config(ctx.obj["app_name"])

            if not app_config:
                click.echo(
                    f"Error: App '{ctx.obj['app_name']}' not found in .droborc",
                    err=True,
                )
                sys.exit(1)

            # Setup the command handler
            ctx.obj["command_handler"] = setup_commands(
                app_config, ctx.obj["verbose"]
            )
        except Exception as e:
            logging.error(f"Command failed: {e}")
            if ctx.obj["verbose"]:
                raise
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

    return ctx.obj["command_handler"]


@cli.command()
@click.argument("path", default="/")
@click.option(
    "-l", "long_format", is_flag=True, help="use a long listing format"
)
@click.option(
    "-r", "--reverse", is_flag=True, help="reverse order while sorting"
)
@click.option(
    "-R", "--recursive", is_flag=True, help="list subdirectories recursively"
)
@click.option(
    "-S", "sort_by_size", is_flag=True, help="sort by file size, largest first"
)
@click.option(
    "-t", "sort_by_time", is_flag=True, help="sort by time, newest first"
)
@click.pass_context
def ls(
    ctx,
    path: str,
    long_format: bool,
    reverse: bool,
    recursive: bool,
    sort_by_size: bool,
    sort_by_time: bool,
) -> None:
    """List remote target contents. Mimic Linux ls command."""
    try:
        command_handler = get_command_handler(ctx)
        command_handler.ls_with_options(
            path=path,
            long_format=long_format,
            reverse=reverse,
            recursive=recursive,
            sort_by_size=sort_by_size,
            sort_by_time=sort_by_time,
        )
    except Exception as e:
        logging.error(f"ls command failed: {e}")
        if ctx.obj.get("verbose"):
            raise
        click.echo(f"ls: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("sources", nargs=-1, required=True)
@click.option(
    "-r", "--recursive", is_flag=True, help="copy directories recursively"
)
@click.option(
    "-T", "treat_as_file", is_flag=True, help="treat DEST as a normal file"
)
@click.option(
    "-t", "--target-directory", help="copy all SOURCE arguments into DIRECTORY"
)
@click.pass_context
def cp(
    ctx,
    sources: tuple,
    recursive: bool,
    treat_as_file: bool,
    target_directory: str,
) -> None:
    """Copy contents from one location to another. Mimic Linux cp command.

    Usage:
    drobo <app name> cp [options] SOURCE ... DEST
    drobo <app name> cp [options] -T SOURCE DEST
    drobo <app name> cp [options] -t DIRECTORY SOURCE ...

    Remote paths begin with //, local paths follow Linux conventions.
    Wildcards (*,?) are supported in SOURCE paths.
    All SOURCE files must be either remote or local (cannot mix).

    Examples:
    drobo myapp cp ~/file1 //          Copy local file to remote root
    drobo myapp cp //subdir/*.pdf .    Copy remote PDFs to current dir
    drobo myapp cp -T //subdir/file2 ../file2    Copy remote to local
    drobo myapp cp -rt ./local_dir //subdir1 //subdir2   Copy remote dirs
    """
    try:
        command_handler = get_command_handler(ctx)
        command_handler.cp_with_options(
            sources=sources,
            recursive=recursive,
            treat_as_file=treat_as_file,
            target_directory=target_directory,
        )
    except Exception as e:
        logging.error(f"cp command failed: {e}")
        if ctx.obj.get("verbose"):
            raise
        click.echo(f"cp: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("sources", nargs=-1, required=True)
@click.option(
    "-f",
    "--force",
    is_flag=True,
    help="do not raise an error if the destination file already exists",
)
@click.option(
    "-u",
    "--update",
    is_flag=True,
    help="move only when SOURCE is newer than destination or "
    "destination is missing",
)
@click.option(
    "-t", "--target-directory", help="move all SOURCE arguments into DIRECTORY"
)
@click.pass_context
def mv(
    ctx,
    sources: tuple,
    force: bool,
    update: bool,
    target_directory: str,
) -> None:
    """Move contents from one location to another. Mimic Linux mv command.

    Usage:
    drobo <app name> mv [options] SOURCE ... DEST
    drobo <app name> mv [options] -t DIRECTORY SOURCE ...

    Remote paths begin with //, local paths follow Linux conventions.
    Wildcards (*,?) are supported in SOURCE paths.
    All SOURCE files must be either remote or local (cannot mix).

    Examples:
    drobo myapp mv ~/file1 //file2      Move local file to remote
    drobo myapp mv //file1 ~/file2      Move remote file to local
    drobo myapp mv //file1 //file2      Move remote file to remote
    drobo myapp mv //subdir/*.pdf .     Move remote PDFs to current dir
    drobo myapp mv -t //dest //src1 //src2   Move multiple files to dest
    drobo myapp mv -f //file1 //file2   Force move even if file2 exists
    drobo myapp mv -u //file1 //file2   Move only if file1 is newer
    """
    try:
        command_handler = get_command_handler(ctx)
        command_handler.mv_with_options(
            sources=sources,
            force=force,
            update=update,
            target_directory=target_directory,
        )
    except Exception as e:
        logging.error(f"mv command failed: {e}")
        if ctx.obj.get("verbose"):
            raise
        click.echo(f"mv: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("sources", nargs=-1, required=True)
@click.option(
    "-f",
    "--force",
    is_flag=True,
    help="ignore nonexistent files and arguments, never prompt",
)
@click.option(
    "-r",
    "--recursive",
    is_flag=True,
    help="remove directories and their contents recursively",
)
@click.pass_context
def rm(ctx, sources: tuple, force: bool, recursive: bool) -> None:
    """Remove remote files and folders. Mimic Linux rm command.

    Usage:
    drobo <app name> rm [options] FILE1 ...

    Remote paths begin with //. Only remote files can be removed.
    Wildcards (*,?) are supported in FILE paths.

    Examples:
    drobo myapp rm //file1              Remove remote file
    drobo myapp rm //file1 //file2      Remove multiple remote files
    drobo myapp rm //subdir/*.pdf       Remove remote PDFs using wildcard
    drobo myapp rm -f //file1 //file2   Force remove (ignore errors)
    drobo myapp rm -r //directory       Remove directory recursively
    drobo myapp rm -rf //directory      Force remove directory recursively
    """
    try:
        command_handler = get_command_handler(ctx)
        command_handler.rm_with_options(sources, force, recursive)
    except Exception as e:
        logging.error(f"rm command failed: {e}")
        if ctx.obj.get("verbose"):
            raise
        click.echo(f"rm: {e}", err=True)
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
