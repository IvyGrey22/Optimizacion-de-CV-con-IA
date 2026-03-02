import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify
from PyPDF2 import PdfReader
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import spacy
import google.generativeai as genai
import os
from dotenv import load_dotenv
import google.generativeai as genai

# Cargar las variables del archivo .env
load_dotenv()

# Obtener la clave de forma segura
api_key = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=api_key)

app = Flask(__name__)

# --- CONFIGURACIÓN DE IA (Google AI Studio) ---
genai.configure(api_key="GOOGLE_API_KEY")

try:
    nlp = spacy.load("es_core_news_sm")
except:
    # Esta línea DEBE tener sangría hacia la derecha
    nlp = None
# --- FUNCIÓN: BÚSQUEDA AUTÓNOMA DE ROLES MEDIANTE IA ---
def obtener_sugerencia_puestos(texto_cv):
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # PROMPT ABIERTO: La IA decide el mejor match sin restricciones
        prompt = f"""
        Actúa como un Headhunter de alto nivel especializado en Ingeniería y Tecnología.
        Analiza profundamente el siguiente CV y determina, mediante inferencia lógica, 
        los dos perfiles profesionales donde el candidato tendría mayor éxito inmediato.

        Formato de respuesta estrictamente breve:
        1. PUESTO IDEAL EN INDUSTRIA: El rol técnico/industrial que mejor explote su experiencia.
        2. PUESTO IDEAL EN TI: El rol tecnológico (Software/Datos/Infraestructura) que mejor se adapte a su perfil.
        3. ANÁLISIS DE POTENCIAL: Justifica la elección basada en sus habilidades más fuertes (máx. 15 palabras).

        Texto del CV: {texto_cv[:3000]}
        """
        
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Sugerencia de IA no disponible: {str(e)}"

# --- EXTRACCIÓN DE TEXTO DE URL ---
def extraer_texto_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        respuesta = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(respuesta.text, 'html.parser')
        for script in soup(["script", "style"]):
            script.extract()
        texto = soup.get_text(separator=' ')
        lineas = (linea.strip() for linea in texto.splitlines())
        trozos = (frase.strip() for linea in lineas for frase in linea.split("  "))
        return '\n'.join(chunk for chunk in trozos if chunk)
    except:
        return None

# --- AUDITORÍA TÉCNICA ATS ---
def auditar_ats(texto_completo):
    reporte = {"legibilidad": False, "contacto": False, "secciones": [], "errores": []}
    if len(texto_completo.strip()) > 100:
        reporte["legibilidad"] = True
    else:
        reporte["errores"].append("⚠️ ALERTA: El PDF no tiene texto legible.")
        return reporte 
    
    if re.search(r'[\w\.-]+@[\w\.-]+', texto_completo) and re.search(r'\d{3}[-.\s]?\d{3}[-.\s]?\d{4}', texto_completo):
        reporte["contacto"] = True
        
    for sec in ["experiencia", "educación", "habilidades", "perfil"]:
        if sec in texto_completo.lower(): 
            reporte["secciones"].append(sec.capitalize())
    return reporte

# --- CÁLCULO DE SIMILITUD ---
def calcular_vs(texto_cv, texto_vacante):
    if not texto_vacante or not texto_cv: return 0, 0, []
    try:
        textos = [texto_cv, texto_vacante]
        vectorizer = TfidfVectorizer(stop_words='english')
        tfidf = vectorizer.fit_transform(textos)
        score_pct = round(cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0] * 100, 1)
        calificacion_10 = round(score_pct / 10, 1)
        faltantes = []
        if nlp:
            doc_v = nlp(texto_vacante.lower())
            keywords = set([t.text for t in doc_v if t.pos_ in ['NOUN', 'PROPN'] and len(t.text)>3])
            faltantes = [kw for kw in keywords if kw not in texto_cv.lower()]
        return calificacion_10, score_pct, list(faltantes)[:8] 
    except: 
        return 0, 0, []

@app.route('/')
def inicio():
    return render_template('index.html')

@app.route('/analizar', methods=['POST'])
def analizar_compatibilidad():
    if 'cv-upload' not in request.files: return jsonify({"error": "No archivo"}), 400
    archivo = request.files['cv-upload']
    try:
        pdf = PdfReader(archivo)
        texto_cv = "".join([page.extract_text() + "\n" for page in pdf.pages])
        auditoria = auditar_ats(texto_cv)
        sugerencia_ia = obtener_sugerencia_puestos(texto_cv)
        
        resultados_vs = []
        for i in range(1, 6): 
            titulo = request.form.get(f'vacante_titulo_{i}')
            desc = request.form.get(f'vacante_desc_{i}')
            url = request.form.get(f'vacante_url_{i}')
            texto_vacante = extraer_texto_url(url) if (url and url.strip().startswith("http")) else desc

            if titulo and texto_vacante:
                nota_10, nota_pct, faltantes = calcular_vs(texto_cv, texto_vacante)
                resultados_vs.append({
                    "titulo": titulo, "calificacion_10": nota_10,
                    "compatibilidad": nota_pct, "faltantes": faltantes
                })

        return jsonify({
            "status": "success", "auditoria": auditoria, 
            "analisis_vs": resultados_vs, "sugerencia_ia": sugerencia_ia 
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)
