# server.py

"""
A simple Flask server to receive video file uploads.
"""

from flask import Flask, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
import os

# --- Configuration ---
UPLOAD_FOLDER = 'datasets/project/images'
ALLOWED_EXTENSIONS = {'mp4'}

# --- Flask App Initialization ---
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SECRET_KEY'] = 'a-secure-secret-key' # Change this for production
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 500  # 500 MB max upload size

# --- Helper Functions ---
def allowed_file(filename):
    """Check if the uploaded file has an allowed extension."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Routes ---
@app.route('/')
def index():
    """A simple index page to show the server is running."""
    return '''
    <!doctype html>
    <title>Upload Server</title>
    <h1>GoPro Upload Server is Running</h1>
    <p>This server is waiting for video uploads from the video.py script.</p>
    '''

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle the file upload."""
    if 'file' not in request.files:
        flash('No file part')
        return redirect(request.url)
    
    file = request.files['file']
    
    if file.filename == '':
        flash('No selected file')
        return 'No selected file', 400

    if file and allowed_file(file.filename):
        # Sanitize the filename to prevent security issues
        filename = secure_filename(file.filename)
        # Ensure the upload folder exists
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        # Save the file
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(save_path)
        print(f"Received and saved file: {filename}")
        return f'File {filename} uploaded successfully', 200
    
    return 'Invalid file type', 400

# --- Main Execution ---
if __name__ == '__main__':
    # To run this on AWS and make it accessible, use host='0.0.0.0'
    # Example command: python server.py
    app.run(host='0.0.0.0', port=5000, debug=True)
