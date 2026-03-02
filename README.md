# Optimizador de CV con IA 

Sistema inteligente desarrollado para las ingeniería en **Mecatrónica**, diseñado para auditar CVs bajo estándares ATS y sugerir perfiles laborales mediante IA.

##  Características
* **Análisis Matemático:** Similitud de coseno con `scikit-learn`.
* **Procesamiento de Lenguaje:** Extracción de entidades con `spaCy`.
* **Inferencia Inteligente:** Sugerencia autónoma de roles con **Google Gemini 1.5 Flash**.

##  Instalación
1. Clonar el repositorio.
2. Crear entorno virtual: `python -m venv entorno_cv`.
3. Instalar dependencias: `pip install -r requirements.txt`.

## Configuración
Requiere una `API_KEY` de Google AI Studio configurada en `app.py`.