import os
import json
import asyncio
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

# === ENV CONFIG ===
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MODEL_NAME = "gemini-1.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"

# === Chat memory (for conversational bot use) ===
chat_memory = {}

async def ask_gemini(chat_id: int, user_id: int, prompt: str) -> str:
    headers = {"Content-Type": "application/json"}
    system_instruction = (
        "You are a helpful AI tutor for LET review students. "
        "Auto-detect the language (Filipino or English). "
        "Translate the answer to the same language. "
        "Start your reply with 1 appropriate emoji. "
        "Be concise, friendly, and easy to understand. "
        "Don't use formatting—just plain text."
    )
    context = [{"role": "user", "parts": [{"text": system_instruction}]}]

    key = (chat_id, user_id)
    if key in chat_memory:
        last_user, last_bot = chat_memory[key]
        context += [
            {"role": "user", "parts": [{"text": last_user}]},
            {"role": "model", "parts": [{"text": last_bot}]}
        ]

    context.append({"role": "user", "parts": [{"text": prompt}]})
    payload = {"contents": context}

    try:
        res = requests.post(GEMINI_URL, headers=headers, json=payload)
        res.raise_for_status()
        reply = res.json()["candidates"][0]["content"]["parts"][0]["text"]
        chat_memory[key] = (prompt, reply)
        return reply
    except Exception as e:
        print("Gemini API error:", e)
        return f"⚠️ Gemini Error: {e}"

# === JSON loader with flexible filename ===
def load_questions_file(filename: str):
    cleaned = filename.strip().lower()
    if not cleaned.endswith(".json"):
        cleaned += ".json"
    try:
        with open(cleaned, "r", encoding="utf-8") as f:
            return json.load(f), cleaned
    except Exception as e:
        print(f"❌ Error loading file '{cleaned}':", e)
        return None, cleaned

# === Use Gemini to enrich questions with explanations ===
def build_explanation_prompt(questions: list) -> str:
    return (
        "Please add a short 'explanation' field to each question object "
        "in the JSON array below. Respond with valid JSON only:\n\n"
        f"{json.dumps(questions, indent=2)}"
    )

async def enrich_questions_with_explanations(questions: list):
    prompt = build_explanation_prompt(questions)
    resp = await ask_gemini(-1, 0, prompt)
    try:
        start = resp.find("[")
        end = resp.rfind("]") + 1
        return json.loads(resp[start:end])
    except Exception as e:
        print("❌ Failed to parse Gemini response:", e)
        return None

# === Send polls from enriched data ===
async def send_polls_from_json(bot, chat_id, questions_data):
    for q in questions_data:
        options = [q.get(k, "") for k in ("a", "b", "c", "d")]
        explanation = q.get("explanation", "")
        await bot.send_poll(
            chat_id=chat_id,
            question=q.get("question", ""),
            options=options,
            is_anonymous=False,
            allows_multiple_answers=False
        )
        if explanation:
            await bot.send_message(chat_id=chat_id, text=f"📘 Explanation: {explanation}")

# === Telegram message handler (optional interactive bot) ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return
    if msg.chat.type in ["group", "supergroup"]:
        if context.bot.username.lower() not in msg.text.lower():
            return
    resp = await ask_gemini(msg.chat.id, msg.from_user.id, msg.text)
    await msg.reply_text(resp)

# === Main entry to enrich and push polls ===
async def main_quiz_flow():
    fname = input("Enter your JSON quiz filename (e.g., quiz.json): ")
    questions, cleaned = load_questions_file(fname)
    if not questions:
        print("No valid questions found. Exiting.")
        return

    enriched = await enrich_questions_with_explanations(questions)
    if not enriched:
        print("Enrichment failed. Exiting.")
        return

    output = "enriched_" + cleaned
    with open(output, "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved enriched JSON to {output}")

    chat_id_input = input("Enter the Telegram chat ID to send polls to: ")
    bot = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build().bot
    await send_polls_from_json(bot, int(chat_id_input), enriched)
    print("🎉 All polls sent!")

# === Run both the enrichment flow and the interactive bot ===
if __name__ == "__main__":
    asyncio.run(main_quiz_flow())
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
