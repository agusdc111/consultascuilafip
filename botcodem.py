import re
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
import PyPDF2
import os

# Token del bot de Telegram
TOKEN = "7647905801:AAGQdzCys6pcPTdgLXSbuSS5gG8O8ZBqhY4"

def process_input(input_str):
    """Procesa el input del usuario y devuelve tipo (DNI/CUIT) y número limpio."""
    numbers = re.sub(r'\D', '', input_str)  # Elimina todo lo que no sea número
    if len(numbers) == 8:
        return 'DNI', numbers
    elif len(numbers) == 11:
        return 'CUIT', numbers
    else:
        return None, None

async def scrape_anses(doc_number, update: Update):
    """Interactúa con la página de ANSES y extrae la información."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # Navegador visible
        page = await browser.new_page()
        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "es-AR,es;q=0.8,en-US;q=0.5,en;q=0.3"
        })
        
        try:
            # Acceder a la página con un tiempo de espera mayor
            await page.goto("https://servicioswww.anses.gob.ar/ooss2/", timeout=60000)
            
            # Verificar si hay CAPTCHA
            captcha = await page.query_selector('div.g-recaptcha')
            if captcha:
                print("DEBUG: Se detectó un CAPTCHA en la página.")
                return "Error: La página requiere resolver un CAPTCHA. Por favor, intenta desde un navegador manualmente."
            
            # Ingresar DNI/CUIT
            await page.fill('input[name="ctl00$ContentPlaceHolder1$txtDoc"]', doc_number)
            
            max_attempts = 10
            attempt = 0
            
            # Esperar 1 segundo antes del primer intento
            if attempt == 0:
                await asyncio.sleep(0.51)
            
            while attempt <= max_attempts:
                # Hacer clic en Continuar
                await page.click('input[name="ctl00$ContentPlaceHolder1$Button1"]')
                
                # Esperar a que la página cargue
                await page.wait_for_load_state('networkidle', timeout=60000)
                
                # Verificar si hay mensaje de error
                error_msg = await page.query_selector('span#ContentPlaceHolder1_MessageLabel')
                if error_msg:
                    error_text = await error_msg.inner_text()
                    print(f"DEBUG: Mensaje de error encontrado en intento {attempt + 1}: {error_text}")
                    
                    # Si el error es "La consulta no arrojó resultados.", no reintentar
                    if error_text == "La consulta no arrojó resultados.":
                        print("DEBUG: Error de consulta sin resultados, deteniendo reintentos.")
                        return f"Error: {error_text}"
                    
                    if attempt == max_attempts:
                        print("DEBUG: Se alcanzó el máximo de intentos.")
                        return f"Error: No se pudieron obtener datos tras {max_attempts} intentos. Último error: {error_text}"
                    
                    # Enviar mensaje de reintento al usuario
                    await update.message.reply_text("Reintentando...")
                    attempt += 1
                    await asyncio.sleep(2)  # Esperar 2 segundos antes del próximo intento
                    continue
                
                # Si no hay mensaje de error, intentar extraer información
                html = await page.content()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Verificar si la tabla esperada existe
                table = soup.find('table', id='ContentPlaceHolder1_DGOOSS')
                if not table:
                    print("DEBUG: No se encontró la tabla ContentPlaceHolder1_DGOOSS.")
                    if attempt == max_attempts:
                        print("DEBUG: Se alcanzó el máximo de intentos.")
                        return f"Error: No se encontraron datos en la página tras {max_attempts} intentos. Verifica el DNI/CUIT ingresado."
                    
                    # Enviar mensaje de reintento al usuario
                    await update.message.reply_text("Reintentando...")
                    attempt += 1
                    await asyncio.sleep(2)  # Esperar 2 segundos antes del próximo intento
                    continue
                
                # Extraer CUIL
                cuil_element = soup.find('span', id='ContentPlaceHolder1_lblCuil')
                if not cuil_element:
                    print("DEBUG: No se encontró el elemento ContentPlaceHolder1_lblCuil.")
                    if attempt == max_attempts:
                        print("DEBUG: Se alcanzó el máximo de intentos.")
                        return f"Error: No se pudo encontrar el CUIL en la página tras {max_attempts} intentos."
                    
                    # Enviar mensaje de reintento al usuario
                    await update.message.reply_text("Reintentando...")
                    attempt += 1
                    await asyncio.sleep(2)  # Esperar 2 segundos antes del próximo intento
                    continue
                
                cuil = cuil_element.text.strip()
                
                # Extraer Nombre
                nombre_element = soup.find('span', id='ContentPlaceHolder1_lblNombre')
                if not nombre_element:
                    print("DEBUG: No se encontró el elemento ContentPlaceHolder1_lblNombre.")
                    if attempt == max_attempts:
                        print("DEBUG: Se alcanzó el máximo de intentos.")
                        return f"Error: No se pudo encontrar el nombre en la página tras {max_attempts} intentos."
                    
                    # Enviar mensaje de reintento al usuario
                    await update.message.reply_text("Reintentando...")
                    attempt += 1
                    await asyncio.sleep(2)  # Esperar 2 segundos antes del próximo intento
                    continue
                
                nombre = nombre_element.text.strip()
                
                # Extraer Descripción y Condición
                rows = table.find_all('tr')
                descripcion, condicion = None, None
                for row in rows[1:]:  # Saltar el encabezado
                    cells = row.find_all('td')
                    if len(cells) >= 4:
                        descripcion = cells[1].text.strip()
                        condicion = cells[3].text.strip()
                        break
                
                if not descripcion or not condicion:
                    print("DEBUG: No se pudieron extraer descripción o condición.")
                    if attempt == max_attempts:
                        print("DEBUG: Se alcanzó el máximo de intentos.")
                        return f"Error: No se pudieron extraer la descripción o condición tras {max_attempts} intentos."
                    
                    # Enviar mensaje de reintento al usuario
                    await update.message.reply_text("Reintentando...")
                    attempt += 1
                    await asyncio.sleep(2)  # Esperar 2 segundos antes del próximo intento
                    continue
                
                # Si llegamos aquí, los datos se extrajeron correctamente
                break
            
            # Descargar el PDF
            async with page.expect_download(timeout=30000) as download_info:
                await page.click('a[href*="__doPostBack"]')
            download = await download_info.value
            pdf_path = await download.path()
            
            # Extraer fecha de nacimiento del PDF
            birthdate = extract_birthdate_from_pdf(pdf_path)
            
            # Formatear mensaje
            message = f"""
