"""
Integración PayPal + Transferencia Bancaria
Complementa (o reemplaza) a Stripe como métodos de pago
"""

import os
import httpx
import base64
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text
from main import Base, Usuario, SessionLocal, engine

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIG
# ============================================================================

PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "")
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox")  # sandbox o live

PAYPAL_BASE_URL = (
    "https://api-m.sandbox.paypal.com" if PAYPAL_MODE == "sandbox"
    else "https://api-m.paypal.com"
)

# Datos bancarios para transferencia (Guatemala: BAM + Banco Industrial)
CUENTAS_BANCARIAS = {
    "bam": {
        "banco": "BAM",
        "titular": os.getenv("BANCO_TITULAR", "Willy Enriquez Palacios"),
        "tipo": "Ahorro",
        "cuenta": os.getenv("BANCO_CUENTA_BAM", "40-5012894-3"),
    },
    "industrial": {
        "banco": "Banco Industrial",
        "titular": os.getenv("BANCO_TITULAR", "Willy Enriquez Palacios"),
        "tipo": "Ahorro",
        "cuenta": os.getenv("BANCO_CUENTA_INDUSTRIAL", "1402158"),
    },
}
# se mantiene por compatibilidad con codigo que use DATOS_BANCARIOS (default: BAM)
DATOS_BANCARIOS = CUENTAS_BANCARIAS["bam"]

# ============================================================================
# MODELO: PAGOS MANUALES (transferencia bancaria)
# ============================================================================

class PagoManual(Base):
    """Registro de pagos por transferencia bancaria (requieren verificación manual)"""
    __tablename__ = "pagos_manuales"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, index=True)
    plan = Column(String)
    monto = Column(Float)
    moneda = Column(String, default="MXN")
    metodo = Column(String, default="transferencia")  # transferencia, deposito
    referencia = Column(String)  # folio que pone el cliente
    comprobante_url = Column(String)  # link a imagen/PDF del comprobante
    estado = Column(String, default="pendiente")  # pendiente, verificado, rechazado
    notas_admin = Column(Text)
    fecha_solicitud = Column(DateTime, default=datetime.utcnow)
    fecha_verificacion = Column(DateTime)

# Crear tabla. BUG CORREGIDO: la version anterior hacia
# "SessionLocal().get_bind()" - eso abre una sesion de BD real y nunca la
# cierra (fuga de conexion en cada arranque). Ahora se usa el engine
# directo, que es lo correcto para esta operacion.
Base.metadata.create_all(bind=engine)

# ============================================================================
# PAYPAL MANAGER
# ============================================================================

class PayPalManager:
    """Gestiona pagos y suscripciones vía PayPal"""

    PLANES_PAYPAL = {
        "basic": {"paypal_plan_id": "P-XXXXXXXXXXXXX1", "precio": 299},
        "pro": {"paypal_plan_id": "P-XXXXXXXXXXXXX2", "precio": 599},
        "enterprise": {"paypal_plan_id": "P-XXXXXXXXXXXXX3", "precio": 999},
    }

    @staticmethod
    async def obtener_access_token() -> str:
        """Obtiene token OAuth2 de PayPal"""

        auth = base64.b64encode(
            f"{PAYPAL_CLIENT_ID}:{PAYPAL_CLIENT_SECRET}".encode()
        ).decode()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{PAYPAL_BASE_URL}/v1/oauth2/token",
                headers={
                    "Authorization": f"Basic {auth}",
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                data={"grant_type": "client_credentials"}
            )

            if response.status_code != 200:
                raise Exception(f"Error obteniendo token PayPal: {response.text}")

            return response.json()["access_token"]

    @staticmethod
    async def crear_orden_pago_unico(plan: str, usuario_id: int) -> dict:
        """
        Crea una orden de pago ÚNICO (no recurrente).
        Útil si prefieres cobrar mes a mes manualmente en vez de suscripción automática.
        """

        if plan not in PayPalManager.PLANES_PAYPAL:
            raise ValueError("Plan no válido")

        token = await PayPalManager.obtener_access_token()
        precio = PayPalManager.PLANES_PAYPAL[plan]["precio"]

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{PAYPAL_BASE_URL}/v2/checkout/orders",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                },
                json={
                    "intent": "CAPTURE",
                    "purchase_units": [{
                        "reference_id": f"usuario_{usuario_id}_plan_{plan}",
                        "description": f"Suscripción {plan.upper()} - SaaS Predictivo",
                        "amount": {
                            "currency_code": "USD",
                            "value": str(precio)
                        }
                    }],
                    "application_context": {
                        "return_url": "https://ingenieroai.pro/pago-exitoso",
                        "cancel_url": "https://ingenieroai.pro/pago-cancelado",
                        "brand_name": "SaaS Predictivo de Conversión",
                        "user_action": "PAY_NOW"
                    }
                }
            )

            data = response.json()

            # Link de aprobación (a donde rediriges al cliente)
            approve_link = next(
                (link["href"] for link in data.get("links", []) if link["rel"] == "approve"),
                None
            )

            return {
                "order_id": data.get("id"),
                "approve_url": approve_link,
                "status": data.get("status")
            }

    @staticmethod
    async def crear_suscripcion_recurrente(plan: str, usuario_id: int) -> dict:
        """
        Crea suscripción RECURRENTE en PayPal.
        Requiere haber creado el "Product" y "Plan" en PayPal Dashboard primero.
        """

        if plan not in PayPalManager.PLANES_PAYPAL:
            raise ValueError("Plan no válido")

        token = await PayPalManager.obtener_access_token()
        paypal_plan_id = PayPalManager.PLANES_PAYPAL[plan]["paypal_plan_id"]

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{PAYPAL_BASE_URL}/v1/billing/subscriptions",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                },
                json={
                    "plan_id": paypal_plan_id,
                    "custom_id": f"usuario_{usuario_id}",
                    "application_context": {
                        "brand_name": "SaaS Predictivo de Conversión",
                        "return_url": "https://ingenieroai.pro/pago-exitoso",
                        "cancel_url": "https://ingenieroai.pro/pago-cancelado",
                        "user_action": "SUBSCRIBE_NOW"
                    }
                }
            )

            data = response.json()

            approve_link = next(
                (link["href"] for link in data.get("links", []) if link["rel"] == "approve"),
                None
            )

            return {
                "subscription_id": data.get("id"),
                "approve_url": approve_link,
                "status": data.get("status")
            }

    @staticmethod
    async def capturar_orden(order_id: str) -> dict:
        """Captura (confirma) el pago después de que el cliente aprobó en PayPal"""

        token = await PayPalManager.obtener_access_token()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{PAYPAL_BASE_URL}/v2/checkout/orders/{order_id}/capture",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }
            )

            return response.json()

    @staticmethod
    async def verificar_webhook(headers: dict, body: bytes, webhook_id: str) -> bool:
        """Verifica que el webhook realmente venga de PayPal (anti-fraude)"""

        token = await PayPalManager.obtener_access_token()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{PAYPAL_BASE_URL}/v1/notifications/verify-webhook-signature",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "auth_algo": headers.get("paypal-auth-algo"),
                    "cert_url": headers.get("paypal-cert-url"),
                    "transmission_id": headers.get("paypal-transmission-id"),
                    "transmission_sig": headers.get("paypal-transmission-sig"),
                    "transmission_time": headers.get("paypal-transmission-time"),
                    "webhook_id": webhook_id,
                    "webhook_event": body
                }
            )

            return response.json().get("verification_status") == "SUCCESS"


