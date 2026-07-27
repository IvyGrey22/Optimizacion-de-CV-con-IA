import express from "express";
import cors from "cors";
import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";
import { createRequire } from "module";
import dotenv from "dotenv";
import multer from "multer";
import axios from "axios";
import * as cheerio from "cheerio";
import { GoogleGenAI } from "@google/genai";

dotenv.config();

const require = createRequire(import.meta.url);
const pdfParseModule = require("pdf-parse");

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = 3000;

app.use(cors());
app.use(express.json({ limit: "50mb" }));
app.use(express.urlencoded({ extended: true, limit: "50mb" }));

// Configure Multer in-memory storage for PDF uploads
const upload = multer({ storage: multer.memoryStorage() });

// Gemini AI setup
const apiKey = (process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY || "").trim();
const ai = apiKey ? new GoogleGenAI({ apiKey }) : null;

async function extractPdfText(buffer: Buffer): Promise<string> {
  try {
    if (typeof pdfParseModule === "function") {
      const data = await pdfParseModule(buffer);
      return data.text || "";
    } else if (pdfParseModule?.PDFParse) {
      const parser = new pdfParseModule.PDFParse({ data: buffer });
      const res = await parser.getText();
      return typeof res === "string" ? res : (res?.text || "");
    } else if (pdfParseModule?.default) {
      const data = await pdfParseModule.default(buffer);
      return data.text || "";
    }
  } catch (e) {
    console.error("Error parsing PDF:", e);
  }
  return "";
}

// Stopwords in Spanish for TF-IDF / Cosine Similarity calculation
const STOPWORDS_ES = new Set([
  "de", "la", "que", "el", "en", "los", "del", "las", "por", "para",
  "con", "una", "como", "mas", "sus", "este", "porque", "esta", "desde",
  "sobre", "entre", "tambien", "pero", "sin", "ser", "son", "han", "hay"
]);

function tokenizar(texto: string): string[] {
  const matches = texto.toLowerCase().match(/[a-zA-ZáéíóúñÁÉÍÓÚÑ]{4,}/g) || [];
  return matches.filter((token) => !STOPWORDS_ES.has(token));
}

function similitudCoseno(tokensA: string[], tokensB: string[]): number {
  const conteoA: Record<string, number> = {};
  const conteoB: Record<string, number> = {};

  for (const t of tokensA) conteoA[t] = (conteoA[t] || 0) + 1;
  for (const t of tokensB) conteoB[t] = (conteoB[t] || 0) + 1;

  if (Object.keys(conteoA).length === 0 || Object.keys(conteoB).length === 0) {
    return 0;
  }

  let producto = 0;
  for (const token in conteoA) {
    if (conteoB[token]) {
      producto += conteoA[token] * conteoB[token];
    }
  }

  let sumaCuadradosA = 0;
  for (const token in conteoA) {
    sumaCuadradosA += conteoA[token] * conteoA[token];
  }

  let sumaCuadradosB = 0;
  for (const token in conteoB) {
    sumaCuadradosB += conteoB[token] * conteoB[token];
  }

  const normaA = Math.sqrt(sumaCuadradosA);
  const normaB = Math.sqrt(sumaCuadradosB);

  return normaA && normaB ? producto / (normaA * normaB) : 0;
}

function calcularVs(textoCv: string, textoVacante: string) {
  if (!textoVacante || !textoCv) {
    return { calificacion_10: 0, compatibilidad: 0, faltantes: [] as string[] };
  }

  try {
    const tokensCv = tokenizar(textoCv);
    const tokensVacante = tokenizar(textoVacante);

    const scorePct = Math.round(similitudCoseno(tokensCv, tokensVacante) * 1000) / 10;
    const calificacion10 = Math.round((scorePct / 10) * 10) / 10;

    const vocabCv = new Set(tokensCv);
    const freqVacante: Record<string, number> = {};
    for (const t of tokensVacante) freqVacante[t] = (freqVacante[t] || 0) + 1;

    const keywords = Object.keys(freqVacante)
      .sort((a, b) => freqVacante[b] - freqVacante[a])
      .slice(0, 40);

    const faltantes = keywords.filter((kw) => !vocabCv.has(kw)).slice(0, 8);

    return {
      calificacion_10: calificacion10,
      compatibilidad: scorePct,
      faltantes,
    };
  } catch (error) {
    return { calificacion_10: 0, compatibilidad: 0, faltantes: [] as string[] };
  }
}

