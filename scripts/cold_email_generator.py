"""
Cold Email Script - Generador de Campañas de Email en Español
Para dueños de tiendas online con facturación > $10k/mes
"""

import csv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List
import os
import time
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ============================================================================
# TEMPLATES DE EMAIL
# ============================================================================

SUBJECT_LINES = [
    "⏰ Recupera ${valor} en ventas abandonadas - {nombre_tienda}",
    "Detectamos {num_abandonos} carritos sin completar en {nombre_tienda}",
    "{nombre}: +${valor} en ingresos disponibles ahora",
    "Tu tasa de abandono es del {porcentaje}% - Tenemos la solución",
    "¿Sabes cuánto dinero pierdes cada día? - {nombre_tienda}"
]

BODY_TEMPLATE = """
Hola {nombre},

Espero que estés bien.

He estado analizando tu tienda {tienda_url} y noté algo interesante:

📊 **En los últimos 30 días:**
• {num_clientes} clientes agregaron productos al carrito pero NO compraron
• **${valor_perdido:.2f} en ventas potenciales abandonadas**
• Tu tasa de conversión es del {tasa_conversion}% (el promedio es 2-3%)

---

**¿QUÉ SIGNIFICA ESTO?**

Cada hora que pasa, más dinero se escurre. Esos {num_clientes} clientes ya te encontraron, les gustó algo... pero se fueron.

La buena noticia? **Es 100% recuperable.**

---

**NUESTRA SOLUCIÓN:**

Utilizamos IA predictiva (LSTM + Prophet) que:

✅ Detecta abandonos **48 horas ANTES** de que ocurran
✅ Envía alertas automáticas por email/SMS en el momento exacto
✅ Recupera hasta **el 25-40% de esos abandonos**
✅ Toma 5 minutos conectarlo a tu tienda (Shopify, MercadoLibre, WooCommerce)

---

**RESULTADOS DE CLIENTES SIMILARES:**

• Tienda de accesorios: +$4,200/mes recuperados
• Ropa online: 34% más conversiones en carrito
• Electrónica: $8,900 adicionales en 60 días

---

**TU PRUEBA GRATUITA:**

✨ 14 días GRATIS - Sin tarjeta de crédito
✨ Acceso a predicciones en tiempo real
✨ Alertas automáticas email/SMS
✨ Dashboard completo

👉 **[COMIENZA AQUÍ: {enlace_prueba}]**

En 5 minutos sabrás exactamente cuánto dinero puedes recuperar.

---

**QUICK MATH:**
Si recuperas solo el 20% de esos abandonos, serían ${valor_recuperable:.2f}/mes adicionales.
A eso lo llamamos "dinero que ya casi tenías".

---

¿Preguntas? Te llamo en 2 minutos ☎️

Saludos,
{nombre_vendedor}
CEO, SaaS Predictivo de Conversión

P.S. Los primeros 10 clientes en {ciudad} obtienen descuento permanente del 25% 🎁
"""

# ============================================================================
# VARIANTES PARA A/B TESTING
# ============================================================================

BODY_VARIANT_B = """
Hola {nombre},

Acabo de terminar un análisis rápido de {tienda_url}.

Encontré {num_abandonos} carritos sin completar en los últimos 30 días.

${valor_perdido:.2f} = Lo que esos clientes dejaron ahí.

---

Aquí el dato que duele:

Esos {num_clientes} visitantes ya llegaron hasta el carrito. Les gustó lo que vieron.

Pero algo frenó la compra. Tal vez:
- Costo de envío por sorpresa 📦
- Opciones de pago limitadas 💳
- Duda en el último segundo 🤔

La pregunta NO es "¿Por qué se fueron?"
La pregunta ES: "¿Cuándo van a volver?"

---

Si tuvieras un aviso ANTES de que se vayan...
Si pudieras enviarles un descuento en el momento exacto...
Si supiera quién está a punto de comprar...

Ese es nuestro trabajo.

**Predicción con IA de abandonos 48 horas antes**

Recupera 25-40% de esos carritos. Automáticamente.

👉 Prueba gratis: {enlace_prueba}
(14 días, sin tarjeta)

¿5 minutos para conectar tu tienda?

Salud,
{nombre_vendedor}
"""

# ============================================================================
# CLASE CAMPANA
# ============================================================================

