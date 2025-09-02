import socket
import threading
import os
import datetime
import glob
import time
import subprocess
import shutil
import json
from rich.console import Console
from flask import Flask, render_template_string, send_from_directory, abort, redirect, url_for
from werkzeug.utils import secure_filename

# --- CONFIGURATION ---
# Network settings
HOST = '0.0.0.0'  # Listen on all available interfaces for compatibility
PORT = 65432      # Port for the main socket server
FLASK_PORT = 5000 # Port for the Flask web server

# Protocol message types (client must send one of these first)
MESSAGE_TYPE_STATUS = "status_check"
MESSAGE_TYPE_FILE = "file_upload"

# Directory settings
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BROWSE_BASE_DIR = os.path.join(SCRIPT_DIR, 'datasets')
UPLOAD_DIR = os.path.join(BROWSE_BASE_DIR, 'project', 'images') # Files are uploaded here
MAPPING_SCRIPT_PATH = os.path.join(SCRIPT_DIR, 'mapping_script.sh')

# --- INITIALIZATION ---
console = Console()
app = Flask(__name__)

# --- FLASK WEB SERVER ---

# Inline HTML template for the file browser
DIR_LISTING_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>File Browser - {{ current_path }}</title>
    <style>
        body { font-family: monospace; background-color: #1e1e1e; color: #d4d4d4; margin: 20px; }
        h1 { color: #569cd6; border-bottom: 1px solid #333; padding-bottom: 10px; }
        a { color: #9cdcfe; text-decoration: none; }
        a:hover { text-decoration: underline; }
        ul { list-style-type: none; padding: 0; }
        li { margin-bottom: 8px; padding: 5px; border-radius: 3px; }
        li:hover { background-color: #2a2d2e; }
        .dir { color: #ce9178; font-weight: bold; }
        .file { color: #d4d4d4; }
        .parent-link { margin-bottom: 20px; display: block; font-size: 1.1em;}
    </style>
</head>
<body>
    <h1>File Browser: {{ current_path }}</h1>
    {% if parent_path %}
        <a href="{{ parent_path }}" class="parent-link"> &larr; Parent Directory</a>
    {% endif %}
    <ul>
        {% for item in items %}
            <li>
                {% if item.type == 'dir' %}
                    <span class="dir">[DIR]</span> <a href="{{ url_for('browse_directory', subpath=item.path) }}">{{ item.name }}</a>
                {% else %}
                    <span class="file">[FILE]</span> <a href="{{ url_for('download_file', filename=item.path) }}">{{ item.name }}</a>
                {% endif %}
            </li>
        {% endfor %}
    </ul>
</body>
</html>
"""

@app.route('/browse/', defaults={'subpath': ''})
@app.route('/browse/<path:subpath>')
def browse_directory(subpath):
    base_dir = BROWSE_BASE_DIR
    # Sanitize and normalize the path
    normalized_subpath = subpath.replace('\\', '/')
    abs_path = os.path.join(base_dir, normalized_subpath)

    # Prevent directory traversal attacks
    if not os.path.abspath(abs_path).startswith(os.path.abspath(base_dir)):
        abort(404)

    if not os.path.exists(abs_path):
        abort(404)

    # If the path is a file, redirect to download it
    if os.path.isfile(abs_path):
        relative_filepath = os.path.relpath(abs_path, base_dir).replace('\\', '/')
        return redirect(url_for('download_file', filename=relative_filepath))

    items = []
    try:
        for item_name in os.listdir(abs_path):
            item_path = os.path.join(abs_path, item_name)
            relative_item_path = os.path.relpath(item_path, base_dir).replace('\\', '/')
            item_type = 'dir' if os.path.isdir(item_path) else 'file'
            items.append({'name': item_name, 'type': item_type, 'path': relative_item_path})
    except PermissionError:
        console.print(f"[bold red]Permission denied to access {abs_path}[/bold red]")
        abort(403) # Forbidden

    # Sort items: directories first, then files, both alphabetically
    items.sort(key=lambda x: (x['type'] == 'file', x['name'].lower()))

    current_path_display = '/' + normalized_subpath if normalized_subpath else '/'
    
    parent_path = None
    if os.path.abspath(abs_path) != os.path.abspath(base_dir):
        parent_abs_path = os.path.dirname(abs_path)
        relative_parent_path = os.path.relpath(parent_abs_path, base_dir).replace('\\', '/')
        # Handle the case where the parent is the base directory
        if relative_parent_path == '.':
            parent_path = url_for('browse_directory', subpath='')
        else:
            parent_path = url_for('browse_directory', subpath=relative_parent_path)

    return render_template_string(DIR_LISTING_TEMPLATE,
                                  current_path=current_path_display,
                                  items=items,
                                  parent_path=parent_path)

@app.route('/download/<path:filename>')
def download_file(filename):
    # Sanitize and normalize the filename path
    normalized_filename = filename.replace('\\', '/')
    abs_filepath = os.path.join(BROWSE_BASE_DIR, normalized_filename)
    if not os.path.abspath(abs_filepath).startswith(os.path.abspath(BROWSE_BASE_DIR)):
        abort(404)

    try:
        return send_from_directory(BROWSE_BASE_DIR, normalized_filename, as_attachment=True)
    except FileNotFoundError:
        abort(404)

def run_flask_app():
    """Runs the Flask application in the background."""
    console.print(f"Flask server starting on http://{HOST}:{FLASK_PORT}/browse/")
    # Set use_reloader=False because it causes issues in a threaded environment
    app.run(host=HOST, port=FLASK_PORT, debug=False, use_reloader=False)


# --- SOCKET SERVER & CLIENT HANDLING ---

def handle_client(conn, addr):
    """
    Handles an individual client connection.
    This function implements the server's communication protocol.
    """
    console.print(f"Connected by {addr}")
    conn.settimeout(20) # Set a timeout for client operations
    
    try:
        # --- PROTOCOL STEP 1: RECEIVE MESSAGE TYPE ---
        # The client MUST first send the length of the message type, then the type itself.
        message_type_len_bytes = conn.recv(4)
        if not message_type_len_bytes:
            console.print(f"Client {addr} disconnected before sending message type length.")
            return
        message_type_len = int.from_bytes(message_type_len_bytes, 'big')
        message_type = conn.recv(message_type_len).decode('utf-8')

        # --- PROTOCOL STEP 2: PROCESS BASED ON MESSAGE TYPE ---
        if message_type == MESSAGE_TYPE_STATUS:
            # Handle status message
            message_len_bytes = conn.recv(4)
            if not message_len_bytes: return
            message_len = int.from_bytes(message_len_bytes, 'big')
            status_message_bytes = conn.recv(message_len)
            status_message = json.loads(status_message_bytes.decode('utf-8'))
            
            mavlink_status = status_message.get('mavlink', 'unknown')
            gopro_status = status_message.get('gopro', 'unknown')
            mavlink_color = "green" if mavlink_status == "connected" else "red"
            gopro_color = "green" if gopro_status == "connected" else "red"

            console.print(f"Received status from {addr}: "
                          f"[bold {mavlink_color}]Mavlink: {mavlink_status}[/bold {mavlink_color}], "
                          f"[bold {gopro_color}]GoPro: {gopro_status}[/bold {gopro_color}]")
            conn.sendall(b"Status received.")

        elif message_type == MESSAGE_TYPE_FILE:
            # Handle file upload (including .flag files)
            file_ext_len_bytes = conn.recv(4)
            if not file_ext_len_bytes: return
            file_ext_len = int.from_bytes(file_ext_len_bytes, 'big')
            file_ext = conn.recv(file_ext_len).decode('utf-8').lstrip('.') # Sanitize extension

            if not file_ext:
                console.print(f"Client {addr} sent an empty file extension.")
                return

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"received_{timestamp}.{file_ext}"
            filepath = os.path.join(UPLOAD_DIR, filename)

            with open(filepath, 'wb') as f:
                while True:
                    data = conn.recv(4096)
                    if not data:
                        break
                    f.write(data)
            console.print(f"Received and saved [cyan]{filename}[/cyan] from {addr}")
            conn.sendall(b"File received.")
            
        else:
            console.print(f"[bold red]Received unknown message type '{message_type}' from {addr}.[/bold red]")

    except ConnectionResetError:
        console.print(f"Client {addr} forcefully closed the connection.")
    except socket.timeout:
        console.print(f"Socket timeout with client {addr}.")
    except json.JSONDecodeError:
        console.print(f"[bold red]Error decoding JSON from client {addr}.[/bold red]")
    except Exception as e:
        console.print(f"[bold red]Error handling client {addr}: {e}[/bold red]")
    finally:
        conn.close()
        console.print(f"Connection with {addr} closed.")


# --- BACKGROUND TASK: FLAG FILE MONITOR ---

def monitor_flag_files():
    """Continuously monitors the UPLOAD_DIR for '.flag' files to trigger the mapping script."""
    console.print("Flag file monitor started.")
    while True:
        try:
            flag_files = glob.glob(os.path.join(UPLOAD_DIR, '*.flag'))
            if flag_files:
                console.print("[bold green]Flag file detected! Ready to start orthophoto generation.[/bold green]")
                
                # Execute the mapping script
                console.print(f"Executing mapping script: {MAPPING_SCRIPT_PATH} with UPLOAD_DIR={UPLOAD_DIR}")
                try:
                    # Ensure the mapping script is executable
                    if not os.access(MAPPING_SCRIPT_PATH, os.X_OK):
                        console.print(f"[bold red]Error: Mapping script {MAPPING_SCRIPT_PATH} is not executable. Attempting to make it executable.[/bold red]")
                        os.chmod(MAPPING_SCRIPT_PATH, 0o755) # Make it executable for owner, group, others

                    # Use Popen to stream stdout/stderr in real-time, passing UPLOAD_DIR as an argument
                    process = subprocess.Popen(
                        [MAPPING_SCRIPT_PATH, UPLOAD_DIR], # Pass UPLOAD_DIR as an argument
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        bufsize=1,
                        universal_newlines=True
                    )

                    # Stream stdout and stderr from the script
                    for line in process.stdout:
                        console.print(f"[blue]SCRIPT OUT:[/] {line.strip()}")
                    for line in process.stderr:
                        console.print(f"[red]SCRIPT ERR:[/] {line.strip()}")
                    
                    process.wait() # Wait for the script to finish

                    if process.returncode == 0:
                        console.print("[bold green]Mapping script executed successfully![/bold green]")
                    else:
                        console.print(f"[bold red]Mapping script exited with error code: {process.returncode}[/bold red]")

                except FileNotFoundError:
                    console.print(f"[bold red]Error: Mapping script not found at {MAPPING_SCRIPT_PATH}. Ensure the file exists and is executable (`chmod +x mapping_script.sh`).[/bold red]")
                except Exception as e:
                    console.print(f"[bold red]An unexpected error occurred while running the mapping script: {e}[/bold red]")
                
                # Clean up flag files after processing
                for flag_file in flag_files:
                    try:
                        os.remove(flag_file)
                        console.print(f"Deleted flag file: {os.path.basename(flag_file)}")
                    except OSError as e:
                        console.print(f"[bold red]Error deleting flag file {flag_file}: {e}[/bold red]")
            
            time.sleep(2) # Check for flag files every 2 seconds
        except Exception as e:
            console.print(f"[bold red]Error in flag monitor loop: {e}[/bold red]")
            time.sleep(5) # Wait a bit longer if there's a recurring error


# --- MAIN SERVER LOGIC ---

def start_socket_server():
    """Starts the main socket server to listen for incoming client connections."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        s.settimeout(1.0) # Use a timeout to allow graceful shutdown with Ctrl+C
        console.print(f"[bold]Server listening on {HOST}:{PORT}[/bold]")
        console.print("Press Ctrl+C to stop the server.")

        while True:
            try:
                conn, addr = s.accept()
                # Create a new thread for each client to handle them concurrently
                thread = threading.Thread(target=handle_client, args=(conn, addr))
                thread.daemon = True # Allows main program to exit even if threads are running
                thread.start()
            except socket.timeout:
                continue # Go back to the start of the loop and wait for a connection
            except KeyboardInterrupt:
                console.print("\nShutting down server...")
                break

if __name__ == '__main__':
    # Ensure necessary directories exist before starting
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR)
        console.print(f"Created upload directory: {UPLOAD_DIR}")
    
    # Start the Flask web server in a background thread
    flask_thread = threading.Thread(target=run_flask_app, daemon=True)
    flask_thread.start()
    
    # Start the flag file monitor in a background thread
    flag_monitor_thread = threading.Thread(target=monitor_flag_files, daemon=True)
    flag_monitor_thread.start()
    
    # Start the main socket server in the main thread
    start_socket_server()
    
    console.print("Server has been closed.")
