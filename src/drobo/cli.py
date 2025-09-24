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
    level = logging.DEBUG if verbose else logging.WARN
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
    "-a",
    "--all",
    "show_all",
    is_flag=True,
    help="do not ignore entries starting with '.'",
)
@click.option(
    "-d",
    "--directory",
    is_flag=True,
    help="list directories themselves, not their contents",
)
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
    show_all: bool,
    directory: bool,
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
            show_all=show_all,
            directory=directory,
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
@click.argument("args", nargs=-1)
@click.pass_context
def cp(ctx, args: tuple) -> None:
    """Copy contents from one location to another. Mimic Linux cp command."""
    try:
        command_handler = get_command_handler(ctx)
        command_handler.cp(args)
    except Exception as e:
        logging.error(f"cp command failed: {e}")
        if ctx.obj.get("verbose"):
            raise
        click.echo(f"cp: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("args", nargs=-1)
@click.pass_context
def mv(ctx, args: tuple) -> None:
    """Move contents from one location to another. Mimic Linux mv command."""
    try:
        command_handler = get_command_handler(ctx)
        command_handler.mv(args)
    except Exception as e:
        logging.error(f"mv command failed: {e}")
        if ctx.obj.get("verbose"):
            raise
        click.echo(f"mv: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("args", nargs=-1)
@click.pass_context
def rm(ctx, args: tuple) -> None:
    """Remove remote files and folders. Mimic Linux rm command."""
    try:
        command_handler = get_command_handler(ctx)
        command_handler.rm(args)
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
