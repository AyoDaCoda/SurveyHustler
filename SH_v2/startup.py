import subprocess
import time
import requests
import os

# Start the Gunicorn web server in a separate process
print("Starting Flask web server...")
web_server_process = subprocess.Popen(["gunicorn", "app:app", "--bind", f"0.0.0.0:{os.getenv('PORT')}", "--workers", "2"])

# Wait for the web server to be reachable
server_is_ready = False
max_retries = 30
retries = 0

print("Waiting for web server to be ready...")
while not server_is_ready and retries < max_retries:
    try:
        # We use localhost to check if the server is up internally
        requests.get(f"http://localhost:{os.getenv('PORT')}")
        server_is_ready = True
    except requests.exceptions.ConnectionError:
        print("Server not ready, retrying in 1 second...")
        time.sleep(1)
        retries += 1

if not server_is_ready:
    print("Web server did not start. Exiting.")
    exit(1)

print("Web server is up! Starting bot...")

# Start the bot.py script as the main process
subprocess.run(["python", "bot.py"])

# Wait for the bot process to finish (it will not) to keep the container alive
web_server_process.wait()