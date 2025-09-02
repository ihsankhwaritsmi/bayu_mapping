import socket
import threading
import os
import datetime
import glob
import time
import subprocess # Import the subprocess module
import shutil # Import shutil for directory operations
import json # Import json for status messages
from rich.console import Console
from flask import Flask, render_template_string, send_from_directory, abort, request, redirect, url_for
from werkzeug.utils import secure_filename

MESSAGE_TYPE_STATUS = "status_check"
MESSAGE_TYPE_FILE = "file_upload"

HOST = '0.0.0.0'  # Listen on all available interfaces for AWS compatibility
PORT = 65432        # Port to listen on (non-privileged ports are > 1023)
FLASK_PORT = 5000   # Port for the Flask web server

# Get the directory where the script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(SCRIPT_DIR, 'datasets', 'project', 'images')
BROWSE_BASE_DIR = os.path.join(SCRIPT_DIR, 'datasets') # New base directory for browsing
MAPPING_SCRIPT_PATH = os.path.join(SCRIPT_DIR, 'mapping_script.sh')

console = Console()
app = Flask(__name__)

# Inline HTML template for directory listing
DIR_LISTING_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Directory Listing - {{ current_path }}</title>
    <style>
        body { font-family: monospace; background-color: #1e1e1e; color: #d4d4d4; margin: 20px; }
        h1 { color: #569cd6; }
        a { color: #9cdcfe; text-decoration: none; }
        a:hover { text-decoration: underline; }
        ul { list-style-type: none; padding: 0; }
        li { margin-bottom: 5px; }
        .dir { color: #ce9178; }
        .file { color: #d4d4d4; }
        .parent-link { margin-bottom: 10px; display: block; }
    </style>
</head>
<body>
    <h1>Directory Listing for: {{ current_path }}</h1>
    {% if parent_path %}
        <a href="{{ parent_path }}" class="parent-link">.. (Parent Directory)</a>
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
    # Normalize subpath to use forward slashes for consistency
    normalized_subpath = subpath.replace('\\', '/')
    abs_path = os.path.join(base_dir, normalized_subpath)
    
    # Sanitize path to prevent directory traversal
    if not os.path.abspath(abs_path).startswith(os.path.abspath(base_dir)):
        abort(404)

    if not os.path.exists(abs_path):
        abort(404)

    if os.path.isfile(abs_path):
        # If it's a file, redirect to download it
        relative_filepath = os.path.relpath(abs_path, BROWSE_BASE_DIR).replace('\\', '/')
        return redirect(url_for('download_file', filename=relative_filepath))

    items = []
    try:
        for item_name in os.listdir(abs_path):
            item_path = os.path.join(abs_path, item_name)
            relative_item_path = os.path.relpath(item_path, BROWSE_BASE_DIR).replace('\\', '/') # Normalize to forward slashes
            
            if os.path.isdir(item_path):
                items.append({'name': item_name, 'type': 'dir', 'path': relative_item_path})
            else:
                items.append({'name': item_name, 'type': 'file', 'path': relative_item_path})
    except PermissionError:
        console.print(f"[bold red]Permission denied to access {abs_path}[/bold red]")
        abort(403) # Forbidden

    # Sort items: directories first, then files, both alphabetically
    items.sort(key=lambda x: (x['type'] == 'file', x['name'].lower()))

    current_path_display = os.path.relpath(abs_path, BROWSE_BASE_DIR).replace('\\', '/') if abs_path != BROWSE_BASE_DIR else '/'
    
    parent_path = None
    if abs_path != BROWSE_BASE_DIR:
        parent_abs_path = os.path.dirname(abs_path)
        relative_parent_path = os.path.relpath(parent_abs_path, BROWSE_BASE_DIR).replace('\\', '/')
        if relative_parent_path == '.': # This means the parent is BROWSE_BASE_DIR itself
            parent_path = url_for('browse_directory', subpath='')
        else:
            parent_path = url_for('browse_directory', subpath=relative_parent_path)

    return render_template_string(DIR_LISTING_TEMPLATE, 
                                  current_path=current_path_display, 
                                  items=items,
                                  parent_path=parent_path)

@app.route('/download/<path:filename>')
def download_file(filename):
    # The filename is expected to be a relative path from BROWSE_BASE_DIR, already sanitized by browse_directory
    # Ensure the path does not attempt directory traversal
    # Normalize filename to use forward slashes for consistency
    normalized_filename = filename.replace('\\', '/')
    abs_filepath = os.path.join(BROWSE_BASE_DIR, normalized_filename)
    if not os.path.abspath(abs_filepath).startswith(os.path.abspath(BROWSE_BASE_DIR)):
        abort(404)
    
    # The filename is already the relative path from BROWSE_BASE_DIR.
    # send_from_directory expects the base directory and the relative path to the file.
    try:
        return send_from_directory(BROWSE_BASE_DIR, normalized_filename, as_attachment=True)
    except FileNotFoundError:
        abort(404)

def handle_client(conn, addr):
    """Handles an individual client connection."""
    console.print(f"Connected by {addr}")
    conn.settimeout(10) # Set a timeout for client connection operations
    try:
        # First, receive the message type identifier
        message_type_len_bytes = conn.recv(4)
        if not message_type_len_bytes:
            console.print(f"Client {addr} disconnected before sending message type length.")
            return
        message_type_len = int.from_bytes(message_type_len_bytes, 'big')
        message_type = conn.recv(message_type_len).decode('utf-8')

        if message_type == MESSAGE_TYPE_STATUS:
            # Handle status message
            message_len_bytes = conn.recv(4)
            if not message_len_bytes:
                console.print(f"Client {addr} disconnected before sending status message length.")
                return
            message_len = int.from_bytes(message_len_bytes, 'big')
            status_message_bytes = conn.recv(message_len)
            status_message = json.loads(status_message_bytes.decode('utf-8'))
            console.print(f"Received status from {addr}:\n"
                          f"  [bold blue]Client Program: {status_message.get('client_program')}[/bold blue]\n"
                          f"  [bold blue]Mavlink: {status_message.get('mavlink')}[/bold blue]\n"
                          f"  [bold blue]GoPro: {status_message.get('gopro')}[/bold blue]")
            # Optionally send a response back to the client
            conn.sendall(b"Status received.")

        elif message_type == MESSAGE_TYPE_FILE:
            # Handle file upload
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
            conn.sendall(b"File received.")
        else:
            console.print(f"Received unknown message type '{message_type}' from {addr}.")

    except ConnectionResetError:
        console.print(f"Client {addr} forcefully closed the connection.")
    except socket.timeout:
        console.print(f"Socket timeout with client {addr}.")
    except json.JSONDecodeError:
        console.print(f"Error decoding JSON from client {addr}.")
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

def start_server():
    """Starts the server and listens for incoming connections."""
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

def run_flask_app():
    """Runs the Flask application."""
    console.print(f"Flask server starting on http://{HOST}:{FLASK_PORT}/browse/")
    app.run(host=HOST, port=FLASK_PORT, debug=True, use_reloader=False) # Set debug to True for more detailed error messages

@app.errorhandler(500)
def internal_error(error):
    console.print(f"[bold red]Flask Internal Server Error: {error}[/bold red]")
    import traceback
    console.print(f"[bold red]Traceback: {traceback.format_exc()}[/bold red]")
    return "Internal Server Error", 500

if __name__ == '__main__':
    # Ensure UPLOAD_DIR and BROWSE_BASE_DIR exist
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR)
        console.print(f"Created upload directory: {UPLOAD_DIR}")
    
    if not os.path.exists(BROWSE_BASE_DIR):
        os.makedirs(BROWSE_BASE_DIR)
        console.print(f"Created browse base directory: {BROWSE_BASE_DIR}")

    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask_app, daemon=True)
    flask_thread.start()
    
    start_server()