# ============================================================================
# TRANSFERENCIA BANCARIA MANAGER
# ============================================================================

class TransferenciaManager:
    """Gestiona pagos por transferencia bancaria (con verificación manual)"""

    @staticmethod
    def generar_instrucciones(plan: str, usuario_id: int, banco: str = "bam") -> dict:
        """Genera instrucciones de pago + referencia única para el cliente.
        banco: 'bam' o 'industrial'"""

        precios = {"basic": 199, "pro": 349, "enterprise": 599}  # en GTQ (Guatemala)
        monto = precios.get(plan, 199)
        referencia = f"SAAS-{usuario_id}-{datetime.utcnow().strftime('%Y%m%d%H%M')}"
        cuenta = CUENTAS_BANCARIAS.get(banco, CUENTAS_BANCARIAS["bam"])

        return {
            "referencia": referencia,
            "monto": monto,
            "moneda": "GTQ",
            "datos_bancarios": cuenta,
            "cuentas_disponibles": CUENTAS_BANCARIAS,
            "instrucciones": (
                f"1. Transfiere Q{monto} a la cuenta indicada ({cuenta['banco']})\n"
                f"2. Usa la referencia: {referencia}\n"
                f"3. Sube tu comprobante en el dashboard\n"
                f"4. Activamos tu cuenta en menos de 24 horas hábiles"
            )
        }

    @staticmethod
    def registrar_solicitud(
        usuario_id: int,
        plan: str,
        monto: float,
        referencia: str,
        comprobante_url: str,
        db: Session
    ) -> PagoManual:
        """El cliente sube su comprobante → queda 'pendiente' de verificación"""

        pago = PagoManual(
            usuario_id=usuario_id,
            plan=plan,
            monto=monto,
            metodo="transferencia",
            referencia=referencia,
            comprobante_url=comprobante_url,
            estado="pendiente"
        )

        db.add(pago)
        db.commit()
        db.refresh(pago)

        logger.info(f"📄 Nueva solicitud de transferencia: {referencia} (${monto})")

        return pago

    @staticmethod
    def verificar_pago(
        pago_id: int,
        aprobado: bool,
        notas: str,
        db: Session
    ) -> dict:
        """TÚ (admin) verificas manualmente el comprobante y activas la cuenta"""

        pago = db.query(PagoManual).filter(PagoManual.id == pago_id).first()

        if not pago:
            raise ValueError("Pago no encontrado")

        pago.estado = "verificado" if aprobado else "rechazado"
        pago.notas_admin = notas
        pago.fecha_verificacion = datetime.utcnow()
        db.commit()

        if aprobado:
            # Activar plan del usuario
            usuario = db.query(Usuario).filter(Usuario.id == pago.usuario_id).first()
            if usuario:
                usuario.plan = pago.plan
                usuario.fecha_proximo_pago = datetime.utcnow() + timedelta(days=30)
                usuario.activo = True
                db.commit()

                logger.info(f"✅ Plan {pago.plan} activado para usuario {usuario.email}")

        return {"pago_id": pago_id, "estado": pago.estado}


# NOTA: los endpoints de pagos y admin ya estan integrados y activos
# de verdad en main.py (no como comentario). Ver seccion
# 'PAGOS: PAYPAL + TRANSFERENCIA + ADMIN' al final de main.py.
