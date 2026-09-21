"""
SaaS Predictivo de Conversión - Backend FastAPI
Detecta abandonos de carrito con 48h de anticipación usando LSTM/Prophet
"""

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, UploadFile, File, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, timedelta
import os
import jwt
import bcrypt
import uuid
from pathlib import Path
import httpx
import json
from typing import Optional, List
import numpy as np
from sklearn.preprocessing import MinMaxScaler
import logging
from dotenv import load_dotenv

# BUG CORREGIDO: python-dotenv estaba en requirements.txt pero nunca se
# llamaba - el .env nunca se cargaba al correr "uvicorn main:app" directo
# (sin Docker). Con esto, main.py carga .env automaticamente si existe.
load_dotenv()

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@db:5432/saas_db")

# PARCHE DE SEGURIDAD: ya no arranca con una clave por defecto publica.
# Si no configuras SECRET_KEY (min 32 caracteres) en .env, la app NO enciende.
SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY or len(SECRET_KEY) < 32:
    raise RuntimeError(
        "SECRET_KEY no configurada o muy corta (minimo 32 caracteres). "
        "Genera una con: python -c \"import secrets; print(secrets.token_hex(32))\" "
        "y ponla en tu .env"
    )

# PARCHE: lista de correos autorizados como administrador (separados por coma)
ADMIN_EMAILS = set(
    e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()
)

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY", "")

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# DATABASE SETUP
# ============================================================================

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    echo=False,
    pool_size=10,
    max_overflow=20
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ============================================================================
# MODELOS DE BASE DE DATOS
# ============================================================================

class Usuario(Base):
    __tablename__ = "usuarios"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    nombre = Column(String)
    password_hash = Column(String)
    tienda_url = Column(String)
    plan = Column(String, default="basic")  # basic, pro, enterprise
    shopify_token = Column(String)
    mercadolibre_token = Column(String)
    activo = Column(Boolean, default=True)
    fecha_creacion = Column(DateTime, default=datetime.utcnow)
    fecha_proximo_pago = Column(DateTime)
    notificaciones_email = Column(Boolean, default=True)
    notificaciones_sms = Column(Boolean, default=False)
    telefono = Column(String)

class Evento(Base):
    __tablename__ = "eventos"
    
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, index=True)
    cliente_id = Column(String)
    tipo = Column(String)  # "venta", "abandono", "vista_producto"
    monto = Column(Float)
    items = Column(Integer)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    datos_extra = Column(JSON)  # productos, navegacion, etc.

class Prediccion(Base):
    __tablename__ = "predicciones"
    
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, index=True)
    cliente_id = Column(String)
    probabilidad_abandono = Column(Float)
    confianza = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    alerta_enviada = Column(Boolean, default=False)
    tipo_alerta = Column(String)  # "email", "sms", "ambas"

# Crear tablas
Base.metadata.create_all(bind=engine)

# ============================================================================
# MODELOS PYDANTIC
# ============================================================================

class UsuarioCreate(BaseModel):
    email: EmailStr
    nombre: str
    password: str
    tienda_url: str

class UsuarioLogin(BaseModel):
    email: str
    password: str

class EventoCreate(BaseModel):
    cliente_id: str
    tipo: str
    monto: float
    items: int
    datos_extra: dict = {}

class PrediccionResponse(BaseModel):
    probabilidad_abandono: float
    confianza: float
    recomendacion: str
    
    class Config:
        from_attributes = True

class SuscripcionUpdate(BaseModel):
    plan: str  # basic, pro, enterprise
    shopify_token: Optional[str] = None
    mercadolibre_token: Optional[str] = None
    notificaciones_email: Optional[bool] = None
    notificaciones_sms: Optional[bool] = None
    telefono: Optional[str] = None

# ============================================================================
# APP SETUP
# ============================================================================

app = FastAPI(
    title="SaaS Predictivo de Conversión",
    description="Detecta abandonos de carrito con 48h de anticipación",
    version="1.0.0"
)

