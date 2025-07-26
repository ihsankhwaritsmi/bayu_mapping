import socket
import threading
import os
import datetime
import glob
import time
from rich.console import Console

HOST = '127.0.0.1'  # Standard loopback interface address (localhost)
PORT = 65432        # Port to listen on (non-privileged ports are > 1023)
UPLOAD_DIR = 'datasets/project/images'

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

def start_server():
    """Starts the server and listens for incoming connections."""
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR)
        console.print(f"Created upload directory: {UPLOAD_DIR}")

    # The 'with' statement ensures the socket is properly closed
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # Optional: allows reuse of address
        s.bind((HOST, PORT))
        s.listen()
        console.print(f"Server listening on {HOST}:{PORT}")
        console.print("Press Ctrl+C to stop the server.")

        flag_detected = False
        try:
            while True:
                conn, addr = s.accept()
                thread = threading.Thread(target=handle_client, args=(conn, addr))
                # Set as a daemon thread so it exits when the main program does
                thread.daemon = True
                thread.start()

                # Check for flag files
                flag_files = glob.glob(os.path.join(UPLOAD_DIR, '*.flag'))
                if flag_files and not flag_detected:
                    console.print("[bold green]Ready to make an orthophoto[/bold green]")
                    flag_detected = True
                    # Delete the flag files after printing the message
                    for flag_file in flag_files:
                        try:
                            os.remove(flag_file)
                            console.print(f"Deleted flag file: {flag_file}")
                        except OSError as e:
                            console.print(f"Error deleting flag file {flag_file}: {e}")
                elif not flag_files and flag_detected:
                    flag_detected = False # Reset if flag files are removed

                time.sleep(1) # Prevent busy-waiting
        except KeyboardInterrupt:
            console.print("\nShutting down server...")
        finally:
            console.print("Server has been closed.")

if __name__ == '__main__':
    start_server()
