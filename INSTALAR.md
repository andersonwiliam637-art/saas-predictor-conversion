# ⚡ INICIO RÁPIDO — Lee esto primero

Este ZIP contiene tu SaaS Predictivo de Conversión completo: backend, frontend,
base de datos, integraciones de pago (PayPal + transferencia BAM/Banco
Industrial) y el componente para tu web ingenieroai.pro.

## 📁 Qué hay en cada carpeta

```
saas-predictor-conversion/
├── main.py                          → Backend FastAPI (el cerebro del sistema)
├── paypal_transferencia_integration.py → Pagos PayPal + transferencia
├── requirements.txt                 → Lista de paquetes Python a instalar
├── .env.example                     → Plantilla de credenciales (copiar a .env)
├── docker-compose.yml               → Levanta todo con un comando
├── Dockerfile                       → Receta para construir el backend
├── startup.sh                       → Script que instala y levanta todo solo
│
├── frontend/app.py                  → Dashboard (Streamlit)
├── scripts/
│   ├── init.sql                     → Estructura de la base de datos
│   ├── data_ingestion.py            → Sincroniza Shopify/MercadoLibre
│   └── cold_email_generator.py      → Generador de campañas de email
│
├── web-integracion/
│   └── componente-pago.html         → Botón de pago para pegar en ingenieroai.pro
│
└── docs/
    ├── DEPLOYMENT_GUIDE.md          → Cómo subirlo a internet (Railway/Render)
    ├── STRIPE_SETUP.md              → (Opcional, no aplica en Guatemala)
    ├── FAQ_LANDING.md               → Preguntas frecuentes para tu web
    └── IMPLEMENTATION_CHECKLIST.md  → Checklist de 7 días
```

## 🚀 Instalar en tu máquina — 2 caminos

### Camino A: Con Docker (recomendado, más fácil)

**Qué necesitas descargar antes:**
- Docker Desktop → https://www.docker.com/products/docker-desktop/
  (incluye Docker y Docker Compose juntos, para Windows/Mac/Linux)

**Pasos:**
```bash
# 1. Descomprime el ZIP y entra a la carpeta
cd saas-predictor-conversion

# 2. Copia el archivo de variables de entorno
cp .env.example .env

# 3. Ábrelo y llena tus datos reales (mínimo estos 3):
#    - SECRET_KEY (invéntate una clave larga y random)
#    - Tus datos bancarios (BANCO_NOMBRE, BANCO_CUENTA, etc.)
#    - PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET (si vas a usar PayPal)
nano .env      # o ábrelo con cualquier editor de texto

# 4. Levanta todo con un solo comando
chmod +x startup.sh
./startup.sh
```

Eso instala TODO automáticamente dentro de contenedores (no ensucia tu compu
con Python ni PostgreSQL instalados directo en tu sistema).

**Acceder:**
- Backend: http://localhost:8000
- Documentación API: http://localhost:8000/docs
- Dashboard: http://localhost:8501

---

### Camino B: Sin Docker (Python directo en tu máquina)

**Qué necesitas descargar antes:**
1. **Python 3.11+** → https://www.python.org/downloads/
   (al instalar, marca la casilla "Add Python to PATH")
2. **PostgreSQL 15** → https://www.postgresql.org/download/
   (anota el usuario/contraseña que configures durante la instalación)
3. **Git** (opcional, solo si vas a versionar el código) → https://git-scm.com/downloads

**Pasos:**
```bash
# 1. Entra a la carpeta del proyecto
cd saas-predictor-conversion

# 2. Crea un entorno virtual de Python (aísla los paquetes)
python -m venv venv

# 3. Actívalo
# En Windows:
venv\Scripts\activate
# En Mac/Linux:
source venv/bin/activate

# 4. Instala TODOS los paquetes necesarios (esto lee requirements.txt)
pip install -r requirements.txt

# 5. Copia y edita tus variables de entorno
cp .env.example .env
nano .env
# IMPORTANTE: cambia DATABASE_URL para que apunte a tu PostgreSQL local,
# ej: postgresql://postgres:tu_password@localhost:5432/saas_db

# 6. Crea la base de datos (una sola vez)
# Abre PostgreSQL (psql o pgAdmin) y corre:
#   CREATE DATABASE saas_db;
# Luego aplica el schema:
psql -U postgres -d saas_db -f scripts/init.sql

# 7. Levanta el backend
uvicorn main:app --reload --port 8000

# 8. En OTRA terminal, levanta el dashboard
cd frontend
streamlit run app.py
```

**Paquetes que se instalan automáticamente vía `pip install -r requirements.txt`
(no necesitas instalarlos uno por uno, esto es solo referencia):**
```
fastapi, uvicorn, sqlalchemy, psycopg2-binary, pydantic, pyjwt,
scikit-learn, numpy, pandas, streamlit, plotly, requests,
sendgrid, twilio, redis, python-dotenv, y más (ver requirements.txt)
```

---

## 💳 Configurar tus pagos (Guatemala)

Edita estas variables en tu `.env`:

```bash
# Tus cuentas bancarias reales
BANCO_TITULAR=Willy Enríquez Palacios
BANCO_CUENTA_BAM=tu_numero_de_cuenta_bam
BANCO_CUENTA_INDUSTRIAL=tu_numero_de_cuenta_industrial

# PayPal (crea una app gratis en developer.paypal.com)
PAYPAL_CLIENT_ID=tu_client_id
PAYPAL_CLIENT_SECRET=tu_client_secret
PAYPAL_MODE=live
```

Y en `web-integracion/componente-pago.html`, reemplaza:
- `TU_USUARIO_PAYPAL` → tu usuario real de paypal.me
- `0000000000` (BAM) → tu cuenta real de BAM
- `0000000000` (Industrial) → tu cuenta real de Banco Industrial

---

## 🌐 Pegar el botón de pago en tu web

Abre `web-integracion/componente-pago.html`, copia los 4 bloques marcados
(fuentes, sección, estilos, script) y pégalos en tu HTML de ingenieroai.pro
en las secciones correspondientes (`<head>`, cuerpo, `<style>`, antes de
`</body>`). Instrucciones detalladas dentro del mismo archivo, arriba.

---

## ☁️ Cuando quieras subirlo a internet (no solo tu máquina)

Ver `docs/DEPLOYMENT_GUIDE.md` — pasos para Railway o Render, ambos con
capa gratuita para empezar.

---

## 🆘 Problemas comunes

| Problema | Solución |
|---|---|
| "docker: command not found" | Instala Docker Desktop y reinicia tu máquina |
| "pip: command not found" | Verifica que Python se instaló con "Add to PATH" marcado |
| "could not connect to server" (PostgreSQL) | Verifica que PostgreSQL esté corriendo y el DATABASE_URL sea correcto |
| Puerto 8000 ocupado | Cierra otras apps o cambia el puerto en el comando uvicorn |
