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
    level = logging.DEBUG if verbose else logging.INFO
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


@click.command()
@click.argument("app_name")
@click.argument("command", type=click.Choice(["ls", "cp", "mv", "rm"]))
@click.argument("args", nargs=-1)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option(
    "--version",
    is_flag=True,
    expose_value=False,
    is_eager=True,
    callback=print_version,
    help="Show version and exit",
)
def cli(app_name: str, command: str, args: tuple, verbose: bool) -> None:
    """
    Drobo - A Dropbox CLI

    Usage: drobo <app name> <command> [options]

    App names are aliases configured in ~/.droborc
    """
    setup_logging(verbose)

    try:
        config_manager = ConfigManager()
        app_config = config_manager.get_app_config(app_name)

        if not app_config:
            click.echo(
                f"Error: App '{app_name}' not found in .droborc", err=True
            )
            sys.exit(1)

        # Setup the command handler
        command_handler = setup_commands(app_config, verbose)

        # Execute the command
        if command == "ls":
            command_handler.ls(args)
        elif command == "cp":
            command_handler.cp(args)
        elif command == "mv":
            command_handler.mv(args)
        elif command == "rm":
            command_handler.rm(args)

    except Exception as e:
        logging.error(f"Command failed: {e}")
        if verbose:
            raise
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
