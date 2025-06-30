import os
import json
import requests
import asyncio  # ✅ Added for delay
import telegram  # For telegram.helpers.escape_markdown
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

# === CONFIG ===
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MODEL_NAME = "gemini-1.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
DEFAULT_FILENAME = "majorship.json"

# === Gemini Prompt Builder ===
def build_explanation_prompt(questions: list) -> str:
    return (
        "For each question object in the JSON array below, add a field called 'explanation'. "
        "The explanation must be concise, with 100 characters or fewer. "
        "Only return valid JSON with the added 'explanation' fields. No extra text.\n\n"
        f"{json.dumps(questions, indent=2)}"
    )

# === Ask Gemini ===
async def ask_gemini(prompt: str):
    headers = {"Content-Type": "application/json"}
    context = [{"role": "user", "parts": [{"text": build_explanation_prompt(prompt)}]}]
    payload = {"contents": context}

    try:
        res = requests.post(GEMINI_URL, headers=headers, json=payload)
        res.raise_for_status()
        reply = res.json()["candidates"][0]["content"]["parts"][0]["text"]
        start = reply.find("[")
        end = reply.rfind("]") + 1
        return json.loads(reply[start:end])
    except Exception as e:
        print("Gemini Error:", e)
        return None

# === Load quiz file ===
def load_quiz(filename=DEFAULT_FILENAME):
    try:
        with open(filename.strip().lower(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("❌ Failed to load quiz:", e)
        return []

# === Send Telegram Polls with delay ===
async def send_polls(bot, chat_id, quiz_data):
    for i, q in enumerate(quiz_data, start=1):
        options = [q.get(k, "") for k in ("a", "b", "c", "d")]
        explanation = q.get("explanation", "")

        correct_letter = q.get("answer", "").strip().upper()
        letter_to_index = {"A": 0, "B": 1, "C": 2, "D": 3}
        correct_index = letter_to_index.get(correct_letter, 0)

        # 🔢 Message for question number
        msg = await bot.send_message(chat_id=chat_id, text=f"🔹 Question no. {i}")
        await bot.pin_chat_message(chat_id=chat_id, message_id=msg.message_id, disable_notification=True)

        # 🔠 Escape MarkdownV2 for poll question
        raw_question = q.get('question', '')
        bold_question = f"*{telegram.helpers.escape_markdown(raw_question, version=2)}*"

        # 📝 Send the quiz poll
        await bot.send_poll(
            chat_id=chat_id,
            question=bold_question,
            options=options,
            type="quiz",
            correct_option_id=correct_index,
            explanation=explanation if explanation else None,
            is_anonymous=False,
            parse_mode="MarkdownV2"
        )

        # ⏳ Delay to avoid flood control
        await asyncio.sleep(1.2)

# === /start Command Handler ===
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text("⏳ Preparing your quiz...")

    quiz_data = load_quiz()
    if not quiz_data:
        await update.message.reply_text("❌ Failed to load quiz.")
        return

    enriched = await ask_gemini(quiz_data)
    if not enriched:
        await update.message.reply_text("❌ Gemini failed to enrich the quiz.")
        return

    await send_polls(context.bot, chat_id, enriched)
    await update.message.reply_text("🎉 Quiz sent!")

# === Message fallback handler ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.text:
        await update.message.reply_text("Try sending /start to begin the quiz.")

# === Main Entry ===
if __name__ == "__main__":
    print("🤖 Bot running... Send /start to trigger the quiz.")
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
