from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import telegram
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import os

# Token del bot (reemplaza con el tuyo)
BOT_TOKEN = "7670064388:AAFeJY7YXLhFw3_fW4Cd-ay8sfRCodBjC6g"

# Estados de la barra de progreso
PROGRESS_BAR = ["[- - - - -] 0/5", "[█ - - - -] 1/5", "[█ █ - - -] 2/5", "[█ █ █ - -] 3/5", "[█ █ █ █ -] 4/5", "[█ █ █ █ █] 5/5"]

async def start(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("¡Hola! Envíame un CUIL (con o sin guiones) y te devolveré una captura de pantalla de los aportes de AFIP.")

async def handle_cuil(update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
    cuil = update.message.text
    chat_id = update.message.chat_id
    
    # Normalizar el CUIL: eliminar guiones si los hay
    cuil = cuil.replace("-", "")
    
    # Validar que el CUIL tenga 11 dígitos
    if not (len(cuil) == 11 and cuil.isdigit()):
        await update.message.reply_text("Por favor, ingresa un CUIL válido de 11 dígitos (con o sin guiones).")
        return
    
    # Reordenar: mover el último dígito al principio
    cuil_reordered = cuil[-1] + cuil[:-1]
    
    # Enviar mensaje inicial con la barra de progreso
    progress_message = await update.message.reply_text(PROGRESS_BAR[0])
    
    # Configurar opciones del navegador
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Modo sin interfaz gráfica
    driver = webdriver.Chrome(options=chrome_options)
    
    # Establecer tamaño de ventana
    driver.set_window_size(1920, 1080)
    
    try:
        # Acceso a la página
        driver.get("https://serviciosweb.afip.gob.ar/TRAMITES_CON_CLAVE_FISCAL/MISAPORTES/app/basica.aspx")
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=progress_message.message_id,
            text=PROGRESS_BAR[1]
        )
        
        # Esperar 2 segundos para la redirección
        time.sleep(2)
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=progress_message.message_id,
            text=PROGRESS_BAR[2]
        )
        
        # Encontrar el campo de entrada
        input_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "ctl00_ContentPlaceHolder2_txtCuil_txtSufijo"))
        )
        
        # Simular escritura dígito por dígito
        for digit in cuil_reordered:
            input_field.send_keys(digit)
            time.sleep(0.1)  # Pausa breve entre dígitos
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=progress_message.message_id,
            text=PROGRESS_BAR[3]
        )
        
        # Enviar Enter
        input_field.send_keys(Keys.RETURN)
        
        # Encontrar y clickear el botón "CONTINUAR"
        continue_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "ctl00_ContentPlaceHolder2_btnContinuar"))
        )
        continue_button.click()
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=progress_message.message_id,
            text=PROGRESS_BAR[4]
        )
        
        # Esperar 3 segundos
        time.sleep(3)
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=progress_message.message_id,
            text=PROGRESS_BAR[5]
        )
        
        # Tomar captura de pantalla
        driver.save_screenshot("aportes.png")
        
        # Enviar la captura al usuario
        with open("aportes.png", "rb") as photo:
            await context.bot.send_photo(chat_id=chat_id, photo=photo)
        print("Captura de pantalla enviada")
        
    except Exception as e:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=progress_message.message_id,
            text=f"Error: {str(e)}"
        )
        driver.save_screenshot("error.png")
        await context.bot.send_photo(chat_id=chat_id, photo=open("error.png", "rb"))
        print("Captura de pantalla de error enviada")
    
    finally:
        driver.quit()

def main():
    # Crear la aplicación del bot
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Comando /start
    application.add_handler(CommandHandler("start", start))
    
    # Manejar mensajes con texto (CUIL)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cuil))
    
    # Iniciar el bot
    print("Bot iniciado")
    application.run_polling(allowed_updates=telegram.Update.ALL_TYPES)

if __name__ == "__main__":
    main()