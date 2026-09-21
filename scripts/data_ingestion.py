"""
Script de Ingesta de Datos - Shopify & MercadoLibre
Corre cada 1 hora para sincronizar eventos de tiendas
"""

import os
import httpx
import logging
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import json
from typing import List, Optional
import asyncio

# Config
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@db:5432/saas_db")
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY", "")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET", "")
MERCADOLIBRE_CLIENT_ID = os.getenv("MERCADOLIBRE_CLIENT_ID", "")
MERCADOLIBRE_CLIENT_SECRET = os.getenv("MERCADOLIBRE_CLIENT_SECRET", "")

# Database setup
from main import SessionLocal, Usuario, Evento, SyncHistory

# ============================================================================
# SHOPIFY CONNECTOR
# ============================================================================

class ShopifyConnector:
    """Conecta y obtiene datos de Shopify"""
    
    def __init__(self, tienda_url: str, token: str):
        self.tienda_url = tienda_url
        self.token = token
        self.base_url = f"https://{tienda_url}/admin/api/2024-01"
        self.headers = {
            "X-Shopify-Access-Token": token,
            "Content-Type": "application/json"
        }
    
    async def obtener_ordenes(self, desde: Optional[datetime] = None) -> List[dict]:
        """Obtiene órdenes de Shopify"""
        
        try:
            ordenes = []
            cursor = None
            limite_fecha = (desde or datetime.utcnow() - timedelta(days=7)).isoformat()
            
            async with httpx.AsyncClient() as client:
                while True:
                    query = {
                        "status": "any",
                        "created_at_min": limite_fecha,
                        "limit": 250
                    }
                    
                    if cursor:
                        query["cursor"] = cursor
                    
                    response = await client.get(
                        f"{self.base_url}/orders.json",
                        headers=self.headers,
                        params=query
                    )
                    
                    if response.status_code != 200:
                        logger.error(f"Error Shopify: {response.status_code}")
                        break
                    
                    data = response.json()
                    ordenes.extend(data.get("orders", []))
                    
                    # Pagination
                    links = response.headers.get("Link", "")
                    if "next" not in links:
                        break
                    
                    cursor = self._parse_cursor(links)
            
            logger.info(f"✅ Obtuvieron {len(ordenes)} órdenes de Shopify")
            return ordenes
        
        except Exception as e:
            logger.error(f"❌ Error obteniendo órdenes Shopify: {e}")
            return []
    
    async def obtener_carros_abandonados(self) -> List[dict]:
        """Obtiene carritos abandonados (checkouts incompletos)"""
        
        try:
            carros = []
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/checkouts.json",
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    # Filtrar completados
                    carros = [c for c in data.get("checkouts", []) if not c.get("completed_at")]
                    logger.info(f"✅ {len(carros)} carritos abandonados detectados")
            
            return carros
        
        except Exception as e:
            logger.error(f"❌ Error obteniendo carros: {e}")
            return []
    
    def _parse_cursor(self, links: str) -> Optional[str]:
        """Parsea cursor de header Link"""
        for link in links.split(","):
            if "next" in link:
                return link.split("cursor=")[1].split(">")[0]
        return None

# ============================================================================
# MERCADOLIBRE CONNECTOR
# ============================================================================

