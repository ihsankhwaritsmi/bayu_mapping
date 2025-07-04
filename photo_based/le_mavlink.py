from pymavlink import mavutil

# Connect via TCP to Mission Planner
print("Connecting to MAVLink over TCP...")
master = mavutil.mavlink_connection('tcp:127.0.0.1:5762')
master.wait_heartbeat()
print("Connected to system ID:", master.target_system)

# Step 1: Request mission list
master.waypoint_request_list_send()
mission_items = {}

# Step 2: Receive all mission items and store them
while True:
    msg = master.recv_match(type=['MISSION_COUNT', 'MISSION_ITEM'], blocking=True)
    
    if msg.get_type() == 'MISSION_COUNT':
        total_items = msg.count
        print(f"Receiving {total_items} mission items...")
    
    elif msg.get_type() == 'MISSION_ITEM':
        mission_items[msg.seq] = msg.command
        if len(mission_items) == total_items:
            print("All mission items received.")
            break

# Step 3: Monitor which item is reached
print("\nMonitoring DO_SET_CAM_TRIGG_DIST events...\n")
try:
    while True:
        msg = master.recv_match(type='MISSION_ITEM_REACHED', blocking=True)
        reached_seq = msg.seq

        # Check if the reached command is DO_SET_CAM_TRIGG_DIST (206)
        if mission_items.get(reached_seq) == mavutil.mavlink.MAV_CMD_DO_SET_CAM_TRIGG_DIST:
            print("DO_SET_CAM_TRIGG_DIST time to take photo")

except KeyboardInterrupt:
    print("Exited by user.")
