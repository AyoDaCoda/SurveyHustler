#!/bin/bash

# Start the Flask web server in the background
gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 &

echo "Waiting for Flask server to start..."

# Wait for the Flask server to be ready by checking its health endpoint.
# We will assume a simple endpoint like `/` exists and responds.
# A `sleep` command is a simple and effective way to do this.
sleep 10

echo "Flask server should be ready. Starting bot..."

# Start the Telegram bot
python bot.py

# The script will continue to run as long as `bot.py` is running