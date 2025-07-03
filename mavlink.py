# MAVLink Data Streamer for Pixhawk to Raspberry Pi
#
# This script connects to a Pixhawk flight controller via a serial port
# on the Raspberry Pi and continuously reads and prints MAVLink messages.
#
# Author: Gemini
# Date: 2024-06-21
#
# Prerequisites:
# 1. A Raspberry Pi connected to a Pixhawk via a serial connection (e.g., TELEM2 port).
# 2. The pymavlink library installed on the Raspberry Pi:
#    pip install pymavlink
#
# How to Run:
# 1. Save this script as `pixhawk_stream.py` on your Raspberry Pi.
# 2. Make sure you know the correct serial port and baud rate.
#    - For Raspberry Pi 5, it's typically `/dev/ttyAMA0`.
#    - For Raspberry Pi 3/4, it's often `/dev/ttyS0` or `/dev/serial0`.
#    - The default baud rate for Pixhawk telemetry ports is usually 57600.
# 3. Run the script from the terminal:
#    python pixhawk_stream.py

import time
from pymavlink import mavutil

def connect_to_pixhawk(connection_string, baudrate):
    """
    Connects to the Pixhawk and returns the connection object.

    Args:
        connection_string (str): The serial port (e.g., '/dev/ttyS0').
        baudrate (int): The baud rate (e.g., 57600).

    Returns:
        The MAVLink connection object or None if connection fails.
    """
    print(f"Attempting to connect to Pixhawk on {connection_string} at {baudrate} baud...")
    try:
        # Start a connection listening to a serial port
        master = mavutil.mavlink_connection(connection_string, baud=baudrate)

        # Wait for the first heartbeat
        # This confirms a connection has been established
        print("Waiting for heartbeat...")
        master.wait_heartbeat()
        print("Heartbeat from system (system %u component %u)" %
              (master.target_system, master.target_component))
        print("Connection successful!")
        return master
    except Exception as e:
        print(f"Failed to connect: {e}")
        return None

def request_data_stream(master, stream_id, rate):
    """
    Requests a specific data stream from the Pixhawk.

    Args:
        master: The MAVLink connection object.
        stream_id (int): The ID of the data stream to request.
                         (e.g., mavutil.mavlink.MAV_DATA_STREAM_ALL for all).
        rate (int): The requested frequency of the stream in Hz.
    """
    print(f"Requesting data stream {stream_id} at {rate}Hz...")
    master.mav.request_data_stream_send(
        master.target_system,    # Target system
        master.target_component, # Target component
        stream_id,               # MAV_DATA_STREAM_ID
        rate,                    # Rate in Hz
        1                        # Start/stop (1 for start)
    )

def listen_for_messages(master):
    """
    Enters a loop to listen for and print incoming MAVLink messages.

    Args:
        master: The MAVLink connection object.
    """
    print("\n--- Starting to listen for messages ---")
    print("Press Ctrl+C to exit.")
    try:
        while True:
            # Wait for a new message
            msg = master.recv_match(blocking=True)

            # Check if a message was received
            if not msg:
                continue

            # Print the message type and its contents
            # You can filter for specific messages here
            msg_type = msg.get_type()
            
            # Example: Filter for ATTITUDE messages
            if msg_type == 'ATTITUDE':
                print(f"ATTITUDE: Roll={msg.roll:.2f}, Pitch={msg.pitch:.2f}, Yaw={msg.yaw:.2f}")

            # Example: Filter for GLOBAL_POSITION_INT (GPS data)
            elif msg_type == 'GLOBAL_POSITION_INT':
                print(f"GPS: Lat={msg.lat/1e7}, Lon={msg.lon/1e7}, Alt={msg.relative_alt/1000.0}m")
            
            # Example: Filter for VFR_HUD (Velocity, Altitude, etc.)
            elif msg_type == 'VFR_HUD':
                 print(f"VFR_HUD: Alt={msg.alt:.2f}m, Groundspeed={msg.groundspeed:.2f}m/s")
            
            # To see all messages, uncomment the line below
            # print(f"Received: {msg}")

            time.sleep(0.01) # Small delay to prevent busy-waiting

    except KeyboardInterrupt:
        print("\n--- Exiting message listener ---")
    except Exception as e:
        print(f"An error occurred while listening for messages: {e}")


if __name__ == "__main__":
    # --- Configuration ---
    # Serial port on Raspberry Pi.
    # For Raspberry Pi 5, this is typically '/dev/ttyAMA0'.
    # For Pi 3/4/Zero W, it can be '/dev/ttyS0' or '/dev/serial0'.
    # Ensure you have disabled the serial console in raspi-config
    SERIAL_PORT = '/dev/ttyAMA0' 
    #SERIAL_PORT = '/dev/ttyACM0' 


    # Baud rate for the telemetry port on your Pixhawk (usually 57600)
    BAUD_RATE = 57600
    #BAUD_RATE = 115200


    # --- Main Execution ---
    # 1. Connect to the Pixhawk
    connection = connect_to_pixhawk(SERIAL_PORT, BAUD_RATE)

    if connection:
        # 2. Request desired data streams
        # Here we request the 'extended status' stream which includes ATTITUDE
        # and the 'position' stream for GPS data.
        # Rates are in Hz. A rate of 2 means 2 messages per second.
        request_data_stream(connection, mavutil.mavlink.MAV_DATA_STREAM_EXTENDED_STATUS, 2)
        request_data_stream(connection, mavutil.mavlink.MAV_DATA_STREAM_POSITION, 2)
        
        # 3. Start listening for messages
        listen_for_messages(connection)

        # 4. Close the connection when done
        connection.close()
        print("Connection closed.")
