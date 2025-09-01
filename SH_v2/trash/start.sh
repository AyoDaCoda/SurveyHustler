# #!/bin/bash

# # Start the Flask web server in the background
# echo "Starting Flask web server..."
# gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 &

# # Wait for the Flask server to be ready
# echo "Waiting for web server to be reachable on port $PORT..."
# while ! curl -s "http://localhost:$PORT" > /dev/null; do
#   sleep 1
# done
# echo "Web server is up! Starting bot..."

# # Start the Telegram bot
# python bot.py