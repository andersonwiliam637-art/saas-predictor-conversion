# 💳 Guía Completa: Integración Stripe en 15 Minutos

## Fase 1: Obtener Credenciales Stripe (2 min)

### 1.1 Crear Cuenta
1. Ir a https://stripe.com
2. Click en **"Start now"** o **"Registrarse"**
3. Usar email de la empresa (ej: ventas@tuempresa.com)
4. Verificar email

### 1.2 Obtener API Keys
1. Dashboard Stripe → **Developers** (esquina superior)
2. Click en **API Keys**
3. Verás dos versiones:
   - **Test Mode** (desarrollo) ← COPIA ESTO AHORA
   - **Live Mode** (producción) ← DESPUÉS

#### Test Mode - COPIA EN .env:
```
STRIPE_SECRET_KEY=sk_test_51234567890abcdefghij...
STRIPE_PUBLISHABLE_KEY=pk_test_51234567890abcdefghij...
```

### 1.3 Crear Webhooks

1. En **Developers** → **Webhooks**
2. Click **Add endpoint**
3. URL: `https://tudominio.com/api/webhooks/stripe`
   - En local: usa ngrok: `https://random.ngrok.io/api/webhooks/stripe`
4. Selecciona eventos:
   - `charge.succeeded`
   - `charge.failed`
   - `invoice.payment_succeeded`
   - `invoice.payment_failed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
5. Click **Add endpoint**
6. En el webhook creado, click en él
7. Abajo: **Signing secret** → COPIA EN .env:
   ```
   STRIPE_WEBHOOK_SECRET=whsec_1234567890...
   ```

---

## Fase 2: Código Backend (5 min)

### 2.1 Instalar librería
```bash
pip install stripe==7.4.0
```

### 2.2 Crear archivo `stripe_integration.py`

```python
"""
Integración Stripe - Pagos recurrentes
"""

import stripe
import os
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from main import Usuario, Suscripcion

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

class StripeManager:
    """Gestiona pagos y suscripciones en Stripe"""
    
    PLANES = {
        "basic": {
            "stripe_id": "price_1234567890",  # Crear en Stripe primero
            "nombre": "Básico",
            "precio": 29900,  # En centavos
            "moneda": "usd",
            "intervalo": "month"
        },
        "pro": {
            "stripe_id": "price_0987654321",
            "nombre": "Profesional",
            "precio": 59900,
            "moneda": "usd",
            "intervalo": "month"
        },
        "enterprise": {
            "stripe_id": "price_abcdefghijk",
            "nombre": "Empresarial",
            "precio": 99900,
            "moneda": "usd",
            "intervalo": "month"
        }
    }
    
    @staticmethod
    def crear_cliente(usuario: Usuario, db: Session) -> str:
        """Crea cliente en Stripe y guarda customer_id"""
        
        if usuario.stripe_customer_id:
            return usuario.stripe_customer_id
        
        try:
            customer = stripe.Customer.create(
                email=usuario.email,
                name=usuario.nombre,
                metadata={
                    "usuario_id": usuario.id,
                    "tienda_url": usuario.tienda_url
                }
            )
            
            usuario.stripe_customer_id = customer.id
            db.commit()
            
            return customer.id
        except stripe.error.StripeError as e:
            raise Exception(f"Error creando cliente Stripe: {e}")
    
    @staticmethod
    def crear_suscripcion(
        usuario: Usuario,
        plan: str,
        db: Session
    ) -> dict:
        """Crea suscripción recurrente"""
        
        if plan not in StripeManager.PLANES:
            raise ValueError("Plan no válido")
        
        try:
            # Asegurar que existe customer
            customer_id = StripeManager.crear_cliente(usuario, db)
            
            # Crear suscripción
            subscription = stripe.Subscription.create(
                customer=customer_id,
                items=[{
                    "price": StripeManager.PLANES[plan]["stripe_id"],
                }],
                payment_behavior="default_incomplete",
                expand=["latest_invoice.payment_intent"],
                metadata={
                    "usuario_id": usuario.id
                }
            )
            
            # Guardar en BD
            suscripcion = Suscripcion(
                usuario_id=usuario.id,
                stripe_subscription_id=subscription.id,
                stripe_customer_id=customer_id,
                plan=plan,
                monto_mensual=StripeManager.PLANES[plan]["precio"] / 100,
                estado="active",
                fecha_inicio=datetime.utcnow(),
                fecha_proximo_pago=datetime.utcnow() + timedelta(days=30)
            )
            
            db.add(suscripcion)
            db.commit()
            
            return {
                "subscription_id": subscription.id,
                "client_secret": subscription.latest_invoice.payment_intent.client_secret,
                "status": subscription.status
            }
        
        except stripe.error.StripeError as e:
            raise Exception(f"Error creando suscripción: {e}")
    
    @staticmethod
    def procesar_webhook(event: dict, db: Session) -> bool:
        """Procesa webhooks de Stripe"""
        
        tipo = event["type"]
        data = event["data"]["object"]
        
        try:
            if tipo == "invoice.payment_succeeded":
                # Pago exitoso - renovar suscripción
                subscription_id = data.get("subscription")
                suscripcion = db.query(Suscripcion).filter(
                    Suscripcion.stripe_subscription_id == subscription_id
                ).first()
                
                if suscripcion:
                    suscripcion.estado = "active"
                    suscripcion.fecha_proximo_pago = datetime.utcnow() + timedelta(days=30)
                    suscripcion.intentos_pago_fallidos = 0
                    db.commit()
            
            elif tipo == "invoice.payment_failed":
                # Pago fallido - alertar
                subscription_id = data.get("subscription")
                suscripcion = db.query(Suscripcion).filter(
                    Suscripcion.stripe_subscription_id == subscription_id
                ).first()
                
                if suscripcion:
                    suscripcion.intentos_pago_fallidos += 1
                    suscripcion.estado = "past_due"
                    
                    if suscripcion.intentos_pago_fallidos >= 3:
                        suscripcion.estado = "canceled"
                    
                    db.commit()
            
            elif tipo == "customer.subscription.deleted":
                # Cancelación - actualizar
                subscription_id = data.get("id")
                suscripcion = db.query(Suscripcion).filter(
                    Suscripcion.stripe_subscription_id == subscription_id
                ).first()
                
                if suscripcion:
                    suscripcion.estado = "canceled"
                    suscripcion.fecha_cancelacion = datetime.utcnow()
                    db.commit()
            
            return True
        
        except Exception as e:
            print(f"Error procesando webhook: {e}")
            return False
    
    @staticmethod
    def cancelar_suscripcion(subscription_id: str, db: Session) -> bool:
        """Cancela suscripción"""
        
        try:
            stripe.Subscription.delete(subscription_id)
            
            suscripcion = db.query(Suscripcion).filter(
                Suscripcion.stripe_subscription_id == subscription_id
            ).first()
            
            if suscripcion:
                suscripcion.estado = "canceled"
                suscripcion.fecha_cancelacion = datetime.utcnow()
                db.commit()
            
            return True
        
        except stripe.error.StripeError as e:
            print(f"Error cancelando: {e}")
            return False

