import streamlit as st
import pandas as pd
from datetime import date
import plotly.graph_objects as go
import os
import json
import requests
from google import genai

# ==========================================
# 1. SEITENKONFIGURATION & LOGO-CHECK
# ==========================================
LOGO_PATH = "caloop_logo.png"
HAS_LOGO = os.path.exists(LOGO_PATH)

st.set_page_config(
    page_title="Caloop Tracker",
    page_icon=LOGO_PATH if HAS_LOGO else "🥗",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ==========================================
# 2. DESIGN & STYLING (HEX-Farben aus Skizze/Logo)
# ==========================================
st.markdown(f"""
<style>
    /* Hintergrund Hauptseite */
    .stApp {{
        background-color: #FFFFFF;
        color: #0E5E6F;
        font-family: 'Segoe UI', Roboto, sans-serif;
    }}

    /* Allgemeines Text-Coloring */
    h1, h2, h3, h4, h5, h6, p, label, span {{
        color: #0E5E6F !important;
    }}

    /* EINGABEFELDER: Dunkles Blaugrün mit weißer Schrift */
    div[data-baseweb="input"] > div, 
    div[data-baseweb="select"] > div, 
    textarea {{
        background-color: #0E5E6F !important;
        color: #FFFFFF !important;
        border-radius: 10px !important;
        border: 1px solid #083D48 !important;
    }}
    
    input {{
        color: #FFFFFF !important;
    }}
    
    /* Placeholdertest in Eingabefeldern */
    input::placeholder, textarea::placeholder {{
        color: #B0BEC5 !important;
    }}

    /* STANDARDBUTTONS */
    .stButton > button {{
        background: linear-gradient(135deg, #108997 0%, #2EC4B6 100%);
        color: white !important;
        font-weight: bold;
        border-radius: 20px;
        border: none;
        padding: 10px 20px;
        width: 100%;
        transition: all 0.3s ease;
        box-shadow: 0 4px 6px rgba(14, 94, 111, 0.2);
    }}

    .stButton > button:hover {{
        background: linear-gradient(135deg, #083D48 0%, #108997 100%);
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(14, 94, 111, 0.3);
    }}

    /* KLEINE RUNDE ICON-BUTTONS AUF DER ÜBERSICHT */
    .round-icon-btn > button {{
        border-radius: 50% !important;
        width: 48px !important;
        height: 48px !important;
        min-width: 48px !important;
        padding: 0 !important;
        font-size: 20px !important;
        line-height: 48px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        margin: auto !important;
    }}

    /* Cards / Container */
    .card-box {{
        background-color: #F4F7F6;
        padding: 20px;
        border-radius: 15px;
        border: 1px solid #E0E7E9;
        margin-bottom: 15px;
    }}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. INITIALISIERUNG DES SESSION STATES
# ==========================================
if "current_user" not in st.session_state:
    st.session_state["current_user"] = "JeannyBunny"

if "selected_page" not in st.session_state:
    st.session_state["selected_page"] = "Übersicht"

if "user_data" not in st.session_state:
    st.session_state["user_data"] = {
        "JeannyBunny": {
            "geschlecht": "Weiblich", "alter": 40, "groesse": 168, "gewicht": 65.0,
            "aktivitaet": "Sitzt hauptsächlich (z. B. Büro)", "ziel": "Gewicht halten",
            "besonderheit": "Keine", "krankheit": False,
            "final_kcal": 2000, "final_wasser": 2300, "final_bewegung": 300
        },
        "PhillyBilly": {
            "geschlecht": "Männlich", "alter": 40, "groesse": 180, "gewicht": 80.0,
            "aktivitaet": "Sitzt hauptsächlich (z. B. Büro)", "ziel": "Gewicht halten",
            "besonderheit": "Keine", "krankheit": False,
            "final_kcal": 2500, "final_wasser": 2800, "final_bewegung": 300
        }
    }

if "daily_logs" not in st.session_state:
    st.session_state["daily_logs"] = {}

if "favorites_all" not in st.session_state:
    st.session_state["favorites_all"] = [
        {"typ": "Zutat", "name": "Magerquark", "kcal": 67, "protein": 12.0, "carbs": 4.0, "fat": 0.2, "std_g": 100},
        {"typ": "Zutat", "name": "Banane", "kcal": 89, "protein": 1.1, "carbs": 22.8, "fat": 0.3, "std_g": 120},
        {"typ": "Mahlzeit", "name": "Quark-Beeren-Bowl", "kcal": 350, "protein": 28.0, "carbs": 40.0, "fat": 3.0, "std_g": 380}
    ]

if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []

# GEMINI KI-CLIENT INITIALISIEREN
@st.cache_resource
def get_gemini_client():
    api_key = st.secrets.get("GEMINI_API_KEY")
    if api_key:
        return genai.Client(api_key=api_key)
    return None

gemini_client = get_gemini_client()

# Navigation Callback Helper
def go_to_page(page_name):
    st.session_state["selected_page"] = page_name

# ==========================================
# 4. HELFER- & BERECHNUNGSFUNKTIONEN
# ==========================================
def calculate_user_needs(data):
    gewicht, groesse, alter, geschlecht = data["gewicht"], data["groesse"], data["alter"], data["geschlecht"]
    bmr = (10 * gewicht) + (6.25 * groesse) - (5 * alter) + (5 if geschlecht == "Männlich" else -161)
    
    pal_map = {
        "Ausschließlich sitzend / liegend": 1.2,
        "Sitzt hauptsächlich (z. B. Büro)": 1.4,
        "Sitzend, stehend / gehend": 1.6,
        "Hauptsächlich stehend / gehend": 1.8,
        "Körperlich anstrengende Arbeit": 2.0
    }
    tdee = bmr * pal_map.get(data.get("aktivitaet"), 1.4)

    extra_kcal, extra_wasser = 0, 0
    if data.get("besonderheit") == "Schwangerschaft":
        extra_kcal += 300; extra_wasser += 300
    elif data.get("besonderheit") == "Stillzeit":
        extra_kcal += 500; extra_wasser += 500

    if data.get("krankheit"):
        extra_kcal += bmr * 0.10
        extra_wasser += 300

    target_kcal = tdee + extra_kcal
    if data.get("ziel") == "Gewicht abnehmen": target_kcal -= 400
    elif data.get("ziel") == "Gewicht zunehmen / Muskelaufbau": target_kcal += 300

    target_kcal = max(target_kcal, bmr)
    target_wasser = (gewicht * 35) + extra_wasser
    return int(target_kcal), int(target_wasser), int(bmr)

user = st.session_state["current_user"]
user_goals = st.session_state["user_data"][user]
calc_kcal, calc_wasser, calc_bmr = calculate_user_needs(user_goals)
user_goals["final_kcal"] = calc_kcal
user_goals["final_wasser"] = calc_wasser

today_key = f"{user}_{date.today()}"
if today_key not in st.session_state["daily_logs"]:
    st.session_state["daily_logs"][today_key] = {"eaten": [], "wasser_ml": 0, "bewegung_kcal": 0}

today_log = st.session_state["daily_logs"][today_key]

# KI NÄHRWERTANALYSE MIT GEMINI
def analyze_food_with_ai(prompt_text):
    if not gemini_client:
        return None
    try:
        sys_prompt = """
        Du bist ein präziser Ernährungs-Assistent. Analysiere den eingegebenen Text für ein Lebensmittel oder ein Gericht.
        Schätze die Gesamtwerte für die angegebene oder eine realistisch vermutete Portionsmenge.
        Antworte AUSSCHLIESSLICH im folgenden JSON-Format ohne zusätzlichen Text oder Markdown-Blöcke:
        {
            "name": "Name des Gerichts/Lebensmittels",
            "gramm": 250,
            "kcal": 350,
            "protein": 12.5,
            "carbs": 45.0,
            "fat": 8.0
        }
        """
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=f"{sys_prompt}\n\nEingabe: {prompt_text}"
        )
        clean_text = response.text.replace("```json", "").replace("