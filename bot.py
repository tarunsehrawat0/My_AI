from dotenv import load_dotenv
from pathlib import Path
import os
import re
import google.generativeai as genai
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OWNER_CHAT_ID = os.getenv("OWNER_CHAT_ID")

if not BOT_TOKEN:
    raise SystemExit("Error: BOT_TOKEN is not set in .env")
if not GEMINI_API_KEY:
    raise SystemExit("Error: GEMINI_API_KEY is not set in .env")

if OWNER_CHAT_ID:
    try:
        OWNER_CHAT_ID = int(OWNER_CHAT_ID)
    except ValueError:
        raise SystemExit("Error: OWNER_CHAT_ID must be an integer")
else:
    raise SystemExit("Error: OWNER_CHAT_ID is not set in .env")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

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
        response = model.generate_content(prompt)
        reply = getattr(response, "text", None) or getattr(response, "content", "")
        reply = reply.strip()
    except Exception as e:
        print(f"Model generation error: {e}")
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

print("Bot is running...")
app.run_polling()
