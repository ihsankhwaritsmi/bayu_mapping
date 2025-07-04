import time
from pymavlink import mavutil

# Connect to the Vehicle (Mission Planner SITL default connection)
# The connection string 'tcp:127.0.0.1:5762' connects to the MAVLink stream
# that Mission Planner's SITL outputs by default.
try:
    vehicle = mavutil.mavlink_connection('tcp:127.0.0.1:5762', wait_ready=True)
    print("Successfully connected to vehicle.")
except Exception as e:
    print(f"Failed to connect: {e}")
    exit()


# Wait for the first heartbeat message to confirm a connection
vehicle.wait_heartbeat()
print("Heartbeat from system (system %u component %u)" % (vehicle.target_system, vehicle.target_component))

# Loop to read and print specific MAVLink messages
while True:
    try:
        # Check for GLOBAL_POSITION_INT message which contains altitude
        msg = vehicle.recv_match(type='GLOBAL_POSITION_INT', blocking=True, timeout=3)
        if msg:
            # Altitude is in millimeters, convert to meters
            altitude_m = msg.relative_alt / 1000.0
            print(f"Current Altitude: {altitude_m:.2f} meters")

        time.sleep(1) # Wait for a second before checking again

    except KeyboardInterrupt:
        print("\nExiting script.")
        break
    except Exception as e:
        print(f"An error occurred: {e}")
        break