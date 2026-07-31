# 🤖 Fresh Cuts Salon — AI-Powered Telegram Bot

An intelligent Telegram customer support bot for **Fresh Cuts Salon** that uses **Google Gemini 2.5 Flash** to automatically answer customer queries based on a customizable knowledge base — and seamlessly escalates unanswered questions to the business owner.

---

## ✨ Features

| Feature | Description |
|---|---|
| **AI-Powered Replies** | Answers customer questions instantly using Google Gemini, grounded in your business knowledge base |
| **Smart Escalation** | Automatically escalates questions the AI can't answer to the business owner via Telegram |
| **Owner Reply Flow** | Owner can reply directly to escalation alerts — responses are forwarded back to the customer |
| **Greeting Detection** | Recognizes casual greetings (hi, hello, namaste, etc.) and responds warmly without invoking the AI |
| **Multi-Customer Support** | Handles multiple pending escalations simultaneously with clear routing |
| **Customizable Knowledge Base** | All business info lives in a plain text file — easy to edit, no code changes needed |

---

## 📁 Project Structure

```
My_AI/
├── bot.py                 # Main bot logic (handlers, Gemini integration, escalation)
├── knowledge_base.txt     # Business information the AI uses to answer questions
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables (API keys, tokens) — not tracked by git
├── .gitignore             # Git ignore rules
└── README.md              # You are here
```

---

## ⚙️ Prerequisites

- **Python 3.9+**
- A **Telegram Bot Token** (from [@BotFather](https://t.me/BotFather))
- A **Google Gemini API Key** (from [Google AI Studio](https://aistudio.google.com/apikey))
- Your **Telegram Chat ID** (the owner who receives escalations)

---

## 🚀 Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/tarunsehrawat0/My_AI.git
cd My_AI
```

### 2. Create a Virtual Environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root with the following:

```env
BOT_TOKEN=your_telegram_bot_token
GEMINI_API_KEY=your_google_gemini_api_key
OWNER_CHAT_ID=your_telegram_chat_id
```

> **Tip:** To find your Telegram Chat ID, message [@userinfobot](https://t.me/userinfobot) on Telegram.

### 5. Customize the Knowledge Base

Edit `knowledge_base.txt` with your business details:

```text
Business Name: Your Business Name
Timings: Monday to Saturday, 10 AM to 8 PM
Location: Your Address

Services & Prices:
- Service A: ₹XXX
- Service B: ₹XXX

Booking: Walk-ins welcome, or message to reserve.
Payment: Cash, UPI, and cards accepted.
```

### 6. Run the Bot

```bash
python bot.py
```

You should see:

```
Bot is running...
```

---

## 💬 How It Works

```
Customer sends a message
        │
        ▼
   Is it a greeting?
   ┌────┴────┐
  YES        NO
   │          │
   ▼          ▼
 Warm      Ask Gemini AI
 reply     (with knowledge base)
              │
              ▼
        Can AI answer?
        ┌────┴────┐
       YES        NO
        │          │
        ▼          ▼
   Send AI     ESCALATE to
   response    business owner
                   │
                   ▼
              Owner replies
              to the alert
                   │
                   ▼
              Response sent
              to customer
```

---

## 🔧 Owner Commands

| Command | Description |
|---|---|
| **Reply to alert** | Reply directly to an escalation message to send your answer back to the customer |
| `/reply <chat_id> <message>` | Manually reply to a specific customer by their chat ID |
| `/update <chat_id> <message>` | Alias for `/reply` |

> When only **one** escalation is pending, the owner can simply type a message without replying to the alert — it will be routed automatically.

---

## 🛠️ Tech Stack

- **Python** — Core language
- **[python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)** — Telegram Bot API wrapper
- **[Google Generative AI SDK](https://github.com/google/generative-ai-python)** — Gemini 2.5 Flash integration
- **[python-dotenv](https://github.com/theskumar/python-dotenv)** — Environment variable management

---

## 📝 License

This project is open source. Feel free to fork and adapt it for your own business.

---

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

> Built with ❤️ by [Tarun Sehrawat](https://github.com/tarunsehrawat0)
