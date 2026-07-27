from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time

print("Descargando drivers necesarios... (esto puede tardar la primera vez)")

# Esta línea mágica instala el controlador de Chrome automáticamente
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))

print("¡Abriendo navegador!")
# Le ordenamos ir a Google
driver.get("https://www.google.com")

print("Esperando 5 segundos para que veas que funciona...")
time.sleep(5)

driver.quit()
print(" Prueba finalizada con éxito.")