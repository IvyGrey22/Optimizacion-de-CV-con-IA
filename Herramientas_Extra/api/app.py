import json
import math
import os
import re
from collections import Counter
from io import BytesIO

import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_file
from flask_cors import CORS
from pypdf import PdfReader


load_dotenv()

api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))
CORS(app)

STOPWORDS_ES = {
    "de", "la", "que", "el", "en", "los", "del", "las", "por", "para",
    "con", "una", "como", "mas", "sus", "este", "porque", "esta", "desde",
    "sobre", "entre", "tambien", "pero", "sin", "ser", "son", "han", "hay",
}


def extraer_texto_url(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        respuesta = requests.get(url, headers=headers, timeout=10)
        respuesta.raise_for_status()
        soup = BeautifulSoup(respuesta.text, "html.parser")

        for script in soup(["script", "style"]):
            script.extract()

        texto = soup.get_text(separator=" ")
        lineas = (linea.strip() for linea in texto.splitlines())
        trozos = (frase.strip() for linea in lineas for frase in linea.split("  "))
        return "\n".join(chunk for chunk in trozos if chunk)
    except Exception:
        return None


def extraer_texto_pdf(archivo):
    pdf = PdfReader(archivo)
    return "".join([page.extract_text() or "" for page in pdf.pages])[:6000]


def resolver_texto_vacante(desc, url):
    if url and url.strip().startswith("http"):
        texto_url = extraer_texto_url(url)
        if texto_url:
            return texto_url
    return desc or ""


def generar_con_gemini(prompt, fallback):
    if not api_key:
        return fallback

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"{fallback}\n\nNota: no se pudo completar la generacion con IA. Detalle: {str(e)}"


def enviar_txt(nombre_archivo, contenido):
    buffer = BytesIO(contenido.encode("utf-8"))
    return send_file(
        buffer,
        as_attachment=True,
        download_name=nombre_archivo,
        mimetype="text/plain; charset=utf-8",
    )


def obtener_sugerencia_puestos(texto_cv):
    if not api_key:
        return "Sugerencia de IA no disponible: falta configurar GEMINI_API_KEY o GOOGLE_API_KEY."

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = f"""
        Actua como un Headhunter de alto nivel especializado en Ingenieria y Tecnologia.
        Analiza profundamente el siguiente CV y determina, mediante inferencia logica,
        los dos perfiles profesionales donde el candidato tendria mayor exito inmediato.

        Formato de respuesta estrictamente breve:
        1. PUESTO IDEAL EN INDUSTRIA: El rol tecnico/industrial que mejor explote su experiencia.
        2. PUESTO IDEAL EN TI: El rol tecnologico que mejor se adapte a su perfil.
        3. ANALISIS DE POTENCIAL: Justifica la eleccion basada en sus habilidades mas fuertes.

        Texto del CV: {texto_cv[:3000]}
        """
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Sugerencia de IA no disponible: {str(e)}"


def auditar_ats(texto_completo):
    reporte = {"legibilidad": False, "contacto": False, "secciones": [], "errores": []}

    if len(texto_completo.strip()) > 100:
        reporte["legibilidad"] = True
    else:
        reporte["errores"].append("ALERTA: El PDF no tiene texto legible.")
        return reporte

    if re.search(r"[\w\.-]+@[\w\.-]+", texto_completo) or re.search(
        r"\d{3}[-.\s]?\d{3}[-.\s]?\d{4}", texto_completo
    ):
        reporte["contacto"] = True

    for sec in ["experiencia", "educacion", "educación", "habilidades", "perfil"]:
        if sec in texto_completo.lower():
            reporte["secciones"].append(sec.capitalize())

    return reporte


def tokenizar(texto):
    return [
        token
        for token in re.findall(r"[a-zA-ZáéíóúñÁÉÍÓÚÑ]{4,}", texto.lower())
        if token not in STOPWORDS_ES
    ]


def similitud_coseno(tokens_a, tokens_b):
    conteo_a = Counter(tokens_a)
    conteo_b = Counter(tokens_b)
    if not conteo_a or not conteo_b:
        return 0

    comunes = set(conteo_a) & set(conteo_b)
    producto = sum(conteo_a[token] * conteo_b[token] for token in comunes)
    norma_a = math.sqrt(sum(valor * valor for valor in conteo_a.values()))
    norma_b = math.sqrt(sum(valor * valor for valor in conteo_b.values()))
    return producto / (norma_a * norma_b) if norma_a and norma_b else 0


def calcular_vs(texto_cv, texto_vacante):
    if not texto_vacante or not texto_cv:
        return 0, 0, []

    try:
        tokens_cv = tokenizar(texto_cv)
        tokens_vacante = tokenizar(texto_vacante)
        score_pct = round(similitud_coseno(tokens_cv, tokens_vacante) * 100, 1)
        calificacion_10 = round(score_pct / 10, 1)

        vocab_cv = set(tokens_cv)
        keywords = [token for token, _ in Counter(tokens_vacante).most_common(40)]
        faltantes = [kw for kw in keywords if kw not in vocab_cv]

        return calificacion_10, score_pct, faltantes[:8]
    except Exception:
        return 0, 0, []


@app.route("/")
def inicio():
    return render_template("index.html")


@app.route("/extraer_vacante", methods=["POST"])
def api_extraer_vacante():
    data = request.json or {}
    url = data.get("url")

    if not url or not url.startswith("http"):
        return jsonify({"error": "URL no valida"}), 400

    texto_sucio = extraer_texto_url(url)
    if not texto_sucio:
        return jsonify({"error": "No se pudo leer el contenido de la URL"}), 400

    if not api_key:
        return jsonify({"titulo": "Puesto Detectado", "descripcion": texto_sucio[:500]})

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = (
            "Extrae el titulo del puesto y un resumen de 3 lineas de los requisitos "
            "clave. Responde unicamente en formato JSON puro sin bloques de codigo "
            f"ni markdown con las llaves 'titulo' y 'descripcion'. Texto: {texto_sucio[:2500]}"
        )
        res = model.generate_content(prompt)
        respuesta_limpia = res.text.replace("```json", "").replace("```", "").strip()
        return jsonify(json.loads(respuesta_limpia))
    except Exception:
        return jsonify({"titulo": "Puesto Detectado", "descripcion": texto_sucio[:500]})


@app.route("/analizar", methods=["POST"])
def analizar_compatibilidad():
    if "cv-upload" not in request.files:
        return jsonify({"error": "No se recibio archivo PDF"}), 400

    archivo = request.files["cv-upload"]

    try:
        texto_cv = extraer_texto_pdf(archivo)[:4000]

        auditoria = auditar_ats(texto_cv)
        sugerencia_ia = obtener_sugerencia_puestos(texto_cv)

        resultados_vs = []
        for i in range(1, 11):
            titulo = request.form.get(f"vacante_titulo_{i}")
            desc = request.form.get(f"vacante_desc_{i}")
            url = request.form.get(f"vacante_url_{i}")

            texto_vacante = resolver_texto_vacante(desc, url)

            if texto_vacante:
                titulo = titulo or f"Vacante {i}"
                nota_10, nota_pct, faltantes = calcular_vs(texto_cv, texto_vacante)
                resultados_vs.append(
                    {
                        "titulo": titulo,
                        "calificacion_10": nota_10,
                        "veredicto": "Compatibilidad evaluada",
                        "compatibilidad": nota_pct,
                        "faltantes": faltantes,
                    }
                )

        return jsonify(
            {
                "status": "success",
                "auditoria": auditoria,
                "analisis_vs": resultados_vs,
                "sugerencia_ia": sugerencia_ia,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/generar_cover_letter", methods=["POST"])
def generar_cover_letter():
    if "cv-upload" not in request.files:
        return jsonify({"error": "No se recibio archivo PDF"}), 400

    archivo = request.files["cv-upload"]
    titulo = request.form.get("vacante_titulo") or "la vacante"
    desc = request.form.get("vacante_desc")
    url = request.form.get("vacante_url")

    try:
        texto_cv = extraer_texto_pdf(archivo)
        texto_vacante = resolver_texto_vacante(desc, url)
        if not texto_vacante:
            return jsonify({"error": "Agrega una URL o descripcion de la vacante."}), 400

        prompt = f"""
        Redacta una carta de presentacion profesional en espanol para postular a: {titulo}.
        Usa un tono claro, humano y directo. Debe tener 4 parrafos cortos.
        Conecta la experiencia del CV con los requisitos de la vacante sin inventar datos.
        Cierra con disponibilidad para entrevista.

        CV:
        {texto_cv[:4500]}

        Vacante:
        {texto_vacante[:3500]}
        """
        fallback = (
            f"Carta de presentacion para {titulo}\n\n"
            "Estimado equipo de seleccion:\n\n"
            "Comparto mi postulacion para la vacante indicada. Mi perfil tecnico presenta "
            "experiencia y habilidades relacionadas con los requisitos descritos, y me interesa "
            "aportar valor desde una perspectiva orientada a resultados.\n\n"
            "Quedo a disposicion para ampliar cualquier informacion en entrevista.\n"
        )
        contenido = generar_con_gemini(prompt, fallback)
        return enviar_txt("cover_letter.txt", contenido)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/corregir_cv", methods=["POST"])
def corregir_cv():
    if "cv-upload" not in request.files:
        return jsonify({"error": "No se recibio archivo PDF"}), 400

    archivo = request.files["cv-upload"]
    titulo = request.form.get("vacante_titulo") or "Vacante objetivo"
    desc = request.form.get("vacante_desc")
    url = request.form.get("vacante_url")

    try:
        texto_cv = extraer_texto_pdf(archivo)
        texto_vacante = resolver_texto_vacante(desc, url)
        if not texto_vacante:
            return jsonify({"error": "Agrega una URL o descripcion de la vacante."}), 400

        auditoria = auditar_ats(texto_cv)
        nota_10, nota_pct, faltantes = calcular_vs(texto_cv, texto_vacante)
        prompt = f"""
        Reescribe y corrige este CV en espanol para mejorar su compatibilidad ATS con la vacante.
        No inventes empresas, fechas, grados ni certificaciones. Conserva solo informacion del CV original.
        Si faltan datos importantes, agrega una seccion final llamada "Recomendaciones para completar".
        Usa formato limpio con estas secciones: Perfil profesional, Experiencia, Educacion,
        Habilidades tecnicas, Palabras clave alineadas a la vacante y Recomendaciones.

        Vacante objetivo: {titulo}
        Compatibilidad actual: {nota_pct}%
        Palabras clave faltantes detectadas: {", ".join(faltantes) if faltantes else "ninguna principal"}
        Auditoria ATS: {json.dumps(auditoria, ensure_ascii=False)}

        CV original:
        {texto_cv[:5000]}

        Vacante:
        {texto_vacante[:3500]}
        """
        fallback = (
            f"CV corregido para: {titulo}\n\n"
            f"Compatibilidad actual estimada: {nota_pct}%\n"
            f"Palabras clave a reforzar: {', '.join(faltantes) if faltantes else 'sin faltantes principales'}\n\n"
            "Perfil profesional\n"
            f"{texto_cv[:1200]}\n\n"
            "Recomendaciones para completar\n"
            "- Refuerza el CV con logros medibles.\n"
            "- Incluye herramientas, tecnologias y competencias mencionadas en la vacante.\n"
            "- Usa secciones claras para experiencia, educacion y habilidades.\n"
        )
        contenido = generar_con_gemini(prompt, fallback)
        return enviar_txt("cv_corregido_ats.txt", contenido)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
