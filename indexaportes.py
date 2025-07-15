from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time

def get_afip_screenshot(cuil):
    # Normalizar el CUIL: eliminar guiones si los hay
    cuil = cuil.replace("-", "")
    
    # Reordenar: mover el último dígito al principio
    cuil_reordered = cuil[-1] + cuil[:-1]
    
    # Configurar opciones del navegador
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Modo sin interfaz gráfica
    driver = webdriver.Chrome(options=chrome_options)
    
    # Establecer tamaño de ventana
    driver.set_window_size(1920, 1080)
    
    try:
        # Acceder a la página
        driver.get("https://serviciosweb.afip.gob.ar/TRAMITES_CON_CLAVE_FISCAL/MISAPORTES/app/basica.aspx")
        print("Página cargada")
        
        # Esperar 2 segundos para la redirección
        time.sleep(2)
        print("Redirección completada")
        
        # Encontrar el campo de entrada
        input_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "ctl00_ContentPlaceHolder2_txtCuil_txtSufijo"))
        )
        
        # Simular escritura dígito por dígito
        for digit in cuil_reordered:
            input_field.send_keys(digit)
            time.sleep(0.1)  # Pausa breve entre dígitos para simular escritura humana
        print("CUIL ingresado")
        
        # Enviar Enter para procesar la búsqueda
        input_field.send_keys(Keys.RETURN)
        
        # Encontrar y clickear el botón "CONTINUAR"
        continue_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "ctl00_ContentPlaceHolder2_btnContinuar"))
        )
        continue_button.click()
        print("Botón CONTINUAR clickeado")
        
        # Esperar 3 segundos
        time.sleep(3)
        print("Esperando 3 segundos")
        
        # Tomar captura de pantalla y sobrescribirla
        driver.save_screenshot("aportes.png")
        print("Captura de pantalla guardada como 'aportes.png'")
        
        return True
    
    except Exception as e:
        print(f"Error: {e}")
        print("Código fuente de la página:")
        print(driver.page_source)
        driver.save_screenshot("error.png")
        print("Captura de pantalla de error guardada como 'error.png'")
        return False
    
    finally:
        # Cerrar el navegador
        driver.quit()

# Ejemplo de uso
if __name__ == "__main__":
    # Solicitar CUIL al usuario
    cuil = input("Ingrese el CUIL (con o sin guiones): ")
    success = get_afip_screenshot(cuil)
    if success:
        print("Script ejecutado con éxito")
    else:
        print("No se pudo completar la ejecución")