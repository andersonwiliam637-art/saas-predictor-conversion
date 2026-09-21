-- ========================================================================
-- SaaS Predictivo de Conversión - Schema PostgreSQL
-- ========================================================================

-- Extensiones
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ========================================================================
-- TABLA: USUARIOS
-- ========================================================================

CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    nombre VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    tienda_url VARCHAR(500),
    plan VARCHAR(50) DEFAULT 'basic', -- basic, pro, enterprise
    shopify_token VARCHAR(500),
    mercadolibre_token VARCHAR(500),
    activo BOOLEAN DEFAULT TRUE,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_proximo_pago TIMESTAMP,
    notificaciones_email BOOLEAN DEFAULT TRUE,
    notificaciones_sms BOOLEAN DEFAULT FALSE,
    telefono VARCHAR(20),
    stripe_customer_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_usuarios_email ON usuarios(email);
CREATE INDEX idx_usuarios_plan ON usuarios(plan);
CREATE INDEX idx_usuarios_activo ON usuarios(activo);
CREATE INDEX idx_usuarios_fecha_proximo_pago ON usuarios(fecha_proximo_pago);

-- ========================================================================
-- TABLA: EVENTOS
-- ========================================================================

CREATE TABLE IF NOT EXISTS eventos (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    cliente_id VARCHAR(255) NOT NULL,
    tipo VARCHAR(50) NOT NULL, -- 'venta', 'abandono', 'vista_producto', 'agregado_carrito'
    monto DECIMAL(12, 2),
    items INTEGER,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}',
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_eventos_usuario ON eventos(usuario_id);
CREATE INDEX idx_eventos_cliente ON eventos(cliente_id);
CREATE INDEX idx_eventos_tipo ON eventos(tipo);
CREATE INDEX idx_eventos_timestamp ON eventos(timestamp DESC);
CREATE INDEX idx_eventos_usuario_timestamp ON eventos(usuario_id, timestamp DESC);
CREATE INDEX idx_eventos_cliente_timestamp ON eventos(cliente_id, timestamp DESC);
CREATE INDEX idx_eventos_metadata ON eventos USING GIN(metadata);

-- ========================================================================
-- TABLA: PREDICCIONES
-- ========================================================================

