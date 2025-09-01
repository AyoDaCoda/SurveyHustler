import requests
from telegram import (
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters, CallbackQueryHandler,
)
from telegram.helpers import escape_markdown
from datetime import datetime, timezone

SERVER_URL = "https://2dd3d5aa0786.ngrok-free.app"
users_cache = {}
user_survey_sessions = {}
user_ai_sessions = {}
SURVEYS_PER_PAGE = 5  # You can adjust this number

NICHE_EDIT_STAGE_GENDER = 1
NICHE_EDIT_STAGE_OPTION = 2
NICHE_EDIT_STAGE_PAYMENT = 3
NICHE_EDIT_STAGE_COMPLETE = 4

COST_OF_NICHE_CHANGES = 2000

user_conversations = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    try:
        response = requests.get(f"{SERVER_URL}/api/check_user/{user_id}")
        data = response.json()
    except Exception:
        await update.message.reply_text("❗ Server connection error.")
        return

    if not data.get("registered"):
        await update.message.reply_text(
            f"🚫 You are not registered.\nPlease register here: {SERVER_URL}/register?tg_id={user_id}"
        )
        return

    users_cache[user_id] = data["user"]

    keyboard = [
        [KeyboardButton("📝 Answer Surveys"), KeyboardButton("💰 Redeem Cash")],
        [KeyboardButton("📊 View My Surveys"), KeyboardButton("🛠️ Customer Support")],
        [KeyboardButton("📤 Upload Surveys")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("🎉 Welcome back! Choose an option:", reply_markup=reply_markup)

# --- NEW HELPER FUNCTION TO GET PAGINATED SURVEYS ---
def get_paginated_survey_message_and_keyboard(tg_id, page=0):
    try:
        res = requests.get(f"{SERVER_URL}/api/eligible_surveys/{tg_id}")
        if res.status_code != 200:
            return "No surveys available at this time.", None

        all_surveys = res.json().get('surveys', [])

        # Store all surveys in the session for pagination
        user_survey_sessions.setdefault(tg_id, {})['eligible_surveys'] = all_surveys
        user_survey_sessions.setdefault(tg_id, {})['page'] = page

        if not all_surveys:
            return "📭 No surveys available for your niche.", None

        start_index = page * SURVEYS_PER_PAGE
        end_index = start_index + SURVEYS_PER_PAGE
        surveys_to_display = all_surveys[start_index:end_index]

        message_text = "Here are the surveys you are eligible for:\n\n"
        keyboard = []

        for survey in surveys_to_display:
            message_text += (
                f"<b>{survey['title']}</b>\n"
                f"  └ Reward: ₦{survey['reward']} | Duration: {survey['duration']}m\n"
                f"  └ Responses: {survey['responses']}/{survey['target']}\n\n"
            )
            keyboard.append([InlineKeyboardButton(
                f"✅ Check '{survey['title']}'",
                callback_data=f"check_survey:{survey['survey_id']}"
            )])

        # Add pagination buttons
        pagination_buttons = []
        if page > 0:
            pagination_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"page_surveys:{page - 1}"))
        if end_index < len(all_surveys):
            pagination_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"page_surveys:{page + 1}"))

        if pagination_buttons:
            keyboard.append(pagination_buttons)

        reply_markup = InlineKeyboardMarkup(keyboard)
        return message_text, reply_markup

    except Exception as e:
        print(f"Error fetching surveys: {e}")
        return "An error occurred while fetching surveys.", None

def get_filter_options():
    try:
        courses_res = requests.get(f"{SERVER_URL}/api/courses")
        levels_res = requests.get(f"{SERVER_URL}/api/levels")

        courses = courses_res.json().get('courses', [])
        levels = levels_res.json().get('levels', [])

        # Add "Everyone" as an option at the beginning of the lists
        courses.insert(0, {'id': None, 'name': 'Everyone'})
        levels.insert(0, {'id': None, 'name': 'Everyone'})

        return courses, levels
    except Exception as e:
        print(f"Error fetching filter options: {e}")
        return [], []

