import argparse
import asyncio
import re
from datetime import datetime
from pathlib import Path

from pymavlink import mavutil
from rich.console import Console

from open_gopro import WiredGoPro
from open_gopro.gopro_base import GoProBase
from open_gopro.models import constants, proto
from open_gopro.util import add_cli_args_and_parse
from open_gopro.util.logger import setup_logging


console = Console()

# --- Shared state to control the photo-taking loop ---
take_photos = False
gopro_is_ready = False


async def gopro_controller(args: argparse.Namespace, output_dir: Path):
    """Manages GoPro connection and takes photos when enabled."""
    global take_photos, gopro_is_ready
    gopro: GoProBase | None = None

    # Outer loop to handle reconnections
    while True:
        try:
            # Establish a wired connection
            async with WiredGoPro(args.identifier) as gopro:
                console.print("📸 GoPro Connected!")

                # Set camera to photo mode
                response = await gopro.http_command.load_preset_group(
                    group=proto.EnumPresetGroup.PRESET_GROUP_ID_PHOTO
                )
                if not response.ok:
                    raise RuntimeError("Failed to set GoPro to Photo Mode.")

                console.print("✅ GoPro is in Photo Mode.")
                gopro_is_ready = True

                # --- Photo-taking loop ---
                while True:
                    if take_photos:
                        console.print("\nCapturing a photo...")

                        media_list_before = await gopro.http_command.get_media_list()
                        if not media_list_before.ok:
                            console.print("[red]Could not get media list before capture.[/red]")
                            await asyncio.sleep(1)
                            continue
                        media_set_before = {f.filename for f in media_list_before.data.files}

                        # Take a photo
                        shutter_response = await gopro.http_command.set_shutter(
                            shutter=constants.Toggle.ENABLE
                        )
                        if not shutter_response.ok:
                            console.print("[red]Failed to trigger shutter. Will try again.[/red]")
                            await asyncio.sleep(3)
                            continue

                        # Find the new photo by comparing media lists
                        new_photo_name = None
                        for _ in range(5):  # Retry 5 times
                            media_list_after = await gopro.http_command.get_media_list()
                            if media_list_after.ok:
                                media_set_after = {f.filename for f in media_list_after.data.files}
                                new_photos = media_set_after.difference(media_set_before)
                                if new_photos:
                                    new_photo_name = new_photos.pop()
                                    break
                            await asyncio.sleep(0.5)

                        if not new_photo_name:
                            console.print("[red]Could not find new photo after capture.[/red]")
                            continue

                        # MODIFIED: Generate filename using only a new timestamp and the file extension,
                        # mirroring the logic from the video.py example.
                        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                        file_extension = Path(new_photo_name).suffix
                        output_file = output_dir / f"{timestamp}{file_extension}"

                        # Download the photo
                        console.print(f"Downloading {new_photo_name} to {output_file.name}...")
                        await gopro.http_command.download_file(
                            camera_file=new_photo_name, local_file=output_file
                        )
                        console.print(f"✅ Success! File downloaded to {output_file.absolute()}")

                        await asyncio.sleep(3)
                    else:
                        await asyncio.sleep(0.5)

        except Exception as e:
            console.print(f"[bold red]GoPro Error: {repr(e)}. Retrying in 10 seconds...[/bold red]")
            gopro_is_ready = False
            if gopro:
                await gopro.close()
            await asyncio.sleep(10)


async def mavlink_listener(connection_string: str):
    """Listens for MAVLink messages and toggles the photo-taking state."""
    global take_photos, gopro_is_ready

    # Outer loop for handling MAVLink reconnections
    while True:
        try:
            # Connect to the vehicle based on the connection string format
            master = None
            if connection_string.startswith('tcp:'):
                console.print(f"📡 Connecting to MAVLink via TCP at {connection_string}...")
                master = mavutil.mavlink_connection(connection_string)
            else:
                device, baud_rate = connection_string.split(':')
                console.print(f"📡 Connecting to MAVLink via Serial at {device} (Baud: {baud_rate})...")
                master = mavutil.mavlink_connection(device, baud=int(baud_rate))

            master.wait_heartbeat()
            console.print(f"✅ MAVLink Heartbeat received from System ID: {master.target_system}")

            # --- MAVLink message listening loop ---
            while True:
                msg = master.recv_match(type="STATUSTEXT", blocking=False)
                if msg:
                    message_text = msg.text.strip()

                    # Check for mission completion command
                    if "DigiCamCtrl" in message_text:
                        if take_photos:
                            take_photos = False
                            console.print(f"\n\n{'='*50}\n⏹️⏹️⏹️ [bold blue]STOPPING[/bold blue] Photo Capture due to DigiCamCtrl command.\n{'='*50}\n")
                        console.print(f"\n\n{'='*50}\n🎉 [bold magenta]Mission Complete: 'DigiCamCtrl' detected.[/bold magenta]\n{'='*50}\n")

                    # Check for the camera trigger command
                    elif "SetCamTrigDst" in message_text:
                        if not gopro_is_ready:
                            console.print("[yellow]MAVLink trigger detected, but GoPro is not ready. Please wait.[/yellow]")
                            continue

                        # Toggle the photo-taking state
                        take_photos = not take_photos
                        match = re.search(r"Mission: (\d+) SetCamTrigDst", message_text)
                        waypoint_num = match.group(1) if match else "N/A"

                        if take_photos:
                            console.print(f"\n\n{'='*50}\n▶️▶️▶️ [bold green]STARTING[/bold green] Photo Capture (Waypoint #{waypoint_num})!\n{'='*50}\n")
                        else:
                            console.print(f"\n\n{'='*50}\n⏹️⏹️⏹️ [bold red]STOPPING[/bold red] Photo Capture (Waypoint #{waypoint_num})!\n{'='*50}\n")

                await asyncio.sleep(0.1)

        except Exception as e:
            console.print(f"[bold red]MAVLink connection error: {repr(e)}. Retrying in 10 seconds...[/bold red]")
            await asyncio.sleep(10)


async def main(args: argparse.Namespace):
    """Run MAVLink listener and GoPro controller concurrently."""
    setup_logging(__name__, args.log)

    output_dir = args.output
    output_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"📸 Photos will be saved to: {output_dir.absolute()}")

    # --- MAVLink Configuration ---
    # connection_string = "tcp:127.0.0.1:5762"
    connection_string = "/dev/ttyAMA0:57600"

    try:
        await asyncio.gather(
            mavlink_listener(connection_string),
            gopro_controller(args, output_dir),
        )
    except KeyboardInterrupt:
        console.print("\nExiting program by user command.")
    except Exception as e:
        console.print(f"\nAn unexpected error occurred: {repr(e)}")


def entrypoint():
    """Main program entrypoint."""
    parser = argparse.ArgumentParser(
        description="Connect to a GoPro and a MAVLink vehicle and toggle photo capture based on MAVLink messages."
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Directory to save downloaded photos. Defaults to 'gopro_captures'.",
        default=Path("gopro_captures"),
    )
    args = add_cli_args_and_parse(parser)

    try:
        asyncio.run(main(args))
    except Exception as e:
        console.print(f"Failed to start asyncio event loop: {repr(e)}")


if __name__ == "__main__":
    entrypoint()