```

### 2.3 Agregar endpoint en `main.py`

```python
from fastapi import Request
from stripe_integration import StripeManager
import stripe

@app.post("/api/webhooks/stripe")
async def webhook_stripe(request: Request, db: Session = Depends(get_db)):
    """Webhook de Stripe"""
    
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            os.getenv("STRIPE_WEBHOOK_SECRET")
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    # Procesar
    StripeManager.procesar_webhook(event, db)
    
    return {"status": "received"}

@app.post("/api/suscripcion/crear-pago")
def crear_pago_suscripcion(
    plan: str,
    authorization: str = None,
    db: Session = Depends(get_db)
):
    """Crea sesión de pago"""
    
    usuario = get_current_user(authorization, db)
    
    try:
        resultado = StripeManager.crear_suscripcion(usuario, plan, db)
        
        return {
            "subscription_id": resultado["subscription_id"],
            "client_secret": resultado["client_secret"],
            "url_pago": f"https://tudominio.com/checkout?secret={resultado['client_secret']}"
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
```

---

## Fase 3: Crear Productos en Stripe (3 min)

1. Dashboard Stripe → **Products**
2. Click **+ Add product**

### Para cada plan:

**BÁSICO:**
- Nombre: "SaaS Predictivo - Plan Básico"
- Descripción: "Hasta 100 eventos/mes, Alertas email"
- Precio: $299/mes
- Tipo de facturación: **Recurring**
- Intervalo: **Monthly**
- Click **Save product**

(Repetir para PRO $599 y ENTERPRISE $999)

---

## Fase 4: Frontend - Botón de Pago (3 min)

### React/JavaScript:

```javascript
import { loadStripe } from "@stripe/js";

const stripePubKey = process.env.REACT_APP_STRIPE_PUBLISHABLE_KEY;

async function handleUpgrade(plan) {
  const response = await fetch("/api/suscripcion/crear-pago", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`
    },
    body: JSON.stringify({ plan })
  });
  
  const { client_secret } = await response.json();
  
  const stripe = await loadStripe(stripePubKey);
  
  stripe.confirmCardPayment(client_secret, {
    payment_method: {
      card: cardElement
    }
  });
}
```

### HTML simple:

```html
<button onclick="handleUpgrade('pro')">Upgrade a Pro - $599/mes</button>
```

---

## Fase 5: Test en Local (2 min)

### Usar ngrok para webhooks:

```bash
# Terminal 1
ngrok http 8000

# Terminal 2
# En .env:
STRIPE_WEBHOOK_SECRET=whsec_test_...
STRIPE_SECRET_KEY=sk_test_...

# Correr app
python main.py
```

### Números de prueba Stripe:

| Resultado | Tarjeta | CVC | Fecha |
|-----------|---------|-----|--------|
| ✅ Exitoso | 4242 4242 4242 4242 | 123 | 12/25 |
| ❌ Fallido | 4000 0000 0000 0002 | 123 | 12/25 |

---

## Fase 6: Pasar a LIVE (1 min)

### Cuando estés listo para producción:

1. Stripe Dashboard → cambiar a **Live Mode**
2. Copiar Live API Keys
3. Actualizar .env en producción:
   ```
   STRIPE_SECRET_KEY=sk_live_...
   STRIPE_PUBLISHABLE_KEY=pk_live_...
   ```
4. Actualizar webhook URL a dominio real
5. **Restart app**

---

## 📋 Checklist Final

- [ ] Cuenta Stripe creada
- [ ] API Keys copiadas en .env
- [ ] Productos creados (Básico, Pro, Enterprise)
- [ ] Webhook configurado
- [ ] Código backend integrado
- [ ] Endpoint POST /api/suscripcion/crear-pago creado
- [ ] Endpoint POST /api/webhooks/stripe creado
- [ ] Test con tarjeta 4242 4242 4242 4242
- [ ] Variables de BD (stripe_customer_id) creadas
- [ ] Emails de confirmación configurados

---

## 🚨 Troubleshooting

**"Invalid signature error"**
→ Verifica que STRIPE_WEBHOOK_SECRET sea correcto

**"No such price"**
→ Usa los price_ids correctos de tus productos

**Webhook no se dispara**
→ Usa ngrok en local, verifica que URL sea accesible

**Cliente no se crea**
→ Verifica que email sea único y válido