async def handle_all_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Check if the user is in an active AI session
    if user_id in user_ai_sessions:
        await handle_ai_chat(update, context)
    else:
        # If not in an AI session, route to the main menu handler
        await handle_menu(update, context)

# --- MODIFIED HELPER FUNCTION TO ADD BACK BUTTON ---
def get_survey_details_message_and_keyboard(survey_data):
    title = survey_data.get('title')
    description = survey_data.get('description')
    reward = survey_data.get('reward')
    duration = survey_data.get('duration')

    message_text = (
        f"<b>Survey: {title}</b>\n\n"
        f"<b>Description:</b> {description}\n"
        f"<b>Reward:</b> ₦{reward}\n"
        f"<b>Duration:</b> {duration} minutes\n"
        "To answer this survey, click the button below."
    )

    keyboard = [
        [InlineKeyboardButton(
            f"📝 Go to Survey",
            url=survey_data['responder_link']
        )],
        [InlineKeyboardButton(
            "✅ Confirm Entry",
            callback_data=f"confirm_entry:{survey_data['survey_id']}"
        )],
        # --- NEW: BACK TO SURVEYS BUTTON ---
        [InlineKeyboardButton(
            "⬅️ Back to Surveys",
            callback_data="back_to_surveys"
        )]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    return message_text, reply_markup

# --- MODIFIED handle_menu FUNCTION ---
async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_cache:
        await update.message.reply_text("❗ Please use /start to begin.")
        return

    if update.message:
        user_text = update.message.text
        reply_target = update.message
    elif update.callback_query:
        user_text = update.callback_query.data
        reply_target = update.callback_query.message
    else:
        user_text = ""
        reply_target = None

    if user_text == "📤 Upload Surveys":
        # ... (rest of your code for this section) ...
        if reply_target:
            await reply_target.reply_text("Opening upload page...")

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Click the button below to upload your survey:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Open Upload Page", url=f"{SERVER_URL}/upload_survey_login?tg_id={user_id}")]
            ])
        )


    elif user_text == "📊 View My Surveys":

        user_id = update.effective_user.id
        try:
            res = requests.get(f"{SERVER_URL}/api/my_surveys/{user_id}")
            surveys = res.json()
            if not surveys:
                await update.message.reply_text("📭 You have not uploaded any surveys yet.")
            else:
                # Build a single message for all surveys
                message_text = "📊 Here are your uploaded surveys:\n\n"
                keyboard = []
                for survey in surveys:
                    message_text += (
                        f"*{escape_markdown(survey['title'], version=2)}*\n"
                        f"📝 Responses: {escape_markdown(str(survey['responses']), version=2)}\n\n"
                    )
                    keyboard.append([InlineKeyboardButton(f"Manage '{survey['title']}'",
                                                          callback_data=f"manage_my_survey:{survey['id']}")])

                    reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    text=message_text,
                    parse_mode="MarkdownV2",
                    reply_markup=reply_markup
                )

        except Exception as e:
            print("[View My Surveys Error]", e)
            await update.message.reply_text(
                "❌ Failed to fetch your surveys. Retry or seek support at @surveyhustler_cs")

    elif user_text == "📝 Answer Surveys":
        user_id = update.effective_user.id
        try:
            # Get the first page of surveys
            message_text, reply_markup = get_paginated_survey_message_and_keyboard(user_id)
            await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='HTML')

        except Exception:
            await update.message.reply_text("❌ Failed to fetch available surveys.")
            await show_main_menu(update)
    else:
        if reply_target:
            await reply_target.reply_text("⚠️ Feature not yet implemented.")

