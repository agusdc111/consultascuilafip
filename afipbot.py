import asyncio
import os
import tempfile
import logging
from typing import Optional, Tuple
import requests
from bs4 import BeautifulSoup
from PIL import Image
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from playwright.async_api import async_playwright
import time

# Configuración de logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    filename="bot.log",
    filemode="a"
)

BOT_TOKEN = "TOKEN DE BOT TELEGRAM"
NOSIS_URL = "https://informes.nosis.com"
AFIP_URL = "https://serviciosweb.afip.gob.ar/TRAMITES_CON_CLAVE_FISCAL/MISAPORTES/app/basica.aspx"
SSSALUD_URL = "https://www.sssalud.gob.ar/index.php?cat=consultas&page=busopc"

# Utility function to crop images
def recortar_imagen(path_entrada: str, path_salida: str, coordenadas: Tuple[int, int, int, int]) -> None:
    """Recorta una imagen y la guarda en el path de salida."""
    try:
        with Image.open(path_entrada) as img:
            recortada = img.crop(coordenadas)
            recortada.save(path_salida)
    except Exception as e:
        logging.error(f"Error al recortar imagen: {e}")

# Command /start
async def main_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mensaje de bienvenida."""
    await update.message.reply_text(
        "👋 ¡Bienvenido! Este bot te ayuda a consultar datos públicos de Argentina.\n"
        "Usa /help para ver los comandos disponibles."
    )

# Command /help
async def main_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra los comandos disponibles."""
    await update.message.reply_text(
        "📋 *Comandos disponibles:*\n"
        "/nosis <DNI> - Consulta CUIL y nombre en Nosis.\n"
        "/aportes <CUIL> - Consulta aportes en AFIP.\n"
        "/tras <CUIL> - Consulta traspasos de obra social en SSSalud.\n"
        "/help - Muestra este menú.",
        parse_mode="Markdown"
    )

# Nosis Functionality
async def nosis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Consulta CUIL y nombre en Nosis a partir de un DNI."""
    if not context.args:
        await update.message.reply_text("⚠️ Uso: /nosis <DNI>\nPor favor, ingresa un DNI válido (solo números).")
        return
    dni = context.args[0].strip()
    if not dni.isdigit() or not (7 <= len(dni) <= 9):
        await update.message.reply_text("❌ DNI inválido. Debe contener solo números (7 a 9 dígitos).")
        return
    await update.message.reply_text("🔎 Buscando información en Nosis, por favor espera...")
    cuil, nombre = await buscar_cuil_nombre(dni)
    if cuil and nombre:
        await update.message.reply_text(f"✅ *CUIL:* {cuil}\n*Nombre:* {nombre}", parse_mode="Markdown")
    else:
        await update.message.reply_text("No se pudo obtener información para ese DNI.")

async def buscar_cuil_nombre(dni: str) -> Tuple[Optional[str], Optional[str]]:
    """Busca CUIL y nombre en Nosis usando Playwright."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(NOSIS_URL)
            await page.fill("#Busqueda_Texto", dni)
            await page.press("#Busqueda_Texto", "Enter")
            await page.wait_for_selector("#wrap-resultados .cuit", timeout=30000)
            cuil = await page.text_content("#wrap-resultados .cuit")
            nombre = await page.text_content("#wrap-resultados .rz")
            return (cuil.strip() if cuil else None, nombre.strip() if nombre else None)
        except Exception as e:
            logging.error(f"Error en Nosis: {e}")
            return (None, None)
        finally:
            await browser.close()

