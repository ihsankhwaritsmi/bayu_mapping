import asyncio
import re
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from pymavlink import mavutil
from rich.console import Console

console = Console()

FLAG_FILE_EXTENSION = "flag"

async def create_flag_file(output_dir: Path):
    """Create a flag file to indicate mission completion."""
    # Create a unique flag file name with the .flag extension
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    flag_file_name = f"mission_completed_{timestamp}.{FLAG_FILE_EXTENSION}"
    flag_file_path = output_dir / flag_file_name
    try:
        flag_file_path.touch()
        console.print(f"[bold green]Created flag file: {flag_file_path.absolute()}[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Failed to create flag file: {repr(e)}[/bold red]")

# --- Shared state variable to control the photo-taking loop ---
take_photos = False
gopro_is_ready = False

# =================================================================
# SIMULATED GOPRO
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
# GOPRO AND MAVLINK CONTROLLERS
# =================================================================

async def gopro_controller(output_dir: Path):
    """Manages connection to the simulated GoPro and takes photos."""
    global take_photos, gopro_is_ready
    GoProDevice = MockGoPro

    while True:
        try:
            async with GoProDevice("Simulated") as gopro:
                console.print("📸 GoPro Initialized!")
                gopro_is_ready = True
                console.print("✅ GoPro is in Photo Mode.")

                while True:
                    if take_photos:
                        console.print("\nCapturing a photo...")
                        media_list_before = await gopro.http_command.get_media_list()
                        media_set_before = set(f.filename for f in media_list_before.data.files)

                        shutter_command = 1
                        assert (await gopro.http_command.set_shutter(shutter=shutter_command)).ok

                        new_photos = set()
                        for _ in range(5):  # Retry for 2.5 seconds
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

async def mavlink_listener(connection_string: str, output_dir):
    """Listens for MAVLink messages and toggles the photo-taking state."""
    global take_photos, gopro_is_ready

    while True:
        try:
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

            while True:
                msg = master.recv_match(type="STATUSTEXT", blocking=False)
                if msg:
                    message_text = msg.text.strip()
                    if "DigiCamCtrl" in message_text:
                        if take_photos:
                            take_photos = False
                            console.print(f"\n\n{'='*50}\n⏹️⏹️⏹️ [bold blue]STOPPING[/bold blue] Photo Capture due to DigiCamCtrl command.\n{'='*50}\n")
                        console.print(f"\n\n{'='*50}\n🎉 [bold magenta]Mission Complete: 'DigiCamCtrl' detected.[/bold magenta]\n{'='*50}\n")
                        await create_flag_file(output_dir) # Call to create flag file
                    elif "SetCamTrigDst" in message_text:
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
            console.print(f"[bold red]MAVLink connection error: {repr(e)}. Retrying in 10 seconds...[/bold red]")
            await asyncio.sleep(10)

async def main():
    """Main function to run MAVLink listener and GoPro controller concurrently."""
    # --- Configuration ---

    connection_string = 'tcp:127.0.0.1:5762'
    
    output_dir = Path("gopro_captures")
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        await asyncio.gather(
            mavlink_listener(connection_string, output_dir),
            gopro_controller(output_dir),
        )
    except KeyboardInterrupt:
        console.print("\nExiting program by user command.")
    except Exception as e:
        console.print(f"\nAn unexpected error occurred: {repr(e)}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        console.print(f"Failed to start asyncio event loop: {repr(e)}")