👤 Nombre: {nombre}
🪪 CUIL N°: {cuil}
♦ Situacion: {descripcion}
✅ Condición: {condicion}
📅 Fecha de Nacimiento: {birthdate or 'No disponible'}
"""
            return message
        
        except PlaywrightTimeoutError:
            print("DEBUG: Tiempo de espera agotado al cargar la página.")
            return "Error: Tiempo de espera agotado al cargar la página. Intenta de nuevo."
        except Exception as e:
            print(f"DEBUG: Error inesperado: {str(e)}")
            return f"Error inesperado: {str(e)}"

def extract_birthdate_from_pdf(pdf_path):
    """Extrae la fecha de nacimiento del PDF."""
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            text = ''
            for page in reader.pages:
                text += page.extract_text() or ''
            match = re.search(r'Fecha de Nacimiento:\s*(\d{2}/\d{2}/\d{4})', text)
            return match.group(1) if match else None
    except Exception:
        return None

async def codem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /codem."""
    if len(context.args) != 1:
        await update.message.reply_text("Uso: /codem <DNI o CUIT> (DNI: 8 dígitos, CUIT: 11 dígitos, con o sin guiones)")
        return
    
    user_input = context.args[0]
    doc_type, doc_number = process_input(user_input)
    
    if not doc_type:
        await update.message.reply_text("Uso: /codem <DNI o CUIT> (DNI: 8 dígitos, CUIT: 11 dígitos, con o sin guiones)")
        return
    
    # Enviar mensaje inicial
    await update.message.reply_text("Buscando datos en CODEM...")
    
    # Obtener información de ANSES
    result = await scrape_anses(doc_number, update)
    await update.message.reply_text(result)

def main():
    """Inicia el bot de Telegram."""
    print("Bot iniciado")
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("codem", codem_command))
    application.run_polling()

if __name__ == "__main__":
    main()
