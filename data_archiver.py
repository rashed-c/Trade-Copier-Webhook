import os
import databento as db
from datetime import datetime, timedelta
import time
import signal
import shutil

# Create a directory for storing the archived data if it doesn't exist
archive_dir = "databento_archives"
os.makedirs(archive_dir, exist_ok=True)

# Flag to control the main loop
running = True

def signal_handler(signum, frame):
    global running
    print("Received signal to stop. Finishing current operation...")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def archive_data():
    global running
    while running:
        try:
            # Generate a filename using the current date
            current_date = datetime.now().strftime('%Y%m%d')
            start_time = datetime.now() - timedelta(hours=2)
            filename = f"ohlcv-1m_{current_date}.dbn"
            file_path = os.path.join(archive_dir, filename)

            # Check if the file already exists, and delete it if it does
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"Existing file {filename} has been deleted.")

            # Create a live client and connect
            live_client = db.Live(key="db-4cBdtNdAxE9CBR3HgFuqJDidcfbrL")

            # Subscribe to the ohlcv-1m schema for the symbols
            live_client.subscribe(
                dataset="GLBX.MDP3",
                schema="ohlcv-1m",
                stype_in="continuous",
                symbols=["MES.c.0", "MNQ.c.0", "MCL.c.0", "MGC.c.1"],
                start=start_time
            )

            # Open a file for writing and start streaming
            live_client.add_stream(file_path)
            live_client.start()

            # Run until stopped or an hour has passed
            # start_time = time.time()
            # while running and (time.time() - start_time) < 3600:  # Run for up to an hour
            #     time.sleep(10)  # Check every 10 seconds

            # live_client.stop()  # Ensure we stop the client after the loop

        except Exception as e:
            print(f"Error occurred: {e}")
            print("Attempting to reconnect in 60 seconds...")
            time.sleep(60)

if __name__ == "__main__":
    archive_data()
    print("Data archiving stopped.")