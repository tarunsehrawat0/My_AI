from dotenv import load_dotenv
from pathlib import Path
import os
from openai import OpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from aiohttp import web

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OWNER_CHAT_ID = os.getenv("OWNER_CHAT_ID")

if not BOT_TOKEN:
    raise SystemExit("Error: BOT_TOKEN is not set in .env")
if not OPENAI_API_KEY:
    raise SystemExit("Error: OPENAI_API_KEY is not set in .env")

if OWNER_CHAT_ID:
    try:
        OWNER_CHAT_ID = int(OWNER_CHAT_ID)
    except ValueError:
        raise SystemExit("Error: OWNER_CHAT_ID must be an integer")
else:
    raise SystemExit("Error: OWNER_CHAT_ID is not set in .env")

client = OpenAI(api_key=OPENAI_API_KEY)
print(f"OpenAI configured with key: {OPENAI_API_KEY[:6]}***")

base_dir = Path(__file__).resolve().parent
kb_path = base_dir / "knowledge_base.txt"
if not kb_path.exists():
    print(f"Warning: {kb_path} not found. Creating placeholder knowledge_base.txt.")
    kb_path.write_text(
        "Business Name: Fresh Cuts Salon\nTimings: Monday to Saturday, 10 AM to 8 PM. Closed on Sundays.\nLocation: Sector 14, Gurugram\n\nServices & Prices:\n- Haircut (Men): ₹200\n- Haircut (Women): ₹500\n- Hair Coloring: ₹1500 onwards\n- Beard Trim: ₹100\n- Facial: ₹800\n\nBooking: Walk-ins welcome, or message here to reserve a slot.\nPayment: Cash, UPI, and cards accepted.\nCancellation Policy: Please inform at least 2 hours before your slot if cancelling.\n",
        encoding="utf-8",
    )

with kb_path.open("r", encoding="utf-8") as f:
    knowledge_base = f.read()

pending_escalations = {}
GREETINGS = {
    "hi",
    "hello",
    "hey",
    "good",
    "good morning",
    "good afternoon",
    "good evening",
    "namaste",
    "kaise ho",
    "kasa ho",
    "how are you",
    "what's up",
    "whats up",
    "sup",
}

