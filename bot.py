import logging
import os
import re
import asyncio
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from aiohttp import web

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()
OWNER_CHAT_ID = os.getenv('OWNER_CHAT_ID', '').strip()

if not BOT_TOKEN:
    raise SystemExit('BOT_TOKEN is not set in .env')

if OWNER_CHAT_ID:
    try:
        OWNER_CHAT_ID = int(OWNER_CHAT_ID)
    except ValueError as exc:
        raise SystemExit('OWNER_CHAT_ID must be an integer') from exc
else:
    raise SystemExit('OWNER_CHAT_ID is not set in .env')

BASE_DIR = Path(__file__).resolve().parent
KB_PATH = BASE_DIR / 'knowledge_base.txt'

if not KB_PATH.exists():
    KB_PATH.write_text(
        'Business Name: Fresh Cuts Salon\n'
        'Timings: Monday to Saturday, 10 AM to 8 PM. Closed on Sundays.\n'
        'Location: Sector 14, Gurugram\n\n'
        'Services & Prices:\n'
        '- Haircut (Men): ₹200\n'
        '- Haircut (Women): ₹500\n'
        '- Hair Coloring: ₹1500 onwards\n'
        '- Beard Trim: ₹100\n'
        '- Facial: ₹800\n\n'
        'Booking: Walk-ins welcome, or message here to reserve a slot.\n'
        'Payment: Cash, UPI, and cards accepted.\n'
        'Cancellation Policy: Please inform at least 2 hours before your slot if cancelling.\n',
        encoding='utf-8',
    )

with KB_PATH.open('r', encoding='utf-8') as f:
    KNOWLEDGE_BASE = f.read().strip()

GREETINGS = {
    'hi', 'hello', 'hey', 'namaste', 'kaise ho', 'kasa ho', 'good morning',
    'good afternoon', 'good evening', 'good', 'how are you', 'whats up', "what's up", 'sup'
}

PENDING_ESCALATIONS: Dict[int, int] = {}


def normalize(text: str) -> str:
    return re.sub(r'\s+', ' ', (text or '').strip().lower())


def build_answer(question: str) -> Optional[str]:
    q = normalize(question)
    if not q:
        return None

    if any(q == g or q.startswith(g + ' ') for g in GREETINGS):
        return 'Hi! Welcome to Fresh Cuts Salon 😊 How can I help you today?'

    kb_lines = [line.strip() for line in KNOWLEDGE_BASE.splitlines() if line.strip()]
    q_tokens = {token for token in re.findall(r'[a-z0-9]+', q) if len(token) > 2}

    scored: list[tuple[int, str]] = []
    for line in kb_lines:
        line_tokens = {token for token in re.findall(r'[a-z0-9]+', normalize(line)) if len(token) > 2}
        score = len(q_tokens & line_tokens)
        if score:
            scored.append((score, line))

    if scored:
        scored.sort(reverse=True)
        best_line = scored[0][1]
        return f"{best_line}\n\nPlease let me know if you'd like to book or need more details."

    return None


