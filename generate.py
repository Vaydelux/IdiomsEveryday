import os
import json
import requests
import telegram  # Add this to use telegram.helpers.escape_markdown
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
DEFAULT_FILENAME = "majorship.json"  # 🔁 change to your filename like "majorship.json"

# === Gemini Prompt Builder ===
def build_explanation_prompt(questions: list) -> str:
    return (
        "Please add a short 'explanation' (atleast 100 characters below) field to each question object. "
        "in the JSON array below. Respond with valid JSON only:\n\n"
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

# === Send Telegram Polls ===
async def send_polls(bot, chat_id, quiz_data):
    for i, q in enumerate(quiz_data, start=1):
        options = [q.get(k, "") for k in ("a", "b", "c", "d")]
        explanation = q.get("explanation", "")
    
        # Determine correct option index (A=0, B=1, C=2, D=3)
        correct_letter = q.get("answer", "").strip().upper()
        letter_to_index = {"A": 0, "B": 1, "C": 2, "D": 3}
        correct_index = letter_to_index.get(correct_letter, 0)
    
        await bot.send_message(chat_id=chat_id, text=f"Question no. {i}")
            
        # 🔢 Format question number and bold using MarkdownV2
        raw_question = q.get('question', '')
        bold_question = f"*{telegram.helpers.escape_markdown(raw_question, version=2)}*"
        print(bold_question)
        print(explanation)
         # ✍️ Add explanation to show after wrong answers
        # Telegram will automatically show this to users who answer incorrectly
        await bot.send_poll(
            chat_id=chat_id,
            question=bold_question,
            options=options,
            type="quiz",  # 🎯 Enables quiz mode
            correct_option_id=correct_index,
            explanation=explanation  if explanation else None,  # 📘 Shows after incorrect answers
            is_anonymous=False
        )

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

# === Optional: normal message handler ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.text:
        chat_id = update.effective_chat.id
        await update.message.reply_text("Try sending /start to begin the quiz.")

# === MAIN ===
if __name__ == "__main__":
    print("🤖 Bot running... Send /start to trigger the quiz.")
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
