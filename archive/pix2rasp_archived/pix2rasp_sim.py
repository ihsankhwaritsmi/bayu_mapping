import argparse
import asyncio
import re
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from pymavlink import mavutil
from rich.console import Console

# --- Conditional import for real GoPro library ---
try:
    from open_gopro import WiredGoPro
    from open_gopro.gopro_base import GoProBase
    from open_gopro.models import constants, proto
    from open_gopro.util import add_cli_args_and_parse, setup_logging
    GOPRO_LIB_AVAILABLE = True
except ImportError:
    GOPRO_LIB_AVAILABLE = False

console = Console()

# --- Shared state variable to control the photo-taking loop ---
take_photos = False
gopro_is_ready = False

# =================================================================
# 📸 MOCK GOPRO IMPLEMENTATION
# =================================================================

class MockHttpCommand:
    """A mock of the GoPro's HTTP command object."""
    def __init__(self):
        self._photo_taken = False

    async def load_preset_group(self, group):
        console.print(f"[green](Simulated)[/green] Set preset group to {group}")
        return SimpleNamespace(ok=True)

    async def get_media_list(self):
        console.print("[green](Simulated)[/green] Getting media list")
        if self._photo_taken:
            self._photo_taken = False
            # Simulate a new file appearing
            return SimpleNamespace(data=SimpleNamespace(files=[SimpleNamespace(filename=f"GOPR{datetime.now().second:04d}.JPG")]))
        return SimpleNamespace(data=SimpleNamespace(files=[SimpleNamespace(filename="GOPR0001.JPG")]))

    async def set_shutter(self, shutter):
        console.print(f"[green](Simulated)[/green] Set shutter to {shutter}")
        self._photo_taken = True
        return SimpleNamespace(ok=True)

    async def download_file(self, camera_file, local_file):
        console.print(f"[green](Simulated)[/green] Downloading {camera_file} to {local_file}")
        with open(local_file, "w") as f:
            f.write(f"This is a simulated image of {camera_file}.\n")
        await asyncio.sleep(0.1)

class MockGoPro:
    """A mock of the WiredGoPro class for simulation purposes."""
    def __init__(self, identifier):
        console.print(f"[yellow]Using Simulated GoPro (identifier: {identifier})[/yellow]")
        self.http_command = MockHttpCommand()

    async def __aenter__(self):
        console.print("[green](Simulated)[/green] GoPro connected.")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        console.print("[green](Simulated)[/green] GoPro disconnected.")

    async def close(self):
        pass

# =================================================================
# 🦾 GOPRO AND MAVLINK CONTROLLERS
# =================================================================

async def gopro_controller(args: argparse.Namespace, output_dir: Path):
    """Manages connection to the GoPro (real or simulated) and takes photos."""
    global take_photos, gopro_is_ready
    GoProDevice = WiredGoPro if args.use_real_gopro else MockGoPro

    while True:
        try:
            async with GoProDevice(args.identifier) as gopro:
                console.print("📸 GoPro Initialized!")
                # In simulation, we assume it's always ready. For real GoPro, check command success.
                is_ready_to_start = False
                if args.use_real_gopro:
                     if (await gopro.http_command.load_preset_group(group=proto.EnumPresetGroup.PRESET_GROUP_ID_PHOTO)).ok:
                         is_ready_to_start = True
                else:
                    is_ready_to_start = True

                if is_ready_to_start:
                    console.print("✅ GoPro is in Photo Mode.")
                    gopro_is_ready = True
                else:
                    console.print("[red]Failed to set GoPro to photo mode.[/red]")
                    gopro_is_ready = False
                    await asyncio.sleep(10)
                    continue

                while True:
                    if take_photos:
                        console.print("\nCapturing a photo...")
                        media_list_before = await gopro.http_command.get_media_list()
                        media_set_before = set(f.filename for f in media_list_before.data.files)

                        shutter_command = getattr(constants, 'Toggle', SimpleNamespace(ENABLE=1)).ENABLE
                        assert (await gopro.http_command.set_shutter(shutter=shutter_command)).ok

                        new_photos = set()
                        for _ in range(5): # Retry for 2.5 seconds
                            await asyncio.sleep(0.5)
                            media_list_after = await gopro.http_command.get_media_list()
                            media_set_after = set(f.filename for f in media_list_after.data.files)
                            new_photos = media_set_after.difference(media_set_before)
                            if new_photos:
                                break

                        if not new_photos:
                            console.print("[red]Could not find new photo after capture.[/red]")
                            continue

                        new_photo_name = new_photos.pop()
                        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                        output_file = output_dir / f"{timestamp}_{new_photo_name}"

                        console.print(f"Downloading {new_photo_name}...")
                        await gopro.http_command.download_file(camera_file=new_photo_name, local_file=output_file)
                        console.print(f"✅ Success! File downloaded to {output_file.absolute()}")

                        await asyncio.sleep(3)
                    else:
                        await asyncio.sleep(0.5)
        except Exception as e:
            console.print(f"[bold red]GoPro Controller Error: {repr(e)}. Retrying in 10 seconds...[/bold red]")
            gopro_is_ready = False
            await asyncio.sleep(10)