class MercadoLibreConnector:
    """Conecta y obtiene datos de MercadoLibre"""
    
    def __init__(self, user_id: str, access_token: str):
        self.user_id = user_id
        self.access_token = access_token
        self.base_url = "https://api.mercadolibre.com"
    
    async def obtener_ordenes(self, desde: Optional[datetime] = None) -> List[dict]:
        """Obtiene órdenes de MercadoLibre"""
        
        try:
            ordenes = []
            offset = 0
            limit = 100
            
            async with httpx.AsyncClient() as client:
                while True:
                    response = await client.get(
                        f"{self.base_url}/orders/search",
                        headers={"Authorization": f"Bearer {self.access_token}"},
                        params={
                            "seller": self.user_id,
                            "offset": offset,
                            "limit": limit,
                            "sort": "date_desc"
                        }
                    )
                    
                    if response.status_code != 200:
                        logger.error(f"Error MercadoLibre: {response.status_code}")
                        break
                    
                    data = response.json()
                    resultado = data.get("results", [])
                    
                    if not resultado:
                        break
                    
                    ordenes.extend(resultado)
                    offset += limit
            
            logger.info(f"✅ Obtuvieron {len(ordenes)} órdenes de MercadoLibre")
            return ordenes
        
        except Exception as e:
            logger.error(f"❌ Error obteniendo órdenes MercadoLibre: {e}")
            return []
    
    async def obtener_visitas(self) -> List[dict]:
        """Obtiene datos de visitas/interacciones"""
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/users/{self.user_id}/listing_visits",
                    headers={"Authorization": f"Bearer {self.access_token}"}
                )
                
                if response.status_code == 200:
                    return response.json()
            
            return []
        
        except Exception as e:
            logger.error(f"❌ Error obteniendo visitas: {e}")
            return []

# ============================================================================
# PROCESADOR DE EVENTOS
# ============================================================================

class EventoProcessor:
    """Procesa eventos de Shopify/MercadoLibre a nuestro formato"""
    
    @staticmethod
    def procesar_orden_shopify(order: dict, usuario_id: int, db) -> Evento:
        """Convierte orden Shopify a Evento"""
        
        tipo = "venta" if order.get("financial_status") == "paid" else "abandono"
        monto = float(order.get("total_price", 0))
        items = len(order.get("line_items", []))
        
        evento = Evento(
            usuario_id=usuario_id,
            cliente_id=order.get("customer", {}).get("id", order.get("email", "unknown")),
            tipo=tipo,
            monto=monto,
            items=items,
            timestamp=datetime.fromisoformat(order.get("created_at", "").replace("Z", "+00:00")),
            metadata={
                "shopify_order_id": order.get("id"),
                "customer_email": order.get("email"),
                "customer_name": order.get("customer", {}).get("first_name"),
                "payment_method": order.get("payment_gateway_names", []),
                "cart_token": order.get("cart_token")
            }
        )
        
        return evento
    
    @staticmethod
    def procesar_carrito_shopify(carrito: dict, usuario_id: int, db) -> Evento:
        """Convierte carrito abandonado a Evento"""
        
        monto = float(carrito.get("total_price", 0))
        items = len(carrito.get("line_items", []))
        
        evento = Evento(
            usuario_id=usuario_id,
            cliente_id=carrito.get("customer_id", carrito.get("email", "unknown")),
            tipo="abandono",
            monto=monto,
            items=items,
            timestamp=datetime.fromisoformat(carrito.get("updated_at", "").replace("Z", "+00:00")),
            metadata={
                "shopify_checkout_id": carrito.get("id"),
                "customer_email": carrito.get("email"),
                "abandoned_at": carrito.get("updated_at"),
                "checkout_url": carrito.get("abandoned_checkout_url")
            }
        )
        
        return evento
    
    @staticmethod
    def procesar_orden_mercadolibre(order: dict, usuario_id: int, db) -> Evento:
        """Convierte orden MercadoLibre a Evento"""
        
        tipo = "venta" if order.get("status") == "paid" else "abandono"
        monto = float(order.get("total_amount", 0))
        
        evento = Evento(
            usuario_id=usuario_id,
            cliente_id=str(order.get("buyer", {}).get("id", "unknown")),
            tipo=tipo,
            monto=monto,
            items=len(order.get("items", [])),
            timestamp=datetime.fromisoformat(order.get("date_created", "").replace("Z", "+00:00")),
            metadata={
                "mercadolibre_order_id": str(order.get("id")),
                "buyer_email": order.get("buyer", {}).get("email"),
                "status": order.get("status")
            }
        )
        
        return evento