function auditarAts(textoCompleto: string) {
  const reporte = {
    legibilidad: false,
    contacto: false,
    secciones: [] as string[],
    errores: [] as string[],
  };

  if (textoCompleto.trim().length > 100) {
    reporte.legibilidad = true;
  } else {
    reporte.errores.push("ALERTA: El PDF no tiene texto legible.");
    return reporte;
  }

  if (
    /[\w\.-]+@[\w\.-]+/.test(textoCompleto) ||
    /\d{3}[-.\s]?\d{3}[-.\s]?\d{4}/.test(textoCompleto)
  ) {
    reporte.contacto = true;
  }

  const seccionesBuscar = ["experiencia", "educacion", "educación", "habilidades", "perfil"];
  const textoLower = textoCompleto.toLowerCase();
  for (const sec of seccionesBuscar) {
    if (textoLower.includes(sec)) {
      reporte.secciones.push(sec.charAt(0).toUpperCase() + sec.slice(1));
    }
  }

  return reporte;
}

async function extraerTextoUrl(url: string): Promise<string | null> {
  try {
    const response = await axios.get(url, {
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
      },
      timeout: 10000,
    });
    const $ = cheerio.load(response.data);
    $("script, style").remove();
    const texto = $("body").text();
    const lineas = texto
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    return lineas.join("\n");
  } catch (e) {
    return null;
  }
}

async function obtenerSugerenciaPuestos(textoCv: string): Promise<string> {
  if (!ai) {
    return "Sugerencia de IA no disponible: falta configurar GEMINI_API_KEY o GOOGLE_API_KEY.";
  }

  try {
    const prompt = `Actua como un Headhunter de alto nivel especializado en Ingenieria y Tecnologia.
Analiza profundamente el siguiente CV y determina, mediante inferencia logica,
los dos perfiles profesionales donde el candidato tendria mayor exito inmediato.

Formato de respuesta estrictamente breve:
1. PUESTO IDEAL EN INDUSTRIA: El rol tecnico/industrial que mejor explote su experiencia.
2. PUESTO IDEAL EN TI: El rol tecnologico que mejor se adapte a su perfil.
3. ANALISIS DE POTENCIAL: Justifica la eleccion basada en sus habilidades mas fuertes.

Texto del CV: ${textoCv.slice(0, 3000)}`;

    const response = await ai.models.generateContent({
      model: "gemini-2.5-flash",
      contents: prompt,
    });

    return response.text || "Sugerencia generada.";
  } catch (e: any) {
    return `Sugerencia de IA no disponible: ${e.message}`;
  }
}

