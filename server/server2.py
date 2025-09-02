import socket
import threading
import json
from rich.console import Console # Import Console for beautified output

HOST = '0.0.0.0'  # Listen on all available interfaces
PORT = 65433      # Port for status messages

MESSAGE_TYPE_STATUS = "status_check"

console = Console() # Initialize rich console

def handle_client(conn, addr):
    """Handle a single client connection, receiving and processing status messages."""
    console.print(f"\n[bold green]Client connected from {addr}[/bold green]")
    conn.settimeout(10) # Set a timeout for client connection operations
    try:
        # First, read the message type length
        message_type_len_bytes = conn.recv(4)
        if not message_type_len_bytes:
            console.print(f"[bold red]Client {addr} disconnected unexpectedly.[/bold red]")
            return
        message_type_len = int.from_bytes(message_type_len_bytes, 'big')

        # Then, read the message type
        message_type = conn.recv(message_type_len).decode('utf-8')

        if message_type == MESSAGE_TYPE_STATUS:
            # Read the length of the JSON status message
            status_len_bytes = conn.recv(4)
            if not status_len_bytes:
                console.print(f"[bold red]Client {addr} disconnected while reading status length.[/bold red]")
                return
            status_len = int.from_bytes(status_len_bytes, 'big')

            # Read the JSON status message
            full_message = b''
            while len(full_message) < status_len:
                packet = conn.recv(status_len - len(full_message))
                if not packet:
                    console.print(f"[bold red]Client {addr} disconnected while reading status message.[/bold red]")
                    return
                full_message += packet
            
            status_data = json.loads(full_message.decode('utf-8'))
            console.print(f"[bold blue]Received status from {addr}:[/bold blue]\n{json.dumps(status_data, indent=2)}")
        else:
            console.print(f"[bold red]Received unknown message type '{message_type}' from {addr}[/bold red]")

    except ConnectionResetError:
        console.print(f"[bold red]Client {addr} forcibly closed the connection.[/bold red]")
    except json.JSONDecodeError:
        console.print(f"[bold red]Error decoding JSON from {addr}. Ensure valid JSON is sent.[/bold red]")
    except Exception as e:
        console.print(f"[bold red]Error handling client {addr}: {e}[/bold red]")
    finally:
        conn.close()
        console.print(f"[bold red]Connection with {addr} closed.[/bold red]\n")

def start_server():
    """Starts the status message server and listens for incoming connections."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # Allow reuse of address
        s.bind((HOST, PORT))
        s.listen()
        console.print(f"[bold magenta]Server2 listening for status messages on {HOST}:{PORT}...[/bold magenta]")
        console.print("Press Ctrl+C to stop the server.")
        try:
            while True:
                conn, addr = s.accept()
                client_thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
                client_thread.start()
        except KeyboardInterrupt:
            console.print("\n[bold red]Shutting down Server2...[/bold red]")
        finally:
            console.print("[bold red]Server2 has been closed.[/bold red]")

if __name__ == '__main__':
    start_server()
