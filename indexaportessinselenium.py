import asyncio
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from playwright.async_api import async_playwright
from PIL import Image

BOT_TOKEN = "7670064388:AAFeJY7YXLhFw3_fW4Cd-ay8sfRCodBjC6g"
URL = "https://serviciosweb.afip.gob.ar/TRAMITES_CON_CLAVE_FISCAL/MISAPORTES/app/basica.aspx"

# Función para recortar imágenes
def recortar_imagen(path_entrada, path_salida, coordenadas):
    with Image.open(path_entrada) as img:
        recortada = img.crop(coordenadas)
        recortada.save(path_salida)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hola! Envíame un CUIL (con o sin guiones) para consultar en AFIP.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    text = update.message.text.strip()

    cuil_clean = text.replace("-", "")
    if not (cuil_clean.isdigit() and len(cuil_clean) == 11):
        await update.message.reply_text("Por favor, enviá un CUIL válido de 11 dígitos (con o sin guiones).")
        return

    # ✅ Enviar mensaje de procesamiento
    await update.message.reply_text("Procesando tu solicitud, por favor espera...")

    cuil_reordered = cuil_clean[-1] + cuil_clean[:-1]

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_viewport_size({"width": 1920, "height": 1080})
            await page.goto(URL)
            await asyncio.sleep(2)

            await page.fill('#ctl00_ContentPlaceHolder2_txtCuil_txtSufijo', '')
            for digit in cuil_reordered:
                await page.keyboard.type(digit)
                await asyncio.sleep(0.1)

            await page.keyboard.press("Enter")
            await page.wait_for_selector('#ctl00_ContentPlaceHolder2_btnContinuar', timeout=8000)
            await page.click('#ctl00_ContentPlaceHolder2_btnContinuar')
            await asyncio.sleep(3)

            # ⚠️ Verificar si aparece el mensaje de CUIL no encontrado
            error_div = await page.query_selector('#ctl00_ContentPlaceHolder2_vldSumaryCuil')
            if error_div:
                texto_error = await error_div.inner_text()
                if "no se encuentra declarado" in texto_error:
                    await update.message.reply_text("❌ El CUIL no se encuentra declarado en el sistema de AFIP.")
                    await browser.close()
                    return

            siguiente_btn = await page.query_selector('#ctl00_ContentPlaceHolder2_btnEmpleSiguiente')

            if siguiente_btn:
                # Dos capturas: antes y después de hacer clic en "Siguiente"
                await page.screenshot(path="antes_full.png", full_page=True)
                await siguiente_btn.click()
                await asyncio.sleep(2)
                await page.screenshot(path="despues_full.png", full_page=True)

                # Recorte: de (654, 439) a (1273, 891)
                recortar_imagen("antes_full.png", "antes.png", (654, 439, 1273, 891))
                recortar_imagen("despues_full.png", "despues.png", (654, 439, 1273, 891))

                await update.message.reply_photo(photo=open("antes.png", "rb"), caption="EMPLEADOR 1")
                await update.message.reply_photo(photo=open("despues.png", "rb"), caption="EMPLEADOR 2")
            else:
                # Solo una captura: resultado
                await page.screenshot(path="resultado_full.png", full_page=True)

                # Recorte: de (651, 295) a (1273, 751)
                recortar_imagen("resultado_full.png", "resultado.png", (651, 295, 1273, 751))
                await update.message.reply_photo(photo=open("resultado.png", "rb"), caption="UNICO EMPLEADOR")

            await browser.close()

    except Exception as e:
        await update.message.reply_text(f"Ocurrió un error procesando tu solicitud: {e}")

    finally:
        for archivo in [
            "antes_full.png", "despues_full.png", "resultado_full.png",
            "antes.png", "despues.png", "resultado.png"
        ]:
            if os.path.exists(archivo):
                os.remove(archivo)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot iniciado")
    app.run_polling()

if __name__ == "__main__":
    main()
