# photo.py/Open GoPro, Version 2.0 (C) Copyright 2021 GoPro, Inc. (http://gopro.com/OpenGoPro).
# This copyright was auto-generated on Wed, Sep  1, 2021  5:05:45 PM

"""Entrypoint for taking a picture via a wired connection."""

import argparse
import asyncio
from pathlib import Path

from rich.console import Console

from open_gopro import WiredGoPro
from open_gopro.gopro_base import GoProBase
from open_gopro.models import constants, proto
from open_gopro.util import add_cli_args_and_parse
from open_gopro.util.logger import setup_logging

console = Console()


async def main(args: argparse.Namespace) -> None:
    """The main async event loop."""
    logger = setup_logging(__name__, args.log)
    gopro: GoProBase | None = None

    try:
        # Establish a wired connection to the GoPro
        async with WiredGoPro(args.identifier) as gopro:
            # Ensure the camera is in photo mode
            assert (await gopro.http_command.load_preset_group(group=proto.EnumPresetGroup.PRESET_GROUP_ID_PHOTO)).ok

            # Get the list of media files before taking the photo
            media_set_before = set((await gopro.http_command.get_media_list()).data.files)

            # Take a photo
            console.print("Capturing a photo...")
            assert (await gopro.http_command.set_shutter(shutter=constants.Toggle.ENABLE)).ok

            # Get the media list again to find the new photo
            media_set_after = set((await gopro.http_command.get_media_list()).data.files)
            # The new photo is the difference between the two media lists
            new_photo = media_set_after.difference(media_set_before).pop()

            # Download the newly captured photo
            console.print(f"Downloading {new_photo.filename}...")
            await gopro.http_command.download_file(camera_file=new_photo.filename, local_file=args.output)
            console.print(f"Success! :smiley: File has been downloaded to {Path(args.output).absolute()}")

    except Exception as e:  # pylint: disable = broad-except
        logger.error(repr(e))

    # Ensure the connection is closed
    if gopro:
        await gopro.close()


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Connect to a GoPro via USB, take a photo, and download it.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Where to write the photo. Defaults to 'photo.jpg'.",
        default=Path("photo.jpg"),
    )
    # The add_cli_args_and_parse function adds other relevant arguments like --identifier
    return add_cli_args_and_parse(parser)


def entrypoint() -> None:
    """The main program entrypoint."""
    asyncio.run(main(parse_arguments()))


if __name__ == "__main__":
    entrypoint()