async def process_customer_question(update: Update, context: ContextTypes.DEFAULT_TYPE, user_question: str) -> None:
    if not update.message or not user_question:
        return

    user_name = update.message.from_user.first_name or 'Customer'
    answer = build_answer(user_question)

    if answer:
        await update.message.reply_text(answer)
        return

    alert = await context.bot.send_message(
        chat_id=OWNER_CHAT_ID,
        text=(
            f'New question from {user_name} (chat_id: {update.effective_chat.id}):\n\n'
            f'{user_question}\n\n'
            'Reply to THIS message to send a reply to the customer.'
        ),
    )
    PENDING_ESCALATIONS[alert.message_id] = update.effective_chat.id
    await update.message.reply_text(
        'Sorry, I could not find an answer from the salon information. I have forwarded your question to the owner and they will reply soon.'
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    if chat_id == OWNER_CHAT_ID:
        if update.message.reply_to_message:
            replied_id = update.message.reply_to_message.message_id
            if replied_id in PENDING_ESCALATIONS:
                target_chat_id = PENDING_ESCALATIONS.pop(replied_id)
                await context.bot.send_message(chat_id=target_chat_id, text=update.message.text)
                await update.message.reply_text('✅ Forwarded to customer')
                return

        if len(PENDING_ESCALATIONS) == 1 and not update.message.reply_to_message:
            _, target_chat_id = PENDING_ESCALATIONS.popitem()
            await context.bot.send_message(chat_id=target_chat_id, text=update.message.text)
            await update.message.reply_text('✅ Forwarded to the pending customer')
            return

        if len(PENDING_ESCALATIONS) > 1 and not update.message.reply_to_message:
            await update.message.reply_text(
                'Multiple escalations are pending. Please reply to the specific alert message or use /reply <chat_id> <message>.'
            )
            return

        return

    await process_customer_question(update, context, text)


async def handle_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    if update.effective_user and update.effective_user.id == OWNER_CHAT_ID:
        return

    command_text = update.message.text.lstrip('/')
    if not command_text:
        await update.message.reply_text('Please type your question or use a message like /location.')
        return

    await process_customer_question(update, context, command_text)


async def reply_to_customer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    if update.message.from_user and update.message.from_user.id != OWNER_CHAT_ID:
        await update.message.reply_text('You are not authorized to use this command.')
        return

    if len(context.args) < 2:
        await update.message.reply_text('Usage: /reply <chat_id> <message>')
        return

    try:
        target_chat_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text('chat_id must be an integer.')
        return

    reply_text = ' '.join(context.args[1:]).strip()
    if not reply_text:
        await update.message.reply_text('Please provide a message to send.')
        return

    try:
        await context.bot.send_message(chat_id=target_chat_id, text=reply_text)
        await update.message.reply_text('✅ Sent to customer')
    except Exception as exc:
        logger.exception('Failed to send manual reply')
        await update.message.reply_text(f'Failed to send the message. Error: {exc}')


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('Hi! I can help answer questions about Fresh Cuts Salon. Ask me anything about timings, services, location, booking, or payments.')


async def webhook_handler(request: web.Request) -> web.Response:
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return web.Response(status=200)


async def health_check(request: web.Request) -> web.Response:
    return web.Response(text='OK', status=200)


def create_application() -> object:
    return ApplicationBuilder().token(BOT_TOKEN).build()


async def run_polling(app: object) -> None:
    logger.info('Starting bot in polling mode')
    await app.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)


async def run_webhook(app: object) -> None:
    logger.info('Starting bot in webhook mode')
    await app.initialize()
    await app.start()

    port = int(os.getenv('PORT', '10000'))
    public_url = os.getenv('RENDER_EXTERNAL_URL') or os.getenv('URL') or os.getenv('RENDER_SERVICE_URL')
    if not public_url:
        raise RuntimeError('RENDER_EXTERNAL_URL or URL must be set for webhook mode')

    webhook_url = public_url.rstrip('/') + '/webhook'
    await app.bot.set_webhook(url=webhook_url)

    web_app = web.Application()
    web_app.router.add_post('/webhook', webhook_handler)
    web_app.router.add_get('/', health_check)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info('Webhook server running on port %s', port)
    await asyncio.Event().wait()


def main() -> None:
    global application
    application = create_application()
    application.add_handler(CommandHandler('start', start_command))
    application.add_handler(CommandHandler('help', start_command))
    application.add_handler(CommandHandler('reply', reply_to_customer))
    application.add_handler(CommandHandler('update', reply_to_customer))
    application.add_handler(MessageHandler(filters.COMMAND & ~filters.User(OWNER_CHAT_ID), handle_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    use_webhook = os.getenv('USE_WEBHOOK', '').lower() in {'1', 'true', 'yes', 'on'}
    if use_webhook:
        asyncio.run(run_webhook(application))
    else:
        asyncio.run(run_polling(application))


if __name__ == '__main__':
    main()
