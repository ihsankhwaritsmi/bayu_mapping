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
    async def load_preset_group(self, group):
        console.print(f"[green](Simulated)[/green] Set preset group to {group}")
        # Return a simple object with an 'ok' attribute
        return SimpleNamespace(ok=True)

    async def get_media_list(self):
        console.print("[green](Simulated)[/green] Getting media list")
        # Return a mock response with a 'data' attribute that has 'files'
        # Simulate a new file appearing after a photo is taken
        if hasattr(self, '_photo_taken') and self._photo_taken:
            self._photo_taken = False
            return SimpleNamespace(data=SimpleNamespace(files=[SimpleNamespace(filename="GOPR0002.JPG")]))
        return SimpleNamespace(data=SimpleNamespace(files=[SimpleNamespace(filename="GOPR0001.JPG")]))

    async def set_shutter(self, shutter):
        console.print(f"[green](Simulated)[/green] Set shutter to {shutter}")
        self._photo_taken = True
        return SimpleNamespace(ok=True)

    async def download_file(self, camera_file, local_file):
        console.print(f"[green](Simulated)[/green] Downloading {camera_file} to {local_file}")
        # Simulate file creation
        with open(local_file, "w") as f:
            f.write("This is a simulated image.\n")
        await asyncio.sleep(0.1) # Simulate download time

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
        pass # No real connection to close

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
                if not args.use_real_gopro or (await gopro.http_command.load_preset_group(group=proto.EnumPresetGroup.PRESET_GROUP_ID_PHOTO)).ok:
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
                        media_set_before = set(f.filename for f in (await gopro.http_command.get_media_list()).data.files)

                        assert (await gopro.http_command.set_shutter(shutter=getattr(constants, 'Toggle', SimpleNamespace(ENABLE=1)).ENABLE)).ok

                        for _ in range(5):
                            media_set_after = set(f.filename for f in (await gopro.http_command.get_media_list()).data.files)
                            new_photos = media_set_after.difference(media_set_before)
                            if new_photos:
                                break
                            await asyncio.sleep(0.5)

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
            console.print(f"[bold red]GoPro Controller Error: {e}. Retrying in 10 seconds...[/bold red]")
            gopro_is_ready = False
            await asyncio.sleep(10)


async def mavlink_listener(connection_string: str):
    """Listens for MAVLink messages and toggles the photo-taking state."""
    global take_photos, gopro_is_ready

    while True:
        try:
            console.print(f"📡 Connecting to MAVLink at {connection_string}...")
            master = mavutil.mavlink_connection(connection_string)
            master.wait_heartbeat()
            console.print(f"✅ MAVLink Heartbeat received from System ID: {master.target_system}")

            while True:
                msg = master.recv_match(type="STATUSTEXT", blocking=False)
                if msg:
                    message_text = msg.text.strip()
                    if "SetCamTrigDst" in message_text:
                        if not gopro_is_ready:
                            console.print("[yellow]MAVLink trigger detected, but GoPro is not ready.[/yellow]")
                            continue

                        take_photos = not take_photos
                        match = re.search(r"Mission: (\d+) SetCamTrigDst", message_text)
                        waypoint_num = match.group(1) if match else "N/A"

                        if take_photos:
                            console.print(f"\n\n{'='*50}\n▶️▶️▶️ [bold green]STARTING[/bold green] Photo Capture (Waypoint #{waypoint_num})!\n{'='*50}\n")
                        else:
                            console.print(f"\n\n{'='*50}\n⏹️⏹️⏹️ [bold red]STOPPING[/bold red] Photo Capture (Waypoint #{waypoint_num})!\n{'='*50}\n")
                await asyncio.sleep(0.1)
        except Exception as e:
            console.print(f"[bold red]MAVLink connection error: {e}. Retrying in 10 seconds...[/bold red]")
            await asyncio.sleep(10)


async def main(args: argparse.Namespace):
    """Main function to run MAVLink listener and GoPro controller concurrently."""
    if GOPRO_LIB_AVAILABLE:
        setup_logging(__name__, args.log)

    output_dir = Path("gopro_captures")
    output_dir.mkdir(parents=True, exist_ok=True)
    connection_string = "tcp:127.0.0.1:5762"

    try:
        await asyncio.gather(
            mavlink_listener(connection_string),
            gopro_controller(args, output_dir),
        )
    except KeyboardInterrupt:
        console.print("\nExiting program by user command.")
    except Exception as e:
        console.print(f"\nAn unexpected error occurred: {e}")


def entrypoint():
    """The main program entrypoint."""
    parser = argparse.ArgumentParser(description="Toggle GoPro photo capture based on MAVLink messages.")
    parser.add_argument(
        "--use-real-gopro",
        action="store_true",
        help="Use the actual open-gopro library to connect to a real GoPro. Requires the library to be installed."
    )

    if GOPRO_LIB_AVAILABLE:
        # Add the usual open-gopro args only if the library is present
        args = add_cli_args_and_parse(parser)
    else:
        # If the library isn't installed, parse without the extra args
        console.print("[yellow]Warning: 'open-gopro-lib' not found. Running in simulation mode.[/yellow]")
        args = parser.parse_args()
        # Manually add necessary attributes if they are missing
        if not hasattr(args, 'identifier'):
            args.identifier = "Simulated"
        if not hasattr(args, 'log'):
            args.log = None

    if args.use_real_gopro and not GOPRO_LIB_AVAILABLE:
        console.print("[bold red]Error: --use-real-gopro flag was set, but 'open-gopro-lib' is not installed.[/bold red]")
        return

    try:
        asyncio.run(main(args))
    except Exception as e:
        console.print(f"Failed to start asyncio event loop: {e}")


if __name__ == "__main__":
    entrypoint()