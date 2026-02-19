import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify
from PyPDF2 import PdfReader
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import spacy

app = Flask(__name__)

try:
    nlp = spacy.load("es_core_news_sm")
except:
    nlp = None

# --- NUEVA FUNCIÓN: EXTRAER TEXTO DE URL ---
def extraer_texto_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        respuesta = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(respuesta.text, 'html.parser')
        
        # Eliminamos scripts y estilos para limpiar el texto
        for script in soup(["script", "style"]):
            script.extract()
            
        texto = soup.get_text(separator=' ')
        # Limpiar espacios extra
        lineas = (linea.strip() for linea in texto.splitlines())
        trozos = (frase.strip() for linea in lineas for frase in linea.split("  "))
        texto_limpio = '\n'.join(chunk for chunk in trozos if chunk)
        return texto_limpio
    except Exception as e:
        print(f"Error al extraer URL: {e}")
        return None

# --- AUDITORÍA TÉCNICA ATS ---
def auditar_ats(texto_completo):
    reporte = {"legibilidad": False, "contacto": False, "secciones": [], "errores": []}
    if len(texto_completo.strip()) > 100:
        reporte["legibilidad"] = True
    else:
        reporte["errores"].append("⚠️ ALERTA: El PDF no tiene texto legible.")
        return reporte 
    email = re.search(r'[\w\.-]+@[\w\.-]+', texto_completo)
    telefono = re.search(r'\d{3}[-.\s]?\d{3}[-.\s]?\d{4}', texto_completo)
    if email and telefono: reporte["contacto"] = True
    secciones_clave = ["experiencia", "educación", "habilidades", "perfil"]
    texto_lower = texto_completo.lower()
    for sec in secciones_clave:
        if sec in texto_lower: reporte["secciones"].append(sec.capitalize())
    return reporte

# --- CÁLCULO SCORE 1-10 ---
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
            cv_l = texto_cv.lower()
            faltantes = [kw for kw in keywords if kw not in cv_l]
        return calificacion_10, score_pct, list(faltantes)[:8] 
    except: return 0, 0, []

@app.route('/')
def inicio():
    return render_template('index.html')

@app.route('/analizar', methods=['POST'])
def analizar_compatibilidad():
    if 'cv-upload' not in request.files: return jsonify({"error": "No archivo"}), 400
    archivo = request.files['cv-upload']
    
    try:
        pdf = PdfReader(archivo)
        texto_cv = ""
        for page in pdf.pages: texto_cv += page.extract_text() + "\n"
        auditoria = auditar_ats(texto_cv)

        resultados_vs = []
        for i in range(1, 6): 
            titulo = request.form.get(f'vacante_titulo_{i}')
            desc = request.form.get(f'vacante_desc_{i}')
            url = request.form.get(f'vacante_url_{i}')
            
            # PRIORIDAD: Si hay URL, extraemos el texto de ahí
            texto_final_vacante = desc
            if url and url.strip().startswith("http"):
                texto_url = extraer_texto_url(url)
                if texto_url:
                    texto_final_vacante = texto_url

            if titulo and texto_final_vacante:
                nota_10, nota_pct, faltantes = calcular_vs(texto_cv, texto_final_vacante)
                veredicto = "🌟 Ideal" if nota_10 >= 8 else "✅ Aceptable" if nota_10 >= 6 else "❌ Bajo"
                resultados_vs.append({
                    "titulo": titulo, "calificacion_10": nota_10,
                    "compatibilidad": nota_pct, "veredicto": veredicto, "faltantes": faltantes
                })

        return jsonify({"status": "success", "auditoria": auditoria, "analisis_vs": resultados_vs})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)
    