async def process_customer_question(update: Update, context: ContextTypes.DEFAULT_TYPE, user_question: str):
    user_name = update.message.from_user.first_name or "Customer"
    normalized_message = user_question.strip().lower()

    if normalized_message in GREETINGS:
        await update.message.reply_text(
            "Hi! Welcome to Fresh Cuts Salon 😊 How can I help you today?"
        )
        return

    prompt = f"""You are a friendly assistant for a business, chatting with a customer on WhatsApp/Telegram.

Rules:
1. If the customer sends a greeting or casual message (hi, hello, hey, kasa ho, kaise ho, good morning, etc.) — reply warmly and briefly as the business would, e.g. "Hi! Welcome to Fresh Cuts Salon 😊 How can I help you today?" Do NOT escalate greetings.
2. If the customer asks a real question that IS answered in the Business Information below, answer using ONLY that information.
3. If the customer asks a real question that is NOT covered in the Business Information, reply exactly with: ESCALATE
4. Keep replies short, warm, and natural — like a real business owner texting back, not a robotic tone.
5. Add a friendly closing that invites the customer to reply, for example "Please let me know if you'd like to book or need more details.".

Business Information:
{knowledge_base}

Customer Message: {user_question}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3000,
        )
        reply = response.choices[0].message.content.strip()
    except Exception as e:
        error_msg = f"Model generation error: {type(e).__name__}: {e}"
        print(error_msg)
        # Send error to owner for debugging
        try:
            await context.bot.send_message(chat_id=OWNER_CHAT_ID, text=f"⚠️ {error_msg}")
        except Exception:
            pass
        reply = ""

    if reply.strip().upper().startswith("ESCALATE"):
        alert = await context.bot.send_message(
            chat_id=OWNER_CHAT_ID,
            text=f"New question from {user_name}: {user_question}\n\n👉 Reply to THIS message to answer them."
        )
        pending_escalations[alert.message_id] = update.effective_chat.id
    elif reply:
        await update.message.reply_text(reply)
    else:
        await update.message.reply_text(
            "Sorry, I couldn't answer right now. Please try again or ask another question."
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    # Owner replying to an alert → forward to that customer
    if chat_id == OWNER_CHAT_ID:
        if update.message.reply_to_message:
            original_id = update.message.reply_to_message.message_id
            if original_id in pending_escalations:
                customer_chat_id = pending_escalations[original_id]
                await context.bot.send_message(chat_id=customer_chat_id, text=update.message.text)
                await update.message.reply_text("✅ Sent to customer")
                return

        # If only one escalation is pending, allow one-tap owner replies without a reply thread
        if len(pending_escalations) == 1:
            customer_chat_id = next(iter(pending_escalations.values()))
            await context.bot.send_message(chat_id=customer_chat_id, text=update.message.text)
            await update.message.reply_text("✅ Sent to the pending customer")
            return

        # If multiple escalations are pending, instruct the owner to reply to the alert or use /reply
        if len(pending_escalations) > 1:
            await update.message.reply_text(
                "Please reply to the specific alert message or use /reply <chat_id> <message> because multiple customers are waiting."
            )
            return

    await process_customer_question(update, context, update.message.text)

async def handle_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == OWNER_CHAT_ID:
        return

    command_text = update.message.text.lstrip("/")
    if not command_text:
        await update.message.reply_text("Please type your question or use a message like /location.")
        return

    await process_customer_question(update, context, command_text)

async def reply_to_customer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender_id = update.message.from_user.id
    if sender_id != OWNER_CHAT_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /update <chat_id> <message>\n(also works with /reply)")
        return

    target_chat_id = context.args[0]
    try:
        target_chat_id = int(target_chat_id)
    except ValueError:
        await update.message.reply_text("Usage: /update <chat_id> <message>\n(also works with /reply)")
        return

    reply_text = " ".join(context.args[1:]).strip()
    if not reply_text:
        await update.message.reply_text("Usage: /update <chat_id> <message>\n(also works with /reply)")
        return

    try:
        await context.bot.send_message(chat_id=target_chat_id, text=reply_text)
        await update.message.reply_text("✅ Sent to customer")
    except Exception as e:
        print(f"Reply command error: {e}")
        await update.message.reply_text("Failed to send the message. Please check the chat_id and try again.")

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("reply", reply_to_customer))
app.add_handler(CommandHandler("update", reply_to_customer))
app.add_handler(MessageHandler(filters.COMMAND & ~filters.User(OWNER_CHAT_ID), handle_user_command))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# --- Webhook setup for Render ---
PORT = int(os.environ.get("PORT", 10000))
# Try multiple possible Render URL environment variables
RENDER_EXTERNAL_URL = (
    os.environ.get("RENDER_EXTERNAL_URL") or
    os.environ.get("RENDER_SERVICE_URL") or
    os.environ.get("URL") or
    f"https://{os.environ.get('RENDER_SERVICE_NAME', 'my-aifresh-cuts-bot')}.onrender.com"
)
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}/webhook"

async def webhook_handler(request):
    """Handle incoming webhook updates from Telegram"""
    print(f"Webhook received request: {request.method}")
    if request.method == "POST":
        try:
            data = await request.json()
            print(f"Webhook received data: {data}")
            await app.update_queue.put(
                Update.de_json(data=data, bot=app.bot)
            )
            print("Webhook data queued successfully")
        except Exception as e:
            print(f"Webhook error: {e}")
            return web.Response(status=400, text=f"Error: {e}")
    return web.Response(status=200)

async def health_check(request):
    """Health check endpoint for Render"""
    return web.Response(text="OK", status=200)

async def setup_webhook():
    """Set up the webhook for Telegram bot"""
    try:
        webhook_info = await app.bot.get_webhook_info()
        print(f"Current webhook info: {webhook_info}")
        
        await app.bot.set_webhook(url=WEBHOOK_URL)
        print(f"Webhook set to: {WEBHOOK_URL}")
        
        # Verify webhook was set
        webhook_info = await app.bot.get_webhook_info()
        print(f"Updated webhook info: {webhook_info}")
        
        if webhook_info.url != WEBHOOK_URL:
            print(f"ERROR: Webhook not set correctly. Expected: {WEBHOOK_URL}, Got: {webhook_info.url}")
            return False
    except Exception as e:
        print(f"Error setting webhook: {e}")
        return False

    # Start aiohttp server
    web_app = web.Application()
    web_app.router.add_post("/webhook", webhook_handler)
    web_app.router.add_get("/", health_check)
    web_app.router.add_get("/webhook", lambda request: web.Response(text="Use POST for webhook", status=405))
    
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"Server running on port {PORT}")
    
    # Keep the application running
    await asyncio.Event().wait()

if __name__ == "__main__":
    import asyncio
    print("Bot is running...")
    
    # Always use webhook mode on Render
    asyncio.run(setup_webhook())
