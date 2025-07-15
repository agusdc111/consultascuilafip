import asyncio
import os
from typing import Optional, Tuple
import requests
from bs4 import BeautifulSoup
from PIL import Image
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from playwright.async_api import async_playwright

BOT_TOKEN = "7670064388:AAFeJY7YXLhFw3_fW4Cd-ay8sfRCodBjC6g"
NOSIS_URL = "https://informes.nosis.com"
AFIP_URL = "https://serviciosweb.afip.gob.ar/TRAMITES_CON_CLAVE_FISCAL/MISAPORTES/app/basica.aspx"
SSSALUD_URL = "https://www.sssalud.gob.ar/index.php?cat=consultas&page=busopc"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "¡Bienvenido! Este bot permite consultar DNI en Nosis, traspasos recientes de obra social y aportes de una persona.\n"
        "Usa /help para ver los comandos disponibles."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Comandos disponibles:\n"
        "/nosis <DNI> - Consulta CUIL y nombre en Nosis.\n"
        "/aportes <CUIL> - Consulta aportes en AFIP.\n"
        "/tras <CUIL> - Consulta traspasos de obra social en SSSalud.\n"
        "/help - Muestra este menú."
    )

# Nosis Functionality
async def nosis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Uso: /nosis <DNI>\nPor favor ingresa un DNI válido (solo números).")
        return

    dni = context.args[0].strip()
    if not dni.isdigit() or len(dni) < 7 or len(dni) > 9:
        await update.message.reply_text("Por favor ingresa un DNI válido (solo números).")
        return

    await update.message.reply_text("Buscando información en Nosis, por favor espera...")

    cuil, name = await search_cuil_name(dni)

    if cuil and name:
        await update.message.reply_text(f"CUIL: {cuil}\nNombre: {name}")
    else:
        await update.message.reply_text("No se pudo obtener información para ese DNI.")

async def search_cuil_name(dni: str) -> Tuple[Optional[str], Optional[str]]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(NOSIS_URL)

        await page.fill("#Busqueda_Texto", dni)
        await page.press("#Busqueda_Texto", "Enter")

        try:
            await page.wait_for_selector("#wrap-resultados .cuit", timeout=30000)
            cuil = await page.text_content("#wrap-resultados .cuit")
            name = await page.text_content("#wrap-resultados .rz")
            await browser.close()
            return (cuil.strip() if cuil else None, name.strip() if name else None)
        except Exception:
            await browser.close()
            return (None, None)

# Aportes Functionality
def recortar_imagen(path_entrada: str, path_salida: str, coordenadas: Tuple[int, int, int, int]) -> None:
    try:
        with Image.open(path_entrada) as img:
            recortada = img.crop(coordenadas)
            recortada.save(path_salida)
    except Exception as e:
        print(f"Error al recortar imagen: {e}")

async def aportes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Uso: /aportes <CUIL>\nPor favor, envía un CUIL válido de 11 dígitos (con o sin guiones).")
        return

    cuil = context.args[0].strip()
    cuil_clean = cuil.replace("-", "")
    if not (cuil_clean.isdigit() and len(cuil_clean) == 11):
        await update.message.reply_text("Por favor, envía un CUIL válido de 11 dígitos (con o sin guiones).")
        return

    await update.message.reply_text("Procesando tu solicitud en AFIP, por favor espera...")

    cuil_reordered = cuil_clean[-1] + cuil_clean[:-1]

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_viewport_size({"width": 1920, "height": 1080})
            await page.goto(AFIP_URL)
            await asyncio.sleep(2)

            await page.fill('#ctl00_ContentPlaceHolder2_txtCuil_txtSufijo', '')
            for digit in cuil_reordered:
                await page.keyboard.type(digit)
                await asyncio.sleep(0.1)

            await page.keyboard.press("Enter")
            await page.wait_for_selector('#ctl00_ContentPlaceHolder2_btnContinuar', timeout=8000)
            await page.click('#ctl00_ContentPlaceHolder2_btnContinuar')
            await asyncio.sleep(3)

            error_div = await page.query_selector('#ctl00_ContentPlaceHolder2_vldSumaryCuil')
            if error_div:
                texto_error = await error_div.inner_text()
                if "no se encuentra declarado" in texto_error:
                    await update.message.reply_text("❌ El CUIL no se encuentra declarado en el sistema de AFIP.")
                    await browser.close()
                    return

            siguiente_btn = await page.query_selector('#ctl00_ContentPlaceHolder2_btnEmpleSiguiente')
            temp_files = []

            if siguiente_btn:
                await page.screenshot(path="antes_full.png", full_page=True)
                temp_files.append("antes_full.png")
                await siguiente_btn.click()
                await asyncio.sleep(2)
                await page.screenshot(path="despues_full.png", full_page=True)
                temp_files.append("despues_full.png")

                recortar_imagen("antes_full.png", "antes.png", (654, 439, 1273, 891))
                recortar_imagen("despues_full.png", "despues.png", (654, 439, 1273, 891))
                temp_files.extend(["antes.png", "despues.png"])

                await update.message.reply_photo(photo=open("antes.png", "rb"), caption="EMPLEADOR 1")
                await update.message.reply_photo(photo=open("despues.png", "rb"), caption="EMPLEADOR 2")
            else:
                await page.screenshot(path="resultado_full.png", full_page=True)
                temp_files.append("resultado_full.png")
                recortar_imagen("resultado_full.png", "resultado.png", (651, 295, 1273, 751))
                temp_files.append("resultado.png")
                await update.message.reply_photo(photo=open("resultado.png", "rb"), caption="UNICO EMPLEADOR")

            await browser.close()

    except Exception as e:
        await update.message.reply_text(f"Ocurrió un error procesando tu solicitud: {e}")

    finally:
        for archivo in temp_files:
            if os.path.exists(archivo):
                os.remove(archivo)

