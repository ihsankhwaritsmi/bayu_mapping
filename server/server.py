import socket
import threading
import os
import datetime
import glob
import time
import subprocess # Import the subprocess module
from rich.console import Console

HOST = '127.0.0.1'  # Standard loopback interface address (localhost)
PORT = 65432        # Port to listen on (non-privileged ports are > 1023)
# Get the directory where the script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(SCRIPT_DIR, 'datasets', 'project', 'images')
MAPPING_SCRIPT_PATH = os.path.join(SCRIPT_DIR, 'mapping_script.sh')

console = Console()

def handle_client(conn, addr):
    """Handles an individual client connection."""
    console.print(f"Connected by {addr}")
    try:
        # Receive file extension first
        file_ext_len_bytes = conn.recv(4)
        if not file_ext_len_bytes:
            console.print(f"Client {addr} disconnected before sending extension length.")
            return
        file_ext_len = int.from_bytes(file_ext_len_bytes, 'big')
        file_ext = conn.recv(file_ext_len).decode('utf-8')

        if not file_ext:
            console.print(f"Client {addr} disconnected or sent empty extension.")
            return

        # Create a unique filename and save the file
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"image_{timestamp}.{file_ext}"
        filepath = os.path.join(UPLOAD_DIR, filename)

        with open(filepath, 'wb') as f:
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                f.write(data)
        console.print(f"Received and saved {filename} from {addr}")
    except ConnectionResetError:
        console.print(f"Client {addr} forcefully closed the connection.")
    except Exception as e:
        console.print(f"Error handling client {addr}: {e}")
    finally:
        conn.close()
        console.print(f"Connection with {addr} closed.")

def monitor_flag_files():
    """Continuously monitors the UPLOAD_DIR for flag files."""
    flag_detected = False
    while True:
        flag_files = glob.glob(os.path.join(UPLOAD_DIR, '*.flag'))
        if flag_files and not flag_detected:
            console.print("[bold green]Ready to make an orthophoto[/bold green]")
            flag_detected = True
            # Execute the mapping script
            console.print(f"Executing mapping script: {MAPPING_SCRIPT_PATH}")
            try:
                # Use subprocess.run to execute the shell script
                # capture_output=True to capture stdout/stderr, text=True for string output
                result = subprocess.run([MAPPING_SCRIPT_PATH], capture_output=True, text=True, check=True)
                console.print("[bold green]Mapping script executed successfully![/bold green]")
                if result.stdout:
                    console.print(f"Script Output:\n{result.stdout}")
                if result.stderr:
                    console.print(f"Script Errors:\n{result.stderr}")
            except subprocess.CalledProcessError as e:
                console.print(f"[bold red]Error executing mapping script: {e}[/bold red]")
                console.print(f"Command: {e.cmd}")
                console.print(f"Return Code: {e.returncode}")
                console.print(f"Output: {e.stdout}")
                console.print(f"Error Output: {e.stderr}")
            except FileNotFoundError:
                console.print(f"[bold red]Mapping script not found at {MAPPING_SCRIPT_PATH}. Make sure it's executable.[/bold red]")
            except Exception as e:
                console.print(f"[bold red]An unexpected error occurred while running the mapping script: {e}[/bold red]")

            # Delete the flag files after attempting to run the script
            for flag_file in flag_files:
                try:
                    os.remove(flag_file)
                    console.print(f"Deleted flag file: {flag_file}")
                except OSError as e:
                    console.print(f"Error deleting flag file {flag_file}: {e}")
        elif not flag_files and flag_detected:
            flag_detected = False # Reset if flag files are removed
        time.sleep(1) # Prevent busy-waiting

def start_server():
    """Starts the server and listens for incoming connections."""
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR)
        console.print(f"Created upload directory: {UPLOAD_DIR}")

    # Start the flag monitoring thread
    flag_monitor_thread = threading.Thread(target=monitor_flag_files, daemon=True)
    flag_monitor_thread.start()
    console.print("Flag file monitor started.")

    # The 'with' statement ensures the socket is properly closed
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # Optional: allows reuse of address
        s.bind((HOST, PORT))
        s.listen()
        console.print(f"Server listening on {HOST}:{PORT}")
        console.print("Press Ctrl+C to stop the server.")

        try:
            while True:
                conn, addr = s.accept()
                thread = threading.Thread(target=handle_client, args=(conn, addr))
                # Set as a daemon thread so it exits when the main program does
                thread.daemon = True
                thread.start()
        except KeyboardInterrupt:
            console.print("\nShutting down server...")
        finally:
            console.print("Server has been closed.")

if __name__ == '__main__':
    start_server()
