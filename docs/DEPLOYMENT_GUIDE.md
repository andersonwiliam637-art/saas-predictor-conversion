# 🚀 Guía de Deployment: Railway vs Render (30 minutos)

> Elige UNO de estos. Railway es más rápido, Render es más barato para empezar.

---

## OPCIÓN A: RAILWAY (Recomendado - 15 minutos)

### Paso 1: Preparar repositorio

```bash
# 1. Ir a carpeta del proyecto
cd saas-predictor

# 2. Inicializar Git
git init
git add .
git commit -m "Initial commit"

# 3. Crear repo en GitHub
# → Ir a github.com/new
# → Nombre: saas-predictor
# → Copiar URL

# 4. Push a GitHub
git remote add origin https://github.com/TU_USUARIO/saas-predictor.git
git branch -M main
git push -u origin main
```

### Paso 2: Conectar Railway

1. Ir a **https://railway.app**
2. Click en **"Start a new project"** o Sign in con GitHub
3. Seleccionar **"Deploy from GitHub"**
4. Autorizar GitHub
5. Seleccionar repo `saas-predictor`
6. Click **Deploy**

### Paso 3: Configurar variables de entorno

En Railway Dashboard:
1. Click en tu proyecto
2. **Variables** (pestaña)
3. Agregar cada variable de `.env.example`:

```
DATABASE_URL=postgresql://...  # Railway crea automáticamente
SECRET_KEY=tu_secret_key_super_largo_aqui
SENDGRID_API_KEY=SG.....
TWILIO_ACCOUNT_SID=...
STRIPE_SECRET_KEY=sk_live_...
```

### Paso 4: Base de datos

Railway → **+ Add** → Buscar **PostgreSQL**:
1. Click **PostgreSQL**
2. Esperar a que se despliegue
3. Click en PostgreSQL
4. **Variables** → Copiar `DATABASE_URL`
5. Pegar en tu app

El esquema (init.sql) se aplica automáticamente ✅

### Paso 5: Verificar deployment

Railway Dashboard → tu app:
- Si ves **"✅ Build succeeded"** y la URL funciona → ¡LISTO!
- Si ves "❌" → Click en **Logs** para debugging

**URL será:** `https://saas-predictor-production.up.railway.app`

### Paso 6: Agregar dominios personalizados

1. Railway → **Settings** → **Domains**
2. **+ Add Domain**
3. Ingresar: `api.tudominio.com`
4. Esperar confirmación DNS (20 min)

---

## OPCIÓN B: RENDER (Más barato para POC)

### Paso 1: Preparar repo igual que Railway

```bash
git init
git add .
git commit -m "Initial"
git push -u origin main
```

### Paso 2: Crear Web Service

1. Ir a **https://render.com**
2. Click **+ New** → **Web Service**
3. Conectar GitHub → Seleccionar repo
4. Nombre: `saas-predictor-api`
5. **Build Command:**
   ```
   pip install -r requirements.txt
   ```
6. **Start Command:**
   ```
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```
7. Plan: **Free** (para empezar)
8. Click **Create Web Service**

### Paso 3: Agregar PostgreSQL

1. Render Dashboard → **+ New** → **PostgreSQL**
2. Nombre: `saas-predictor-db`
3. Plan: **Free** ($7/mes)
4. Crear
5. Copiar **Internal Database URL**

### Paso 4: Variables de entorno

Render → tu app (saas-predictor-api) → **Environment**:

```
DATABASE_URL=postgres://...  # Del paso anterior
SECRET_KEY=...
SENDGRID_API_KEY=...
# etc
```

Click **Save**

### Paso 5: Esperar deploy

Render tarda ~5 min. Verás status en **Events**.

**URL será:** `https://saas-predictor-api.onrender.com`

---

## Configuración Común (Railway + Render)

### Opción 1: Usar base de datos existente

Si tienes PostgreSQL en otro lugar:

```
DATABASE_URL=postgresql://usuario:contraseña@host:5432/nombre_db
```

### Opción 2: Aplicar schema

Después del primer deploy:

```bash
# Local (con DB conectada)
python -c "
from sqlalchemy import create_engine
import os
from main import Base

engine = create_engine(os.getenv('DATABASE_URL'))
Base.metadata.create_all(engine)
"
```