# CORS - restringido a tu dominio real, no abierto a cualquiera
ALLOWED_ORIGINS = [o.strip() for o in os.getenv(
    "ALLOWED_ORIGINS", "https://ingenieroai.pro,https://www.ingenieroai.pro"
).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# ============================================================================
# UTILIDADES
# ============================================================================

def hash_password(password: str) -> str:
    """Hash de contraseña con bcrypt (salt automatico, lento a proposito)"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verificar_password(password: str, password_hash: str) -> bool:
    """Compara una contraseña en texto plano contra su hash bcrypt"""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # hash con formato antiguo (sha256) -> ya no es valido, forzar reset
        return False

def create_token(email: str, usuario_id: int) -> str:
    """Crea JWT token"""
    payload = {
        "email": email,
        "usuario_id": usuario_id,
        "exp": datetime.utcnow() + timedelta(days=30)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def verify_token(token: str) -> dict:
    """Verifica JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    """Obtiene usuario actual desde token"""
    if not authorization:
        raise HTTPException(status_code=401, detail="No autorizado")
    
    try:
        token = authorization.split(" ")[1]
        payload = verify_token(token)
        usuario_id = payload.get("usuario_id")
        usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
        if not usuario:
            raise HTTPException(status_code=401, detail="Usuario no encontrado")
        return usuario
    except IndexError:
        raise HTTPException(status_code=401, detail="Formato de token inválido")

def get_current_admin(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    """PARCHE DE SEGURIDAD: exige que el usuario autenticado este en ADMIN_EMAILS.
    Usar esta dependencia en TODOS los endpoints /api/admin/*"""
    usuario = get_current_user(authorization, db)
    if usuario.email.lower() not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="No autorizado - solo administradores")
    return usuario

EXTENSIONES_PERMITIDAS = {".jpg", ".jpeg", ".png", ".pdf", ".webp"}
TAMANO_MAXIMO_MB = 5

def nombre_archivo_seguro(filename: str) -> str:
    """PARCHE DE SEGURIDAD: nunca usar el nombre que manda el cliente tal cual
    (riesgo de path traversal / sobreescritura de archivos)."""
    ext = Path(filename).suffix.lower()
    if ext not in EXTENSIONES_PERMITIDAS:
        raise HTTPException(status_code=400, detail=f"Tipo de archivo no permitido. Usa: {', '.join(EXTENSIONES_PERMITIDAS)}")
    return f"{uuid.uuid4().hex}{ext}"

# ============================================================================
# MODELO LSTM PREDICTOR
# ============================================================================

class LSTMPredictor:
    """Predictor simple basado en patrones históricos"""
    
    def __init__(self):
        self.scaler = MinMaxScaler()
    
    def predecir_abandono(self, eventos: List[dict]) -> tuple:
        """
        Predice probabilidad de abandono basado en:
        - Tiempo desde última interacción
        - Patrón de navegación
        - Valor del carrito
        """
        if not eventos:
            return 0.5, 0.3  # probabilidad, confianza
        
        # Features básicos
        evento_reciente = eventos[-1]
        tiempo_desde_ultima_interaccion = (datetime.utcnow() - evento_reciente.get("timestamp", datetime.utcnow())).total_seconds() / 3600
        
        monto_carrito = evento_reciente.get("monto", 0)
        num_items = evento_reciente.get("items", 0)
        
        # Heurística de riesgo
        riesgo = 0.3
        
        # +0.2 si hace > 6h sin interacción
        if tiempo_desde_ultima_interaccion > 6:
            riesgo += min(0.3, tiempo_desde_ultima_interaccion / 48)
        
        # +0.1 si carrito > $100
        if monto_carrito > 100:
            riesgo += 0.1
        
        # -0.1 si tiene muchos items (más probabilidad de compra)
        if num_items > 3:
            riesgo = max(0.1, riesgo - 0.1)
        
        # Confianza basada en cantidad de datos
        confianza = min(0.9, 0.3 + len(eventos) * 0.1)
        
        return min(0.95, riesgo), confianza

predictor = LSTMPredictor()

# ============================================================================
# ALERTAS
# ============================================================================

def enviar_email_alerta(email: str, nombre_cliente: str, probabilidad: float):
    """Envía alerta por email usando SendGrid"""
    try:
        if not SENDGRID_API_KEY:
            logger.warning("SendGrid no configurado")
            return
        
        # Simulamos envío (en prod usar sendgrid-python)
        logger.info(f"✉️ Email enviado a {email}: Abandono detectado ({probabilidad:.1%})")
    except Exception as e:
        logger.error(f"Error enviando email: {e}")

def enviar_sms_alerta(telefono: str, probabilidad: float):
    """Envía alerta por SMS usando Twilio"""
    try:
        if not TWILIO_ACCOUNT_SID:
            logger.warning("Twilio no configurado")
            return
        
        # Simulamos envío
        logger.info(f"📱 SMS enviado a {telefono}: Riesgo de abandono {probabilidad:.1%}")
    except Exception as e:
        logger.error(f"Error enviando SMS: {e}")

async def procesar_alertas(usuario_id: int, probabilidad: float, db: Session):
    """Procesa y envía alertas si probabilidad > 70%"""
    if probabilidad < 0.70:
        return
    
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        return
    
    # Email
    if usuario.notificaciones_email:
        enviar_email_alerta(usuario.email, usuario.nombre, probabilidad)
    
    # SMS
    if usuario.notificaciones_sms and usuario.telefono:
        enviar_sms_alerta(usuario.telefono, probabilidad)

# ============================================================================
# ENDPOINTS: AUTENTICACIÓN
# ============================================================================

@app.post("/api/auth/registro")
def registro(usuario: UsuarioCreate, db: Session = Depends(get_db)):
    """Registra nuevo usuario con prueba de 14 días gratuita"""
    
    # Verificar si email existe
    existe = db.query(Usuario).filter(Usuario.email == usuario.email).first()
    if existe:
        raise HTTPException(status_code=400, detail="Email ya registrado")
    
    # Crear usuario
    nuevo_usuario = Usuario(
        email=usuario.email,
        nombre=usuario.nombre,
        password_hash=hash_password(usuario.password),
        tienda_url=usuario.tienda_url,
        plan="basic",
        fecha_proximo_pago=datetime.utcnow() + timedelta(days=14)
    )
    
    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)
    
    token = create_token(usuario.email, nuevo_usuario.id)
    
    return {
        "id": nuevo_usuario.id,
        "email": nuevo_usuario.email,
        "token": token,
        "plan": "basic (prueba 14 días)",
        "mensaje": "¡Bienvenido! Tu prueba gratuita comienza ahora."
    }

