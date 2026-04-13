"""
bot.py — AURA Creator Bot with live Telegram progress updates
"""
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters

import gemini_gen
import ig_post

load_dotenv(override=True)
MY_ID = int(os.getenv("MY_CHAT_ID"))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID:
        return

    topic = update.message.text.strip()
    if not topic:
        return

    # Status message we'll edit in place
    status_msg = await update.message.reply_text("⚙️ AURA pipeline starting...")

    async def progress(msg: str):
        """Update the status message in Telegram."""
        try:
            await status_msg.edit_text(msg, parse_mode="Markdown")
        except:
            pass

    # Run generation with live updates
    result = await gemini_gen.generate(topic, progress_cb=progress)

    if result["error"] == "session_expired":
        await status_msg.edit_text(
            "⚠️ *Gemini session expired!*\n\n"
            "Run:\n`cd ~/AURA-Automation && source venv/bin/activate && python gemini_login.py`\n\n"
            "Then restart the bot.",
            parse_mode="Markdown"
        )
        return

    if result["error"]:
        await status_msg.edit_text(f"❌ Failed: {result['error']}")
        return

    caption = result["caption"]
    image_path = result["image_path"]

    # ── Send caption ──────────────────────────────────────────────────────────
    await status_msg.edit_text(
        f"✅ *Step 1 — CAPTION:*\n\n{caption}",
        parse_mode="Markdown"
    )

    # ── Send image preview ────────────────────────────────────────────────────
    with open(image_path, "rb") as f:
        await update.message.reply_photo(
            photo=f,
            caption="🎨 *Step 2 — Image generated!*\n📤 Posting to Instagram...",
            parse_mode="Markdown"
        )

    # ── Post to Instagram ─────────────────────────────────────────────────────
    try:
        success = ig_post.post(image_path, caption)
        if success:
            await update.message.reply_text(
                "✅ *Live on @aura2026.socials!* 🎉",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❌ Instagram post failed — check terminal.")
    except Exception as e:
        await update.message.reply_text(f"❌ Post error: {str(e)[:200]}")


async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID:
        return
    await update.message.reply_text(
        "🤖 *AURA Creator Online* ✅\n\n"
        "Send any scene description to generate + post!\n\n"
        "_Example: A pixar girl surfing a glowing wave at sunset_",
        parse_mode="Markdown"
    )


if __name__ == "__main__":
    print("🚀 AURA Creator Bot — Live progress edition")
    app = (
        ApplicationBuilder()
        .token(os.getenv("TELEGRAM_BOT_TOKEN"))
        .read_timeout(300)
        .write_timeout(300)
        .connect_timeout(30)
        .pool_timeout(30)
        .build()
    )
    app.add_handler(CommandHandler("status", handle_status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Listening...")
    app.run_polling()