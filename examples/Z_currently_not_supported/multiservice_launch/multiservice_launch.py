import subprocess
import time

# To be called from the root of the repository
# python examples/multiservice_launch.py

# Define each service with its command and optional working directory
services = [
    {
        "name": "Launch Entity Core Docker",
        "command": ["make install",
                    "make run-docker"],
        "cwd": "../entitycore",
        "post_sleep_time": 5,
    },

    {
        "name": "Open EntitySDK",
        "command": ["open http://127.0.0.1:8000/docs"],
        "cwd": ".",
        "post_sleep_time": 1,
    },

    {
        "name": "Launch OBI-ONE Service",
        "command": ["make install",
                    "make run-docker"],
        "cwd": ".",
        "post_sleep_time": 1,
    },

    {
        "name": "Open OBI-ONE Service",
        "command": ["open http://127.0.0.1:8100/docs"],
        "cwd": ".",
        "post_sleep_time": 1,
    },

    {
        "name": "GUI",
        "command": ["make run-docker"],
        "cwd": "../obi-generative-gui",
        "post_sleep_time": 1,
    },

    {
        "name": "Open GUI",
        "command": ["open http://localhost:3000"],
        "cwd": ".",
        "post_sleep_time": 1,
    },
]


processes = []

try:
    for service in services:
        print(f"Launching {service['name']}...")

        command = " && ".join(service["command"])
        process = subprocess.Popen(
            command,
            cwd=service["cwd"],
            shell=True,
        )

        time.sleep(service["post_sleep_time"])

    print("All services launched. Press Ctrl+C to stop.")
    while True:
        time.sleep(1)

except KeyboardInterrupt:
    print("\nShutting down services...")
    for process in processes:
        process.terminate()
    for process in processes:
        process.wait()
    print("All services stopped.")
