import random
from faker import Faker
import datetime

# Configuración inicial
fake = Faker('es_MX') # Datos en español de México
archivo_salida = "25_CVs_Candidatos_UTSV.txt"

# --- BASES DE DATOS PARA LA SIMULACIÓN ---

# Universidades locales para darle realismo
unis = [
    'Universidad Tecnológica del Sureste de Veracruz (UTSV)',
    'Instituto Tecnológico de Minatitlán',
    'Instituto Tecnológico Superior de Coatzacoalcos (ITESCO)',
    'Universidad Veracruzana (Campus Coatzacoalcos)',
    'Universidad del Valle de México (Villahermosa)',
    'Instituto Politécnico Nacional (Egresado Foráneo)'
    'Universidad Autónoma de México (Egresado Foráneo)'
]

# Títulos afines a la vacante
titulos = [
    'Ingeniero en Mecatrónica',
    'Ingeniero en Electrónica y Automatización',
    'Ingeniero en Mantenimiento Industrial',
    'Ingeniero Mecánico Eléctrico',
    'Licenciado en Educación (Perfil Técnico)', # Caso trampa
    'Técnico Superior Universitario en Mecatrónica' # Caso trampa (Nivel bajo)
]

maestrias = [
    'Maestría en Docencia',
    'Maestría en Ciencias de la Ingeniería',
    'Maestría en Administración Industrial',
    'Sin Maestría'
]

# Empresas de la zona industrial
empresas = [
    'Braskem Idesa', 'Complejo Petroquímico Morelos', 'Cydsa', 
    'Taller de Torno y Soldadura "El Rayo"', 'Bachillerato Tecnológico CBTIS 213',
    'Universidad de Sotavento', 'Freelance', 'Desempleado'
]

# Habilidades (Mezcla de buenas y malas para el puesto)
skills_hard = ['PLC Siemens', 'AutoCAD', 'SolidWorks', 'Python', 'Matlab', 'Neumática', 'Soldadura', 'Diseño de PCBs', 'Word y Excel']
skills_soft = ['Liderazgo', 'Trabajo en equipo', 'Puntualidad', 'Comunicación asertiva', 'Manejo de grupos']

# --- FUNCIONES GENERADORAS ---

def generar_cv(id_candidato):
    # 1. Datos Personales
    genero = random.choice(['M', 'F'])
    if genero == 'M':
        nombre = fake.name_male()
    else:
        nombre = fake.name_female()
    
    telefono = f"921-{random.randint(100,999)}-{random.randint(1000,9999)}"
    email = f"{nombre.split()[0].lower()}.{nombre.split()[-1].lower()}@email.com"
    ciudad = random.choice(['Nanchital, Ver.', 'Coatzacoalcos, Ver.', 'Minatitlán, Ver.', 'Ixhuatlán del Sureste, Ver.'])

    # 2. Definir Perfil del Candidato (Bueno, Regular, Malo)
    calidad = random.choice(['Excelente', 'Promedio', 'Bajo', 'Huecos_Laborales'])
    
    perfil_texto = ""
    educacion_texto = ""
    experiencia_texto = ""
    skills_texto = ""

    # --- LÓGICA DE EDUCACIÓN ---
    uni = random.choice(unis)
    carrera = random.choice(titulos)
    anio_grad = random.randint(2015, 2023)
    
    educacion_texto += f"LICENCIATURA:\n   {carrera} | {uni} | {anio_grad}\n"
    
    if calidad == 'Excelente':
        maestria = 'Maestría en Docencia'
        educacion_texto += f"   POSTGRADO:\n   {maestria} | Universidad Veracruzana | {anio_grad + 2}\n"
        perfil_texto = "Ingeniero con sólida formación académica y experiencia docente, buscando aportar conocimientos en la UTSV."
    elif calidad == 'Huecos_Laborales':
        perfil_texto = "Profesional en búsqueda de reingreso al mercado laboral tras pausa personal."
    else:
        perfil_texto = "Busco desarrollarme profesionalmente en el área de mantenimiento o docencia."

    # --- LÓGICA DE EXPERIENCIA (Aquí creamos los huecos y la docencia) ---
    experiencia_texto += "HISTORIAL LABORAL:\n"
    
    # Trabajo actual o último
    puesto = random.choice(['Docente de Asignatura', 'Supervisor de Mantenimiento', 'Auxiliar Técnico', 'Ingeniero de Proyectos'])
    empresa = random.choice(empresas)
    
    if calidad == 'Huecos_Laborales':
        # Simulamos un hueco grande
        experiencia_texto += f"   2024 - Presente: {puesto} en {empresa}\n"
        experiencia_texto += f"   [2021 - 2023]: PERIODO SIN ACTIVIDAD LABORAL REGISTRADA\n"
        experiencia_texto += f"   2019 - 2021: Ayudante General en {random.choice(empresas)}\n"
    elif calidad == 'Excelente':
        # Mucha experiencia docente y técnica
        experiencia_texto += f"   2020 - Presente: Docente de Ingeniería en ITESCO (Maronitas y Mecatrónica)\n"
        experiencia_texto += f"      * Desarrollo de planeaciones didácticas y prácticas de laboratorio.\n"
        experiencia_texto += f"   2018 - 2020: Ingeniero de Automatización en Braskem Idesa\n"
    else:
        # Experiencia promedio
        experiencia_texto += f"   2021 - Presente: {puesto} en {empresa}\n"
        experiencia_texto += f"      * Actividades generales del área.\n"

    # --- LÓGICA DE HABILIDADES ---
    mis_skills = random.sample(skills_hard, 3) + random.sample(skills_soft, 2)
    skills_texto = ", ".join(mis_skills)

    # --- ARMADO DEL FORMATO HARVARD (Texto Plano) ---
    cv_final = f"""
================================================================================
CANDIDATO #{id_candidato} ({calidad})
================================================================================
{nombre.upper()}
{ciudad} | {telefono} | {email}

PERFIL PROFESIONAL
{perfil_texto}

EDUCACIÓN
{educacion_texto}
EXPERIENCIA
{experiencia_texto}
HABILIDADES TÉCNICAS Y BLANDAS
{skills_texto}

"""
    return cv_final

# --- EJECUCIÓN DEL SCRIPT ---

print("Generando 25 CVs... Por favor espere.")

with open(archivo_salida, "w", encoding="utf-8") as f:
    f.write("GENERACIÓN DE 25 PERFILES PARA PUESTO: PROFESOR DE TIEMPO COMPLETO MECATRÓNICA UTSV\n")
    f.write(f"Fecha de generación: {datetime.date.today()}\n")
    f.write("Nota: Los perfiles marcados como 'Huecos_Laborales' o 'Bajo' sirven para probar si los gerentes los descartan.\n\n")
    
    for i in range(1, ):
        cv = generar_cv(i)
        f.write(cv)

print(f"¡Listo! Se ha creado el archivo '{archivo_salida}' con los 25 currículums.")
print("Abre ese archivo para ver los CVs listos para imprimir o enviar.")