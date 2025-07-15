from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time

def get_cuil_and_name(dni):
    # Configurar opciones del navegador
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Modo sin interfaz gráfica
    driver = webdriver.Chrome(options=chrome_options)
    
    # Establecer un tamaño de ventana adecuado
    driver.set_window_size(1920, 1080)
    
    try:
        # Acceder a la página
        driver.get("https://informes.nosis.com")
        print("Página cargada")
        
        # Encontrar el campo de entrada y enviar el DNI
        input_field = driver.find_element(By.ID, "Busqueda_Texto")
        input_field.send_keys(dni)
        input_field.send_keys(Keys.RETURN)
        print("Búsqueda enviada")
        
        # Esperar hasta que el elemento sea visible (máximo 30 segundos)
        WebDriverWait(driver, 30).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "#wrap-resultados .cuit"))
        )
        print("Resultados cargados")
        
        # Extraer CUIL y nombre
        cuil_element = driver.find_element(By.CSS_SELECTOR, "#wrap-resultados .cuit")
        name_element = driver.find_element(By.CSS_SELECTOR, "#wrap-resultados .rz")
        
        cuil = cuil_element.text.strip()
        name = name_element.text.strip()
        
        return cuil, name
    
    except Exception as e:
        # Manejar el error imprimiendo detalles útiles
        print(f"Error: {e}")
        print("Código fuente de la página:")
        print(driver.page_source)
        driver.save_screenshot("error.png")
        print("Captura de pantalla guardada como 'error.png'")
        return None, None
    
    finally:
        # Cerrar el navegador
        driver.quit()

# Ejemplo de uso
if __name__ == "__main__":
    
    dni = input("DNI a consultar: ")
    cuil, name = get_cuil_and_name(dni)
    if cuil and name:
        print(f"CUIL: {cuil}")
        print(f"Nombre: {name}")
    else:
        print("No se pudo obtener la información.")