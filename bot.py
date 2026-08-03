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
        'OWNER_NAME: Tarun Sehrawat\n'
        'Timings: Monday to Saturday, 10 AM to 8 PM. Closed on Sundays.\n'
        'Location: Sector 14, Gurugram\n\n'
        'parking: Free parking available\n'
        'Services & Prices:\n'
        '- Haircut (Men): ₹200\n'
        '- Haircut (Women): ₹500\n'
        '- Hair Coloring: ₹1500 onwards\n'
        '- Beard Trim: ₹100\n'
        '- Facial: ₹800\n\n'
        'Booking: Walk-ins welcome, or message here to reserve a slot.\n'
        'Payment: Cash, UPI, and cards accepted.\n'
        'Contact: 8059049365\n'
        'UPI: 8059049365@ybl\n'
        'WhatsApp: 8059049365\n'
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
    
    # More flexible token matching - include shorter tokens
    q_tokens = {token for token in re.findall(r'[a-z0-9]+', q) if len(token) > 1}
    
    # Add comprehensive keywords mapping
    keyword_map = {
        'time': 'timings',
        'timing': 'timings', 
        'open': 'timings',
        'close': 'timings',
        'when': 'timings',
        'hours': 'timings',
        'hour': 'timings',
        'price': 'prices',
        'cost': 'prices',
        'rate': 'rates',
        'charges': 'charges',
        'money': 'payment',
        'pay': 'payment',
        'address': 'location',
        'where': 'location',
        'place': 'location',
        'sit': 'location',
        'located': 'location',
        'find': 'location',
        'book': 'booking',
        'appointment': 'booking',
        'reserve': 'booking',
        'slot': 'booking',
        'cancel': 'cancellation',
        'contact': 'contact',
        'call': 'contact',
        'phone': 'contact',
        'number': 'contact',
        'mobile': 'contact',
        'upi': 'upi',
        'whatsapp': 'whatsapp',
        'park': 'parking',
        'owner': 'owner',
        'who': 'owner',
        'name': 'owner',
        'service': 'services',
        'facial': 'facial',
        'hair': 'haircut',
        'haircut': 'haircut',
        'beard': 'beard',
        'color': 'coloring',
        'colour': 'coloring',
    }
    
    # Map question tokens to knowledge base terms
    expanded_q_tokens = set()
    for token in q_tokens:
        if token in keyword_map:
            expanded_q_tokens.add(keyword_map[token])
        expanded_q_tokens.add(token)
    
    # Score each line and track context
    scored: list[tuple[int, str, int]] = []
    for idx, line in enumerate(kb_lines):
        line_tokens = {token for token in re.findall(r'[a-z0-9]+', normalize(line)) if len(token) > 1}
        # Calculate match score
        score = len(expanded_q_tokens & line_tokens)
        # Bonus for matching important keywords
        if any(keyword in line.lower() for keyword in ['timings', 'price', 'location', 'booking', 'contact', 'upi', 'whatsapp', 'parking', 'owner']):
            score += 1
        # Bonus for exact word matches
        if any(token in line.lower() for token in q_tokens):
            score += 1
        if score > 0:
            scored.append((score, line, idx))
    
    if scored:
        scored.sort(reverse=True)
        best_score, best_line, best_idx = scored[0]
        
        # Special handling for price-related questions - return entire price section
        if any(keyword in q for keyword in ['price', 'cost', 'rate', 'charges', 'money']):
            # Find the Services & Prices section
            price_section = []
            in_price_section = False
            for line in kb_lines:
                if 'services' in line.lower() and 'price' in line.lower():
                    in_price_section = True
                if in_price_section:
                    price_section.append(line.strip())
                    if line.strip() and not any(char.isdigit() for char in line) and 'services' not in line.lower():
                        # End of price section (line without numbers and not the header)
                        if len(price_section) > 2:  # Ensure we have at least header + one service
                            break
            if price_section:
                answer = '\n'.join(price_section)
                return f"{answer}\n\nPlease let me know if you'd like to book or need more details."
        
        # Only return answer if we have a strong match (higher threshold)
        if best_score >= 2:
            # Get surrounding lines for context, but only if they're related
            context_lines = []
            start_idx = max(0, best_idx - 1)
            end_idx = min(len(kb_lines), best_idx + 2)
            
            for i in range(start_idx, end_idx):
                if kb_lines[i].strip():
                    # Only include line if it shares some tokens with the question
                    line_tokens = {token for token in re.findall(r'[a-z0-9]+', normalize(kb_lines[i])) if len(token) > 1}
                    if len(expanded_q_tokens & line_tokens) > 0:
                        context_lines.append(kb_lines[i].strip())
            
            if context_lines:
                answer = '\n'.join(context_lines)
                return f"{answer}\n\nPlease let me know if you'd like to book or need more details."

    return None


async def process_customer_question(update: Update, context: ContextTypes.DEFAULT_TYPE, user_question: str) -> None:
    if not update.message or not user_question:
        return

    user_name = update.message.from_user.first_name or 'Customer'
    answer = build_answer(user_question)

    if answer:
        await update.message.reply_text(answer)
        return

    logger.info(f'Escalating question from {user_name}: {user_question}')
    alert = await context.bot.send_message(
        chat_id=OWNER_CHAT_ID,
        text=(
            f'New question from {user_name} (chat_id: {update.effective_chat.id}):\n\n'
            f'{user_question}\n\n'
            'Reply to THIS message to send a reply to the customer.'
        ),
    )
    PENDING_ESCALATIONS[alert.message_id] = update.effective_chat.id
    logger.info(f'Escalation stored: message_id={alert.message_id}, chat_id={update.effective_chat.id}')


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
        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
