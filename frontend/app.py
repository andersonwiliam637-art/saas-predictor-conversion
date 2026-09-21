"""
Dashboard Streamlit - SaaS Predictivo de Conversión
"""

import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import json

# ============================================================================
# CONFIG
# ============================================================================

st.set_page_config(
    page_title="SaaS Predictivo - Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

API_URL = "http://backend:8000"

# CSS personalizado
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 10px;
        color: white;
        margin: 10px 0;
    }
    .metric-value {
        font-size: 32px;
        font-weight: bold;
        margin: 10px 0;
    }
    .metric-label {
        font-size: 14px;
        opacity: 0.8;
    }
    .alert-high {
        background-color: #fee;
        padding: 10px;
        border-radius: 5px;
        border-left: 4px solid #f44;
    }
    .alert-medium {
        background-color: #fef3cd;
        padding: 10px;
        border-radius: 5px;
        border-left: 4px solid #ffc107;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# SESSION STATE
# ============================================================================

if "token" not in st.session_state:
    st.session_state.token = None
if "usuario" not in st.session_state:
    st.session_state.usuario = None

# ============================================================================
# AUTH
# ============================================================================

def login():
    """Página de login"""
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("# 🚀 SaaS Predictivo de Conversión")
        st.markdown("Detecta abandonos de carrito con 48h de anticipación")
        
        st.markdown("---")
        
        tab1, tab2 = st.tabs(["Inicia Sesión", "Regístrate"])
        
        with tab1:
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Contraseña", type="password", key="login_password")
            
            if st.button("Inicia Sesión", use_container_width=True, type="primary"):
                try:
                    response = requests.post(
                        f"{API_URL}/api/auth/login",
                        json={"email": email, "password": password}
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        st.session_state.token = data["token"]
                        st.session_state.usuario = data
                        st.success("✅ Sesión iniciada")
                        st.rerun()
                    else:
                        st.error("❌ Email o contraseña inválidos")
                except Exception as e:
                    st.error(f"Error: {e}")
        
        with tab2:
            nombre = st.text_input("Nombre Completo", key="reg_nombre")
            email = st.text_input("Email", key="reg_email")
            password = st.text_input("Contraseña", type="password", key="reg_password")
            tienda_url = st.text_input("URL de tu tienda", key="reg_tienda")
            
            if st.button("Crear Cuenta", use_container_width=True, type="primary"):
                try:
                    response = requests.post(
                        f"{API_URL}/api/auth/registro",
                        json={
                            "nombre": nombre,
                            "email": email,
                            "password": password,
                            "tienda_url": tienda_url
                        }
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        st.session_state.token = data["token"]
                        st.session_state.usuario = {"email": email, "nombre": nombre}
                        st.success("✅ Cuenta creada. ¡Bienvenido!")
                        st.info("📅 Tienes 14 días de prueba gratuita sin tarjeta de crédito")
                        st.rerun()
                    else:
                        st.error("❌ El email ya está registrado")
                except Exception as e:
                    st.error(f"Error: {e}")

# ============================================================================
# DASHBOARD PRINCIPAL
# ============================================================================

def dashboard():
    """Dashboard principal post-login"""
    
    # Header
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        st.markdown(f"# 📊 Dashboard")
        st.markdown(f"Bienvenido, **{st.session_state.usuario.get('nombre', 'Usuario')}**")
    with col3:
        if st.button("🚪 Cerrar Sesión"):
            st.session_state.token = None
            st.session_state.usuario = None
            st.rerun()
    
    st.markdown("---")
    
    # Obtener datos
    headers = {"authorization": f"Bearer {st.session_state.token}"}
    
    try:
        dashboard_response = requests.get(f"{API_URL}/api/dashboard", headers=headers)
        predicciones_response = requests.get(f"{API_URL}/api/predicciones?dias=30", headers=headers)
        
        if dashboard_response.status_code != 200:
            st.error("❌ Error al cargar datos")
            return
        
        dash_data = dashboard_response.json()
        pred_data = predicciones_response.json()
        
        metricas = dash_data["metricas"]
        
        # ====================================================================
        # KPIs
        # ====================================================================
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "💰 Ventas (30d)",
                f"${metricas['ventas_30d']:.2f}",
                delta="vs mes anterior"
            )
        
        with col2:
            st.metric(
                "⚠️ Abandonos",
                f"${metricas['abandono_detectado']:.2f}",
                delta="potencial recuperable"
            )
        
        with col3:
            st.metric(
                "🔔 Alertas",
                metricas['alertas_enviadas'],
                delta="enviadas esta semana"
            )
        
        with col4:
            st.metric(
                "✅ Tasa Conversión",
                f"{metricas['tasa_recuperacion']}%",
                delta="desde detección"
            )
        
        st.markdown("---")
        
        # ====================================================================
        # GRÁFICOS
        # ====================================================================
        
        tab1, tab2, tab3, tab4 = st.tabs([
            "📈 Predicciones",
            "🔔 Alertas",
            "⚙️ Configuración",
            "💳 Plan"
        ])
        
        # Tab 1: Predicciones
        with tab1:
            col1, col2 = st.columns(2)
            
            with col1:
                # Distribución de probabilidades
                probs = [p["probabilidad"] for p in pred_data["predicciones"]]
                fig = go.Figure(data=[
                    go.Histogram(x=probs, nbinsx=20, name="Probabilidad")
                ])
                fig.update_layout(
                    title="Distribución de Predicciones",
                    xaxis_title="Probabilidad de Abandono",
                    yaxis_title="Cantidad",
                    height=400,
                    showlegend=False
                )
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                # Confianza vs Probabilidad
                probs = [p["probabilidad"] for p in pred_data["predicciones"]]
                confs = [p["confianza"] for p in pred_data["predicciones"]]
                fig = go.Figure(data=[
                    go.Scatter(
                        x=probs,
                        y=confs,
                        mode='markers',
                        marker=dict(size=8, color=probs, colorscale='Viridis')
                    )
                ])
                fig.update_layout(
                    title="Confianza vs Probabilidad",
                    xaxis_title="Probabilidad",
                    yaxis_title="Confianza",
                    height=400
                )
                st.plotly_chart(fig, use_container_width=True)
            
            # Lista detallada
            st.subheader("Últimas Predicciones")
            df = pd.DataFrame(pred_data["predicciones"][:20])
            if not df.empty:
                df["probabilidad"] = df["probabilidad"].apply(lambda x: f"{x:.1%}")
                df["confianza"] = df["confianza"].apply(lambda x: f"{x:.1%}")
                df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M")
                st.dataframe(df, use_container_width=True)
        
        # Tab 2: Alertas
        with tab2:
            st.subheader("🔔 Alertas Activas (>70% abandono)")
            
            alertas = [p for p in pred_data["predicciones"] if p["probabilidad"] > 0.70]
            
            if alertas:
                for alerta in alertas[:10]:
                    with st.container():
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.markdown(f"""
                            <div class="alert-high">
                                <strong>Cliente: {alerta['cliente_id']}</strong><br>
                                Probabilidad: <strong>{alerta['probabilidad']:.1%}</strong><br>
                                Confianza: {alerta['confianza']:.1%}
                            </div>
                            """, unsafe_allow_html=True)
                        with col2:
                            if st.button("📧 Contactar", key=f"contact_{alerta['cliente_id']}"):
                                st.success("✅ Email enviado al cliente")
            else:
                st.info("✅ No hay alertas activas en este momento")
        
        # Tab 3: Configuración
        with tab3:
            st.subheader("⚙️ Preferencias de Alertas")
            
            col1, col2 = st.columns(2)
            
            with col1:
                email_alerts = st.checkbox(
                    "Alertas por Email",
                    value=True,
                    help="Recibe notificaciones por email cuando detectamos abandonos"
                )
            
            with col2:
                sms_alerts = st.checkbox(
                    "Alertas por SMS",
                    value=False,
                    help="Recibe SMS para alertas de alta prioridad"
                )
            
            if sms_alerts:
                telefono = st.text_input("Número telefónico", "+1")
            
            st.markdown("---")
            st.subheader("🔌 Integraciones")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### Shopify")
                shopify_token = st.text_input(
                    "Token de Shopify",
                    type="password",
                    help="Tu token privado de Shopify"
                )
                if st.button("Conectar Shopify"):
                    st.success("✅ Shopify conectado")
            
            with col2:
                st.markdown("### MercadoLibre")
                ml_token = st.text_input(
                    "Token de MercadoLibre",
                    type="password",
                    help="Tu token de autenticación de MercadoLibre"
                )
                if st.button("Conectar MercadoLibre"):
                    st.success("✅ MercadoLibre conectado")
        
        # Tab 4: Plan
        with tab4:
            st.subheader(f"📋 Plan Actual: {dash_data['usuario']['plan'].upper()}")
            
            planes = requests.get(f"{API_URL}/api/planes").json()["planes"]
            
            col1, col2, col3 = st.columns(3)
            
            for i, plan in enumerate(planes):
                with [col1, col2, col3][i]:
                    st.markdown(f"""
                    ### {plan['nombre']}
                    
                    ## ${plan['precio']}/mes
                    
                    {' | '.join([f"✅ {f}" for f in plan['features']])}
                    """)
                    
                    if st.button(f"Elegir {plan['nombre']}", key=f"plan_{plan['id']}"):
                        st.info(f"Redirigiendo a Stripe para {plan['nombre']}...")
                        st.markdown(f"[Ir a Stripe →](https://stripe.com/checkout)")
            
            st.markdown("---")
            st.markdown(f"**Próxima facturación:** {dash_data['proxima_facturacion']}")
    
    except Exception as e:
        st.error(f"❌ Error: {e}")

# ============================================================================
# MAIN
# ============================================================================

def main():
    if st.session_state.token is None:
        login()
    else:
        dashboard()

if __name__ == "__main__":
    main()