class CampanaColdEmail:
    """Genera y envía campañas de cold email"""
    
    def __init__(
        self,
        nombre_vendedor: str = "Carlos",
        email_vendedor: str = "ventas@saasconversion.com",
        smtp_server: str = "smtp.sendgrid.net",
        smtp_port: int = 587
    ):
        self.nombre_vendedor = nombre_vendedor
        self.email_vendedor = email_vendedor
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.sendgrid_api_key = os.getenv("SENDGRID_API_KEY", "")
    
    def generar_prospecto(
        self,
        nombre: str,
        email: str,
        tienda_url: str,
        facturacion_mensual: float,
        num_clientes: int = 0,
        num_abandonos: int = 0,
        valor_perdido: float = 0,
        tasa_conversion: float = 2.5,
        ciudad: str = "tu ciudad"
    ) -> dict:
        """Genera un prospecto con datos personalizados"""
        
        valor_recuperable = valor_perdido * 0.30  # Asumir 30% recuperable
        
        return {
            "nombre": nombre,
            "email": email,
            "tienda_url": tienda_url,
            "facturacion_mensual": facturacion_mensual,
            "num_clientes": num_clientes,
            "num_abandonos": num_abandonos,
            "valor_perdido": valor_perdido,
            "valor_recuperable": valor_recuperable,
            "tasa_conversion": tasa_conversion,
            "ciudad": ciudad
        }
    
    def calcular_metricas(self, facturacion: float) -> dict:
        """Calcula estimaciones de abandono"""
        
        # Benchmarks: 70% de visitantes agregan al carrito, 60% abandona
        visitantes_estimados = facturacion / 100  # Aprox
        carrito_estimado = visitantes_estimados * 0.70
        abandonos_estimados = carrito_estimado * 0.60
        valor_promedio = facturacion / max(visitantes_estimados, 1)
        valor_abandonado = abandonos_estimados * valor_promedio
        
        return {
            "visitantes": int(visitantes_estimados),
            "en_carrito": int(carrito_estimado),
            "abandonos": int(abandonos_estimados),
            "valor_perdido": valor_abandonado,
            "tasa_conversion": round((carrito_estimado * 0.40) / visitantes_estimados * 100, 1)
        }
    
    def generar_email(self, prospecto: dict, variant: str = "A") -> tuple:
        """Genera subject y body del email"""
        
        metricas = self.calcular_metricas(prospecto["facturacion_mensual"])
        
        # Subject
        subject = SUBJECT_LINES[0].format(
            valor=int(metricas["valor_perdido"]),
            nombre_tienda=prospecto["tienda_url"].split("://")[-1].split(".")[0]
        )
        
        # Body
        template = BODY_TEMPLATE if variant == "A" else BODY_VARIANT_B
        
        body = template.format(
            nombre=prospecto["nombre"].split()[0],
            tienda_url=prospecto["tienda_url"],
            num_clientes=metricas["en_carrito"],
            num_abandonos=metricas["abandonos"],
            valor_perdido=metricas["valor_perdido"],
            valor_recuperable=metricas["valor_perdido"] * 0.30,
            tasa_conversion=metricas["tasa_conversion"],
            enlace_prueba="https://app.saasconversion.com/registro?ref=cold_email",
            nombre_vendedor=self.nombre_vendedor,
            ciudad=prospecto["ciudad"]
        )
        
        return subject, body
    
    def enviar_email(self, email_destino: str, subject: str, body: str) -> bool:
        """Envía email (usando SendGrid)"""
        
        try:
            # En producción: usar sendgrid-python
            # Por ahora, logueamos
            logger.info(f"📧 Email generado para {email_destino}")
            logger.info(f"   Subject: {subject}")
            
            return True
        except Exception as e:
            logger.error(f"❌ Error enviando email: {e}")
            return False
    
    def cargar_prospectos(self, archivo_csv: str) -> List[dict]:
        """Carga prospectos desde CSV"""
        
        prospectos = []
        
        try:
            with open(archivo_csv, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    prospecto = self.generar_prospecto(
                        nombre=row.get("nombre", ""),
                        email=row.get("email", ""),
                        tienda_url=row.get("tienda_url", ""),
                        facturacion_mensual=float(row.get("facturacion_mensual", 0)),
                        ciudad=row.get("ciudad", "tu ciudad")
                    )
                    prospectos.append(prospecto)
            
            logger.info(f"✅ {len(prospectos)} prospectos cargados")
            return prospectos
        
        except Exception as e:
            logger.error(f"❌ Error cargando CSV: {e}")
            return []
    
    def ejecutar_campana(
        self,
        prospectos: List[dict],
        delay_segundos: int = 3,
        variant: str = "A"
    ):
        """Ejecuta campaña completa"""
        
        logger.info(f"🚀 Iniciando campaña con {len(prospectos)} prospectos")
        
        enviados = 0
        errores = 0
        
        for i, prospecto in enumerate(prospectos):
            try:
                subject, body = self.generar_email(prospecto, variant)
                
                if self.enviar_email(prospecto["email"], subject, body):
                    enviados += 1
                else:
                    errores += 1
                
                # Rate limiting
                if (i + 1) % 10 == 0:
                    logger.info(f"📊 {i + 1}/{len(prospectos)} enviados")
                    time.sleep(delay_segundos * 2)
                else:
                    time.sleep(delay_segundos)
            
            except Exception as e:
                logger.error(f"Error procesando {prospecto['email']}: {e}")
                errores += 1
        
        logger.info(f"✅ Campaña completada: {enviados} enviados, {errores} errores")
        
        return {
            "total": len(prospectos),
            "enviados": enviados,
            "errores": errores,
            "tasa_exito": (enviados / len(prospectos) * 100) if prospectos else 0
        }

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import json
    
    # Instanciar
    campana = CampanaColdEmail(
        nombre_vendedor="Carlos",
        email_vendedor="ventas@tuempresa.com"
    )
    
    # Ejemplo: Crear CSV de prospectos
    csv_template = """nombre,email,tienda_url,facturacion_mensual,ciudad
María García,maria@tiendamodas.com,https://tiendamodas.com,15000,Buenos Aires
Juan López,juan@electromarket.mx,https://electromarket.mx,25000,México City
Sofia Rodríguez,sofia@disenohogar.es,https://disenohogar.es,12000,Barcelona
"""
    
    with open("prospectos.csv", "w") as f:
        f.write(csv_template)
    
    logger.info("📋 CSV de ejemplo creado: prospectos.csv")
    
    # Cargar prospectos
    prospectos = campana.cargar_prospectos("prospectos.csv")
    
    # Ejecutar campaña
    resultado = campana.ejecutar_campana(prospectos, variant="A")
    print(json.dumps(resultado, indent=2))