O ejecutar SQL manualmente en pgAdmin.

### Opción 3: Webhook de Stripe

En Stripe Dashboard → Developers → Webhooks:

**Endpoint URL:**
```
https://saas-predictor-production.up.railway.app/api/webhooks/stripe
```

(Reemplazar con tu URL real)

---

## Dominio Personalizado

### Railway:

Settings → Domains → Add Domain → `api.tudominio.com`

### Render:

Settings → Custom Domains → Add Custom Domain

Luego configurar en tu registrador de dominios:
```
CNAME api.tudominio.com → onrender.com
```

---

## Frontend Streamlit

### Option 1: Deploy en mismo Railway/Render

1. Crear `streamlit_app.py` en raíz
2. Crear `runtime.txt`:
   ```
   python-3.11
   ```
3. Crear `.streamlit/config.toml`:
   ```toml
   [server]
   headless = true
   port = 8501
   
   [browser]
   gatherUsageStats = false
   ```
4. Deploy igual que backend

**URL será:** `https://saas-predictor-streamlit.up.railway.app`

### Option 2: Deploy en Streamlit Cloud (Gratis)

1. Copiar `frontend/app.py` a repo público
2. Ir a **https://streamlit.io/cloud**
3. **New app** → Conectar GitHub
4. Seleccionar repo y archivo: `frontend/app.py`
5. Deploy automático

---

## Monitoreo en Producción

### Railway

Dashboard → tu app → **Monitoring**:
- CPU/Memory usage
- Request logs
- Error tracking

### Render

Dashboard → tu app → **Logs** y **Metrics**

### Alertas de Error (Sentry)

```bash
# 1. Crear cuenta en sentry.io
# 2. Crear proyecto Python
# 3. Copiar DSN

# 3. Agregar variable:
SENTRY_DSN=https://...@sentry.io/...

# 4. En main.py:
import sentry_sdk
sentry_sdk.init(os.getenv("SENTRY_DSN"))
```

---

## Actualizar Código (Después del primer deploy)

### Con Git:
```bash
git add .
git commit -m "Update features"
git push origin main
```

→ Railway/Render detectan cambios y redeploy automático

### Manual (Render):
Render → Repo → **Manual Deploy** → **Deploy latest commit**

---

## Troubleshooting

### "Build failed"
```
Ver en Logs exactamente qué falló
- Verificar requirements.txt
- Verificar variables de entorno
```

### "App crashes"
```
Logs → Ver línea del error
- DATABASE_URL incorrecto?
- Dependencias faltando?
- Puerto incorrecto?
```

### "502 Bad Gateway"
```
Probablemente:
1. App no está escuchando en puerto 8000
2. Demora al iniciar (agregar healthcheck)
```

### "Can't connect to database"
```
1. DATABASE_URL correcta?
2. PostgreSQL encendido?
3. Firewall bloqueando?
```

---

## 📋 Checklist Deployment

- [ ] Repo en GitHub con código
- [ ] `.env` NO committeado (.gitignore)
- [ ] `requirements.txt` actualizado
- [ ] Dockerfile presente
- [ ] `docker-compose.yml` presente
- [ ] Conectado a Railway O Render
- [ ] PostgreSQL creado
- [ ] Variables de entorno seteadas
- [ ] Primera build exitosa
- [ ] Puedo acceder a `/health`
- [ ] Base de datos schema aplicado
- [ ] Stripe webhooks apuntando a prod

---

## Cost Estimates (2024)

### Railway:
- **Free tier:** Primeros $5/mes gratis
- API: ~$0.03/hora = ~$22/mes (en uso)
- DB: Incluida en free tier
- Total: ~$22/mes cuando crece

### Render:
- **Free tier:** App (¡gratis!) pero duerme después de 15min
- **Starter plan:** $7/mes (app + DB)
- Total: $7/mes para pequeño

---

## Escalado Futuro

Cuando necesites más performance:

### Railway
```
1. Dashboard → Settings → Scaling
2. Aumentar RAM/CPU
3. Aumentar réplicas
```

### Render
```
1. Upgrade plan de Free → Pro
2. Automático scaling
```

---

¡**Listo para producción!** 🎉

Próximo paso: Configurar dominio personalizado + SSL (automático en ambos)
