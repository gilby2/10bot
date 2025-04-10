import os
import logging
import time
from datetime import datetime, timedelta
import schedule
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext, MessageHandler, Filters
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium_stealth import stealth
import undetected_chromedriver as uc
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# Get environment variables
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_TOKEN = "7564884815:AAEN3A5NXZAgMf3zCSVh6SK8n57nOUeHXsc"
TENBIT_USERNAME = os.getenv('TENBIT_USERNAME')
TENBIT_USERNAME = "gil.b@tevel-tech.com"
TENBIT_PASSWORD = os.getenv('TENBIT_PASSWORD')
TENBIT_PASSWORD = "Gby9973290"
USER_CHAT_ID = os.getenv('USER_CHAT_ID')  # Your Telegram chat ID
USER_CHAT_ID = "782604487"

# Global variables
daily_question_sent = False
chrome_options = Options()
# chrome_options.add_argument("--headless")  # Run in headless mode
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--start-maximized")


# chrome_options = uc.ChromeOptions()
# chrome_options.add_argument("--disable-blink-features=AutomationControlled")
# chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
# chrome_options.add_experimental_option("useAutomationExtension", False)

def start(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /start is issued."""
    update.message.reply_text('שלום! אני בוט שיזכיר לך להטעין את כרטיס תן ביס.')
    context.user_data['chat_id'] = update.effective_chat.id
    logger.info(f"Bot started. Chat ID: {update.effective_chat.id}")
    ask_working_status(context)


def ask_working_status(context: CallbackContext) -> None:
    """Ask the user if they are working today."""
    global daily_question_sent

    # Check if it's a weekday (0 = Monday, 4 = Friday, 5 = Saturday, 6 = Sunday)
    # In Python's datetime, the week starts with Monday as 0
    day_of_week = datetime.now().weekday()

    # If it's Friday or Saturday (weekend in Israel), don't send the message
    if day_of_week == 4 or day_of_week == 5:
        logger.info("It's weekend, not sending working status question")
        return

    # Create inline keyboard
    keyboard = [
        [
            InlineKeyboardButton("כן, אני עובד/ת היום", callback_data='working'),
            InlineKeyboardButton("לא, אני לא עובד/ת היום", callback_data='not_working'),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Send message with inline keyboard
    context.bot.send_message(
        chat_id=USER_CHAT_ID,
        text="האם את/ה עובד/ת היום?",
        reply_markup=reply_markup
    )

    daily_question_sent = True
    logger.info("Daily working status question sent")


def ask_for_sms_verification(context: CallbackContext, browser=None, chat_id=None) -> None:
    """
    Ask the user for SMS verification code and wait for their response.
    This function handles two-factor authentication for 10bis login.

    Args:
        context: The CallbackContext from the telegram bot
        browser: The active Selenium webdriver instance
        chat_id: The Telegram chat ID to send the message to
    """
    if not chat_id:
        chat_id = USER_CHAT_ID

    # Store the browser instance in context.user_data to access it when user responds
    if browser:
        if context.user_data is None:
            context.user_data = {}
        context.user_data['browser'] = browser

    # Create a conversation handler setup
    context.user_data['awaiting_sms_code'] = True

    # Send message to user asking for the verification code
    message = context.bot.send_message(
        chat_id=chat_id,
        text="תן ביס שלח לך קוד אימות בהודעת SMS. אנא הקלד את הקוד כאן:"
    )

    # Store the message ID so we can update it later
    context.user_data['verification_message_id'] = message.message_id

    logger.info("Requested SMS verification code from user")

    # We'll need to create a separate message handler for this
    # This will be handled in the handle_text_message function below


def handle_text_message(update: Update, context: CallbackContext) -> None:
    """Handle text messages from the user, including SMS verification codes."""
    # Check if we're waiting for an SMS code
    if context.user_data.get('awaiting_sms_code', False):
        sms_code = update.message.text.strip()

        # Validate that the input looks like a verification code (typically 4-6 digits)
        if not sms_code.isdigit() or len(sms_code) < 4 or len(sms_code) > 6:
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="הקוד שהזנת אינו נראה תקין. אנא נסה שוב (4-6 ספרות):"
            )
            return

        # Get the browser instance from user_data
        browser = context.user_data.get('browser')
        if not browser:
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="שגיאה: תהליך ההתחברות נכשל. אנא התחל מחדש עם /start"
            )
            context.user_data['awaiting_sms_code'] = False
            return

        try:
            # Find the SMS code input field and enter the code
            sms_input = WebDriverWait(browser, 10).until(
                EC.presence_of_element_located((By.ID, "authenticationCode"))
            )
            sms_input.clear()
            sms_input.send_keys(sms_code)

            # Find and click the submit button
            submit_button = browser.find_element(By.XPATH, "//button[@type='submit']")
            time.sleep(2)
            submit_button.click()
            time.sleep(2)

            # Wait for successful login
            WebDriverWait(browser, 10).until(
                EC.url_contains("next")
            )

            # Reset the awaiting flag
            context.user_data['awaiting_sms_code'] = False

            # Inform the user
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="תודה! אימות הקוד בוצע בהצלחה. ממשיך בתהליך הטעינה..."
            )

            # Continue with the credit loading process
            continue_load_10bis_credit(context, browser, update.effective_chat.id)

        except Exception as e:
            logger.error(f"Error processing SMS verification: {e}")
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="שגיאה באימות הקוד. ייתכן שהקוד שגוי או שפג תוקפו. אנא נסה שוב מאוחר יותר."
            )
            context.user_data['awaiting_sms_code'] = False
            try:
                browser.quit()
            except:
                pass
            return
    else:
        # Handle regular messages when not awaiting verification
        update.message.reply_text(
            "היי! אם ברצונך להתחיל את התהליך, אנא שלח /start"
        )


def continue_load_10bis_credit(context, browser, chat_id):
    """Continue the 10bis credit loading process after successful SMS verification."""
    try:
        # Navigate to the credit page
        browser.get('https://www.10bis.co.il/next/user-report/transactions')
        logger.info("Navigated to credit page")

        # Wait for the credit page to load
        WebDriverWait(browser, 10).until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'הטענת תן ביס קרדיט')]"))
        )

        # Click the credit load button
        credit_button = browser.find_element(By.XPATH, "//button[contains(text(), 'הטענת תן ביס קרדיט')]")

        if credit_button.get_attribute('aria-disabled') == 'true':
            logger.info("Credit button is disabled - credit has already been loaded today")
            context.bot.send_message(
                chat_id=chat_id,
                text="נראה שכבר הטענת קרדיט היום בתן ביס. אין צורך בהטענה נוספת. בתיאבון! 😊"
            )
            browser.quit()
            return True

        # Credit button is enabled, proceed with loading credit
        credit_button.click()
        logger.info("Clicked credit load button")

        # # Wait for the credit amount field to appear
        # credit_input = WebDriverWait(browser, 10).until(
        #     EC.presence_of_element_located((By.CLASS_NAME, "Input-fSxwnm loiTnA"))
        # )
        # credit_input.clear()
        # credit_input.send_keys("30")

        # WebDriverWait(browser, 10).until(
        #     EC.presence_of_element_located((By.XPATH, "//input[@placeholder='סכום']"))
        # )
        #
        # # Enter credit amount
        # credit_input = browser.find_element(By.XPATH, "//input[@placeholder='סכום']")

        logger.info("Entered credit amount: 30 NIS")

        # Click the confirm amount button
        # WebDriverWait(browser, 10).until(
        #     EC.presence_of_element_located((By.CSS_SELECTOR, "Button-dtEEMF SubmitButton-etwBPp iXOfjm hHtDlm")))
        WebDriverWait(browser, 10).until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'המשך')]")))
        # confirm_amount_button = browser.find_element(By.CSS_SELECTOR, "Button-dtEEMF SubmitButton-etwBPp iXOfjm hHtDlm")
        confirm_amount_button = browser.find_element(By.XPATH, "//button[contains(text(), 'המשך')]")
        confirm_amount_button.click()
        logger.info("Confirmed credit load")

        WebDriverWait(browser, 10).until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'הטענת קרדיט')]")))
        confirm_button = browser.find_element(By.XPATH, "//button[contains(text(), 'הטענת קרדיט')]")
        confirm_button.click()
        logger.info("Confirmed credit load")

        # Wait for payment processing
        WebDriverWait(browser, 10).until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'סגירה')]")))
        close_button = browser.find_element(By.XPATH, "//button[contains(text(), 'סגירה')]")
        close_button.click()
        logger.info("Payment completed successfully")

        # Send success message
        context.bot.send_message(
            chat_id=chat_id,
            text="הטענתי בהצלחה 30 ש\"ח לכרטיס תן ביס שלך! בתיאבון!"
        )

        # Close the browser
        browser.quit()
        return True

    except Exception as e:
        logger.error(f"Error loading 10bis credit after verification: {e}")
        context.bot.send_message(
            chat_id=chat_id,
            text="התרחשה שגיאה בהטענת הכרטיס לאחר האימות. אנא נסה להטעין ידנית או צור קשר עם מנהל המערכת."
        )
        try:
            browser.quit()
        except:
            pass
        return False


def handle_response(update: Update, context: CallbackContext) -> None:
    """Handle user response about working status."""
    query = update.callback_query
    query.answer()

    # Get the choice
    choice = query.data

    if choice == 'working':
        query.edit_message_text(text="מצוין! אני מטעין את כרטיס תן ביס שלך ב-30 ש\"ח...")
        logger.info("User is working today. Initiating 10bis credit load")

        # Start the 10bis credit loading process
        result = load_10bis_credit(context)

        # Check if SMS verification is needed
        if isinstance(result, dict):
            if result.get("status") == "needs_verification":
                # Get the browser instance from the result
                browser = result.get("browser")

                # Ask for SMS verification
                ask_for_sms_verification(context, browser=browser, chat_id=query.message.chat_id)

                # The rest of the process will be handled by handle_text_message when user sends the code
            elif result.get("status") == "already_loaded":
                # Credit has already been loaded today
                context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=result.get("message", "נראה שכבר הטענת קרדיט היום בתן ביס. אין צורך בהטענה נוספת. בתיאבון! 😊")
                )
        elif result:
            context.bot.send_message(
                chat_id=query.message.chat_id,
                text="הטענתי בהצלחה 30 ש\"ח לכרטיס תן ביס שלך! בתיאבון!"
            )
        else:
            context.bot.send_message(
                chat_id=query.message.chat_id,
                text="התרחשה שגיאה בהטענת הכרטיס. אנא נסה להטעין ידנית או צור קשר עם מנהל המערכת."
            )
    else:
        query.edit_message_text(text="תודה על העדכון. לא אטעין את כרטיס תן ביס היום.")
        logger.info("User is not working today. No credit load needed")


def load_10bis_credit(context) -> bool:
    """Connect to 10bis account and load 30 NIS credit."""
    try:
        # Initialize the browser
        browser = uc.Chrome(options=chrome_options)
        # browser = webdriver.Chrome(options=chrome_options)
        browser.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        logger.info("Browser initialized")
        stealth(browser,
                languages=["he-IL", "he", "en-US", "en"],
                vendor="Google Inc.",
                platform="Win32",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine",
                fix_hairline=True,
                )

        # Navigate to 10bis login page
        browser.get('https://www.10bis.co.il/next')
        logger.info("Navigated to 10bis login page")

        # Wait for the login form to load
        WebDriverWait(browser, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-test="homeHeader-openLogin"]'))
        )

        # Enter login credentials
        # Using CSS selector
        login_button = browser.find_element(By.CSS_SELECTOR, '[data-test="homeHeader-openLogin"]')
        login_button.click()
        time.sleep(0.2)
        browser.find_element(By.ID, "email").send_keys(TENBIT_USERNAME)
        browser.find_element(By.CSS_SELECTOR, '[data-test="login-submit"]').click()
        logger.info("Login credentials submitted")
        time.sleep(0.2)

        # ask_for_sms_verification(context, browser=browser)

        try:
            # Wait a short time to see if SMS verification page appears
            sms_verification = WebDriverWait(browser, 5).until(
                EC.presence_of_element_located((By.ID, "authenticationCode"))
            )

            # If we found the SMS input field, we need verification
            logger.info("SMS verification required")

            # We need to ask the user for the verification code
            # Since we can't directly call the function that needs context,
            # we'll return a special value and handle it in the callback
            return {
                "status": "needs_verification",
                "browser": browser
            }

        except:
            # No SMS verification needed, continue with normal flow
            logger.info("No SMS verification required")

            # Wait for login to complete
            WebDriverWait(browser, 10).until(
                EC.url_contains("next=")
            )
            logger.info("Login successful")

            # Navigate to the credit page
            browser.get('https://www.10bis.co.il/next/user-report/transactions')
            logger.info("Navigated to credit page")

            # Wait for the credit page to load
            WebDriverWait(browser, 10).until(
                EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'הטענת קרדיט')]"))
            )

            # Click the credit load button
            browser.find_element(By.XPATH, "//button[contains(text(), 'הטענת קרדיט')]").click()
            logger.info("Clicked credit load button")

            # Wait for the credit amount field to appear
            WebDriverWait(browser, 10).until(
                EC.presence_of_element_located((By.XPATH, "//input[@placeholder='סכום']"))
            )

            # Enter credit amount
            credit_input = browser.find_element(By.XPATH, "//input[@placeholder='סכום']")
            credit_input.clear()
            credit_input.send_keys("30")
            logger.info("Entered credit amount: 30 NIS")

            # Click the confirm button
            browser.find_element(By.XPATH, "//button[contains(text(), 'אישור')]").click()
            logger.info("Confirmed credit load")

            # Wait for payment processing
            WebDriverWait(browser, 20).until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(text(), 'תשלום הושלם בהצלחה')]"))
            )
            logger.info("Payment completed successfully")

            # Close the browser
            browser.quit()
            return True
    except Exception as e:
        logger.error(f"Error loading 10bis credit: {e}")
        try:
            browser.quit()
        except:
            pass
        return False


def reset_daily_flag() -> None:
    """Reset the daily question flag at midnight."""
    global daily_question_sent
    daily_question_sent = False
    logger.info("Daily question flag reset")


def main() -> None:
    """Start the bot."""
    # Create the Updater and pass it your bot's token
    updater = Updater(TELEGRAM_TOKEN)

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # Register command handlers
    dispatcher.add_handler(CommandHandler("start", start))

    dispatcher.add_handler(CommandHandler("now", start))

    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text_message))

    # Register callback query handler
    dispatcher.add_handler(CallbackQueryHandler(handle_response))

    # Start the Bot
    updater.start_polling()
    logger.info("Bot started and polling for updates")

    # Schedule the daily question at 11:00 AM
    # ask_working_status(CallbackContext(dispatcher))
    schedule.every().day.at("11:00").do(
        lambda: ask_working_status(CallbackContext(dispatcher))
    )

    # Schedule the reset of the daily flag at midnight
    schedule.every().day.at("00:00").do(reset_daily_flag)

    # Run the scheduler in a loop
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute


if __name__ == '__main__':
    main()
