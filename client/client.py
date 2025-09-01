import socket
import os
import time
import queue
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

HOST = '172.232.231.100'  # The server's hostname or IP address
PORT = 65432        # The port used by the server
GOPRO_CAPTURES_DIR = 'gopro_captures'
FLAG_FILE_EXTENSION = "flag"

def uploader_worker(upload_queue):
    """
    Pulls filepaths from a queue and sends them to the server.
    Retries indefinitely on connection failure.
    Deletes image files and the flag file after successful transmission of a flag file.
    """
    time.sleep(2)
    files_in_current_mission = [] # Stores paths of files successfully sent in the current mission batch

    while True:
        filepath = upload_queue.get()
        if filepath is None:  # Sentinel value to signal thread termination
            break

        filename = os.path.basename(filepath)
        file_ext = filename.split('.')[-1].lower() # Ensure extension is lowercase for consistent comparison
        
        sent_successfully = False
        while not sent_successfully:
            try:
                time.sleep(1) 
                
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(10) 
                    print(f"Attempting to send {filename}...")
                    s.connect((HOST, PORT))
                    
                    ext_bytes = file_ext.encode('utf-8')
                    s.sendall(len(ext_bytes).to_bytes(4, 'big'))
                    s.sendall(ext_bytes)

                    with open(filepath, 'rb') as f:
                        s.sendall(f.read())

                    print(f"✅ Successfully sent {filename} to server.")
                    sent_successfully = True

                    # Add to mission list if successfully sent
                    files_in_current_mission.append(filepath)

                    # If a flag file was just sent, trigger batch deletion
                    if file_ext == FLAG_FILE_EXTENSION:
                        print(f"🚩 Flag file {filename} sent. Initiating deletion of mission files...")
                        for file_to_delete in files_in_current_mission:
                            try:
                                os.remove(file_to_delete)
                                print(f"🗑️ Deleted file: {os.path.basename(file_to_delete)}")
                            except OSError as e:
                                print(f"❗️ Error deleting {os.path.basename(file_to_delete)}: {e}")
                        files_in_current_mission.clear() # Reset for the next mission

            except ConnectionRefusedError:
                print(f"❗️ Connection refused for {filename}. Retrying in 5 seconds...")
                time.sleep(5)
            except FileNotFoundError:
                print(f"❗️ File {filename} was not found. It might have been deleted externally. Skipping.")
                break # Stop trying for this file
            except Exception as e:
                print(f"❗️ Error sending {filename}: {e}. Retrying in 5 seconds...")
                time.sleep(5)
        
        upload_queue.task_done()


class ImageHandler(FileSystemEventHandler):
    """Queues new images for upload instead of sending them directly."""
    def __init__(self, upload_queue):
        super().__init__()
        self.upload_queue = upload_queue

    def on_created(self, event):
        if not event.is_directory:
            filepath = event.src_path
            filename = os.path.basename(filepath)
            file_ext = filename.split('.')[-1].lower() # Ensure extension is lowercase
            if file_ext in ['jpg', 'jpeg', 'png', 'gif', 'bmp']:
                print(f"📥 Detected new image, adding to queue: {filename}")
                self.upload_queue.put(filepath)
            elif file_ext == FLAG_FILE_EXTENSION:
                print(f"🚩 Detected mission completion flag, adding to queue: {filename}")
                self.upload_queue.put(filepath)


def start_client():
    """Initializes the queue, worker thread, and file monitor."""
    if not os.path.exists(GOPRO_CAPTURES_DIR):
        os.makedirs(GOPRO_CAPTURES_DIR)
        print(f"Created GoPro captures directory: {GOPRO_CAPTURES_DIR}")

    upload_queue = queue.Queue()
    worker_thread = threading.Thread(target=uploader_worker, args=(upload_queue,))
    worker_thread.start()

    event_handler = ImageHandler(upload_queue)
    observer = Observer()
    observer.schedule(event_handler, GOPRO_CAPTURES_DIR, recursive=False)
    observer.start()
    
    print(f"Client monitoring {GOPRO_CAPTURES_DIR} for new images...")
    print("Press Ctrl+C to stop the client.")

    try:
        worker_thread.join()
    except KeyboardInterrupt:
        print("\nShutting down client...")
        observer.stop()
        observer.join()

        # Wait for the queue to be empty (all files uploaded)
        print("Waiting for pending uploads to complete...")
        upload_queue.join()

        # Stop the worker thread gracefully
        upload_queue.put(None)
        # The main thread already joined, but we do it again to be sure
        if worker_thread.is_alive():
           worker_thread.join()
        
        print("Client has shut down.")

if __name__ == '__main__':
    start_client()