async function obtenerConsejosRedaccion(textoCv: string, resultadosVs: any[]): Promise<string[]> {
  const fallbackConsejos = [
    "Sustituye frases pasivas por verbos de acción en tiempo pasado como 'Lideré', 'Desarrollé', 'Implementé' u 'Optimicé'.",
    "Cuantifica tus logros en la sección de experiencia agregando porcentajes, métricas de rendimiento o volumen gestionado (ej: 'reducido un 20%', 'equipo de 5 personas').",
    "Incorpora de forma explícita en las viñetas de experiencia las tecnologías y herramientas requeridas por la vacante objetivo.",
    "Aplica la fórmula STAR (Situación, Tarea, Acción, Resultado) en cada viñeta para demostrar impacto directo y relevante."
  ];

  if (!ai) {
    return fallbackConsejos;
  }

  try {
    const faltantesTotales = Array.from(new Set(resultadosVs.flatMap(v => v.faltantes || [])));
    const vacanteEjemplo = resultadosVs[0]?.titulo || "Puesto Objetivo";

    const prompt = `Actua como un reclutador experto y coach de carrera especializado en optimizacion de CV para ATS.
Analiza las viñetas y descripciones de experiencia del siguiente CV frente a la vacante "${vacanteEjemplo}" y las palabras clave faltantes: ${faltantesTotales.join(", ") || "ninguna principal"}.

Genera exactamente 4 consejos dinamicos, concretos y especificos para reescribir y mejorar los puntos de experiencia laboral en el CV original basandote en sus debilidades.
Cada consejo debe ser claro, practico y directo.

Responde unicamente en formato JSON puro (un arreglo de 4 strings), sin bloques de markdown ni comillas adicionales.
Ejemplo: ["Consejo 1...", "Consejo 2...", "Consejo 3...", "Consejo 4..."]

CV ORIGINAL:
${textoCv.slice(0, 3500)}`;

    const response = await ai.models.generateContent({
      model: "gemini-2.5-flash",
      contents: prompt,
    });

    const respuestaLimpia = (response.text || "")
      .replace(/```json/g, "")
      .replace(/```/g, "")
      .trim();

    const jsonParsed = JSON.parse(respuestaLimpia);
    if (Array.isArray(jsonParsed) && jsonParsed.length > 0) {
      return jsonParsed.map((item: any) => String(item));
    }
  } catch (e) {
    console.error("Error generando consejos de redaccion:", e);
  }

  return fallbackConsejos;
}

// Serve Static templates
app.use(express.static(path.join(__dirname, "templates")));

// Routes
app.get("/", (req, res) => {
  res.sendFile(path.join(__dirname, "templates", "index.html"));
});

app.get("/editor", (req, res) => {
  res.sendFile(path.join(__dirname, "templates", "editor.html"));
});

app.post("/extraer_vacante", async (req, res) => {
  const { url } = req.body || {};

  if (!url || typeof url !== "string" || !url.startsWith("http")) {
    return res.status(400).json({ error: "URL no valida" });
  }

  const textoSucio = await extraerTextoUrl(url);
  if (!textoSucio) {
    return res.status(400).json({ error: "No se pudo leer el contenido de la URL" });
  }

  if (!ai) {
    return res.json({
      titulo: "Puesto Detectado",
      empresa: "Empresa No Especificada",
      descripcion: textoSucio.slice(0, 500),
    });
  }

  try {
    const prompt = `Extrae de forma precisa el titulo del puesto, el nombre de la empresa organizadora o contratante y un resumen claro de los requisitos y responsabilidades de la vacante.
Responde unicamente en formato JSON puro sin bloques de codigo ni markdown con las llaves 'titulo', 'empresa' y 'descripcion'.
Texto a analizar: ${textoSucio.slice(0, 3000)}`;

    const response = await ai.models.generateContent({
      model: "gemini-2.5-flash",
      contents: prompt,
    });

    const respuestaLimpia = (response.text || "")
      .replace(/```json/g, "")
      .replace(/```/g, "")
      .trim();

    const jsonParsed = JSON.parse(respuestaLimpia);
    return res.json({
      titulo: jsonParsed.titulo || "Puesto Detectado",
      empresa: jsonParsed.empresa || "Empresa No Especificada",
      descripcion: jsonParsed.descripcion || textoSucio.slice(0, 500),
    });
  } catch (e) {
    return res.json({
      titulo: "Puesto Detectado",
      empresa: "Empresa No Especificada",
      descripcion: textoSucio.slice(0, 500),
    });
  }
});

