import socket
import threading
import os
from rich.console import Console

HOST = '127.0.0.1'  # Standard loopback interface address (localhost)
PORT = 65433        # Port to listen on for GCS (different from server.py)
RECEIVE_DIR = 'received_orthophotos' # Directory to save received orthophotos

console = Console()

def handle_incoming_file(conn, addr):
    """Handles an individual incoming file connection."""
    console.print(f"[bold magenta]GCS: Connected by {addr}[/bold magenta]")
    try:
        # Receive file name length first
        file_name_len_bytes = conn.recv(4)
        if not file_name_len_bytes:
            console.print(f"GCS: Client {addr} disconnected before sending file name length.")
            return
        file_name_len = int.from_bytes(file_name_len_bytes, 'big')
        file_name = conn.recv(file_name_len).decode('utf-8')

        if not file_name:
            console.print(f"GCS: Client {addr} disconnected or sent empty file name.")
            return

        filepath = os.path.join(RECEIVE_DIR, file_name)
        os.makedirs(os.path.dirname(filepath), exist_ok=True) # Ensure directory exists

        with open(filepath, 'wb') as f:
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                f.write(data)
        console.print(f"[bold green]GCS: Received and saved {file_name} from {addr}[/bold green]")
    except ConnectionResetError:
        console.print(f"GCS: Client {addr} forcefully closed the connection.")
    except Exception as e:
        console.print(f"[bold red]GCS: Error handling incoming file from {addr}: {e}[/bold red]")
    finally:
        conn.close()
        console.print(f"GCS: Connection with {addr} closed.")

def start_gcs_receiver():
    """Starts the GCS receiver and listens for incoming file transfers."""
    if not os.path.exists(RECEIVE_DIR):
        os.makedirs(RECEIVE_DIR)
        console.print(f"GCS: Created receive directory: {RECEIVE_DIR}")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        console.print(f"[bold magenta]GCS: Receiver listening on {HOST}:{PORT}[/bold magenta]")
        console.print("GCS: Press Ctrl+C to stop the receiver.")

        try:
            while True:
                conn, addr = s.accept()
                thread = threading.Thread(target=handle_incoming_file, args=(conn, addr))
                thread.daemon = True
                thread.start()
        except KeyboardInterrupt:
            console.print("\n[bold magenta]GCS: Shutting down receiver...[/bold magenta]")
        finally:
            console.print("[bold magenta]GCS: Receiver has been closed.[/bold magenta]")

if __name__ == '__main__':
    start_gcs_receiver()
