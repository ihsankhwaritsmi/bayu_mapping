# Pix2Rasp Documentation

Pix2Rasp is a system designed to integrate GoPro cameras with Mavlink SITL (Software In The Loop) for automated image capture during drone missions. This documentation provides instructions for setting up and running the system.

## 1. Prerequisites

### 1.1 Miniconda Setup (Recommended)

It is highly recommended to use Miniconda to manage your Python environment.

*   **Install Miniconda:** Download and install Miniconda from the official website: [Miniconda Installer](https://docs.conda.io/en/latest/miniconda.html)
*   **Create Conda Environment:**
    ```bash
    conda create -n pix2rasp_env python=3.13
    ```
*   **Activate Conda Environment:**
    ```bash
    conda activate pix2rasp_env
    ```

### 1.2 Python Dependencies

All required Python libraries are listed in `requirements.txt`.

*   **Install Dependencies:**
    ```bash
    pip install -r pix2rasp/requirements.txt
    ```

## 2. Mission Planner Setup (SITL Simulation)

This section guides you through setting up Mission Planner for SITL (Software In The Loop) simulation.

*   **Open Waypoint File:** Open the mission file located at `/mission_sample/TheGoatMission.waypoints`.
*   **Import Mission:** Import this mission into Mission Planner.
*   **Setup Simulation (SITL TCP):** Configure Mission Planner to use SITL with a TCP connection.

## 3. Running the Simulation (without GoPro)

This mode allows you to test the Mavlink integration and image capture logic using dummy JPG files.

*   **Run Simulation Script:**
    ```bash
    python pix2rasp/pix2rasp_sim.py
    ```
    This will start the simulation and verify the Mavlink connection.
*   **Set Mission Planner to Auto Mode:** In Mission Planner, set the drone's mode to "Auto".
*   **Verify Output:** Dummy JPG images should be generated and saved in the `gopro_captures` folder.
*   **Proceed:** Once this simulation runs successfully, you can proceed to integrate with a real GoPro.

### 3.1 GoPro Setup

Ensure your GoPro camera is properly set up for wired control.

*   **Connect GoPro:** Connect your GoPro camera to your laptop via a wired connection.
*   **Install `open_gopro` Library:** Verify that the `open_gopro` library is installed (it should be included in `requirements.txt`).
*   **Test GoPro Connection:** To confirm the GoPro is recognized and can capture photos, run the following command in your terminal:
    ```bash
    gopro-photo --wired
    ```
    This command should capture a photo and download it to your laptop.

## 4. Running with GoPro + Mavlink SITL

This section details how to run the system with a physical GoPro camera.

*   **Ensure GoPro is Connected:** Make sure your GoPro is connected to your laptop via a wired connection and the `gopro-photo --wired` test (from section 3.1) is successful.
*   **Run GoPro Integration Script:**
    ```bash
    python pix2rasp/pix2rasp_sim_gopro.py
    ```
*   **Restart Mission:** In Mission Planner, restart the mission to begin the automated photo capture process with your GoPro.