app.post("/analizar", upload.single("cv-upload"), async (req, res) => {
  if (!req.file) {
    return res.status(400).json({ error: "No se recibio archivo PDF" });
  }

  try {
    const extractedText = await extractPdfText(req.file.buffer);
    const textoCv = extractedText.slice(0, 5000);

    const auditoria = auditarAts(textoCv);
    const sugerenciaIa = await obtenerSugerenciaPuestos(textoCv);

    const resultadosVs = [];
    for (let i = 1; i <= 10; i++) {
      const titulo = req.body[`vacante_titulo_${i}`];
      const desc = req.body[`vacante_desc_${i}`];
      const url = req.body[`vacante_url_${i}`];

      let textoVacante = desc;
      if (url && typeof url === "string" && url.trim().startsWith("http")) {
        const extraido = await extraerTextoUrl(url.trim());
        if (extraido) textoVacante = extraido;
      }

      if (titulo && textoVacante) {
        const { calificacion_10, compatibilidad, faltantes } = calcularVs(
          textoCv,
          textoVacante
        );
        resultadosVs.push({
          titulo,
          calificacion_10,
          veredicto: calificacion_10 >= 7 ? "Perfil Altamente Calificado" : "Requiere Ajustes ATS",
          compatibilidad,
          faltantes,
          texto_vacante: textoVacante.slice(0, 3500),
        });
      }
    }

    const consejosRedaccion = await obtenerConsejosRedaccion(textoCv, resultadosVs);

    return res.json({
      status: "success",
      texto_cv: textoCv,
      auditoria,
      analisis_vs: resultadosVs,
      sugerencia_ia: sugerenciaIa,
      consejos_redaccion: consejosRedaccion,
    });
  } catch (e: any) {
    return res.status(500).json({ error: e.message || "Error procesando el PDF" });
  }
});

async function procesarGeneracionDocumento(params: {
  tipo: string;
  vacante_titulo?: string;
  vacante_desc?: string;
  texto_vacante?: string;
  cv_texto?: string;
  texto_cv?: string;
  nota_pct?: number;
  compatibilidad?: number;
  faltantes?: string[];
  auditoria?: any;
}) {
  const { tipo, vacante_titulo, vacante_desc, texto_vacante, cv_texto, texto_cv, nota_pct, compatibilidad, faltantes, auditoria } = params;

  const cvTextoUsar = cv_texto || texto_cv || "";
  const vacanteDescUsar = vacante_desc || texto_vacante || "";
  const tituloUsar = vacante_titulo || "Puesto Objetivo";
  const notaUsar = nota_pct ?? compatibilidad ?? 0;

  if (!ai) {
    return `[Modo sin API Key - Vista Previa]
DOCUMENTO GENERADO: ${tipo.toUpperCase()}
Puesto: ${tituloUsar}

Estimado reclutador,
Este es un documento generado automaticamente en modo vista previa sin API Key configurada.
Para activar las respuestas generativas avanzadas con Gemini, agregue GEMINI_API_KEY en las variables de entorno.`;
  }

  let prompt = "";
  if (tipo === "cover" || tipo === "cover_letter") {
    prompt = `Actua como un experto reclutador y redactor profesional de cartas de presentacion.
Redacta una Cover Letter (Carta de Presentacion) profesional, persuasiva e impactante en espanol para la vacante "${tituloUsar}".

REGLAS DE ESTRUCTURA Y CONTENIDO (Exactamente 4 parrafos bien redactados):
1. Parrafo 1 (Introduccion): Presentacion formal, declaracion clara de interes por el puesto "${tituloUsar}" e impacto inicial.
2. Parrafo 2 (Experiencia y Habilidades): Resumen de la experiencia previa mas relevante y competencias tecnicas alineadas con los requisitos de la vacante.
3. Parrafo 3 (Logros e Impacto): Demostracion de logros destacados y el valor diferencial que el candidato aportara a la empresa.
4. Parrafo 4 (Cierre y Llamado a la Accion): Cierre formal, reiteracion de entusiasmo y solicitud de entrevista profesional.

VACANTE OBJETIVO:
${tituloUsar}

REQUISITOS DE LA VACANTE:
${vacanteDescUsar.slice(0, 3000)}

CV DEL CANDIDATO (Extraer nombre real, datos de contacto y enlaces si estan presentes):
${cvTextoUsar.slice(0, 4000)}`;
  } else {
    prompt = `Actua como un experto reclutador y especialista en optimizacion ATS.
Reescribe y corrige este CV en espanol para maximizar su compatibilidad ATS con la vacante objetivo.

REGLAS DE RECRUITMENT Y FIDELIDAD:
1. No inventes empresas, fechas, grados academicos ni certificaciones. Conserva unicamente la informacion real del CV original.
2. INSTRUCCION DE ENLACES: Detecta y extrae todas las URLs o perfiles de LinkedIn, GitHub, o Portafolio Web presentes en el CV original, e insertalos explicitamente dentro de la seccion inicial de Datos de Contacto.
3. Integrar de forma natural las palabras clave de la vacante objetivo en el perfil y en las descripciones de experiencia.
4. Si detectas vacios importantes o informacion critica faltante para el rol, agrega una seccion final llamada "Recomendaciones para completar".

ESTRUCTURA OBLIGATORIA DEL DOCUMENTO:
1. Datos de Contacto y Enlaces (Incluir correo, telefono, LinkedIn, Portafolio, GitHub)
2. Perfil Profesional (Alineado a la vacante)
3. Experiencia Profesional (Enfocada en logros y herramientas clave)
4. Educacion y Certificaciones
5. Habilidades Tecnicas y Competencias
6. Palabras Clave Alineadas
7. Recomendaciones para Completar (Si aplica)

DATOS DE ENTRADA:
Vacante objetivo: ${tituloUsar}
Compatibilidad actual: ${notaUsar}%
Palabras clave faltantes detectadas: ${Array.isArray(faltantes) && faltantes.length ? faltantes.join(", ") : "ninguna principal"}
Auditoria ATS previa: ${JSON.stringify(auditoria || {})}

CV ORIGINAL:
${cvTextoUsar.slice(0, 5000)}

DESCRIPCION DE LA VACANTE:
${vacanteDescUsar.slice(0, 3500)}`;
  }

  const response = await ai.models.generateContent({
    model: "gemini-2.5-flash",
    contents: prompt,
  });

  return response.text || "";
}