# ============================================================================
# SYNC ORQUESTADOR
# ============================================================================

async def sincronizar_usuario(usuario: Usuario, db):
    """Sincroniza datos para un usuario específico"""
    
    logger.info(f"🔄 Sincronizando usuario {usuario.email}...")
    
    eventos_nuevos = 0
    
    try:
        # Shopify
        if usuario.shopify_token:
            logger.info(f"📦 Sincronizando Shopify...")
            shopify = ShopifyConnector(usuario.tienda_url, usuario.shopify_token)
            
            # Órdenes
            ordenes = await shopify.obtener_ordenes()
            for order in ordenes:
                try:
                    evento = EventoProcessor.procesar_orden_shopify(order, usuario.id, db)
                    
                    # Verificar si ya existe
                    existe = db.query(Evento).filter(
                        Evento.datos_extra.op('->')('shopify_order_id').astext == str(order.get("id")),
                        Evento.usuario_id == usuario.id
                    ).first()
                    
                    if not existe:
                        db.add(evento)
                        eventos_nuevos += 1
                except Exception as e:
                    logger.error(f"Error procesando orden: {e}")
            
            # Carritos abandonados
            carros = await shopify.obtener_carros_abandonados()
            for carrito in carros:
                try:
                    evento = EventoProcessor.procesar_carrito_shopify(carrito, usuario.id, db)
                    existe = db.query(Evento).filter(
                        Evento.datos_extra.op('->')('shopify_checkout_id').astext == str(carrito.get("id")),
                        Evento.usuario_id == usuario.id
                    ).first()
                    
                    if not existe:
                        db.add(evento)
                        eventos_nuevos += 1
                except Exception as e:
                    logger.error(f"Error procesando carrito: {e}")
        
        # MercadoLibre
        if usuario.mercadolibre_token:
            logger.info(f"🛒 Sincronizando MercadoLibre...")
            ml = MercadoLibreConnector(
                usuario.id,
                usuario.mercadolibre_token
            )
            
            ordenes = await ml.obtener_ordenes()
            for order in ordenes:
                try:
                    evento = EventoProcessor.procesar_orden_mercadolibre(order, usuario.id, db)
                    existe = db.query(Evento).filter(
                        Evento.datos_extra.op('->')('mercadolibre_order_id').astext == str(order.get("id")),
                        Evento.usuario_id == usuario.id
                    ).first()
                    
                    if not existe:
                        db.add(evento)
                        eventos_nuevos += 1
                except Exception as e:
                    logger.error(f"Error procesando orden ML: {e}")
        
        db.commit()
        
        # Log en sync_history
        sync_log = SyncHistory(
            usuario_id=usuario.id,
            plataforma="shopify_mercadolibre",
            tipo_sync="ordenes",
            eventos_procesados=len(ordenes) if ordenes else 0,
            eventos_nuevos=eventos_nuevos,
            fecha_inicio=datetime.utcnow(),
            fecha_fin=datetime.utcnow(),
            estado="success"
        )
        db.add(sync_log)
        db.commit()
        
        logger.info(f"✅ {usuario.email}: {eventos_nuevos} eventos nuevos")
        
    except Exception as e:
        logger.error(f"❌ Error sincronizando {usuario.email}: {e}")
        db.rollback()

async def sync_todos_usuarios():
    """Sincroniza todos los usuarios activos"""
    
    logger.info("🌍 Iniciando sincronización global...")
    
    db = SessionLocal()
    
    try:
        usuarios = db.query(Usuario).filter(Usuario.activo == True).all()
        logger.info(f"📊 {len(usuarios)} usuarios a sincronizar")
        
        for usuario in usuarios:
            await sincronizar_usuario(usuario, db)
        
        logger.info("✅ Sincronización completada")
    
    except Exception as e:
        logger.error(f"❌ Error en sincronización: {e}")
    
    finally:
        db.close()

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    asyncio.run(sync_todos_usuarios())
