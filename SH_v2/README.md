# SurveyHustler

![SurveyHustler Logo]

## 💡 Project Overview

SurveyHustler is a Telegram-based platform that connects survey requesters with a network of university students to get high-quality responses.

The platform provides a simple user flow:
- **For Requesters:** Users can upload survey details, define their target audience using filters, and pay to publish the survey. The system then automatically distributes the survey to the right audience.
- **For Respondents:** Students can complete surveys, earn cash rewards, and withdraw their earnings directly to their bank accounts.

## ✨ Key Features

- **Telegram Bot Integration:** A seamless user interface is provided via a Telegram bot for all core interactions.
- **Audience Filtering:** Requesters can specify their target audience by university, college, department, course, gender, and academic level.
- **Automated Survey Distribution:** Surveys are automatically shared with users who match the defined demographic filters.
- **Payment Processing:** Integrates with the Korapay payment gateway to handle secure survey uploads and user payouts.
- **Secure Authentication:** User data is managed securely via Telegram IDs and a robust backend.
- **Database Management:** Uses PostgreSQL to store user profiles, survey details, and transaction history.
- **AI-powered Survey Analysis:** (Future Feature)

## 🛠️ Technology Stack

- **Backend:** Flask (Python)
- **Database:** PostgreSQL
- **Telegram Bot API:** `python-telegram-bot`
- **Payment Gateway:** Korapay
- **Hosting:** Currently deployed with Ngrok for development. (Transitioning to a production server for wider use)
- **Environment Management:** `python-dotenv` for managing sensitive API keys and secrets.
- **Frontend (for survey details):** HTML, CSS, JavaScript

## 🚀 Getting Started

To get a local copy up and running, follow these steps.

### Prerequisites

- Python 3.8+
- PostgreSQL
- `pip`
- A Telegram bot token from BotFather
- Korapay API keys
- A Google Service Account credentials file for Google Sheets/Forms access.

### Installation

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/AyoDaCoda/surveyhustler.git](https://github.com/AyoDaCoda/surveyhustler.git)
    cd surveyhustler
    ```
2.  **Create a virtual environment and activate it:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Set up environment variables:**
    Create a file named `surveyhustler.env` in the root directory and add your secrets:
    ```ini
    TELEGRAM_BOT_TOKEN="<your_token>"
    SERVER_URL="<your_ngrok_or_server_url>"
    DATABASE_URL="postgresql://<user>:<password>@<host>:<port>/<db_name>"
    FLASK_SECRET_KEY="<your_flask_secret>"
    EMAIL_USER="<your_email>"
    EMAIL_PASS="<your_app_password>"
    GOOGLE_CREDENTIALS_PATH="<path_to_your_json_file>"
    GENAI_API_KEY="<your_genai_key>"
    KORAPAY_PUBLIC_KEY="<your_korapay_public_key>"
    KORAPAY_SECRET_KEY="<your_korapay_secret_key>"
    ```
5.  **Set up your database:**
    Initialize and run migrations to create the database tables. (Requires `flask-migrate`)
    ```bash
    flask db init
    flask db migrate -m "Initial migration."
    flask db upgrade
    ```
6.  **Run the application:**
    ```bash
    python app.py
    python bot.py
    ```

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.

## 🤝 Contact

Your Name - 
[@ayomideabod - telegram]

Project Link: [https://github.com/AyoDaCoda/surveyhustler](https://github.com/AyoDaCoda/surveyhustler)