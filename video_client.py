# video.py/Open GoPro, Version 2.0 (C) Copyright 2021 GoPro, Inc. (http://gopro.com/OpenGoPro).
# This copyright was auto-generated on Wed, Sep  1, 2021  5:05:46 PM

"""
Entrypoint for taking a video with manual start/stop, sending it to a server,
and using a wired connection.
"""

import argparse
import asyncio
from pathlib import Path
import sys
from datetime import datetime
import requests # Make sure to install this: pip install requests
import os

from rich.console import Console

from open_gopro import WiredGoPro
from open_gopro.models import constants, proto
from open_gopro.util import add_cli_args_and_parse
from open_gopro.util.logger import setup_logging

console = Console()

# IMPORTANT: Replace with the public IP address of your AWS server
SERVER_URL = "http://YOUR_AWS_IP_HERE:5000/upload"


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
    # Construct the full output path
    output_path_mp4 = output_dir / f"{timestamp}.mp4"
    output_path_gpmf = output_dir / f"{timestamp}.gpmf"

    try:
        # Exclusively use WiredGoPro for the connection
        async with WiredGoPro(args.identifier) as gopro:
            assert gopro
            # Load the video preset
            assert (await gopro.http_command.load_preset_group(group=proto.EnumPresetGroup.PRESET_GROUP_ID_VIDEO)).ok

            # Get the media list before taking the video
            media_set_before = set((await gopro.http_command.get_media_list()).data.files)

            # Wait for the user to start recording
            console.print("\nPress [bold]Enter[/bold] to begin recording.", style="bold yellow")
            await asyncio.to_thread(sys.stdin.readline)

            # Start recording
            console.print("✅ Recording started! Press [bold]Enter[/bold] again to stop.", style="bold green")
            assert (await gopro.http_command.set_shutter(shutter=constants.Toggle.ENABLE)).ok

            # Wait for the user to stop recording
            await asyncio.to_thread(sys.stdin.readline)
            
            console.print("⏹️ Recording stopped!", style="bold green")
            assert (await gopro.http_command.set_shutter(shutter=constants.Toggle.DISABLE)).ok

            # Get the media list after taking the video
            console.print("Getting updated media list...")
            await asyncio.sleep(2) # Delay to ensure media list is updated
            media_set_after = set((await gopro.http_command.get_media_list()).data.files)
            
            try:
                video = media_set_after.difference(media_set_before).pop()
            except KeyError:
                console.print("[bold red]No new video was found on the camera.[/bold red]")
                return

            # Download the video and its GPMF data
            console.print(f"Downloading {video.filename}...")
            await gopro.http_command.download_file(
                camera_file=video.filename, local_file=output_path_mp4
            )
            await gopro.http_command.get_gpmf_data(
                camera_file=video.filename, local_file=output_path_gpmf
            )
            console.print(f"Download complete: '{output_path_mp4.name}'")

            # Send the video file to the server
            console.print(f"Uploading {output_path_mp4.name} to server at {SERVER_URL}...")
            try:
                with open(output_path_mp4, 'rb') as f:
                    files = {'file': (output_path_mp4.name, f, 'video/mp4')}
                    response = requests.post(SERVER_URL, files=files, timeout=60)
                
                if response.status_code == 200:
                    console.print("✅ Upload successful!", style="bold green")
                else:
                    console.print(f"[bold red]Upload failed. Server responded with status: {response.status_code}[/bold red]")
                    console.print(f"Response body: {response.text}")

            except requests.exceptions.RequestException as e:
                console.print(f"[bold red]An error occurred while sending the file: {e}[/bold red]")
            finally:
                # Clean up local files
                console.print("Cleaning up local files...")
                if os.path.exists(output_path_mp4):
                    os.remove(output_path_mp4)
                if os.path.exists(output_path_gpmf):
                    os.remove(output_path_gpmf)


    except Exception as e:  # pylint: disable = broad-except
        logger.error(repr(e))
    finally:
        if gopro:
            await gopro.close()
        console.print("Exiting...")


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Connect to a GoPro, record a video, and send it to a server.")
    return add_cli_args_and_parse(parser)


def entrypoint() -> None:
    """Entrypoint for poetry script."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main(parse_arguments()))


if __name__ == "__main__":
    entrypoint()