async def show_main_menu(update: Update):
    # ... (rest of your code for this section) ...
    keyboard = [
        [KeyboardButton("📝 Answer Surveys"), KeyboardButton("💰 Redeem Cash")],
        [KeyboardButton("📊 View My Surveys"), KeyboardButton("🛠️ Customer Support")],
        [KeyboardButton("📤 Upload Surveys")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("🎯 What would you like to do next?", reply_markup=reply_markup)

async def get_my_survey_details_message_and_keyboard(survey):
    escaped_title = escape_markdown(survey.get('title', 'N/A'), version=2)
    escaped_responses = escape_markdown(str(survey.get('responses', 0)), version=2)
    escaped_target = escape_markdown(str(survey.get('target', 0)), version=2)
    escaped_niche = escape_markdown(survey.get('niche', 'Everyone'), version=2)
    escaped_levels = escape_markdown(survey.get('levels', 'Everyone'), version=2)
    escaped_form_link = escape_markdown(survey.get('responder_link', 'N/A'), version=2)

    raw_created_at = survey.get('created_at')
    if raw_created_at:
        try:
            # Handle potential ISO format with timezone
            created_at_dt = datetime.fromisoformat(raw_created_at.replace('Z', '+00:00'))

            # Change the format to dd/mm/yyyy
            formatted_date = created_at_dt.strftime('%d/%m/%Y')
            escaped_created_at = escape_markdown(formatted_date, version=2)
        except ValueError:
            escaped_created_at = escape_markdown(raw_created_at, version=2)
    else:
        escaped_created_at = escape_markdown("N/A", version=2)

    message_text = (
        f"📊 *{escaped_title}*\n"
        f"📝 Responses: {escaped_responses}/{escaped_target}\n"
        f"🔗 Form Link: {escaped_form_link}\n"
        f"🗓️ Uploaded: {escaped_created_at}\n\n"
        f"🎯 Niche: {escaped_niche}\n"
        f"🎓 Level: {escaped_levels}"
    )

    keyboard = [
        [
            InlineKeyboardButton("✏️ Edit Niche", callback_data=f"edit_niche:{survey['id']}"),
            InlineKeyboardButton("📊 Analyse with AI", callback_data=f"analyse_ai:{survey['id']}"),
        ],
        [
            InlineKeyboardButton("🗑️ Discontinue Survey", callback_data=f"discontinue_survey_confirm:{survey['id']}"),
        ],
        [
            InlineKeyboardButton("⬅️ Back to My Surveys", callback_data="back_to_my_surveys")
        ]
    ]

    return message_text, InlineKeyboardMarkup(keyboard)

async def handle_ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message_text = update.message.text.strip()

    # FIX: Add a check for empty message text to prevent errors
    if not message_text:
        return  # Do nothing if the message is empty

    # Check if the user is in an active AI session
    if user_id not in user_ai_sessions:
        return  # Let the next handler process the message

    # Check for the stop command
    if message_text.lower() == '/stop':
        del user_ai_sessions[user_id]
        await update.message.reply_text("👋 Conversation ended. Returning to the main menu.",
                                        reply_markup=get_main_menu_keyboard())
        return

    session = user_ai_sessions[user_id]

    # Send user's query and survey data to the backend
    try:
        response = requests.post(
            f"{SERVER_URL}/api/ai_chat/{session['survey_id']}",
            json={
                'tg_id': user_id,
                'user_query': message_text,
                'survey_data': session['data'],
                'conversation_history': session['history']
            }
        )
        result = response.json()

        if response.status_code == 200:
            analysis_text = result.get('analysis', 'I could not generate an analysis for that query.')
            await update.message.reply_text(analysis_text)

            # Update the conversation history
            session['history'].append({'role': 'user', 'parts': [message_text]})
            session['history'].append({'role': 'model', 'parts': [analysis_text]})

        else:
            await update.message.reply_text(f"❌ An error occurred: {result.get('error', 'Unknown error')}")

    except Exception as e:
        print(f"Error communicating with AI backend: {e}")
        await update.message.reply_text("❌ An error occurred while processing your request. Please try again.")

def get_main_menu_keyboard():
    keyboard = [
        [KeyboardButton("📝 Answer Surveys"), KeyboardButton("💰 Redeem Cash")],
        [KeyboardButton("📊 View My Surveys"), KeyboardButton("🛠️ Customer Support")],
        [KeyboardButton("📤 Upload Surveys")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)


# --- MODIFIED handle_callback FUNCTION ---
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data.startswith("check_survey:"):
        survey_id = int(data.split(":", 1)[1])

        # Fetch full survey info from the backend using the ID
        res = requests.get(f"{SERVER_URL}/api/survey_by_id/{survey_id}")
        survey = res.json()

        if "error" in survey:
            await query.edit_message_text(f"🚫 Error fetching survey details: {survey['error']}")
            return

        # Use .get() to safely access keys and avoid a KeyError
        responder_link = survey.get("responder_link")
        sheet_link = survey.get("sheet_link")
        is_verified = False

        # Edit the message to show "Verifying access..."
        await query.edit_message_text("⏳ Verifying access to the survey response sheet...")

        if sheet_link:
            try:
                verify_res = requests.post(
                    f"{SERVER_URL}/api/verify_sheet_access",
                    json={"sheet_link": sheet_link}
                )
                verify_result = verify_res.json()

                if verify_result.get("verified"):
                    is_verified = True
                    print(f"DEBUG: Backend confirmed sheet access for survey ID {survey_id}")
                else:
                    print(
                        f"ERROR: Backend failed to confirm sheet access for survey ID {survey_id}. Reason: {verify_result.get('reason', 'Unknown')}")
            except requests.exceptions.ConnectionError as e:
                print(f"ERROR: Bot could not connect to Flask backend for sheet verification: {e}")
                await query.edit_message_text(
                    "❌ There was a problem connecting to the server. Please try again later."
                )
                return
            except Exception as e:
                print(f"ERROR: Failed to access sheet {sheet_link} for survey ID {survey_id}: {e}")
                is_verified = False
        else:
            print(f"WARN: Survey ID {survey_id} has no sheet_link defined.")
            await query.edit_message_text(
                "🚫 Survey is unavailable: Missing response sheet link."
            )
            return

        if is_verified:
            # Store session data
            user_survey_sessions.setdefault(user_id, {})
            user_survey_sessions[user_id]['last_survey_id'] = survey_id
            user_survey_sessions[user_id]['last_form_link'] = responder_link
            user_survey_sessions[user_id]['start_time'] = datetime.now(timezone.utc).isoformat()

            message_text, reply_markup = get_survey_details_message_and_keyboard(survey)
            await query.edit_message_text(
                text=message_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        else:
            await query.edit_message_text(
                "🚫 Survey is no longer available (sheet access failed)."
            )

    elif data.startswith('page_surveys:'):
        page = int(data.split(':')[1])
        message_text, reply_markup = get_paginated_survey_message_and_keyboard(user_id, page)
        await query.edit_message_text(
            text=message_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    elif data == "back_to_surveys":
        page = user_survey_sessions.get(user_id, {}).get('page', 0)
        message_text, reply_markup = get_paginated_survey_message_and_keyboard(user_id, page)

        await query.edit_message_text(
            text=message_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    elif data.startswith("confirm_entry:"):

        survey_id = int(data.split(':')[1])
        print("DEBUG: Survey id = ", survey_id)

        # Fetch the survey details from the backend to ensure we have the correct form link

        res = requests.get(f"{SERVER_URL}/api/survey_by_id/{survey_id}")

        survey = res.json()

        if "error" in survey:
            await query.edit_message_text(f"🚫 Error confirming entry: Could not find survey details.")

            return

        session = user_survey_sessions.get(user_id)

        if not session or session.get('last_survey_id') != survey_id:
            await query.edit_message_text("Session expired or invalid. Please check a survey again.")

            return

        await query.edit_message_text("⏳ Confirming if entry has been taken...")

        # We now use the form_link from the newly fetched survey, not the session

        payload = {

            "tg_id": user_id,

            "form_link": survey["responder_link"],  # Use the link from the fresh API call

            "start_time": session["start_time"]

        }

        print(f"Sending check_entry for {payload}")

        res = requests.post(f"{SERVER_URL}/api/check_entry", json=payload)

        result = res.json()

        if result.get("verified"):

            reward = result.get("reward")

            await query.edit_message_text(

                text=f"🎉 Entry verified!\nYou just earned ₦{reward}!",

                reply_markup=InlineKeyboardMarkup([

                    [InlineKeyboardButton("📝 Answer More Surveys", callback_data="back_to_surveys")],

                    [InlineKeyboardButton("💰 Redeem Cash", callback_data="redeem_cash")]

                ])

            )

        else:

            reason = result.get("reason", "Unknown reason.")

            await query.edit_message_text(

                text=f"❌ Entry not verified, survey {survey_id}.\nWhy? {reason}",

                reply_markup=InlineKeyboardMarkup([

                    [InlineKeyboardButton("📋 Return to Available Surveys", callback_data="back_to_surveys")],

                    [InlineKeyboardButton("🛠 Customer Support", callback_data="customer_support")]

                ])

            )

    elif data == "back_to_menu":
        await show_main_menu(update)

    # Add this new handler for "manage my survey"
    elif data.startswith("manage_my_survey:"):
        survey_id = int(data.split(":", 1)[1])
        try:
            res = requests.get(f"{SERVER_URL}/api/my_survey_by_id/{survey_id}?tg_id={user_id}")
            survey = res.json()
            if not survey or 'error' in survey:
                await query.edit_message_text("❌ Survey not found or an error occurred.")
                return

            message_text, reply_markup = await get_my_survey_details_message_and_keyboard(survey)
            await query.edit_message_text(
                text=message_text,
                parse_mode="MarkdownV2",
                reply_markup=reply_markup
            )
        except Exception as e:
            print(f"[Manage My Survey Error] {e}")
            await query.edit_message_text("❌ An error occurred while fetching survey details.")

    # Modify the existing "discontinue_survey_confirm" logic
    elif data.startswith("discontinue_survey_confirm:"):
        survey_id = data.split(":")[1]
        keyboard = [
            [
                InlineKeyboardButton("✅ Yes, Discontinue", callback_data=f"discontinue_survey:{survey_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"manage_my_survey:{survey_id}")
            ]
        ]
        await query.edit_message_text(
            "⚠️ Are you sure you want to discontinue this survey? This action is irreversible.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("edit_niche:"):
        survey_id = int(data.split(':')[1])
        try:
            response = requests.get(f"{SERVER_URL}/api/get_survey_details/{survey_id}", json={'tg_id': user_id})
            survey_details = response.json().get('survey', {})
            niche_str = survey_details.get('niche', 'Everyone')
            niche_list = [n.strip() for n in niche_str.split(',')]

            # Check if the niche is "Everyone"
            if len(niche_list) == 1 and niche_list[0].lower() == 'everyone':
                message = "You cannot edit the niche for surveys targeted at 'Everyone'."
                keyboard = [
                    [InlineKeyboardButton("⬅️ Back to Survey Details",
                                          callback_data=f"manage_my_survey:{survey_id}")]
                ]

                await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
                return

            # Store the survey details and niches
            user_conversations[user_id] = {
                'survey_id': survey_id,
                'niches': niche_list,
                'raw_filters': survey_details.get('raw_filters', []),
                'chosen_gender': None,
                'chosen_option': None,
                'selected_niche_index': None
            }

            # If there are multiple niches, ask the user to select one
            if len(niche_list) > 1:
                message = "This survey has multiple niches. Please select the one you would like to edit."
                keyboard_buttons = [
                    [InlineKeyboardButton(niche, callback_data=f"select_niche_to_edit:{i}:{survey_id}")]
                    for i, niche in enumerate(niche_list)
                ]
                keyboard_buttons.append(
                    [InlineKeyboardButton("⬅️ Go Back", callback_data=f"manage_my_survey:{survey_id}")])
                await query.edit_message_text(
                    message,
                    reply_markup=InlineKeyboardMarkup(keyboard_buttons)
                )

            else:
                # If only one niche, skip straight to the confirmation message
                user_conversations[user_id]['selected_niche_index'] = 0
                message = (
                    "⚠️ *Attention: Editing a survey's niche incurs an additional cost of N2,000\\.*"
                    "\n\n You can only change the *gender* and the *option* for your current filter type\\."
                    " You cannot change the filter type itself\\."
                    "\n\nWould you like to proceed?"
                )

                keyboard = [
                    [InlineKeyboardButton("✅ Continue", callback_data=f"start_niche_edit:{survey_id}")],
                    [InlineKeyboardButton("⬅️ Go Back", callback_data=f"manage_my_survey:{survey_id}")]
                ]

                await query.edit_message_text(
                    message,
                    parse_mode='MarkdownV2',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )


        except Exception as e:
            print(f"Error initiating niche edit: {e}")
            await query.edit_message_text("❌ An error occurred. Please try again later.")
            if user_id in user_conversations:
                del user_conversations[user_id]

    elif data.startswith("select_niche_to_edit:"):

        _, index, survey_id = data.split(':')

        survey_id = int(survey_id)

        user_id = query.from_user.id

        if user_id not in user_conversations or user_conversations[user_id]['survey_id'] != survey_id:
            await query.edit_message_text("❌ Session expired. Please start over.")

            return

        user_conversations[user_id]['selected_niche_index'] = int(index)

        message = (
            "⚠️ *Attention: Editing a survey's niche incurs an additional cost of N2,000\\.*"
            "\n\n You can only change the *gender* and the *option* for your current filter type\\."
            " You cannot change the filter type itself\\."
            "\n\nWould you like to proceed?"
        )

        keyboard = [
            [InlineKeyboardButton("✅ Continue", callback_data=f"start_niche_edit:{survey_id}")],
            [InlineKeyboardButton("⬅️ Go Back", callback_data=f"manage_my_survey:{survey_id}")]
        ]

        await query.edit_message_text(
            message,
            parse_mode='MarkdownV2',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("start_niche_edit:"):

        survey_id = int(data.split(':')[1])

        user_id = query.from_user.id

        if user_id not in user_conversations or user_conversations[user_id]['survey_id'] != survey_id:
            await query.edit_message_text("❌ Session expired. Please start over.")

            return

        # Prompt user to select a new gender

        message = "Please select the new gender for your survey:"

        keyboard = InlineKeyboardMarkup([

            [InlineKeyboardButton("👦 Male", callback_data=f"niche_gender:Male:{survey_id}")],

            [InlineKeyboardButton("👧 Female", callback_data=f"niche_gender:Female:{survey_id}")],

            [InlineKeyboardButton("🚻 Both", callback_data=f"niche_gender:Both:{survey_id}")]

        ])

        await query.edit_message_text(message, reply_markup=keyboard)

    elif data.startswith("niche_gender:"):

        _, gender, survey_id = data.split(':')
        survey_id = int(survey_id)
        user_id = query.from_user.id
        if user_id not in user_conversations or user_conversations[user_id]['survey_id'] != survey_id:
            await query.edit_message_text("❌ Session expired. Please start over.")
            return

        user_conversations[user_id]['chosen_gender'] = gender

        selected_niche_index = user_conversations[user_id]['selected_niche_index']
        if selected_niche_index is None:
            await query.edit_message_text("❌ An error occurred. Please go back to survey details.")
            return

        raw_filter_data = user_conversations[user_id]['raw_filters'][selected_niche_index]
        filter_by = raw_filter_data.get('filter_by', 'N/A')

        try:
            response = requests.get(f"{SERVER_URL}/api/get_niche_options/{filter_by}")
            options = response.json().get('options', [])

            message = f"Please select the new option for the '{filter_by}' filter:"
            keyboard_buttons = [
                [InlineKeyboardButton(option['name'],
                                      callback_data=f"niche_option:{option['name']}:{option['value']}:{survey_id}")]
                for option in options
            ]
            keyboard_buttons.append([InlineKeyboardButton("⬅️ Back", callback_data=f"start_niche_edit:{survey_id}")])

            await query.edit_message_text(
                message,
                reply_markup=InlineKeyboardMarkup(keyboard_buttons)
            )

        except Exception as e:
            print(f"Error fetching niche options: {e}")
            await query.edit_message_text("❌ An error occurred while fetching options. Please try again later.")

    elif data.startswith("niche_option:"):

        _, option_name, option_id, survey_id = data.split(':')
        survey_id = int(survey_id)
        user_id = query.from_user.id

        if user_id not in user_conversations or user_conversations[user_id]['survey_id'] != survey_id:
            await query.edit_message_text("❌ Session expired. Please start over.")
            return

        user_conversations[user_id]['chosen_option'] = option_name
        user_conversations[user_id]['chosen_option_id'] = option_id

        message = (
            f"💰 *Payment Breakdown*\n"
            f"Cost to apply changes: N{COST_OF_NICHE_CHANGES:,}\n"
            f"\nNew Niche:\n"
            f"\\- Gender: {user_conversations[user_id]['chosen_gender']}\n"
            f"\\- Option: {user_conversations[user_id]['chosen_option']}\n"
            f"\nClick 'Pay' to confirm and apply changes\\."
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Pay N2,000", callback_data=f"niche_payment:{survey_id}")],
            [InlineKeyboardButton("⬅️ Back",
                                  callback_data=f"niche_gender:{user_conversations[user_id]['chosen_gender']}:{survey_id}")]
        ])

        await query.edit_message_text(message, parse_mode='MarkdownV2', reply_markup=keyboard)

    elif data.startswith("niche_payment:"):

        survey_id = int(data.split(':')[1])
        user_id = query.from_user.id
        if user_id not in user_conversations or user_conversations[user_id]['survey_id'] != survey_id:
            await query.edit_message_text("❌ Session expired. Please start over.")
            return

        await query.edit_message_text("🔄 Processing payment...")

        try:
            selected_niche_index = user_conversations[user_id]['selected_niche_index']
            current_filter_data = user_conversations[user_id]['raw_filters'][selected_niche_index]

            updated_niches_list = [{
                'current_filter_data': current_filter_data,
                'new_gender': user_conversations[user_id]['chosen_gender'],
                'new_option_id': user_conversations[user_id]['chosen_option_id']
            }]

            # Send the final request to the backend to update the niche
            response = requests.post(
                f"{SERVER_URL}/api/update_multiple_niches/{survey_id}",
                json={
                    'tg_id': user_id,
                    'updated_niches': updated_niches_list
                }
            )

            result = response.json()

            if response.status_code == 200:
                await query.edit_message_text(
                    "✅ Niche updated successfully!",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton(
                            "⬅️ Back to Survey Details",
                            callback_data=f"manage_my_survey:{survey_id}"
                        )]
                    ])
                )
            else:
                await query.edit_message_text(
                    f"❌ Payment failed or an error occurred: {result.get('error', 'Unknown error')}")

        except Exception as e:
            print(f"Error updating niche: {e}")
            await query.edit_message_text("❌ An error occurred during payment. Please try again.")

        # Clean up the conversation state

        if user_id in user_conversations:
            del user_conversations[user_id]

    elif data.startswith("discontinue_survey:"):
        survey_id = int(data.split(':')[1])
        try:
            res = requests.delete(f"{SERVER_URL}/api/delete_survey/{survey_id}")
            if res.status_code == 200:
                await query.edit_message_text("✅ Survey discontinued successfully.")
            else:
                # The backend sent an error, so we display the error message.
                result = res.json()
                await query.edit_message_text(f"❌ An error occurred: {result.get('error', 'Unknown error')}")
        except Exception as e:
            print(f"Error discontinuing survey: {e}")
            await query.edit_message_text(
                "❌ An error occurred while trying to discontinue the survey. Please try again later.")

    # Add the new "back to my surveys" handler
    elif data == "back_to_my_surveys":
        user_id = query.from_user.id
        try:
            res = requests.get(f"{SERVER_URL}/api/my_surveys/{user_id}")
            surveys = res.json()
            if not surveys:
                await query.edit_message_text("📭 You have not uploaded any surveys yet.")
            else:
                message_text = "📊 Here are your uploaded surveys:\n\n"
                keyboard = []
                for survey in surveys:
                    responses_so_far = survey.get('responses', 0)
                    target_responses = survey.get('target', 0)
                    message_text += (
                        f"*{escape_markdown(survey['title'], version=2)}*\n"
                        f"📝 Responses: {escape_markdown(str(responses_so_far), version=2)} / {escape_markdown(str(target_responses), version=2)}\n\n"
                    )
                    keyboard.append([InlineKeyboardButton(f"Manage '{survey['title']}'",
                                                          callback_data=f"manage_my_survey:{survey['id']}")])

                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    text=message_text,
                    parse_mode="MarkdownV2",
                    reply_markup=reply_markup
                )
        except Exception as e:
            print("[Back to My Surveys Error]", e)
            await query.edit_message_text("❌ Failed to fetch your surveys. Retry or seek support.")

    elif data.startswith("cancel_discontinue:"):
        await query.edit_message_text("Discontinuation cancelled.")
        await query.answer()
        await show_main_menu(update)

    elif data == "redeem_cash":
        await query.edit_message_text("💰 Redeem functionality coming soon!")
    elif data == "customer_support":
        await query.edit_message_text("🛠 Please contact support@example.com")
    elif data.startswith("analyse_ai:"):
        survey_id = int(data.split(':')[1])

        # Fetch survey data once and store it in the session
        try:
            res = requests.post(f"{SERVER_URL}/api/get_survey_data/{survey_id}", json={'tg_id': user_id})
            result = res.json()
            if res.status_code != 200 or 'error' in result:
                await query.edit_message_text(
                    f"❌ An error occurred: {result.get('error', 'Could not get survey data')}")
                return

            # Cache the data and initialize conversation history
            user_ai_sessions[user_id] = {
                'survey_id': survey_id,
                'data': result['data'],
                'title': result['title'],
                'description': result['description'],
                'history': []
            }

            # Start the AI session
            message_text = escape_markdown(
                f"🧠 AI Survey Analyst Activated! 🧠\n\n"
                f"Hello! I am ready to help you analyze your survey data titled: {result['title']}.\n"
                "You can ask me questions like:\n\n"
                "- What is the average age of respondents?\n"
                "- Which course had the most responses?\n"
                "- What is the most common answer to the question 'What is your biggest challenge?'\n\n"
                "Type your question below, or type /stop to return to the main menu.",
                version=2
            )
            await query.edit_message_text(message_text, parse_mode='MarkdownV2')
        except Exception as e:
            print(f"Error initiating AI session: {e}")
            await query.edit_message_text("❌ An error occurred while starting the AI session.")


# bot.py
def main():
    app = ApplicationBuilder().token("8014493565:AAGo_N64xG2Sz2hxNkXy0Ky4PhNdecwssNk").build()

    # Command Handlers should always be at the top to have priority
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", handle_ai_chat))

    # This single handler will now correctly route all text messages
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_all_text_messages))

    # Callback queries from inline buttons
    app.add_handler(CallbackQueryHandler(handle_callback))

    print("🤖 Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()