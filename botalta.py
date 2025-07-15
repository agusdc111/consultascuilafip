import os
import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from playwright.async_api import async_playwright

BOT_TOKEN = "7670064388:AAFeJY7YXLhFw3_fW4Cd-ay8sfRCodBjC6g"
ALTA_URL = "https://www.sssalud.gob.ar/index.php?page=bus650&user=GRAL&cat=consultas"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "¡Bienvenido! Este bot permite consultar la obra social que dio de alta a un empleador.\n"
        "Usa /help para ver los comandos disponibles."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Comandos disponibles:\n"
        "/alta <CUIL> - Consulta la obra social que le dio de alta su empleador.\n"
        "/help - Muestra este menú."
    )

async def alta(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Uso: /alta <CUIL>\nPor favor ingresa un CUIL válido de 11 dígitos.")
        return

    cuil = context.args[0].strip().replace("-", "")
    if not (cuil.isdigit() and len(cuil) == 11):
        await update.message.reply_text("Por favor ingresa un CUIL válido de 11 dígitos.")
        return

    cuil_fmt = f"{cuil[:2]}-{cuil[2:10]}-{cuil[10]}"
    context.user_data['cuil'] = cuil_fmt
    context.user_data['waiting_for_captcha'] = True

    try:
        sess = requests.Session()
        r = sess.get(ALTA_URL, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')

        img = soup.find('img', id='siimage')
        captcha_url = img['src'] if img else None
        if not captcha_url:
            context.user_data.clear()
            await update.message.reply_text("No se pudo encontrar el CAPTCHA. Intenta de nuevo más tarde.")
            return
        if not captcha_url.startswith('http'):
            captcha_url = requests.compat.urljoin(ALTA_URL, captcha_url)

        img_data = sess.get(captcha_url, timeout=10).content
        with open("captcha.png", "wb") as f:
            f.write(img_data)

        context.user_data['session'] = sess
        await context.bot.send_photo(chat_id=update.message.chat_id, photo=open("captcha.png", "rb"))
        await update.message.reply_text("Por favor, ingresa el texto del CAPTCHA mostrado.")

    except Exception as e:
        context.user_data.clear()
        if os.path.exists("captcha.png"):
            os.remove("captcha.png")
        await update.message.reply_text(f"Error al procesar la solicitud: {e}")

def formatear_texto_afiliacion(texto_crudo: str) -> str:
    lineas = texto_crudo.split('\n')
    resultado = []
    skip_next = False

    titulos = [
        "DATOS DE AFILIACION VIGENTE",
        "Datos personales",
        "Datos de Afiliación"
    ]

    for i, linea in enumerate(lineas):
        if skip_next:
            skip_next = False
            continue

        linea_strip = linea.strip()

        if linea_strip in titulos:
            if resultado and resultado[-1] != '':
                resultado.append('')
            resultado.append(linea_strip)
            resultado.append('')
        else:
            if i + 1 < len(lineas):
                siguiente = lineas[i+1].strip()
                if siguiente and siguiente not in titulos:
                    resultado.append(f"{linea_strip}: {siguiente}")
                    skip_next = True
                else:
                    resultado.append(linea_strip)
            else:
                resultado.append(linea_strip)

    final = []
    for linea in resultado:
        if final and linea == '' and final[-1] == '':
            continue
        final.append(linea)

    return '\n'.join(final)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get('waiting_for_captcha'):
        sess = context.user_data.get('session')
        cuil_fmt = context.user_data.get('cuil')
        captcha_text = update.message.text.strip()

        try:
            payload = {
                'cuil_b': cuil_fmt,
                'code': captcha_text,
                'B1': 'Consultar'
            }

            r2 = sess.post(ALTA_URL, data=payload, timeout=10)
            soup2 = BeautifulSoup(r2.text, 'html.parser')

            main_table = soup2.find('table', class_='tablaconsultas', summary=lambda s: s and "afiliación vigente" in s.lower())
            if not main_table:
                raise Exception("CAPTCHA incorrecto o no se encontraron resultados.")

            texto_completo = main_table.get_text(separator="\n", strip=True)
            texto_formateado = formatear_texto_afiliacion(texto_completo)

            await update.message.reply_text(f"📋 Resultado:\n\n{texto_formateado}")

            context.user_data.clear()
            if os.path.exists("captcha.png"):
                os.remove("captcha.png")

        except Exception as e:
            context.user_data.clear()
            if os.path.exists("captcha.png"):
                os.remove("captcha.png")
            await update.message.reply_text(f"🚫 Error: {e}\nPor favor envía nuevamente /alta <CUIL> para reiniciar.")
    else:
        await update.message.reply_text("Por favor usa un comando válido. Escribe /help para ver los comandos disponibles.")

def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("alta", alta))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot iniciado")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