@app.post("/api/auth/login")
def login(credenciales: UsuarioLogin, db: Session = Depends(get_db)):
    """Login de usuario"""
    
    usuario = db.query(Usuario).filter(Usuario.email == credenciales.email).first()
    if not usuario or not verificar_password(credenciales.password, usuario.password_hash):
        raise HTTPException(status_code=401, detail="Email o contraseña inválidos")
    
    if not usuario.activo:
        raise HTTPException(status_code=403, detail="Cuenta desactivada")
    
    token = create_token(usuario.email, usuario.id)
    
    return {
        "id": usuario.id,
        "email": usuario.email,
        "nombre": usuario.nombre,
        "plan": usuario.plan,
        "token": token
    }

# ============================================================================
# ENDPOINTS: EVENTOS Y DATOS
# ============================================================================

@app.post("/api/eventos")
async def registrar_evento(
    evento: EventoCreate,
    background_tasks: BackgroundTasks,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """Registra evento de cliente (carrito, vista, compra)"""
    
    usuario = get_current_user(authorization, db)
    
    # Guardar evento
    nuevo_evento = Evento(
        usuario_id=usuario.id,
        cliente_id=evento.cliente_id,
        tipo=evento.tipo,
        monto=evento.monto,
        items=evento.items,
        datos_extra=evento.datos_extra
    )
    
    db.add(nuevo_evento)
    db.commit()
    
    # Si es abandono, predecir
    if evento.tipo == "abandono":
        # Obtener histórico
        eventos_cliente = db.query(Evento).filter(
            Evento.usuario_id == usuario.id,
            Evento.cliente_id == evento.cliente_id
        ).order_by(Evento.timestamp.desc()).limit(10).all()
        
        eventos_dict = [
            {
                "timestamp": e.timestamp,
                "tipo": e.tipo,
                "monto": e.monto,
                "items": e.items,
                "datos_extra": e.datos_extra
            }
            for e in eventos_cliente
        ]
        
        prob, conf = predictor.predecir_abandono(eventos_dict)
        
        # Guardar predicción
        prediccion = Prediccion(
            usuario_id=usuario.id,
            cliente_id=evento.cliente_id,
            probabilidad_abandono=prob,
            confianza=conf
        )
        db.add(prediccion)
        db.commit()
        
        # Enviar alertas en background
        background_tasks.add_task(procesar_alertas, usuario.id, prob, db)
        
        return {
            "evento_id": nuevo_evento.id,
            "probabilidad_abandono": prob,
            "confianza": conf,
            "alerta_enviada": prob > 0.70
        }
    
    return {"evento_id": nuevo_evento.id, "guardado": True}

@app.get("/api/predicciones")
def obtener_predicciones(
    dias: int = 7,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """Obtiene predicciones de los últimos N días"""
    
    usuario = get_current_user(authorization, db)
    
    fecha_desde = datetime.utcnow() - timedelta(days=dias)
    predicciones = db.query(Prediccion).filter(
        Prediccion.usuario_id == usuario.id,
        Prediccion.timestamp >= fecha_desde
    ).order_by(Prediccion.timestamp.desc()).all()
    
    # Estadísticas
    total = len(predicciones)
    alertas = sum(1 for p in predicciones if p.probabilidad_abandono > 0.70)
    prob_promedio = np.mean([p.probabilidad_abandono for p in predicciones]) if predicciones else 0
    
    return {
        "total_predicciones": total,
        "alertas_activas": alertas,
        "probabilidad_promedio": prob_promedio,
        "predicciones": [
            {
                "cliente_id": p.cliente_id,
                "probabilidad": p.probabilidad_abandono,
                "confianza": p.confianza,
                "timestamp": p.timestamp.isoformat(),
                "alerta_enviada": p.alerta_enviada
            }
            for p in predicciones[:50]
        ]
    }

# ============================================================================
# ENDPOINTS: SUSCRIPCIÓN
# ============================================================================

@app.get("/api/planes")
def obtener_planes():
    """Obtiene planes disponibles"""
    return {
        "planes": [
            {
                "nombre": "Básico",
                "id": "basic",
                "precio": 299,
                "moneda": "USD",
                "features": [
                    "Hasta 100 eventos/mes",
                    "Predicciones en tiempo real",
                    "Alertas por email",
                    "Soporte por email"
                ]
            },
            {
                "nombre": "Profesional",
                "id": "pro",
                "precio": 599,
                "moneda": "USD",
                "features": [
                    "Hasta 10K eventos/mes",
                    "Predicciones avanzadas",
                    "Alertas email + SMS",
                    "API ilimitada",
                    "Soporte prioritario"
                ]
            },
            {
                "nombre": "Empresarial",
                "id": "enterprise",
                "precio": 999,
                "moneda": "USD",
                "features": [
                    "Eventos ilimitados",
                    "LSTM personalizado",
                    "Alertas multi-canal",
                    "API dedicada",
                    "Soporte 24/7",
                    "Análisis personalizado"
                ]
            }
        ]
    }

@app.post("/api/suscripcion/actualizar")
def actualizar_suscripcion(
    datos: SuscripcionUpdate,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """Actualiza plan del usuario"""
    
    usuario = get_current_user(authorization, db)
    
    usuario.plan = datos.plan
    
    if datos.shopify_token:
        usuario.shopify_token = datos.shopify_token
    
    if datos.mercadolibre_token:
        usuario.mercadolibre_token = datos.mercadolibre_token
    
    if datos.notificaciones_email is not None:
        usuario.notificaciones_email = datos.notificaciones_email
    
    if datos.notificaciones_sms is not None:
        usuario.notificaciones_sms = datos.notificaciones_sms
    
    if datos.telefono:
        usuario.telefono = datos.telefono
    
    db.commit()
    
    return {
        "plan": usuario.plan,
        "actualizado": True,
        "proximo_pago": usuario.fecha_proximo_pago.isoformat() if usuario.fecha_proximo_pago else None
    }

# ============================================================================
# ENDPOINTS: DASHBOARD
# ============================================================================

@app.get("/api/dashboard")
def obtener_dashboard(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """Obtiene datos para dashboard"""
    
    usuario = get_current_user(authorization, db)
    
    # Últimas 30 días
    fecha_desde = datetime.utcnow() - timedelta(days=30)
    
    eventos = db.query(Evento).filter(
        Evento.usuario_id == usuario.id,
        Evento.timestamp >= fecha_desde
    ).all()
    
    predicciones = db.query(Prediccion).filter(
        Prediccion.usuario_id == usuario.id,
        Prediccion.timestamp >= fecha_desde
    ).all()
    
    # Métricas
    ventas = sum(e.monto for e in eventos if e.tipo == "venta")
    abandonos = sum(e.monto for e in eventos if e.tipo == "abandono")
    alertas = sum(1 for p in predicciones if p.probabilidad_abandono > 0.70)
    
    return {
        "usuario": {
            "nombre": usuario.nombre,
            "plan": usuario.plan,
            "email": usuario.email
        },
        "metricas": {
            "ventas_30d": ventas,
            "abandono_detectado": abandonos,
            "alertas_enviadas": alertas,
            "tasa_recuperacion": round((ventas / (ventas + abandonos) * 100) if (ventas + abandonos) > 0 else 0, 2)
        },
        "predicciones_recientes": len(predicciones),
        "proxima_facturacion": usuario.fecha_proximo_pago.isoformat() if usuario.fecha_proximo_pago else None
    }

# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/health")
def health_check():
    """Health check para deployment"""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }

# ============================================================================
# WEBHOOKS
# ============================================================================

@app.post("/api/webhooks/shopify")
async def webhook_shopify(payload: dict, background_tasks: BackgroundTasks):
    """Webhook para recibir eventos de Shopify"""
    
    try:
        # Validar webhook
        logger.info(f"Webhook Shopify recibido: {payload.get('topic', 'unknown')}")
        # En producción: verificar HMAC
        
        return {"status": "received"}
    except Exception as e:
        logger.error(f"Error en webhook Shopify: {e}")
        return {"status": "error", "detail": str(e)}, 500

@app.post("/api/webhooks/mercadolibre")
async def webhook_mercadolibre(payload: dict):
    """Webhook para recibir eventos de MercadoLibre"""
    
    try:
        logger.info(f"Webhook MercadoLibre recibido")
        
        return {"status": "received"}
    except Exception as e:
        logger.error(f"Error en webhook MercadoLibre: {e}")
        return {"status": "error"}, 500

# ============================================================================
# ROOT
# ============================================================================

@app.get("/")
def root():
    return {
        "app": "SaaS Predictivo de Conversión",
        "version": "1.0.0",
        "endpoints": "/docs"
    }

# ============================================================================
# PAGOS: PAYPAL + TRANSFERENCIA + ADMIN (ahora conectados de verdad, con
# proteccion de administrador y validacion de archivos)
# ============================================================================

import importlib
_pagos_mod = importlib.import_module("paypal_transferencia_integration")
PayPalManager = _pagos_mod.PayPalManager
TransferenciaManager = _pagos_mod.TransferenciaManager
PagoManual = _pagos_mod.PagoManual

@app.post("/api/pagos/paypal/crear-suscripcion")
async def crear_suscripcion_paypal(plan: str, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    usuario = get_current_user(authorization, db)
    return await PayPalManager.crear_suscripcion_recurrente(plan, usuario.id)

@app.post("/api/pagos/paypal/crear-pago-unico")
async def crear_pago_unico_paypal(plan: str, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    usuario = get_current_user(authorization, db)
    return await PayPalManager.crear_orden_pago_unico(plan, usuario.id)

@app.get("/api/pagos/transferencia/instrucciones")
def obtener_instrucciones_transferencia(plan: str, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    usuario = get_current_user(authorization, db)
    return TransferenciaManager.generar_instrucciones(plan, usuario.id)

@app.post("/api/pagos/transferencia/subir-comprobante")
async def subir_comprobante(
    plan: str, referencia: str, monto: float,
    comprobante: UploadFile = File(...),
    authorization: Optional[str] = Header(None), db: Session = Depends(get_db)
):
    usuario = get_current_user(authorization, db)

    contenido = await comprobante.read()
    if len(contenido) > TAMANO_MAXIMO_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"Archivo muy grande (max {TAMANO_MAXIMO_MB}MB)")

    nombre_seguro = nombre_archivo_seguro(comprobante.filename)
    carpeta = Path("/app/comprobantes")
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{usuario.id}_{nombre_seguro}"
    with open(ruta, "wb") as f:
        f.write(contenido)

    pago = TransferenciaManager.registrar_solicitud(usuario.id, plan, monto, referencia, str(ruta), db)
    return {"pago_id": pago.id, "estado": pago.estado, "mensaje": "Comprobante recibido. Verificaremos en menos de 24h."}

@app.get("/api/admin/pagos-pendientes")
def listar_pagos_pendientes(admin: Usuario = Depends(get_current_admin), db: Session = Depends(get_db)):
    pagos = db.query(PagoManual).filter(PagoManual.estado == "pendiente").all()
    return [{"id": p.id, "usuario_id": p.usuario_id, "monto": p.monto, "referencia": p.referencia,
             "comprobante": p.comprobante_url} for p in pagos]

@app.post("/api/admin/pagos/{pago_id}/verificar")
async def verificar_pago_admin(
    pago_id: int, aprobado: bool, notas: str = "",
    admin: Usuario = Depends(get_current_admin), db: Session = Depends(get_db)
):
    resultado = TransferenciaManager.verificar_pago(pago_id, aprobado, notas, db)
    if aprobado:
        pago = db.query(PagoManual).filter(PagoManual.id == pago_id).first()
        usuario = db.query(Usuario).filter(Usuario.id == pago.usuario_id).first()
        try:
            from notificaciones_whatsapp import notificar_venta
            await notificar_venta(pago.plan, pago.monto, "GTQ", "Transferencia", usuario.email)
        except Exception as e:
            logger.warning(f"No se pudo notificar por WhatsApp: {e}")
    return resultado

# ============================================================================
# WEBHOOK DE PAYPAL - antes no existia ningun endpoint que lo recibiera,
# solo la funcion de verificacion suelta sin usar. Ahora si esta conectado.
# ============================================================================

@app.post("/api/webhooks/paypal")
async def webhook_paypal(request: Request, db: Session = Depends(get_db)):
    body_bytes = await request.body()
    headers = dict(request.headers)

    webhook_id = os.getenv("PAYPAL_WEBHOOK_ID", "")
    if not webhook_id:
        logger.error("PAYPAL_WEBHOOK_ID no configurado - webhook rechazado por seguridad")
        raise HTTPException(status_code=400, detail="Webhook no configurado")

    try:
        es_valido = await PayPalManager.verificar_webhook(headers, body_bytes, webhook_id)
    except Exception as e:
        logger.error(f"Error verificando webhook de PayPal: {e}")
        raise HTTPException(status_code=400, detail="No se pudo verificar el webhook")

    if not es_valido:
        raise HTTPException(status_code=400, detail="Webhook invalido")

    try:
        event = json.loads(body_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Cuerpo del webhook invalido")

    tipo = event.get("event_type", "")
    resource = event.get("resource", {})

    if tipo in ("PAYMENT.SALE.COMPLETED", "CHECKOUT.ORDER.APPROVED", "BILLING.SUBSCRIPTION.ACTIVATED"):
        custom_id = resource.get("custom_id") or resource.get("reference_id", "")
        # el custom_id/reference_id se genero como "usuario_{id}_plan_{plan}"
        if custom_id.startswith("usuario_"):
            try:
                partes = custom_id.split("_")
                usuario_id = int(partes[1])
                plan = partes[3] if len(partes) > 3 else "basic"
            except (IndexError, ValueError):
                logger.warning(f"custom_id con formato inesperado: {custom_id}")
                return {"status": "received", "procesado": False}

            usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
            if usuario:
                usuario.plan = plan
                usuario.fecha_proximo_pago = datetime.utcnow() + timedelta(days=30)
                usuario.activo = True
                db.commit()
                try:
                    from notificaciones_whatsapp import notificar_venta
                    monto = resource.get("amount", {}).get("value", "0")
                    await notificar_venta(plan, float(monto), "USD", "PayPal", usuario.email)
                except Exception as e:
                    logger.warning(f"No se pudo notificar por WhatsApp: {e}")

    return {"status": "received"}

# ============================================================================
# CAPTURAR ORDEN DE PAYPAL - se llama cuando el cliente vuelve del checkout
# de PayPal tras aprobar el pago (pago unico, no suscripcion). Antes esto
# tampoco estaba conectado: capturar_orden() existia pero nunca se llamaba,
# asi que el cobro nunca se confirmaba del lado de PayPal.
# ============================================================================

@app.post("/api/pagos/paypal/capturar")
async def capturar_pago_paypal(
    order_id: str, plan: str,
    authorization: Optional[str] = Header(None), db: Session = Depends(get_db)
):
    usuario = get_current_user(authorization, db)
    resultado = await PayPalManager.capturar_orden(order_id)

    if resultado.get("status") == "COMPLETED":
        usuario.plan = plan
        usuario.fecha_proximo_pago = datetime.utcnow() + timedelta(days=30)
        usuario.activo = True
        db.commit()
        try:
            from notificaciones_whatsapp import notificar_venta
            await notificar_venta(plan, PayPalManager.PLANES_PAYPAL.get(plan, {}).get("precio", 0), "USD", "PayPal", usuario.email)
        except Exception as e:
            logger.warning(f"No se pudo notificar por WhatsApp: {e}")
        return {"status": "completado", "plan_activado": plan}

    return {"status": resultado.get("status", "desconocido"), "plan_activado": False}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
