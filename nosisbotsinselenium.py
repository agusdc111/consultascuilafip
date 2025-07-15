import asyncio
from typing import Optional, Tuple
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from playwright.async_api import async_playwright

BOT_TOKEN = "7670064388:AAFeJY7YXLhFw3_fW4Cd-ay8sfRCodBjC6g"
URL = "https://informes.nosis.com"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "¡Hola! Envíame un DNI para consultar el CUIL y nombre."
    )

async def search_cuil_name(dni: str) -> Tuple[Optional[str], Optional[str]]:
    """Usa Playwright para buscar CUIL y nombre dado un DNI."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)  # headless para servidores
        page = await browser.new_page()
        await page.goto(URL)

        # Esperamos que cargue el input y tipeamos el DNI
        await page.fill("#Busqueda_Texto", dni)
        await page.press("#Busqueda_Texto", "Enter")

        try:
            # Esperamos que aparezca el resultado (hasta 30 seg)
            await page.wait_for_selector("#wrap-resultados .cuit", timeout=30000)

            cuil = await page.text_content("#wrap-resultados .cuit")
            name = await page.text_content("#wrap-resultados .rz")

            await browser.close()
            return (cuil.strip() if cuil else None, name.strip() if name else None)

        except Exception:
            await browser.close()
            return (None, None)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    dni = update.message.text.strip()

    if not dni.isdigit() or len(dni) < 7 or len(dni) > 9:
        await update.message.reply_text("Por favor ingresa un DNI válido (solo números).")
        return

    await update.message.reply_text("Buscando información, por favor espera...")

    cuil, name = await search_cuil_name(dni)

    if cuil and name:
        await update.message.reply_text(f"CUIL: {cuil}\nNombre: {name}")
    else:
        await update.message.reply_text("No se pudo obtener información para ese DNI.")

def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot iniciado")
    application.run_polling()

if __name__ == "__main__":
    main()
