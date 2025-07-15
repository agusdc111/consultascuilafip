import asyncio
import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Reemplaza con tu token de Telegram
BOT_TOKEN = "7670064388:AAFeJY7YXLhFw3_fW4Cd-ay8sfRCodBjC6g"
URL = "https://www.sssalud.gob.ar/index.php?cat=consultas&page=busopc"

def force_kill_driver(driver: webdriver.Chrome):
    """
    Cierra Selenium y mata el proceso de Chromedriver inmediatamente.
    """
    try:
        service = driver.service
        driver.quit()
        if hasattr(service, "process") and service.process:
            service.process.kill()
    except Exception:
        pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "¡Hola! Envíame un CUIL (con o sin guiones) para consultar en SSSalud."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    chat_id = update.message.chat_id

    # --- Caso 1: estamos esperando el CAPTCHA ---
    if context.user_data.get("waiting_for_captcha", False):
        driver: webdriver.Chrome = context.user_data.get("driver")
        cuil_formatted: str = context.user_data.get("cuil_formatted")

        # Si no hay driver, reiniciar
        if not driver:
            await update.message.reply_text(
                "La sesión expiró. Por favor envía de nuevo tu CUIL."
            )
            context.user_data.clear()
            return

        # Ingresamos CUIL + CAPTCHA + click
        try:
            # Reingreso de CUIL por precaución
            el_cuil = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "nro_cuil"))
            )
            el_cuil.clear()
            el_cuil.send_keys(cuil_formatted)

            el_captcha = driver.find_element(By.NAME, "code")
            el_captcha.clear()
            el_captcha.send_keys(text)

            driver.find_element(By.NAME, "buscar").click()

            # 1. Comprobación rápida de mensaje de error de CAPTCHA
            try:
                WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located(
                        (By.XPATH, "//span[@style='color:red;']")
                    )
                )
                # CAPTCHA incorrecto
                force_kill_driver(driver)
                context.user_data.clear()
                await update.message.reply_text(
                    "🚫 CAPTCHA incorrecto. Reinicia enviando tu CUIL nuevamente."
                )
                return
            except TimeoutException:
                # No hubo error, seguimos
                pass

            # 2. Espera de la tabla
            table = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CLASS_NAME, "tablaconsultas"))
            )

            # Parseo y formateo

            # RESULTADO ENVIADO SIN EDITAR

            # soup = BeautifulSoup(table.get_attribute("outerHTML"), "html.parser")
            # filas = soup.find_all("tr")
            # mensaje = "Resultado de la consulta:\n\n"
            # headers = [th.text.strip() for th in filas[0].find_all("th")]
            # for fila in filas[1:]:
            #     cols = [td.text.strip() for td in fila.find_all("td")]
            #     for h, v in zip(headers, cols):
            #         mensaje += f"**{h}:** {v}\n"
            #     mensaje += "—\n"

            # RESULTADO ENVIADO PERSONALZIADO

            
            soup = BeautifulSoup(table.get_attribute("outerHTML"), "html.parser")
            filas = soup.find_all("tr")

            mensaje = "Resultado de la consulta:\n\n"
            # Saltamos la fila de encabezados (filas[0])
            for fila in filas[1:]:
                cols = [td.text.strip() for td in fila.find_all("td")]
                # cols = [ Código registro, Obra Social, Período desde, Período hasta, Código movimiento, Estado ]
                codigo, obra, desde, hasta, movimiento, estado = cols

                mensaje += f"{codigo}\n"
                mensaje += f"Obra Social: {obra}\n"
                mensaje += f"Período desde: {desde}\n"
                mensaje += f"Período hasta: {hasta}\n"
                mensaje += f"{movimiento}\n"
                mensaje += f"Estado: {estado}\n\n"



            # Cerramos todo antes de responder
            force_kill_driver(driver)
            context.user_data.clear()
            await update.message.reply_text(mensaje)
            return

        except Exception as e:
            # En caso de error inesperado
            driver.save_screenshot("error_captcha.png")
            force_kill_driver(driver)
            context.user_data.clear()
            await update.message.reply_text(f"Error al procesar CAPTCHA: {e}")
            with open("error_captcha.png", "rb") as photo:
                await context.bot.send_photo(chat_id=chat_id, photo=photo)
            return

    # --- Caso 2: recibimos un CUIL ---
    cuil_clean = text.replace("-", "")
    if not (cuil_clean.isdigit() and len(cuil_clean) == 11):
        await update.message.reply_text(
            "Por favor ingresa un CUIL válido de 11 dígitos (con o sin guiones)."
        )
        return

    cuil_formatted = f"{cuil_clean[:2]}-{cuil_clean[2:10]}-{cuil_clean[10]}"
    context.user_data["cuil_formatted"] = cuil_formatted

    # Iniciamos navegador
    chrome_opts = Options()
    # chrome_opts.add_argument("--headless")  # Descomenta para producción
    driver = webdriver.Chrome(options=chrome_opts)
    context.user_data["driver"] = driver

    try:
        driver.get(URL)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "nro_cuil"))
        ).send_keys(cuil_formatted)

        # Capturamos y enviamos CAPTCHA
        captcha_el = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "siimage"))
        )
        captcha_el.screenshot("captcha.png")
        with open("captcha.png", "rb") as photo:
            await context.bot.send_photo(chat_id=chat_id, photo=photo)

        await update.message.reply_text("Por favor, ingresa el texto del CAPTCHA mostrado.")
        context.user_data["waiting_for_captcha"] = True

    except Exception as e:
        driver.save_screenshot("error_cuil.png")
        force_kill_driver(driver)
        context.user_data.clear()
        await update.message.reply_text(f"Error al procesar el CUIL: {e}")
        with open("error_cuil.png", "rb") as photo:
            await context.bot.send_photo(chat_id=chat_id, photo=photo)

def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    print("Bot iniciado")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