# Tras Functionality
async def tras(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Uso: /tras <CUIL>\nPor favor ingresa un CUIL válido de 11 dígitos (con o sin guiones).")
        return

    cuil = context.args[0].strip()
    cuil_clean = cuil.replace("-", "")
    if not (cuil_clean.isdigit() and len(cuil_clean) == 11):
        await update.message.reply_text("Por favor ingresa un CUIL válido de 11 dígitos (con o sin guiones).")
        return

    cuil_fmt = f"{cuil_clean[:2]}-{cuil_clean[2:10]}-{cuil_clean[10]}"
    context.user_data['cuil'] = cuil_fmt
    context.user_data['waiting_for_captcha'] = True

    try:
        sess = requests.Session()
        r = sess.get(SSSALUD_URL, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')

        img = soup.find('img', id='siimage')
        captcha_url = img['src'] if img else None
        if not captcha_url:
            context.user_data.clear()
            await update.message.reply_text("No se pudo encontrar el CAPTCHA. Intenta de nuevo más tarde.")
            return
        if not captcha_url.startswith('http'):
            captcha_url = requests.compat.urljoin(SSSALUD_URL, captcha_url)

        img_data = sess.get(captcha_url, timeout=10).content
        context.user_data['session'] = sess

        await context.bot.send_photo(chat_id=update.message.chat_id, photo=img_data)
        await update.message.reply_text("Por favor, ingresa el texto del CAPTCHA mostrado.")
    except Exception as e:
        context.user_data.clear()
        await update.message.reply_text(f"Error al procesar la solicitud: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get('waiting_for_captcha'):
        sess: requests.Session = context.user_data.get('session')
        cuil_fmt: str = context.user_data.get('cuil')
        captcha_text = update.message.text.strip()

        payload = {
            'nro_cuil': cuil_fmt,
            'code': captcha_text,
            'buscar': 'Buscar'
        }

        try:
            r2 = sess.post(SSSALUD_URL, data=payload, timeout=10)
            soup2 = BeautifulSoup(r2.text, 'html.parser')

            if soup2.find('span', style='color:red;'):
                context.user_data.clear()
                await update.message.reply_text(
                    "🚫 CAPTCHA incorrecto. Por favor, envía nuevamente /tras <CUIL> para reiniciar el proceso."
                )
                return

            table = soup2.find('table', class_='tablaconsultas')
            if not table:
                context.user_data.clear()
                await update.message.reply_text("No se encontraron resultados para ese CUIL.")
                return

            filas = table.find_all('tr')[1:]
            mensaje = "Resultado de la consulta:\n\n"
            for fila in filas:
                cols = [td.text.strip() for td in fila.find_all('td')]
                codigo, obra, desde, hasta, mov, estado = cols
                mensaje += (
                    f"{codigo}\n"
                    f"Obra Social: {obra}\n"
                    f"Período desde: {desde}\n"
                    f"Período hasta: {hasta}\n"
                    f"{mov}\n"
                    f"Estado: {estado}\n\n"
                )

            context.user_data.clear()
            await update.message.reply_text(mensaje)

        except Exception as e:
            context.user_data.clear()
            await update.message.reply_text(f"Error al procesar la solicitud: {e}")
    else:
        await update.message.reply_text(
            "Por favor usa un comando válido. Escribe /help para ver los comandos disponibles."
        )

def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("nosis", nosis))
    application.add_handler(CommandHandler("aportes", aportes))
    application.add_handler(CommandHandler("tras", tras))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot iniciado")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()