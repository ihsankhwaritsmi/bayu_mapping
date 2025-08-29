import socket
import threading
import os
import datetime
import glob
import time
import subprocess # Import the subprocess module
import shutil # Import shutil for directory operations
from rich.console import Console

HOST = '127.0.0.1'  # Standard loopback interface address (localhost)
PORT = 65432        # Port to listen on (non-privileged ports are > 1023)
GCS_HOST = '127.0.0.1' # GCS Host
GCS_PORT = 65433     # GCS Port (must match gcs.py)
# Get the directory where the script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(SCRIPT_DIR, 'datasets', 'project', 'images')
MAPPING_SCRIPT_PATH = os.path.join(SCRIPT_DIR, 'mapping_script.sh')

console = Console()

def handle_client(conn, addr):
    """Handles an individual client connection."""
    console.print(f"Connected by {addr}")
    conn.settimeout(10) # Set a timeout for client connection operations
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
                # Use subprocess.Popen to stream output in real-time
                process = subprocess.Popen(
                    [MAPPING_SCRIPT_PATH],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True, # Decode stdout/stderr as text
                    bufsize=1 # Line-buffered output
                )

                # Stream stdout
                for line in process.stdout:
                    console.print(f"[blue]SCRIPT OUT:[/blue] {line.strip()}")
                # Stream stderr
                for line in process.stderr:
                    console.print(f"[red]SCRIPT ERR:[/red] {line.strip()}")

                # Wait for the process to complete and get the return code
                process.wait()

                if process.returncode == 0:
                    console.print("[bold green]Mapping script executed successfully![/bold green]")
                    # After successful mapping, send orthophotos to GCS
                    orthophoto_path = os.path.join(SCRIPT_DIR, 'datasets', 'project', 'odm_orthophoto', 'odm_orthophoto.tif')
                    original_orthophoto_path = os.path.join(SCRIPT_DIR, 'datasets', 'project', 'odm_orthophoto', 'odm_orthophoto.original.tif')

                    if os.path.exists(orthophoto_path):
                        send_file_to_gcs(orthophoto_path, max_retries=3, retry_delay=5)
                    else:
                        console.print(f"[bold yellow]Warning: {orthophoto_path} not found. Skipping transfer.[/bold yellow]")

                    if os.path.exists(original_orthophoto_path):
                        send_file_to_gcs(original_orthophoto_path, max_retries=3, retry_delay=5)
                    else:
                        console.print(f"[bold yellow]Warning: {original_orthophoto_path} not found. Skipping transfer.[/bold yellow]")

                    # Delete the datasets folder after sending files
                    delete_datasets_folder()

                else:
                    console.print(f"[bold red]Mapping script exited with error code: {process.returncode}[/bold red]")

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

def send_file_to_gcs(filepath, max_retries=3, retry_delay=5):
    """Sends a file to the GCS receiver with retry mechanism."""
    filename = os.path.basename(filepath)
    attempts = 0
    while attempts < max_retries:
        console.print(f"Attempt {attempts + 1}/{max_retries}: Sending {filename} to GCS at {GCS_HOST}:{GCS_PORT}")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(10) # Set a timeout for GCS socket operations
                s.connect((GCS_HOST, GCS_PORT))
                # Send file name length and then file name
                file_name_bytes = filename.encode('utf-8')
                s.sendall(len(file_name_bytes).to_bytes(4, 'big'))
                s.sendall(file_name_bytes)

                # Send file content
                with open(filepath, 'rb') as f:
                    while True:
                        bytes_read = f.read(4096)
                        if not bytes_read:
                            break
                        s.sendall(bytes_read)
            console.print(f"[bold green]Successfully sent {filename} to GCS.[/bold green]")
            return True # Successfully sent
        except ConnectionRefusedError:
            console.print(f"[bold red]Error: GCS receiver not running or connection refused at {GCS_HOST}:{GCS_PORT}. Retrying in {retry_delay} seconds...[/bold red]")
        except FileNotFoundError:
            console.print(f"[bold red]Error: File not found at {filepath}. Skipping GCS transfer for this file.[/bold red]")
            return False # No point in retrying if file doesn't exist
        except socket.timeout:
            console.print(f"[bold red]Error: Socket timeout while sending {filename} to GCS. Retrying in {retry_delay} seconds...[/bold red]")
        except Exception as e:
            console.print(f"[bold red]Error sending {filename} to GCS: {e}. Retrying in {retry_delay} seconds...[/bold red]")
        
        attempts += 1
        time.sleep(retry_delay)
    
    console.print(f"[bold red]Failed to send {filename} to GCS after {max_retries} attempts.[/bold red]")
    return False

def delete_datasets_folder():
    """Deletes the server/datasets folder."""
    datasets_path = os.path.join(SCRIPT_DIR, 'datasets')
    console.print(f"Attempting to delete datasets folder: {datasets_path}")
    try:
        if os.path.exists(datasets_path):
            # First, try to change permissions recursively to ensure deletion is possible
            console.print(f"Setting permissions for {datasets_path} to allow deletion...")
            for dirpath, dirnames, filenames in os.walk(datasets_path):
                os.chmod(dirpath, 0o777) # Set directory permissions
                for filename in filenames:
                    os.chmod(os.path.join(dirpath, filename), 0o777) # Set file permissions
            
            shutil.rmtree(datasets_path)
            console.print(f"[bold green]Successfully deleted datasets folder: {datasets_path}[/bold green]")
        else:
            console.print(f"[bold yellow]Warning: Datasets folder not found at {datasets_path}. Nothing to delete.[/bold yellow]")
    except OSError as e:
        console.print(f"[bold red]Error deleting datasets folder {datasets_path}: {e}[/bold red]")
    except Exception as e:
        console.print(f"[bold red]An unexpected error occurred during datasets folder deletion: {e}[/bold red]")

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
        s.settimeout(1) # Set a timeout for accept to allow KeyboardInterrupt to be caught
        console.print(f"Server listening on {HOST}:{PORT}")
        console.print("Press Ctrl+C to stop the server.")

        try:
            while True:
                try:
                    conn, addr = s.accept()
                    thread = threading.Thread(target=handle_client, args=(conn, addr))
                    # Set as a daemon thread so it exits when the main program does
                    thread.daemon = True
                    thread.start()
                except socket.timeout:
                    pass # Timeout occurred, continue listening
        except KeyboardInterrupt:
            console.print("\nShutting down server...")
        finally:
            console.print("Server has been closed.")

if __name__ == '__main__':
    start_server()
