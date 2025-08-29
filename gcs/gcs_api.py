import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from rich.console import Console

app = Flask(__name__)
CORS(app) # Enable CORS for all routes

RECEIVE_DIR = 'received_orthophotos' # Directory to save received orthophotos
if not os.path.exists(RECEIVE_DIR):
    os.makedirs(RECEIVE_DIR)

console = Console()

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(RECEIVE_DIR, filename)
        file.save(filepath)
        console.print(f"[bold green]API: Received and saved {filename}[/bold green]")
        return jsonify({"message": f"File {filename} uploaded successfully"}), 200
    return jsonify({"error": "Something went wrong"}), 500

@app.route('/files', methods=['GET'])
def list_files():
    try:
        files = [f for f in os.listdir(RECEIVE_DIR) if os.path.isfile(os.path.join(RECEIVE_DIR, f))]
        return jsonify({"files": files}), 200
    except Exception as e:
        console.print(f"[bold red]API: Error listing files: {e}[/bold red]")
        return jsonify({"error": "Could not list files"}), 500

@app.route('/files/<filename>', methods=['GET'])
def download_file(filename):
    try:
        return send_from_directory(RECEIVE_DIR, filename, as_attachment=True)
    except FileNotFoundError:
        return jsonify({"error": "File not found"}), 404
    except Exception as e:
        console.print(f"[bold red]API: Error downloading file {filename}: {e}[/bold red]")
        return jsonify({"error": "Could not download file"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