app.post("/generar_documento", async (req, res) => {
  try {
    const contenido = await procesarGeneracionDocumento(req.body || {});
    return res.json({ contenido });
  } catch (e: any) {
    return res.status(500).json({ error: e.message || "Error al generar documento" });
  }
});

app.post("/corregir_cv", async (req, res) => {
  try {
    const contenido = await procesarGeneracionDocumento({ ...req.body, tipo: "cv" });
    return res.json({ contenido, status: "success" });
  } catch (e: any) {
    return res.status(500).json({ error: e.message || "Error al corregir CV" });
  }
});

app.post("/generar_cover_letter", async (req, res) => {
  try {
    const contenido = await procesarGeneracionDocumento({ ...req.body, tipo: "cover" });
    return res.json({ contenido, status: "success" });
  } catch (e: any) {
    return res.status(500).json({ error: e.message || "Error al generar cover letter" });
  }
});

app.post("/descargar_pdf", (req, res) => {
  const { nombre, email, telefono, perfil, experiencia, educacion, skills, vacante } = req.body;

  const cvFormatted = `================================================================================
CV OPTIMIZADO ATS - FORMATO HARVARD
================================================================================
CANDIDATO: ${(nombre || "NOMBRE COMPLETO").toUpperCase()}
Contacto: ${email || "email@ejemplo.com"} | ${telefono || "000-000-0000"}

PERFIL PROFESIONAL
--------------------------------------------------------------------------------
${perfil || "Perfil profesional..."}

EDUCACIÓN
--------------------------------------------------------------------------------
${educacion || "Educación..."}

EXPERIENCIA LABORAL
--------------------------------------------------------------------------------
${experiencia || "Experiencia..."}

HABILIDADES TÉCNICAS Y BLANDAS
--------------------------------------------------------------------------------
${skills || "Skills..."}
`;

  res.setHeader("Content-Disposition", `attachment; filename="CV_Optimizado_${(nombre || "Candidato").replace(/\s+/g, "_")}.txt"`);
  res.setHeader("Content-Type", "text/plain; charset=utf-8");
  return res.send(cvFormatted);
});

app.listen(PORT, "0.0.0.0", () => {
  console.log(`Server running on http://0.0.0.0:${PORT}`);
});