# Aportes Functionality with isolation per request
async def aportes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Consulta aportes en AFIP a partir de un CUIL."""
    if not context.args:
        await update.message.reply_text("⚠️ Uso: /aportes <CUIL>\nEnvía un CUIL válido de 11 dígitos (con o sin guiones).")
        return
    cuil_original = context.args[0].strip()
    cuil_clean = cuil_original.replace("-", "")
    if not (cuil_clean.isdigit() and len(cuil_clean) == 11):
        await update.message.reply_text("❌ CUIL inválido. Debe tener 11 dígitos (con o sin guiones).")
        return
    await update.message.reply_text("⏳ Procesando tu solicitud en AFIP, por favor espera...")
    with tempfile.TemporaryDirectory(prefix=f"aportes_{update.effective_chat.id}_") as tmpdir:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.set_viewport_size({"width": 1920, "height": 1080})
                await page.goto(AFIP_URL)
                await asyncio.sleep(2)

                # Generar variantes posibles del CUIL
                variantes = []
                # Si el usuario lo envió con guiones
                if "-" in cuil_original:
                    variantes.append(cuil_original.replace("-", ""))  # solo números
                    variantes.append(cuil_original)                  # con guiones
                else:
                    variantes.append(cuil_original)                  # solo números
                    # Si empieza con 0, probar sin el primer dígito
                    if cuil_original.startswith("0"):
                        variantes.append(cuil_original[1:])
                    # Si tiene 11 dígitos, probar con guiones
                    if len(cuil_original) == 11:
                        variantes.append(f"{cuil_original[:2]}-{cuil_original[2:10]}-{cuil_original[10]}")
                # Probar con el número sin el primer dígito
                if len(cuil_clean) == 11:
                    variantes.append(cuil_clean)
                    variantes.append(cuil_clean[1:])
                    variantes.append(f"{cuil_clean[:2]}-{cuil_clean[2:10]}-{cuil_clean[10]}")
                    variantes.append(f"{cuil_clean[10]}{cuil_clean[:10]}")  # último dígito adelante

                # Eliminar duplicados preservando el orden
                seen = set()
                variantes = [x for x in variantes if not (x in seen or seen.add(x))]

                cuil_valido = None
                for intento, cuil_var in enumerate(variantes, 1):
                    await page.fill('#ctl00_ContentPlaceHolder2_txtCuil_txtSufijo', '')
                    # Limpiar el campo antes de escribir
                    await page.click('#ctl00_ContentPlaceHolder2_txtCuil_txtSufijo', click_count=3)
                    await page.keyboard.press("Backspace")
                    await asyncio.sleep(0.1)
                    for digito in cuil_var:
                        await page.keyboard.type(digito)
                        await asyncio.sleep(0.01)
                    await page.keyboard.press("Enter")
                    await page.wait_for_selector('#ctl00_ContentPlaceHolder2_btnContinuar', timeout=8000)
                    await page.click('#ctl00_ContentPlaceHolder2_btnContinuar')
                    await asyncio.sleep(2)
                    # Verificar si aparece el mensaje de CUIL inválido
                    error_div = await page.query_selector('#ctl00_ContentPlaceHolder2_vldSumaryCuil')
                    error_text = ""
                    if error_div:
                        error_text = await error_div.inner_text()
                    if "El CUIL ingresado es inválido." not in error_text:
                        cuil_valido = cuil_var
                        break
                if not cuil_valido:
                    await update.message.reply_text("❌ El CUIL ingresado es inválido en todos los formatos probados.")
                    return

                # Continuar con el flujo normal si el CUIL fue aceptado
                await asyncio.sleep(1)
                path_full = os.path.join(tmpdir, "full_0.png")
                await page.screenshot(path=path_full, full_page=True)
                siguiente = await page.query_selector('#ctl00_ContentPlaceHolder2_btnEmpleSiguiente')
                if not siguiente:
                    path_emple = os.path.join(tmpdir, "unico.png")
                    recortar_imagen(path_full, path_emple, (651, 295, 1273, 751))
                    await update.message.reply_photo(photo=open(path_emple, "rb"), caption="UNICO EMPLEADOR")
                else:
                    contador = 1
                    path_prev = path_full
                    while True:
                        path_emple = os.path.join(tmpdir, f"empleador_{contador}.png")
                        recortar_imagen(path_prev, path_emple, (654, 439, 1273, 891))
                        await update.message.reply_photo(photo=open(path_emple, "rb"), caption=f"EMPLEADOR {contador}")
                        siguiente = await page.query_selector('#ctl00_ContentPlaceHolder2_btnEmpleSiguiente')
                        if not siguiente:
                            break
                        await siguiente.click()
                        await asyncio.sleep(2)
                        new_full = os.path.join(tmpdir, f"full_{contador}.png")
                        await page.screenshot(path=new_full, full_page=True)
                        path_prev = new_full
                        contador += 1
            except Exception as e:
                logging.error(f"Error en aportes: {e}")
                await update.message.reply_text(f"Ocurrió un error procesando tu solicitud. Intenta más tarde.")
            finally:
                await browser.close()

# Tras Functionality (session per user)
async def tras(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Consulta traspasos de obra social en SSSalud (requiere captcha)."""
    if not context.args:
        await update.message.reply_text("⚠️ Uso: /tras <CUIL>\nPor favor, ingresa un CUIL válido de 11 dígitos (con o sin guiones).")
        return
    cuil = context.args[0].strip().replace("-", "")
    if not (cuil.isdigit() and len(cuil) == 11):
        await update.message.reply_text("❌ CUIL inválido. Debe tener 11 dígitos (con o sin guiones).")
        return
    cuil_fmt = f"{cuil[:2]}-{cuil[2:10]}-{cuil[10]}"
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
        await update.message.reply_text("📝 Por favor, ingresa el texto del CAPTCHA mostrado.")
    except Exception as e:
        context.user_data.clear()
        logging.error(f"Error en tras: {e}")
        await update.message.reply_text("Error al procesar la solicitud. Intenta más tarde.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja mensajes de texto (para resolver el captcha de SSSalud)."""
    if context.user_data.get('waiting_for_captcha'):
        sess: requests.Session = context.user_data.get('session')
        cuil_fmt: str = context.user_data.get('cuil')
        captcha_text = update.message.text.strip()
        payload = {'nro_cuil': cuil_fmt, 'code': captcha_text, 'buscar': 'Buscar'}
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
            mensaje = "📄 *Resultado de la consulta:*\n\n"
            for fila in filas:
                cols = [td.text.strip() for td in fila.find_all('td')]
                if len(cols) < 6:
                    continue
                codigo, obra, desde, hasta, mov, estado = cols
                mensaje += (
                    f"• {codigo}\n"
                    f"  Obra Social: {obra}\n"
                    f"  Período desde: {desde}\n"
                    f"  Período hasta: {hasta}\n"
                    f"  {mov}\n"
                    f"  Estado: {estado}\n\n"
                )
            context.user_data.clear()
            await update.message.reply_text(mensaje, parse_mode="Markdown")
        except Exception as e:
            context.user_data.clear()
            logging.error(f"Error resolviendo captcha SSSalud: {e}")
            await update.message.reply_text("Error al procesar la solicitud. Intenta más tarde.")
    else:
        await update.message.reply_text(
            "Por favor usa un comando válido. Escribe /help para ver los comandos disponibles."
        )

# Ping functionality
async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mide el ping del bot."""
    inicio = time.perf_counter()
    mensaje = await update.message.reply_text("🏓 Pong!")
    fin = time.perf_counter()
    ping_ms = int((fin - inicio) * 1000)
    await mensaje.edit_text(f"🏓 Pong! ({ping_ms} ms)")

# Main and handler configuration
def main() -> None:
    """Configura y lanza el bot."""
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", main_start))
    application.add_handler(CommandHandler("help", main_help))
    application.add_handler(CommandHandler("nosis", nosis))
    application.add_handler(CommandHandler("aportes", aportes))
    application.add_handler(CommandHandler("tras", tras))
    application.add_handler(CommandHandler("ping", ping))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logging.info("Bot iniciado")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()