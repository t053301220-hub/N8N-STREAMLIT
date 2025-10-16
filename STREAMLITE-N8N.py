import streamlit as st
import google.generativeai as genai
from pdf2image import convert_from_bytes
import io
import time
import pandas as pd
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
import json
import re
from PIL import Image

# Configuración de la página
st.set_page_config(
    page_title="Sistema de Calificación Automática",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personalizado
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 10px;
        text-align: center;
        color: white;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: white;
        padding: 1.5rem;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        border-left: 4px solid #667eea;
    }
    .success-msg {
        background-color: #d4edda;
        border-left: 5px solid #28a745;
        padding: 1rem;
        border-radius: 5px;
        margin: 1rem 0;
    }
    .stButton>button {
        width: 100%;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        font-weight: bold;
        border: none;
        padding: 0.75rem;
        border-radius: 8px;
        transition: transform 0.2s;
    }
    .stButton>button:hover {
        transform: scale(1.05);
    }
    .processing-box {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Título principal
st.markdown("""
<div class="main-header">
    <h1>📝 Sistema de Calificación Automática de Exámenes</h1>
    <p>Análisis inteligente con Google Gemini AI</p>
</div>
""", unsafe_allow_html=True)

# Inicializar session state
if 'resultados' not in st.session_state:
    st.session_state.resultados = None
if 'procesado' not in st.session_state:
    st.session_state.procesado = False
if 'api_configurada' not in st.session_state:
    st.session_state.api_configurada = False

# Configurar Gemini API con la key proporcionada
GEMINI_API_KEY = "AIzaSyBBxiisLsoPKLvKdWpjcE7cTtyXsRWQN7s"

@st.cache_resource
def configurar_gemini():
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        return model
    except Exception as e:
        st.error(f"❌ Error al configurar Gemini: {e}")
        return None

# Inicializar modelo
model = configurar_gemini()

if model:
    st.session_state.api_configurada = True
    st.sidebar.success("✅ Google Gemini AI configurado correctamente")
else:
    st.sidebar.error("❌ Error al configurar Google Gemini")

# Función para parsear clave de respuestas
def parsear_clave(clave_str):
    """Parsea la clave en formato: 1:a, 2:d, 3:e, 4:v, 5:f"""
    clave = {}
    try:
        items = [item.strip() for item in clave_str.split(',')]
        for item in items:
            if ':' in item:
                num, resp = item.split(':')
                clave[int(num.strip())] = resp.strip().lower()
        return clave
    except Exception as e:
        st.error(f"❌ Error al parsear clave: {e}")
        return None

# Función para extraer respuestas con Gemini
def extraer_respuestas_gemini(model, pdf_file, num_preguntas):
    """Extrae respuestas del PDF usando Gemini Vision"""
    try:
        # Resetear puntero del archivo
        pdf_file.seek(0)
        
        # Convertir PDF a imágenes
        pdf_bytes = pdf_file.read()
        imagenes = convert_from_bytes(pdf_bytes, dpi=150, first_page=1, last_page=5)
        
        respuestas = {}
        
        # Procesar cada página con Gemini
        for idx, imagen in enumerate(imagenes):
            # Reducir tamaño de imagen si es muy grande
            max_size = (1024, 1024)
            imagen.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Convertir imagen a bytes
            img_byte_arr = io.BytesIO()
            imagen.save(img_byte_arr, format='PNG', optimize=True, quality=85)
            img_byte_arr.seek(0)
            
            # Crear prompt optimizado para Gemini
            prompt = f"""Analiza esta imagen de un examen y extrae SOLAMENTE las respuestas que están marcadas.

INSTRUCCIONES IMPORTANTES:
- Busca preguntas numeradas (1, 2, 3, etc.)
- Las respuestas marcadas pueden tener una X, un círculo, o estar resaltadas
- Para alternativas múltiples: las opciones son a, b, c, d, e
- Para verdadero/falso: las opciones son v (verdadero) o f (falso)

FORMATO DE RESPUESTA:
Responde ÚNICAMENTE con un objeto JSON sin texto adicional:
{{"1": "a", "2": "d", "3": "v", "4": "f", "5": "b"}}

Si no encuentras respuestas marcadas en esta página, responde: {{}}

NO incluyas explicaciones, solo el JSON puro."""

            try:
                # Generar respuesta con Gemini
                response = model.generate_content([prompt, imagen])
                texto_respuesta = response.text.strip()
                
                # Limpiar respuesta (remover markdown si existe)
                texto_respuesta = texto_respuesta.replace('```json', '').replace('```', '').strip()
                
                # Buscar JSON en la respuesta
                json_match = re.search(r'\{[^{}]*\}', texto_respuesta)
                
                if json_match:
                    try:
                        respuestas_pagina = json.loads(json_match.group())
                        # Convertir keys a int y valores a lowercase
                        for k, v in respuestas_pagina.items():
                            num_pregunta = int(k)
                            respuesta_valor = str(v).lower().strip()
                            # Validar que la respuesta sea válida
                            if respuesta_valor in ['a', 'b', 'c', 'd', 'e', 'v', 'f']:
                                respuestas[num_pregunta] = respuesta_valor
                    except json.JSONDecodeError:
                        continue
                        
            except Exception as e:
                st.warning(f"⚠️ Error en página {idx+1}: {str(e)[:100]}")
                continue
        
        return respuestas
        
    except Exception as e:
        st.error(f"❌ Error al procesar PDF: {e}")
        return {}

# Función para calcular nota
def calcular_nota(respuestas_alumno, clave_correcta, escala=20):
    """Calcula la nota en escala 0-20"""
    if not clave_correcta:
        return 0, 0, 0
    
    total_preguntas = len(clave_correcta)
    correctas = 0
    
    for num, resp_correcta in clave_correcta.items():
        if num in respuestas_alumno:
            if respuestas_alumno[num] == resp_correcta:
                correctas += 1
    
    incorrectas = total_preguntas - correctas
    nota = (correctas / total_preguntas) * escala if total_preguntas > 0 else 0
    
    return round(nota, 2), correctas, incorrectas

# Función para generar PDF de reporte
def generar_reporte_pdf(resultados, curso_nombre, curso_codigo, clave):
    """Genera el reporte en PDF"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    elementos = []
    styles = getSampleStyleSheet()
    
    # Estilo personalizado para título
    titulo_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#667eea'),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    # Título
    elementos.append(Paragraph("📝 SISTEMA DE CALIFICACIÓN AUTOMÁTICA", titulo_style))
    elementos.append(Paragraph("Reporte de Resultados", styles['Heading2']))
    elementos.append(Spacer(1, 0.5*cm))
    
    # Información del curso
    info_data = [
        ['Curso:', curso_nombre],
        ['Código:', curso_codigo],
        ['Fecha:', datetime.now().strftime('%d/%m/%Y %H:%M:%S')],
        ['Total Preguntas:', str(len(clave))]
    ]
    
    info_table = Table(info_data, colWidths=[4*cm, 12*cm])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#667eea')),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elementos.append(info_table)
    elementos.append(Spacer(1, 1*cm))
    
    # Estadísticas generales
    df = pd.DataFrame(resultados)
    notas = df['nota'].values
    aprobados = len(df[df['nota'] >= 14])
    desaprobados = len(df[df['nota'] < 14])
    
    elementos.append(Paragraph("📊 ESTADÍSTICAS GENERALES", styles['Heading2']))
    elementos.append(Spacer(1, 0.3*cm))
    
    stats_data = [
        ['Métrica', 'Valor'],
        ['Promedio General', f"{notas.mean():.2f}"],
        ['Promedio Aprobados', f"{df[df['nota'] >= 14]['nota'].mean():.2f}" if aprobados > 0 else "N/A"],
        ['Nota Más Alta', f"{notas.max():.2f}"],
        ['Nota Más Baja', f"{notas.min():.2f}"],
        ['Total Aprobados', f"{aprobados} ({aprobados/len(df)*100:.1f}%)"],
        ['Total Desaprobados', f"{desaprobados} ({desaprobados/len(df)*100:.1f}%)"]
    ]
    
    stats_table = Table(stats_data, colWidths=[8*cm, 8*cm])
    stats_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')])
    ]))
    
    elementos.append(stats_table)
    elementos.append(Spacer(1, 1*cm))
    
    # Tabla de notas individuales
    elementos.append(Paragraph("📋 DETALLE DE CALIFICACIONES", styles['Heading2']))
    elementos.append(Spacer(1, 0.3*cm))
    
    notas_data = [['#', 'Nombre PDF', 'Correctas', 'Incorrectas', 'Nota', 'Estado']]
    
    for idx, row in df.iterrows():
        estado = 'Aprobado' if row['nota'] >= 14 else 'Desaprobado'
        notas_data.append([
            str(idx + 1),
            row['nombre_pdf'][:40],  # Truncar nombres largos
            str(row['correctas']),
            str(row['incorrectas']),
            f"{row['nota']:.2f}",
            estado
        ])
    
    notas_table = Table(notas_data, colWidths=[1*cm, 6*cm, 2.5*cm, 2.5*cm, 2*cm, 3*cm])
    notas_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')])
    ]))
    
    elementos.append(notas_table)
    
    # Construir PDF
    doc.build(elementos)
    buffer.seek(0)
    return buffer

# ==================== INTERFAZ PRINCIPAL ====================

st.sidebar.header("⚙️ Panel de Control")
st.sidebar.markdown("---")

# PASO 1: Datos del curso
st.header("1️⃣ Datos del Curso")
col1, col2 = st.columns(2)

with col1:
    curso_nombre = st.text_input(
        "📚 Nombre del Curso:", 
        placeholder="Ej: Matemática Avanzada",
        help="Ingresa el nombre completo del curso"
    )

with col2:
    curso_codigo = st.text_input(
        "🔢 Código del Curso:", 
        placeholder="Ej: MAT-301",
        help="Ingresa el código del curso"
    )

# Ingreso de clave de respuestas
st.subheader("🔑 Clave de Respuestas")
st.info("📝 **Formato:** 1:**a, 2**:**d, 3**:**e, 4**:**v, 5**:f (separados por comas)")

clave_input = st.text_area(
    "Ingresa las respuestas correctas:",
    height=100,
    placeholder="Ejemplo: 1:a, 2:b, 3:c, 4:v, 5:f, 6:d, 7:e, 8:a, 9:f, 10:b",
    help="Usa 'v' para verdadero y 'f' para falso. Usa 'a', 'b', 'c', 'd', 'e' para alternativas múltiples."
)

if clave_input:
    clave = parsear_clave(clave_input)
    if clave:
        st.success(f"✅ Clave cargada correctamente: **{len(clave)} preguntas**")
        with st.expander("👁️ Ver clave de respuestas"):
            df_clave = pd.DataFrame(list(clave.items()), columns=['Pregunta', 'Respuesta'])
            df_clave['Respuesta'] = df_clave['Respuesta'].str.upper()
            st.dataframe(df_clave, use_container_width=True, hide_index=True)
else:
    clave = None

st.markdown("---")

# PASO 2: Carga de PDFs
st.header("2️⃣ Carga de Exámenes (PDFs)")
st.info("📤 Puedes cargar hasta **30 archivos PDF** simultáneamente")

uploaded_files = st.file_uploader(
    "Selecciona los PDFs de los exámenes:",
    type=['pdf'],
    accept_multiple_files=True,
    help="Arrastra y suelta o haz clic para seleccionar archivos PDF"
)

if uploaded_files:
    if len(uploaded_files) > 30:
        st.error("❌ **Máximo 30 archivos permitidos.** Por favor reduce la cantidad de archivos.")
    else:
        st.success(f"✅ **{len(uploaded_files)} archivo(s) cargado(s) exitosamente**")
        with st.expander("📂 Ver archivos cargados"):
            for idx, file in enumerate(uploaded_files, 1):
                st.write(f"{idx}. 📄 {file.name} ({file.size / 1024:.1f} KB)")

st.markdown("---")

# PASO 3: Análisis con n8n (simulado)
st.header("3️⃣ Análisis Automático")

# Validación antes de habilitar el botón
puede_analizar = all([
    st.session_state.api_configurada,
    clave,
    uploaded_files,
    curso_nombre,
    curso_codigo,
    len(uploaded_files) <= 30
])

if not puede_analizar:
    mensajes_faltantes = []
    if not curso_nombre:
        mensajes_faltantes.append("📚 Nombre del curso")
    if not curso_codigo:
        mensajes_faltantes.append("🔢 Código del curso")
    if not clave:
        mensajes_faltantes.append("🔑 Clave de respuestas")
    if not uploaded_files:
        mensajes_faltantes.append("📄 Archivos PDF")
    
    if mensajes_faltantes:
        st.warning(f"⚠️ **Completa los siguientes campos:** {', '.join(mensajes_faltantes)}")

if st.button("🚀 Analizar con n8n", disabled=not puede_analizar, type="primary"):
    # Simulación de procesamiento en n8n
    st.markdown("""
    <div class="processing-box">
        <h2>🔄 Procesando en n8n...</h2>
        <p>Analizando exámenes con Inteligencia Artificial</p>
    </div>
    """, unsafe_allow_html=True)
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    resultados = []
    total_files = len(uploaded_files)
    
    for idx, pdf_file in enumerate(uploaded_files):
        # Actualizar progreso
        progreso = (idx + 1) / total_files
        progress_bar.progress(progreso)
        status_text.markdown(f"⚙️ **Procesando:** `{pdf_file.name}` ... ({idx + 1}/{total_files})")
        
        # Simular procesamiento en n8n (delay visual)
        time.sleep(0.8)
        
        # Extraer respuestas con Gemini
        with st.spinner(f"🤖 Analizando con IA..."):
            respuestas_alumno = extraer_respuestas_gemini(model, pdf_file, len(clave))
        
        # Calcular nota
        nota, correctas, incorrectas = calcular_nota(respuestas_alumno, clave)
        
        # Guardar resultado
        resultados.append({
            'nombre_pdf': pdf_file.name,
            'nota': nota,
            'correctas': correctas,
            'incorrectas': incorrectas,
            'respuestas': respuestas_alumno
        })
        
        # Resetear el file pointer para uso futuro
        pdf_file.seek(0)
    
    # Completar progreso
    progress_bar.progress(1.0)
    status_text.markdown("✅ **¡Procesamiento completado exitosamente!**")
    time.sleep(1.5)
    status_text.empty()
    progress_bar.empty()
    
    # Guardar en session state
    st.session_state.resultados = resultados
    st.session_state.procesado = True
    st.session_state.curso_nombre = curso_nombre
    st.session_state.curso_codigo = curso_codigo
    st.session_state.clave = clave
    
    st.balloons()
    st.success("🎉 **¡Análisis completado exitosamente!** Revisa los resultados abajo.")

# PASO 4: Mostrar resultados
if st.session_state.procesado and st.session_state.resultados:
    st.markdown("---")
    st.header("4️⃣ Resultados del Análisis")
    
    df_resultados = pd.DataFrame(st.session_state.resultados)
    
    # Métricas principales
    st.subheader("📊 Estadísticas Generales")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="📈 Promedio General", 
            value=f"{df_resultados['nota'].mean():.2f}",
            help="Promedio de todas las notas"
        )
    
    with col2:
        aprobados = len(df_resultados[df_resultados['nota'] >= 14])
        porcentaje_aprobados = (aprobados/len(df_resultados)*100)
        st.metric(
            label="✅ Aprobados", 
            value=f"{aprobados}",
            delta=f"{porcentaje_aprobados:.1f}%",
            help="Estudiantes con nota >= 14"
        )
    
    with col3:
        desaprobados = len(df_resultados[df_resultados['nota'] < 14])
        porcentaje_desaprobados = (desaprobados/len(df_resultados)*100)
        st.metric(
            label="❌ Desaprobados", 
            value=f"{desaprobados}",
            delta=f"-{porcentaje_desaprobados:.1f}%",
            delta_color="inverse",
            help="Estudiantes con nota < 14"
        )
    
    with col4:
        st.metric(
            label="👥 Total Estudiantes", 
            value=len(df_resultados),
            help="Total de exámenes procesados"
        )
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    col5, col6, col7, col8 = st.columns(4)
    
    with col5:
        if aprobados > 0:
            promedio_aprobados = df_resultados[df_resultados['nota'] >= 14]['nota'].mean()
            st.metric(
                label="📊 Promedio Aprobados", 
                value=f"{promedio_aprobados:.2f}",
                help="Promedio solo de estudiantes aprobados"
            )
        else:
            st.metric(label="📊 Promedio Aprobados", value="N/A")
    
    with col6:
        st.metric(
            label="🏆 Nota Más Alta", 
            value=f"{df_resultados['nota'].max():.2f}",
            help="Mejor nota obtenida"
        )
    
    with col7:
        st.metric(
            label="📉 Nota Más Baja", 
            value=f"{df_resultados['nota'].min():.2f}",
            help="Menor nota obtenida"
        )
    
    with col8:
        st.metric(
            label="📝 Total Preguntas", 
            value=len(st.session_state.clave),
            help="Cantidad de preguntas del examen"
        )
    
    st.markdown("---")
    
    # Tabla de resultados
    st.subheader("📋 Detalle de Calificaciones")
    
    df_display = df_resultados[['nombre_pdf', 'correctas', 'incorrectas', 'nota']].copy()
    df_display['estado'] = df_display['nota'].apply(
        lambda x: '✅ Aprobado' if x >= 14 else '❌ Desaprobado'
    )
    df_display = df_display.sort_values('nota', ascending=False).reset_index(drop=True)
    df_display.index += 1
    
    st.dataframe(
        df_display,
        use_container_width=True,
        column_config={
            "nombre_pdf": st.column_config.TextColumn(
                "Nombre del Archivo",
                width="large"
            ),
            "correctas": st.column_config.NumberColumn(
                "Correctas ✓",
                format="%d"
            ),
            "incorrectas": st.column_config.NumberColumn(
                "Incorrectas ✗",
                format="%d"
            ),
            "nota": st.column_config.NumberColumn(
                "Nota Final",
                format="%.2f"
            ),
            "estado": st.column_config.TextColumn(
                "Estado"
            )
        }
    )
    
    # Botón de exportación
    st.markdown("---")
    st.header("5️⃣ Exportar Reporte")
    
    col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
    
    with col_btn2:
        if st.button("📄 Generar Reporte PDF", type="primary", use_container_width=True):
            with st.spinner("📝 Generando reporte PDF..."):
                time.sleep(1)  # Simular procesamiento
                pdf_buffer = generar_reporte_pdf(
                    st.session_state.resultados,
                    st.session_state.curso_nombre,
                    st.session_state.curso_codigo,
                    st.session_state.clave
                )
                
                st.success("✅ **¡Reporte generado exitosamente!**")
                
                # Botón de descarga
                nombre_archivo = f"reporte_{st.session_state.curso_codigo}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                
                st.download_button(
                    label="⬇️ Descargar Reporte PDF",
                    data=pdf_buffer,
                    file_name=nombre_archivo,
                    mime="application/pdf",
                    use_container_width=True
                )

# Sidebar con información adicional
with st.sidebar:
    st.markdown("---")
    st.subheader("ℹ️ Información")
    st.info("""
    **Escala de Notas:** 0 - 20
    
    **Nota Aprobatoria:** 14
    
    **Formatos Aceptados:**
    - Alternativas: a, b, c, d, e
    - Binarias: v (verdadero), f (falso)
    
    **Marcas Reconocidas:**
    - X (equis)
    - Círculos
    - Resaltados
    """)
    
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; padding: 1rem;'>
        <p style='font-size: 0.9rem; color: #666;'>
            <strong>Sistema v1.0</strong><br>
            Powered by Google Gemini AI 🤖
        </p>
    </div>
    """, unsafe_allow_html=True)

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 1rem;'>
    <p><strong>Sistema de Calificación Automática</strong> | Desarrollado con ❤️ usando Streamlit</p>
</div>

""", unsafe_allow_html=True)

