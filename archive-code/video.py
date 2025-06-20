# video.py/Open GoPro, Version 2.0 (C) Copyright 2021 GoPro, Inc. (http://gopro.com/OpenGoPro).
# This copyright was auto-generated on Wed, Sep  1, 2021  5:05:46 PM

"""Entrypoint for taking a video demo with manual start/stop controls using a wired connection."""

import argparse
import asyncio
from pathlib import Path
import sys
from datetime import datetime

from rich.console import Console

from open_gopro import WiredGoPro
from open_gopro.models import constants, proto
from open_gopro.util import add_cli_args_and_parse
from open_gopro.util.logger import setup_logging

console = Console()


async def main(args: argparse.Namespace) -> None:
    """The main async event loop.

    Args:
        args: command-line arguments
    """
    logger = setup_logging(__name__, args.log)
    gopro: WiredGoPro | None = None

    # Generate a timestamp-based filename
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    # Define the output directory as 'output'
    output_dir = Path("output")
    # Ensure the output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)
    # Construct the full output path (without a suffix)
    output_path = output_dir / timestamp

    try:
        # Exclusively use WiredGoPro for the connection
        async with WiredGoPro(args.identifier) as gopro:
            assert gopro
            # Load the video preset
            assert (await gopro.http_command.load_preset_group(group=proto.EnumPresetGroup.PRESET_GROUP_ID_VIDEO)).ok

            # Get the media list before taking the video
            media_set_before = set((await gopro.http_command.get_media_list()).data.files)

            # Wait for the user to start recording
            console.print("\nType 'start' and press Enter to begin recording.", style="bold yellow")
            while True:
                # Run blocking input in a separate thread to not block asyncio event loop
                command = await asyncio.to_thread(sys.stdin.readline)
                if command.strip().lower() == 'start':
                    break
                console.print("Invalid command. Please type 'start' to begin.", style="bold red")

            # Start recording
            console.print("✅ Recording started!", style="bold green")
            assert (await gopro.http_command.set_shutter(shutter=constants.Toggle.ENABLE)).ok

            # Wait for the user to stop recording
            console.print("Type 'stop' and press Enter to end recording.", style="bold yellow")
            while True:
                command = await asyncio.to_thread(sys.stdin.readline)
                if command.strip().lower() == 'stop':
                    break
                console.print("Invalid command. Please type 'stop' to end recording.", style="bold red")
            
            console.print("⏹️ Recording stopped!", style="bold green")
            assert (await gopro.http_command.set_shutter(shutter=constants.Toggle.DISABLE)).ok

            # Get the media list after taking the video
            console.print("Getting updated media list...")
            # Add a small delay to ensure the media list is updated on the camera
            await asyncio.sleep(2)
            media_set_after = set((await gopro.http_command.get_media_list()).data.files)
            # The new video is (most likely) the difference between the two media lists
            try:
                video = media_set_after.difference(media_set_before).pop()
            except KeyError:
                console.print("[bold red]No new video was found on the camera.[/bold red]")
                return


            # Download the video and its GPMF data
            console.print(f"Downloading {video.filename}...")
            await gopro.http_command.download_file(
                camera_file=video.filename, local_file=output_path.with_suffix(".mp4")
            )
            await gopro.http_command.get_gpmf_data(
                camera_file=video.filename, local_file=output_path.with_suffix(".gpmf")
            )
            console.print(f"Success!! :smiley: Files have been downloaded to '{output_path.with_suffix('.mp4')}'")
    except Exception as e:  # pylint: disable = broad-except
        logger.error(repr(e))
    finally:
        if gopro:
            await gopro.close()
        console.print("Exiting...")


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        argparse.Namespace: parsed arguments
    """
    parser = argparse.ArgumentParser(description="Connect to a GoPro via USB, take a video with manual start/stop, then download it.")
    # The output directory argument has been removed.
    # Other arguments from the Open GoPro SDK can still be used (e.g., --identifier)
    return add_cli_args_and_parse(parser)


def entrypoint() -> None:
    """Entrypoint for poetry script."""
    # This is a workaround to prevent a NotImplementedError on Windows with Python 3.8+
    # See: https://github.com/aio-libs/aiohttp/issues/4324
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    asyncio.run(main(parse_arguments()))


if __name__ == "__main__":
    entrypoint()
