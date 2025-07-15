import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = "7670064388:AAFeJY7YXLhFw3_fW4Cd-ay8sfRCodBjC6g"
URL = "https://www.sssalud.gob.ar/index.php?cat=consultas&page=busopc"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "¡Hola! Envíame un CUIL (con o sin guiones) para consultar en SSSalud."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    chat_id = update.message.chat_id

    # Caso 1: Si no existe sesión en context, interpretamos text como CUIL
    if 'session' not in context.user_data:
        cuil_clean = text.replace("-", "")
        if not (cuil_clean.isdigit() and len(cuil_clean) == 11):
            return await update.message.reply_text("Por favor ingresa un CUIL válido de 11 dígitos (con o sin guiones).")

        cuil_fmt = f"{cuil_clean[:2]}-{cuil_clean[2:10]}-{cuil_clean[10]}"
        context.user_data['cuil'] = cuil_fmt

        # Iniciamos sesión HTTP
        sess = requests.Session()
        r = sess.get(URL, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')

        # Extraemos CAPTCHA
        img = soup.find('img', id='siimage')
        captcha_url = img['src'] if img else None
        if not captcha_url:
            return await update.message.reply_text("No se pudo encontrar el CAPTCHA. Intenta de nuevo más tarde.")
        # A veces la URL es relativa
        if not captcha_url.startswith('http'):
            captcha_url = requests.compat.urljoin(URL, captcha_url)

        img_data = sess.get(captcha_url, timeout=10).content
        context.user_data['session'] = sess

        # Enviamos la imagen al usuario
        await context.bot.send_photo(chat_id=chat_id, photo=img_data)
        return await update.message.reply_text("Por favor, ingresa el texto del CAPTCHA mostrado.")

    # Caso 2: Ya existe sesión => text es el CAPTCHA
    sess: requests.Session = context.user_data['session']
    cuil_fmt: str = context.user_data['cuil']

    # Construimos payload para POST
    payload = {
        'nro_cuil': cuil_fmt,
        'code': text,
        'buscar': 'Buscar'
    }

    # Ejecutamos POST
    r2 = sess.post(URL, data=payload, timeout=10)
    soup2 = BeautifulSoup(r2.text, 'html.parser')

    # Verificamos error de CAPTCHA
    if soup2.find('span', style='color:red;'):
        context.user_data.clear()
        return await update.message.reply_text(
            "🚫 CAPTCHA incorrecto. Por favor, envía nuevamente tu CUIL para reiniciar el proceso."
        )

    # Extraemos tabla de resultados
    table = soup2.find('table', class_='tablaconsultas')
    if not table:
        context.user_data.clear()
        return await update.message.reply_text("No se encontraron resultados para ese CUIL.")

    filas = table.find_all('tr')[1:]  # saltamos encabezados
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

    # Limpiamos contexto y enviamos
    context.user_data.clear()
    await update.message.reply_text(mensaje)


def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    print('Bot iniciado')
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
