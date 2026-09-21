#!/bin/bash

# ============================================================================
# SaaS Predictivo - Script de Inicio Rápido
# ============================================================================

set -e

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     🚀 SaaS Predictivo de Conversión - Quick Start           ║"
echo "║     Detecta abandonos de carrito con IA                      ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ============================================================================
# PASO 1: Verificar dependencias
# ============================================================================

echo "📋 PASO 1: Verificando dependencias..."
echo ""

if ! command -v docker &> /dev/null; then
    echo "❌ Docker no encontrado. Instala desde: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose no encontrado. Instala desde: https://docs.docker.com/compose/install/"
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo "⚠️  Python3 no encontrado. Es recomendado para desarrollo local."
else
    PYTHON_VERSION=$(python3 --version | awk '{print $2}')
    echo "✅ Python $PYTHON_VERSION encontrado"
fi

echo "✅ Docker detectado"
echo "✅ Docker Compose detectado"
echo ""

# ============================================================================
# PASO 2: Crear .env si no existe
# ============================================================================

echo "⚙️  PASO 2: Configurando variables de entorno..."
echo ""

if [ -f .env ]; then
    echo "✅ Archivo .env ya existe"
else
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "✅ Archivo .env creado desde .env.example"
        echo ""
        echo "⚠️  IMPORTANTE: Edita .env con tus credenciales:"
        echo "   nano .env"
        echo ""
        echo "   Variables críticas:"
        echo "   - SENDGRID_API_KEY (para emails)"
        echo "   - TWILIO_ACCOUNT_SID (para SMS)"
        echo "   - STRIPE_SECRET_KEY (para pagos)"
        echo "   - SHOPIFY_API_KEY (para Shopify)"
        echo ""
        read -p "¿Continuamos? (s/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Ss]$ ]]; then
            echo "⚠️  Recuerda editar .env y correr de nuevo: ./startup.sh"
            exit 1
        fi
    else
        echo "❌ .env.example no encontrado"
        exit 1
    fi
fi

echo ""

# ============================================================================
# PASO 3: Verificar Docker daemon
# ============================================================================

echo "🐳 PASO 3: Verificando Docker daemon..."
echo ""

if ! docker ps &> /dev/null; then
    echo "❌ Docker daemon no está corriendo"
    echo "   Inicia Docker y vuelve a intentar"
    exit 1
fi

echo "✅ Docker daemon activo"
echo ""

# ============================================================================
# PASO 4: Levantar servicios
# ============================================================================

echo "🚀 PASO 4: Levantando servicios con Docker Compose..."
echo ""

docker-compose down 2>/dev/null || true

echo "📦 Construyendo imágenes..."
docker-compose build --no-cache 2>&1 | grep -E "Successfully|Building" || true

echo ""
echo "⏳ Iniciando servicios..."
docker-compose up -d

echo ""
echo "⏳ Esperando a que los servicios se inicien completamente..."
sleep 10

# ============================================================================
# PASO 5: Verificar que todos estén listos
# ============================================================================

echo ""
echo "🔍 PASO 5: Verificando servicios..."
echo ""

HEALTH_CHECK_RETRIES=10
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $HEALTH_CHECK_RETRIES ]; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "✅ Backend (FastAPI) en http://localhost:8000"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "⏳ Esperando backend... ($RETRY_COUNT/$HEALTH_CHECK_RETRIES)"
    sleep 2
done

if [ $RETRY_COUNT -eq $HEALTH_CHECK_RETRIES ]; then
    echo "❌ Backend no responde"
    echo "   Ver logs: docker-compose logs backend"
    exit 1
fi

sleep 2

if docker-compose ps | grep -q "frontend"; then
    echo "✅ Frontend (Streamlit) en http://localhost:8501"
fi

if docker-compose ps | grep -q "db.*healthy"; then
    echo "✅ Database (PostgreSQL) en localhost:5432"
elif docker-compose ps | grep -q "db"; then
    echo "⏳ Database iniciando..."
    sleep 5
    echo "✅ Database (PostgreSQL) en localhost:5432"
fi

if docker-compose ps | grep -q "redis"; then
    echo "✅ Cache (Redis) en localhost:6379"
fi

echo ""

# ============================================================================
# PASO 6: Mostrar URLs de acceso
# ============================================================================

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     ✅ TODO LISTO - Accede a tu SaaS                        ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║                                                              ║"
echo "║  🔵 Backend API (FastAPI):                                  ║"
echo "║     http://localhost:8000                                   ║"
echo "║     Documentación: http://localhost:8000/docs               ║"
echo "║                                                              ║"
echo "║  🔴 Frontend Dashboard (Streamlit):                         ║"
echo "║     http://localhost:8501                                   ║"
echo "║                                                              ║"
echo "║  📊 Base de Datos (PostgreSQL):                             ║"
echo "║     localhost:5432                                          ║"
echo "║     Usuario: saas_user                                      ║"
echo "║     Base: saas_db                                           ║"
echo "║                                                              ║"
echo "║  🔧 Health Check:                                           ║"
echo "║     curl http://localhost:8000/health                       ║"
echo "║                                                              ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Primeros Pasos:                                            ║"
echo "║                                                              ║"
echo "║  1. 📝 Ver logs:                                            ║"
echo "║     docker-compose logs -f backend                          ║"
echo "║                                                              ║"
echo "║  2. 🧪 Registrarse:                                         ║"
echo "║     curl -X POST http://localhost:8000/api/auth/registro \\ ║"
echo "║       -H \"Content-Type: application/json\" \\                ║"
echo "║       -d '{\"email\":\"test@test.com\",                     ║"
echo "║            \"nombre\":\"Test\",                             ║"
echo "║            \"password\":\"pass123\",                        ║"
echo "║            \"tienda_url\":\"https://test.com\"}'            ║"
echo "║                                                              ║"
echo "║  3. 🌐 Abrir Dashboard:                                     ║"
echo "║     http://localhost:8501                                   ║"
echo "║                                                              ║"
echo "║  4. 🛑 Detener todo:                                        ║"
echo "║     docker-compose down                                     ║"
echo "║                                                              ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Documentación:                                             ║"
echo "║                                                              ║"
echo "║  📚 README.md          - Overview del proyecto              ║"
echo "║  💳 STRIPE_SETUP.md    - Setup de pagos                    ║"
echo "║  🚀 DEPLOYMENT_GUIDE.md - Deploy a Railway/Render          ║"
echo "║  ❓ FAQ_LANDING.md     - Preguntas frecuentes              ║"
echo "║                                                              ║"
echo "╚══════════════════════════════════════════════════════════════╝"

echo ""
echo "🎉 ¡Tu SaaS Predictivo está listo para usar!"
echo ""
echo "💡 Tip: Todos los archivos necesarios están en esta carpeta."
echo "        Revisa README.md para más instrucciones."
echo ""