CREATE TABLE IF NOT EXISTS predicciones (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    cliente_id VARCHAR(255) NOT NULL,
    probabilidad_abandono DECIMAL(5, 4), -- 0.0000 a 1.0000
    confianza DECIMAL(5, 4),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    alerta_enviada BOOLEAN DEFAULT FALSE,
    tipo_alerta VARCHAR(50), -- 'email', 'sms', 'ambas'
    enviado_a_email VARCHAR(255),
    enviado_a_sms VARCHAR(20),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_predicciones_usuario ON predicciones(usuario_id);
CREATE INDEX idx_predicciones_cliente ON predicciones(cliente_id);
CREATE INDEX idx_predicciones_timestamp ON predicciones(timestamp DESC);
CREATE INDEX idx_predicciones_probabilidad ON predicciones(probabilidad_abandono DESC);
CREATE INDEX idx_predicciones_usuario_timestamp ON predicciones(usuario_id, timestamp DESC);
CREATE INDEX idx_predicciones_alerta_enviada ON predicciones(alerta_enviada);

-- ========================================================================
-- TABLA: SUSCRIPCIONES / PAGOS
-- ========================================================================

CREATE TABLE IF NOT EXISTS suscripciones (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER NOT NULL UNIQUE REFERENCES usuarios(id) ON DELETE CASCADE,
    stripe_subscription_id VARCHAR(255) UNIQUE,
    stripe_customer_id VARCHAR(255),
    plan VARCHAR(50) NOT NULL, -- basic, pro, enterprise
    monto_mensual DECIMAL(12, 2),
    moneda VARCHAR(3) DEFAULT 'USD',
    estado VARCHAR(50) DEFAULT 'active', -- active, canceled, past_due, unpaid
    fecha_inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_proximo_pago TIMESTAMP,
    fecha_renovacion TIMESTAMP,
    fecha_cancelacion TIMESTAMP,
    intentos_pago_fallidos INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_suscripciones_usuario ON suscripciones(usuario_id);
CREATE INDEX idx_suscripciones_estado ON suscripciones(estado);
CREATE INDEX idx_suscripciones_fecha_proximo_pago ON suscripciones(fecha_proximo_pago);

-- ========================================================================
-- TABLA: ALERTAS ENVIADAS
-- ========================================================================

CREATE TABLE IF NOT EXISTS alertas_enviadas (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    prediccion_id INTEGER REFERENCES predicciones(id) ON DELETE SET NULL,
    cliente_id VARCHAR(255),
    tipo VARCHAR(50), -- 'email', 'sms'
    destinatario VARCHAR(255),
    asunto TEXT,
    body TEXT,
    estado VARCHAR(50) DEFAULT 'sent', -- sent, failed, bounced, opened, clicked
    error_mensaje TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_alertas_usuario ON alertas_enviadas(usuario_id);
CREATE INDEX idx_alertas_cliente ON alertas_enviadas(cliente_id);
CREATE INDEX idx_alertas_estado ON alertas_enviadas(estado);
CREATE INDEX idx_alertas_timestamp ON alertas_enviadas(timestamp DESC);

-- ========================================================================
-- TABLA: WEBHOOKS RECIBIDOS
-- ========================================================================

CREATE TABLE IF NOT EXISTS webhooks_log (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    fuente VARCHAR(50), -- 'shopify', 'mercadolibre', 'stripe'
    tipo_evento VARCHAR(255),
    payload JSONB,
    procesado BOOLEAN DEFAULT FALSE,
    error TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_webhooks_fuente ON webhooks_log(fuente);
CREATE INDEX idx_webhooks_procesado ON webhooks_log(procesado);
CREATE INDEX idx_webhooks_timestamp ON webhooks_log(timestamp DESC);

-- ========================================================================
-- TABLA: SYNC HISTORY
-- ========================================================================

CREATE TABLE IF NOT EXISTS sync_history (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    plataforma VARCHAR(50), -- 'shopify', 'mercadolibre'
    tipo_sync VARCHAR(50), -- 'ordenes', 'clientes', 'productos'
    eventos_procesados INTEGER,
    eventos_nuevos INTEGER,
    fecha_inicio TIMESTAMP,
    fecha_fin TIMESTAMP,
    estado VARCHAR(50) DEFAULT 'success', -- success, failed, partial
    error_mensaje TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sync_history_usuario ON sync_history(usuario_id);
CREATE INDEX idx_sync_history_fecha ON sync_history(fecha_fin DESC);

-- ========================================================================
-- TABLA: MÉTRICAS DIARIAS
-- ========================================================================

CREATE TABLE IF NOT EXISTS metricas_diarias (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    fecha DATE NOT NULL,
    total_eventos INTEGER DEFAULT 0,
    total_abandonos INTEGER DEFAULT 0,
    total_ventas DECIMAL(12, 2) DEFAULT 0,
    valor_abandonos DECIMAL(12, 2) DEFAULT 0,
    predicciones_activas INTEGER DEFAULT 0,
    alertas_enviadas INTEGER DEFAULT 0,
    tasa_conversion DECIMAL(5, 2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(usuario_id, fecha)
);

CREATE INDEX idx_metricas_usuario_fecha ON metricas_diarias(usuario_id, fecha DESC);

-- ========================================================================
-- VIEWS
-- ========================================================================

-- Vista: Predicciones sin alertar
CREATE VIEW predicciones_pendientes AS
SELECT p.*
FROM predicciones p
WHERE p.alerta_enviada = FALSE
AND p.probabilidad_abandono >= 0.70
AND p.timestamp > CURRENT_TIMESTAMP - INTERVAL '48 hours';

-- Vista: Top clientes en riesgo
CREATE VIEW top_clientes_riesgo AS
SELECT 
    usuario_id,
    cliente_id,
    MAX(probabilidad_abandono) as max_probabilidad,
    COUNT(*) as predicciones_count,
    MAX(timestamp) as ultima_prediccion
FROM predicciones
WHERE probabilidad_abandono >= 0.70
AND timestamp > CURRENT_TIMESTAMP - INTERVAL '7 days'
GROUP BY usuario_id, cliente_id
ORDER BY max_probabilidad DESC;

-- Vista: Resumen diario por usuario
CREATE VIEW resumen_diario AS
SELECT 
    e.usuario_id,
    DATE(e.timestamp) as fecha,
    COUNT(*) FILTER (WHERE e.tipo = 'venta') as ventas,
    COUNT(*) FILTER (WHERE e.tipo = 'abandono') as abandonos,
    SUM(e.monto) FILTER (WHERE e.tipo = 'venta') as total_ventas,
    SUM(e.monto) FILTER (WHERE e.tipo = 'abandono') as valor_abandonos,
    COUNT(DISTINCT p.id) as predicciones
FROM eventos e
LEFT JOIN predicciones p ON e.usuario_id = p.usuario_id AND DATE(e.timestamp) = DATE(p.timestamp)
GROUP BY e.usuario_id, DATE(e.timestamp);

-- ========================================================================
-- FUNCIONES Y TRIGGERS
-- ========================================================================

-- Función: Actualizar timestamp
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers para update_updated_at
CREATE TRIGGER usuarios_update_timestamp BEFORE UPDATE ON usuarios
FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER suscripciones_update_timestamp BEFORE UPDATE ON suscripciones
FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ========================================================================
-- INITIAL DATA
-- ========================================================================

-- Insertar datos de prueba (comentado en producción)
-- INSERT INTO usuarios (email, nombre, password_hash, tienda_url, plan)
-- VALUES ('demo@example.com', 'Demo User', 'demo_hash', 'https://demo.example.com', 'basic');

-- ========================================================================
-- PERMISOS
-- ========================================================================

-- En producción, crear usuario con permisos limitados
-- CREATE ROLE saas_app WITH LOGIN PASSWORD 'secure_password';
-- GRANT CONNECT ON DATABASE saas_db TO saas_app;
-- GRANT USAGE ON SCHEMA public TO saas_app;
-- GRANT ALL ON ALL TABLES IN SCHEMA public TO saas_app;
-- GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO saas_app;
