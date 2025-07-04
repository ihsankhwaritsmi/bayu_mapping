# mavlink_gopro_trigger.py
# Integrates OpenGoPro with PyMAVLink to trigger a wired GoPro from a Pixhawk.
# TO RUN THIS THING :

# For USB connection
# python mavlink_gopro_trigger.py --connect /dev/ttyACM0 --baud 115200

# For RXTX UART connection
# python mavlink_gopro_trigger.py --connect /dev/ttyAMA0 --baud 57600


import argparse
import asyncio
import threading
from datetime import datetime
from pathlib import Path

from rich.console import Console
from pymavlink import mavutil

from open_gopro import WiredGoPro
from open_gopro.gopro_base import GoProBase
from open_gopro.models import constants, proto
from open_gopro.util import add_cli_args_and_parse, setup_logging

console = Console()

# --- GoPro Control Functions ---

async def take_photo(gopro: GoProBase, output_dir: Path) -> None:
    """
    Commands the GoPro to capture and download a photo.

    Args:
        gopro (GoProBase): The connected GoPro instance.
        output_dir (Path): The directory to save the photo in.
    """
    try:
        console.print("[yellow]📸 Trigger received! Taking a photo...[/yellow]")
        # Get media list before taking photo
        media_set_before = set((await gopro.http_command.get_media_list()).data.files)

        # Take a photo
        assert (await gopro.http_command.set_shutter(shutter=constants.Toggle.ENABLE)).ok

        # Get media list after to find the new photo
        media_set_after = set((await gopro.http_command.get_media_list()).data.files)
        new_photo = media_set_after.difference(media_set_before).pop()

        # Generate a timestamped filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_file = output_dir / f"{timestamp}.jpg"

        # Download the newly captured photo
        console.print(f"[cyan]   Downloading {new_photo.filename}...[/cyan]")
        await gopro.http_command.download_file(camera_file=new_photo.filename, local_file=output_file)
        console.print(f"[green]   ✅ Success! Photo saved to {output_file.absolute()}[/green]")

    except Exception as e:
        console.print(f"[red]   🔥 GoPro photo capture/download failed: {e}[/red]")


# --- MAVLink Communication ---

def mavlink_listener(
    mav_connection: mavutil.mavlink_connection,
    gopro: GoProBase,
    output_dir: Path,
    loop: asyncio.AbstractEventLoop,
    stop_event: threading.Event,
) -> None:
    """
    Listens for MAVLink messages in a blocking manner and triggers GoPro.
    This function is designed to be run in a separate thread.
    """
    console.print("[bold blue]MAVLink listener thread started. Waiting for triggers...[/bold blue]")
    while not stop_event.is_set():
        # Wait for a command or mission finished message. Using a timeout allows checking the stop_event.
        msg = mav_connection.recv_match(
            type=["COMMAND_LONG", "MISSION_FINISHED"], blocking=True, timeout=1
        )
        if not msg:
            continue

        msg_type = msg.get_type()
        console.print(f"\n[blue]MAVLink message received: {msg_type}[/blue]")

        # Stop condition: Mission has ended
        if msg_type == "MISSION_FINISHED":
            console.print("[bold red]Mission finished message received. Stopping...[/bold red]")
            stop_event.set()
            break

        # Handle commands
        if msg_type == "COMMAND_LONG":
            # Trigger condition: DO_SET_CAM_TRIGG_DIST
            if msg.command == mavutil.mavlink.MAV_CMD_DO_SET_CAM_TRIGG_DIST:
                # Schedule the async take_photo function to run on the main event loop
                asyncio.run_coroutine_threadsafe(take_photo(gopro, output_dir), loop)

            # Stop condition: IMAGE_STOP_CAPTURE
            elif msg.command == mavutil.mavlink.MAV_CMD_IMAGE_STOP_CAPTURE:
                console.print("[bold red]Image stop capture command received. Stopping...[/bold red]")
                stop_event.set()
                break
    console.print("[bold blue]MAVLink listener thread finished.[/bold blue]")


# --- Main Application ---

async def main(args: argparse.Namespace) -> None:
    """The main async event loop."""
    logger = setup_logging(__name__, args.log)
    gopro: GoProBase | None = None
    stop_event = threading.Event()

    # Define and create the output directory
    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Establish MAVLink Connection
        console.print(f"Connecting to Pixhawk at {args.connect}...")
        mav_connection = mavutil.mavlink_connection(args.connect, baud=args.baud)
        mav_connection.wait_heartbeat()
        console.print("[bold green]✅ Pixhawk connection successful! System ID: {}, Component ID: {}[/bold green]".format(
            mav_connection.target_system, mav_connection.target_component))
            
        # Establish Wired GoPro Connection
        console.print("Connecting to GoPro via USB...")
        async with WiredGoPro(args.identifier) as gopro:
            console.print("[bold green]✅ GoPro connection successful![/bold green]")
            # Load photo preset
            await gopro.http_command.load_preset_group(group=proto.EnumPresetGroup.PRESET_GROUP_ID_PHOTO)
            
            # Start the MAVLink listener in a background thread
            loop = asyncio.get_running_loop()
            listener_thread = threading.Thread(
                target=mavlink_listener,
                args=(mav_connection, gopro, output_dir, loop, stop_event),
                daemon=True,
            )
            listener_thread.start()

            # Keep the main async task running until the stop event is set
            while not stop_event.is_set():
                await asyncio.sleep(1)
            
            # Wait for the listener thread to finish
            listener_thread.join()

    except Exception as e:
        logger.error(repr(e))
        console.print(f"[bold red]An error occurred: {repr(e)}[/bold red]")
        stop_event.set() # Ensure listener thread exits on error
    finally:
        console.print("Closing connections...")
        if gopro and gopro.is_open:
            await gopro.close()
        console.print("Script finished.")


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Connect to a GoPro and Pixhawk. Trigger photos based on MAVLink commands."
    )
    parser.add_argument(
        "--connect",
        type=str,
        help="MAVLink connection string (e.g., '/dev/ttyAMA0' for serial, 'udp:127.0.0.1:14550' for UDP)",
        required=True,
    )
    parser.add_argument(
        "--baud",
        type=int,
        help="MAVLink connection baud rate (for serial connections)",
        default=57600,
    )
    return add_cli_args_and_parse(parser)


def entrypoint() -> None:
    """The main program entrypoint."""
    try:
        asyncio.run(main(parse_arguments()))
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Script interrupted by user. Exiting.[/bold yellow]")


if __name__ == "__main__":
    entrypoint()