import json
import logging
from pathlib import Path

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

import config
from checker import DB
from vision import scan_photo
from web_search import search_unknowns
from formatter import format_scan_result

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Pre-serialize DB for prompt injection (done once at startup)
DB_STR = json.dumps(DB)

WELCOME_MESSAGE = """\
👶 *G6PD Safety Scanner*

Send me a photo of any product label — medicine, food, cosmetic, supplement — \
and I'll check every ingredient for G6PD deficiency triggers.

I check against:
💊 Drugs & medications
🥦 Foods & legumes
🧪 Food additives & E-numbers
💄 Cosmetics & topical products
🌿 Herbal & traditional medicines
☣️ Household chemicals

Unknown ingredients get a live web search too.

Just send a photo to get started.
"""


def _is_allowed(user_id: int) -> bool:
    return user_id in config.ALLOWED_USER_IDS


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        return
    await update.message.reply_text(WELCOME_MESSAGE, parse_mode="Markdown")


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        return
    await update.message.reply_text(WELCOME_MESSAGE, parse_mode="Markdown")


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        return
    await update.message.reply_text(
        "📸 Send me a photo of a product label and I'll scan it for G6PD triggers."
    )


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        return

    await update.message.reply_text("🔍 Scanning... please wait.")

    try:
        # Download highest-resolution version of the photo
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()

        # Determine media type
        file_path = file.file_path or ""
        media_type = "image/png" if file_path.endswith(".png") else "image/jpeg"

        # Run vision scan
        scan_result = scan_photo(
            image_bytes=bytes(image_bytes),
            media_type=media_type,
            db_str=DB_STR,
            api_key=config.ANTHROPIC_API_KEY,
        )

        # Web search for unknowns
        web_results = []
        unknowns = scan_result.get("unknowns", [])
        if unknowns:
            web_results = search_unknowns(
                unknowns,
                api_key=config.ANTHROPIC_API_KEY,
                max_results=5,
            )

        # Format and send response
        message = format_scan_result(scan_result, web_results)
        await update.message.reply_text(message, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Scan failed: {e}", exc_info=True)
        await update.message.reply_text(
            "⚠️ Scan failed — something went wrong. Please try again with a clearer photo."
        )


def main() -> None:
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    logger.info("G6PD Bot started. Polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
