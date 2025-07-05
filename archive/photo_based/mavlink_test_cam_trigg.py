from pymavlink import mavutil
import re

# ===============================
# 1. Connect to the Vehicle
# ===============================
# --- Use the TCP connection string as requested ---
connection_string = 'tcp:127.0.0.1:5762'

try:
    # For TCP connections, baud rate is not needed.
    master = mavutil.mavlink_connection(connection_string)
    
    print(f"Connecting to {connection_string}...")
    master.wait_heartbeat()
    print(f"Heartbeat received. Connected to system ID: {master.target_system}")
    print("\nMonitoring for STATUSTEXT messages related to camera triggers...")

except Exception as e:
    print(f"Failed to connect: {e}")
    exit()

# ===============================
# 2. Listen for STATUSTEXT
# ===============================
try:
    while True:
        # Wait for a STATUSTEXT message
        msg = master.recv_match(type='STATUSTEXT', blocking=True)
        
        if not msg:
            continue

        print(msg)

        # Convert the message text to a string
        message_text = msg.text.strip()
        # print(message_text)

        # Check if the text contains the string for the camera trigger command
        if "SetCamTrigDst" in message_text:
            
            # The text looks like: "Mission: 9 SetCamTrigDst"
            # We can use regex to extract the waypoint number
            match = re.search(r'Mission: (\d+) SetCamTrigDst', message_text)
            
            print("="*50)
            if match:
                waypoint_num = match.group(1)
                print(f"📸 Camera Trigger Command Detected at Waypoint #{waypoint_num}!")
            else:
                # Fallback if the format is slightly different
                print(f"📸 Camera Trigger Command Detected: '{message_text}'")
            
            # print("   NOTE: The trigger parameters (e.g., distance) are not in this message.")
            print("="*50)


except KeyboardInterrupt:
    print("\nExited by user.")
except Exception as e:
    print(f"An error occurred: {e}")