async def mavlink_listener(connection_string: str):
    """Listens for MAVLink messages and toggles the photo-taking state."""
    global take_photos, gopro_is_ready

    while True:
        try:
            master = None
            if connection_string.startswith('tcp:'):
                console.print(f"📡 Connecting to MAVLink via TCP at {connection_string}...")
                master = mavutil.mavlink_connection(connection_string)
            elif ':' in connection_string:
                device, baud_rate = connection_string.split(':')
                console.print(f"📡 Connecting to MAVLink via Serial at {device} (Baud: {baud_rate})...")
                master = mavutil.mavlink_connection(device, baud=int(baud_rate))
            else:
                # Default to serial with a standard baud if no baud is specified
                console.print(f"📡 Connecting to MAVLink via Serial at {connection_string} (Baud: 57600)...")
                master = mavutil.mavlink_connection(connection_string, baud=57600)

            master.wait_heartbeat()
            console.print(f"✅ MAVLink Heartbeat received from System ID: {master.target_system}")

            while True:
                msg = master.recv_match(type="STATUSTEXT", blocking=False)
                if msg:
                    message_text = msg.text.strip()
                    if "DigiCamCtrl" in message_text:
                        # If a mission complete message is received, stop taking photos.
                        if take_photos:
                            take_photos = False
                            console.print(f"\n\n{'='*50}\n⏹️⏹️⏹️ [bold blue]STOPPING[/bold blue] Photo Capture due to DigiCamCtrl command.\n{'='*50}\n")
                        console.print(f"\n\n{'='*50}\n🎉 [bold magenta]Mission Complete: 'DigiCamCtrl' detected.[/bold magenta]\n{'='*50}\n")

                    elif "SetCamTrigDst" in message_text:
                        if not gopro_is_ready:
                            console.print("[yellow]MAVLink trigger detected, but GoPro is not ready.[/yellow]")
                            continue

                        # Toggle photo capture state
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
    """Main function to run MAVLink listener and GoPro controller concurrently."""
    if GOPRO_LIB_AVAILABLE and args.use_real_gopro:
        setup_logging(__name__, args.log)

    output_dir = Path("gopro_captures")
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        await asyncio.gather(
            mavlink_listener(args.connect),
            gopro_controller(args, output_dir),
        )
    except KeyboardInterrupt:
        console.print("\nExiting program by user command.")
    except Exception as e:
        console.print(f"\nAn unexpected error occurred: {repr(e)}")

def entrypoint():
    """The main program entrypoint."""
    parser = argparse.ArgumentParser(description="Toggle GoPro photo capture based on MAVLink messages.")
    parser.add_argument(
        '--connect',
        type=str,
        default='tcp:127.0.0.1:5762',
        help="MAVLink connection string. Formats: 'tcp:HOST:PORT' or 'DEVICE:BAUDRATE' (e.g., /dev/ttyACM0:115200)."
    )
    parser.add_argument(
        "--use-real-gopro",
        action="store_true",
        help="Use the actual open-gopro library to connect to a real GoPro. Requires the library to be installed."
    )

    args, unknown = parser.parse_known_args()

    if args.use_real_gopro:
        if not GOPRO_LIB_AVAILABLE:
            console.print("[bold red]Error: --use-real-gopro flag was set, but 'open-gopro-lib' is not installed.[/bold red]")
            return
        # Let open-gopro parse its specific arguments
        gopro_parser = argparse.ArgumentParser()
        args = add_cli_args_and_parse(gopro_parser, [arg for arg in unknown if arg.startswith('--')])
        # Combine the arguments
        args.connect = parser.parse_args(unknown).connect
        args.use_real_gopro = True
    else:
        # Manually add necessary attributes for simulation mode
        if not hasattr(args, 'identifier'):
            args.identifier = "Simulated"
        if not hasattr(args, 'log'):
            args.log = None

    try:
        asyncio.run(main(args))
    except Exception as e:
        console.print(f"Failed to start asyncio event loop: {repr(e)}")


# =================================================================
# HOW TO RUN
# =================================================================
#
# Save the script as a Python file (e.g., pix2rasp_com.py) and run from your terminal.
#
# --- Examples ---
#
# 1. Simulated GoPro with Default TCP Connection (for SITL):
#    python pix2rasp_com.py
#
# 2. Simulated GoPro with Serial Connection (e.g., Raspberry Pi GPIO):
#    python pix2rasp_com.py --connect /dev/ttyAMA0:57600
#
# 3. Simulated GoPro with USB Serial Connection:
#    python pix2rasp_com.py --connect /dev/ttyACM0:115200
#
# 4. Real GoPro with TCP Connection:
#    (Requires 'open-gopro-lib' to be installed)
#    python pix2rasp_com.py --use-real-gopro --connect tcp:127.0.0.1:5762
#
# 5. Real GoPro with Serial Connection:
#    (Requires 'open-gopro-lib' to be installed)
#    python pix2rasp_com.py --use-real-gopro --connect /dev/ttyAMA0:57600
#
if __name__ == "__main__":
    entrypoint()
