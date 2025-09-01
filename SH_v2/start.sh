#!/bin/bash

# Start the Flask web server
gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 &

# Start the Telegram bot
python bot.py &

# Keep the script running
wait