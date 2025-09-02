import socket
import threading
import json

HOST = '0.0.0.0'  # Listen on all available interfaces
PORT = 65433      # Port for status messages

MESSAGE_TYPE_STATUS = "status_check"

def handle_client(conn, addr):
    """Handle a single client connection."""
    print(f"Connected by {addr}")
    try:
        # First, read the message type length
        message_type_len_bytes = conn.recv(4)
        if not message_type_len_bytes:
            print(f"Client {addr} disconnected unexpectedly.")
            return
        message_type_len = int.from_bytes(message_type_len_bytes, 'big')

        # Then, read the message type
        message_type = conn.recv(message_type_len).decode('utf-8')

        if message_type == MESSAGE_TYPE_STATUS:
            # Read the length of the JSON status message
            status_len_bytes = conn.recv(4)
            if not status_len_bytes:
                print(f"Client {addr} disconnected while reading status length.")
                return
            status_len = int.from_bytes(status_len_bytes, 'big')

            # Read the JSON status message
            full_message = b''
            while len(full_message) < status_len:
                packet = conn.recv(status_len - len(full_message))
                if not packet:
                    print(f"Client {addr} disconnected while reading status message.")
                    return
                full_message += packet
            
            status_data = json.loads(full_message.decode('utf-8'))
            print(f"Received status from {addr}: {status_data}")
        else:
            print(f"Received unknown message type '{message_type}' from {addr}")

    except ConnectionResetError:
        print(f"Client {addr} forcibly closed the connection.")
    except json.JSONDecodeError:
        print(f"Error decoding JSON from {addr}.")
    except Exception as e:
        print(f"Error handling client {addr}: {e}")
    finally:
        conn.close()
        print(f"Connection with {addr} closed.")

def start_server():
    """Starts the status message server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        print(f"Server2 listening for status messages on {HOST}:{PORT}...")
        while True:
            conn, addr = s.accept()
            client_thread = threading.Thread(target=handle_client, args=(conn, addr))
            client_thread.start()

if __name__ == '__main__':
    start_server()
