import streamlit as st
import pandas as pd
from datetime import date
import plotly.graph_objects as go
import os
import re
import requests
import json
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
        padding: 12px 24px;
        width: 100%;
        transition: all 0.3s ease;
        box-shadow: 0 4px 6px rgba(14, 94, 111, 0.2);
    }}

    .stButton > button:hover {{
        background: linear-gradient(135deg, #083D48 0%, #108997 100%);
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(14, 94, 111, 0.3);
    }}

    /* RUNDE ICON-BUTTONS AUF DER ÜBERSICHT */
    .round-icon-btn > button {{
        border-radius: 50% !important;
        width: 70px !important;
        height: 70px !important;
        padding: 0 !important;
        font-size: 28px !important;
        line-height: 70px !important;
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

# LOGO OBEN MITTIG AUF JEDER SEITE (ca. 20% kleiner = width 100)
if HAS_LOGO:
    col_l1, col_l2, col_l3 = st.columns([1, 1, 1])
    with col_l2:
        st.image(LOGO_PATH, width=100)

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
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)
    except Exception as e:
        return None

def search_open_food_facts(query_text):
    url = "https://world.openfoodfacts.org/cgi/search.pl"
    params = {"search_terms": query_text, "search_simple": 1, "action": "process", "json": 1, "page_size": 1}
    headers = {"User-Agent": "CaloopApp/2.0"}
    try:
        res = requests.get(url, params=params, headers=headers, timeout=3)
        data = res.json()
        if data.get("products"):
            prod = data["products"][0]
            nut = prod.get("nutriments", {})
            return {
                "name": prod.get("product_name", query_text.capitalize()),
                "kcal": int(nut.get("energy-kcal_100g", nut.get("energy-kcal", 0))),
                "protein": round(float(nut.get("proteins_100g", 0.0)), 1),
                "carbs": round(float(nut.get("carbohydrates_100g", 0.0)), 1),
                "fat": round(float(nut.get("fat_100g", 0.0)), 1)
            }
    except Exception: pass
    return None

# ==========================================
# 5. SIDEBAR / BÜRGERMENÜ NAVIGATION
# ==========================================
with st.sidebar:
    st.title("👤 Nutzer wechseln")
    new_user = st.selectbox("Aktueller Profil:", ["JeannyBunny", "PhillyBilly"], index=0 if user == "JeannyBunny" else 1)
    if new_user != user:
        st.session_state["current_user"] = new_user
        st.rerun()

    st.write("---")
    st.title("📌 Caloop Menü")
    
    # Reduzierte Navigationsliste (Essen, Trinken, Bewegung & Scanner ausgeblendet)
    menu_pages = ["Übersicht", "Favoriten", "Feedback", "Profil und Ziele"]
    
    # Sicherstellen, dass kein Absturz passiert, wenn versteckte Seiten aktiv sind
    current_idx = menu_pages.index(st.session_state["selected_page"]) if st.session_state["selected_page"] in menu_pages else 0
    choice = st.radio("Gehe zu:", menu_pages, index=current_idx)
    st.session_state["selected_page"] = choice

selected_page = st.session_state["selected_page"]

# ==========================================
# REITER: ÜBERSICHT (DAS DASHBOARD)
# ==========================================
# ==========================================
# REITER: ÜBERSICHT (DAS DASHBOARD)
# ==========================================
if selected_page == "Übersicht":
    st.markdown(f"<p style='text-align: center; color: gray;'>{date.today().strftime('%A, %d. %B %Y')}</p>", unsafe_allow_html=True)

    # Berechnungen für Ring & Pegel
    eaten_kcal = sum(item["kcal"] for item in today_log["eaten"])
    burned_kcal = today_log["bewegung_kcal"]
    net_kcal = max(0, eaten_kcal - burned_kcal)
    goal_kcal = user_goals["final_kcal"]
    
    water_ml = today_log["wasser_ml"]
    goal_water = user_goals["final_wasser"]
    water_ratio = min(1.0, water_ml / max(1, goal_water))

    # Plotly Donut Ring
    fig = go.Figure()

    fig.add_trace(go.Pie(
        values=[min(net_kcal, goal_kcal), max(0, goal_kcal - net_kcal)],
        hole=0.68,
        marker_colors=["#2EC4B6" if net_kcal <= goal_kcal else "#D9534F", "#E0E7E9"],
        textinfo="none",
        hoverinfo="none",
        direction="clockwise",
        sort=False
    ))

    # Der innere Wasser-Kreis passt sich exakt an die Donut-Lochgröße an
    fig.update_layout(
        showlegend=False,
        margin=dict(t=10, b=10, l=10, r=10),
        height=320,
        annotations=[
            dict(
                text=f"<b>{net_kcal}</b> / {goal_kcal} kcal<br><span style='font-size:12px;color:#1E88E5;'>💧 {water_ml} / {goal_water} ml</span>",
                x=0.5, y=0.5, font_size=18, showarrow=False, font_color="#0E5E6F"
            )
        ],
        shapes=[
            dict(
                type="circle",
                xref="paper", yref="paper",
                x0=0.16, y0=0.16, x1=0.84, y1=0.84,
                fillcolor=f"rgba(30, 136, 229, {round(water_ratio * 0.75, 2)})",
                line=dict(color="#1E88E5", width=1),
                layer="below"
            )
        ]
    )
    
    st.plotly_chart(fig, use_container_width=True)

    # Callback-Funktionen für fehlerfreie Navigation
    def go_to_page(page_name):
        st.session_state["selected_page"] = page_name

    # RUNDE ICON-BUTTONS NEBENEINANDER (Ohne Text)
    c_btn1, c_btn2, c_btn3 = st.columns(3)
    
    with c_btn1:
        st.markdown('<div class="round-icon-btn">', unsafe_allow_html=True)
        st.button("🍽️", key="nav_essen", on_click=go_to_page, args=("Essen",))
        st.markdown('</div>', unsafe_allow_html=True)

    with c_btn2:
        st.markdown('<div class="round-icon-btn">', unsafe_allow_html=True)
        st.button("💧", key="nav_trinken", on_click=go_to_page, args=("Trinken",))
        st.markdown('</div>', unsafe_allow_html=True)

    with c_btn3:
        st.markdown('<div class="round-icon-btn">', unsafe_allow_html=True)
        st.button("🏃", key="nav_bewegung", on_click=go_to_page, args=("Bewegung",))
        st.markdown('</div>', unsafe_allow_html=True)
        
# ==========================================
# REITER: ESSEN
# ==========================================
elif selected_page == "Essen":
    if st.button("⬅️ Zurück zur Übersicht"):
        st.session_state["selected_page"] = "Übersicht"
        st.rerun()

    st.title("🍽️ Essen erfassen")

    if st.button("📷 Barcode scannen (Scanner öffnen)"):
        st.session_state["selected_page"] = "Barcodescanner"
        st.rerun()

    st.write("---")
    
    target_dest = st.radio("Speichern in:", ["Tagestracker", "Favoriten"], horizontal=True)
    kat = st.selectbox("Mahlzeit", ["Frühstück", "Mittagessen", "Abendessen", "Snack"])

    tab1, tab2 = st.tabs(["🤖 KI-Texteingabe", "✏️ Manuell"])

    with tab1:
        txt = st.text_input("Zutat / Gericht beschreiben", placeholder="z. B. 150g Magerquark oder 2 Scheiben Vollkornbrot mit Butter")
        if st.button("✨ Mit KI schätzen & Speichern"):
            if txt:
                with st.spinner("Gemini analysiert deine Eingabe..."):
                    ai_result = analyze_food_with_ai(txt)
                
                if ai_result:
                    p_name = ai_result.get("name", txt)
                    p_gramm = ai_result.get("gramm", 100)
                    p_kcal = ai_result.get("kcal", 0)
                    p_prot = ai_result.get("protein", 0.0)

                    if target_dest == "Tagestracker":
                        today_log["eaten"].append({"name": f"[{kat}] {p_name} ({p_gramm}g)", "kcal": p_kcal, "protein": p_prot})
                        st.success(f"✅ KI-Ergebnis: **{p_name}** (~{p_kcal} kcal, {p_prot}g Protein) hinzugefügt!")
                    else:
                        st.session_state["favorites_all"].append({"typ": "Mahlzeit", "name": p_name, "kcal": p_kcal, "protein": p_prot, "std_g": p_gramm})
                        st.success(f"⭐ **{p_name}** zu Favoriten hinzugefügt!")
                else:
                    st.warning("KI nicht erreichbar. Nutze Suche in OpenFoodFacts...")
                    prod = search_open_food_facts(txt)
                    if prod:
                        today_log["eaten"].append({"name": f"[{kat}] {prod['name']} (100g)", "kcal": prod['kcal'], "protein": prod['protein']})
                        st.success(f"✅ {prod['name']} ({prod['kcal']} kcal) hinzugefügt!")
                    else:
                        st.error("Nährwerte konnten nicht ermittelt werden. Bitte manuell eingeben.")

    with tab2:
        m_name = st.text_input("Name", placeholder="Selbstgemachter Riegel")
        m_g = st.number_input("Gewicht (g)", min_value=1, value=100)
        m_k = st.number_input("Kalorien (kcal pro 100g)", min_value=0, value=200)
        m_p = st.number_input("Protein (g pro 100g)", min_value=0.0, value=10.0)

        if st.button("➕ Manuell Speichern"):
            if m_name:
                factor = m_g / 100.0
                calc_k = int(m_k * factor)
                calc_p = round(m_p * factor, 1)
                if target_dest == "Tagestracker":
                    today_log["eaten"].append({"name": f"[{kat}] {m_name} ({m_g}g)", "kcal": calc_k, "protein": calc_p})
                    st.success(f"✅ Hinzugefügt!")
                else:
                    st.session_state["favorites_all"].append({"typ": "Mahlzeit", "name": m_name, "kcal": m_k, "protein": m_p, "std_g": m_g})
                    st.success(f"⭐ Zu Favoriten gespeichert!")

    st.write("---")
    st.subheader("📋 Heute gegessen:")
    for idx, item in enumerate(today_log["eaten"]):
        c1, c2 = st.columns([4, 1])
        c1.write(f"• **{item['name']}**: {item['kcal']} kcal ({item.get('protein', 0)}g Protein)")
        if c2.button("🗑️", key=f"del_eaten_{idx}"):
            today_log["eaten"].pop(idx)
            st.rerun()

# ==========================================
# REITER: TRINKEN
# ==========================================
elif selected_page == "Trinken":
    if st.button("⬅️ Zurück zur Übersicht"):
        st.session_state["selected_page"] = "Übersicht"
        st.rerun()

    st.title("💧 Wasseraufnahme")

    st.metric("Bereits getrunken", f"{today_log['wasser_ml']} / {user_goals['final_wasser']} ml")

    st.subheader("Quick-Add Buttons:")
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("+ 100 ml"): today_log['wasser_ml'] += 100; st.rerun()
    if c2.button("+ 250 ml"): today_log['wasser_ml'] += 250; st.rerun()
    if c3.button("+ 500 ml"): today_log['wasser_ml'] += 500; st.rerun()
    if c4.button("+ 1000 ml"): today_log['wasser_ml'] += 1000; st.rerun()

    st.write("---")
    custom_w = st.number_input("Manuelle Menge (ml)", min_value=0, step=50, value=200)
    if st.button("➕ Hinzufügen"):
        today_log['wasser_ml'] += custom_w
        st.success(f"{custom_w} ml hinzugefügt!")
        st.rerun()

# ==========================================
# REITER: BEWEGUNG
# ==========================================
elif selected_page == "Bewegung":
    if st.button("⬅️ Zurück zur Übersicht"):
        st.session_state["selected_page"] = "Übersicht"
        st.rerun()

    st.title("🏃 Bewegung & Kalorienverbrauch")

    st.metric("Verbrannt durch Sport", f"{today_log['bewegung_kcal']} kcal")

    tab_auto, tab_man = st.tabs(["⚡ Automatische Berechnung", "✏️ Manuelle Eingabe"])

    with tab_auto:
        act = st.selectbox("Aktivität", ["Spazierengehen (moderat)", "Joggen (8-10 km/h)", "Radfahren", "Krafttraining / Fitness", "Schwimmen"])
        duration = st.number_input("Dauer (in Minuten)", min_value=5, value=30, step=5)
        
        met_table = {"Spazierengehen (moderat)": 3.5, "Joggen (8-10 km/h)": 8.0, "Radfahren": 6.0, "Krafttraining / Fitness": 5.0, "Schwimmen": 7.0}
        weight = user_goals["gewicht"]
        calc_burn = int((met_table[act] * 3.5 * weight / 200) * duration)

        st.info(f"Berechneter Verbrauch: ca. **{calc_burn} kcal** für {user} ({weight} kg).")
        if st.button("🔥 Aktivität verbuchen", key="btn_auto_burn"):
            today_log['bewegung_kcal'] += calc_burn
            st.success(f"{calc_burn} kcal gutgeschrieben!")
            st.rerun()

    with tab_man:
        m_burn = st.number_input("Verbrauchte Kalorien", min_value=10, value=150, step=10)
        m_desc = st.text_input("Beschreibung (optional)", placeholder="z. B. Gartenarbeit")
        if st.button("➕ Manuell verbuchen"):
            today_log['bewegung_kcal'] += m_burn
            st.success(f"{m_burn} kcal hinzugefügt!")
            st.rerun()

# ==========================================
# REITER: FAVORITEN
# ==========================================
elif selected_page == "Favoriten":
    st.title("⭐ Kombinierte Favoritenliste")
    st.write("Hier sind all deine gespeicherten Zutaten & Mahlzeiten an einem Ort:")

    for idx, fav in enumerate(st.session_state["favorites_all"]):
        c1, c2 = st.columns([4, 1])
        c1.write(f"• **[{fav['typ']}] {fav['name']}** ({fav.get('std_g', 100)}g) – {fav['kcal']} kcal | Protein: {fav.get('protein', 0)}g")
        if c2.button("🗑️", key=f"del_fav_all_{idx}"):
            st.session_state["favorites_all"].pop(idx)
            st.rerun()

# ==========================================
# REITER: FEEDBACK (INTERAKTIVER CHATBOT)
# ==========================================
elif selected_page == "Feedback":
    st.title("🤖 Caloop Feedback Coach")
    st.write("Frag mich alles zu deiner heutigen Bilanz, Nährstoffen oder Tipps!")

    tot_k = sum(i["kcal"] for i in today_log["eaten"])
    tot_p = sum(i.get("protein", 0) for i in today_log["eaten"])
    tot_w = today_log["wasser_ml"]
    net_k = tot_k - today_log["bewegung_kcal"]
    diff_k = user_goals["final_kcal"] - net_k

    if not st.session_state["chat_history"]:
        intro = f"Hallo {user}! 👋 Hier ist dein Feedback-Status:\n\n"
        intro += f"- **Kalorien-Netto:** {net_k} / {user_goals['final_kcal']} kcal\n"
        intro += f"- **Protein:** {tot_p:.1f}g (Ziel: ~{round(user_goals['gewicht']*1.5, 1)}g)\n"
        intro += f"- **Wasser:** {tot_w} / {user_goals['final_wasser']} ml\n\n"
        
        if diff_k > 800:
            intro += "🚨 **Achtung vor dem Notmodus!** Du hast heute deutlich zu wenig gegessen."
        elif tot_k < calc_bmr:
            intro += "⚠️ Du liegst noch unter deinem Grundumsatz!"
        else:
            intro += "👍 Du bist gut im Zielbereich! Hast du Fragen zu Mahlzeiten oder Nährstoffen?"

        st.session_state["chat_history"].append({"role": "assistant", "content": intro})

    for msg in st.session_state["chat_history"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if user_prompt := st.chat_input("Stelle eine Frage an deinen Coach..."):
        st.session_state["chat_history"].append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        prompt_low = user_prompt.lower()
        if "essen" in prompt_low or "rezept" in prompt_low or "hunger" in prompt_low:
            if tot_p < (user_goals['gewicht'] * 1.5):
                reply = "Empfehlung: Dir fehlt noch Protein! Wie wäre es mit Magerquark mit Beeren oder einem Hähnchen-/Tofusalat?"
            else:
                reply = "Dein Proteinstand ist top! Greif zu einer bunten Gemüsepfanne oder Nüssen für gesunde Fette."
        elif "trinken" in prompt_low or "wasser" in prompt_low:
            reply = f"Du hast {tot_w} ml getrunken. " + ("Super Ziel erreicht!" if tot_w >= user_goals['final_wasser'] else f"Dir fehlen noch {user_goals['final_wasser'] - tot_w} ml!")
        elif "notmodus" in prompt_low or "abnehmen" in prompt_low:
            reply = "Der Notmodus entsteht, wenn du dauerhaft unter deinem Grundumsatz (BMR) isst. Dann baut der Körper Muskeln ab und senkt den Stoffwechsel."
        else:
            reply = f"Basierend auf deinen Daten (Netto {net_k} kcal): Achte darauf, dein Proteinziel ({round(user_goals['gewicht']*1.5,1)}g) und deine Trinkmenge zu halten!"

        st.session_state["chat_history"].append({"role": "assistant", "content": reply})
        st.rerun()

# ==========================================
# REITER: PROFIL UND ZIELE
# ==========================================
elif selected_page == "Profil und Ziele":
    st.title(f"⚙️ Profil & Ziele für {user}")

    col_p1, col_p2 = st.columns(2)
    with col_p1:
        user_goals["geschlecht"] = st.selectbox("Geschlecht", ["Weiblich", "Männlich"], index=0 if user_goals["geschlecht"] == "Weiblich" else 1)
        user_goals["alter"] = st.number_input("Alter", value=user_goals["alter"])
        user_goals["groesse"] = st.number_input("Größe (cm)", value=user_goals["groesse"])
        user_goals["gewicht"] = st.number_input("Gewicht (kg)", value=user_goals["gewicht"], step=0.5)

    with col_p2:
        user_goals["aktivitaet"] = st.selectbox("Aktivität (PAL)", ["Ausschließlich sitzend / liegend", "Sitzt hauptsächlich (z. B. Büro)", "Sitzend, stehend / gehend", "Hauptsächlich stehend / gehend", "Körperlich anstrengende Arbeit"], index=1)
        user_goals["ziel"] = st.selectbox("Hauptziel", ["Gewicht halten", "Gewicht abnehmen", "Gewicht zunehmen / Muskelaufbau"])
        user_goals["besonderheit"] = st.selectbox("Besonderheiten", ["Keine", "Schwangerschaft", "Stillzeit"])
        user_goals["krankheit"] = st.checkbox("Krank / Regeneration (+10%)", value=user_goals.get("krankheit", False))

    st.write("---")
    c_k, c_w, c_b = calculate_user_needs(user_goals)
    st.metric("Berechneter Grundumsatz (BMR)", f"{c_b} kcal")
    st.metric("Ziel-Kalorien", f"{c_k} kcal")
    st.metric("Ziel-Wasser", f"{c_w} ml")

    if st.button("💾 Speichern"):
        user_goals["final_kcal"] = c_k
        user_goals["final_wasser"] = c_w
        st.success("Profil erfolgreich gespeichert!")

# ==========================================
# REITER: BARCODESCANNER
# ==========================================
elif selected_page == "Barcodescanner":
    if st.button("⬅️ Zurück zum Essen"):
        st.session_state["selected_page"] = "Essen"
        st.rerun()

    st.title("📷 Barcode Scanner")

    import streamlit.components.v1 as components
    scanner_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://unpkg.com/html5-qrcode" type="text/javascript"></script>
    </head>
    <body style="margin:0; background:transparent;">
        <div id="reader" style="width:100%; max-width:400px; margin:auto; border:2px solid #0E5E6F; border-radius:12px;"></div>
        <script>
            function onScanSuccess(decodedText) {
                window.parent.postMessage({type: 'streamlit:setComponentValue', value: decodedText}, '*');
            }
            let scanner = new Html5QrcodeScanner("reader", { fps: 10, qrbox: {width: 250, height: 150} }, false);
            scanner.render(onScanSuccess);
        </script>
    </body>
    </html>
    """
    components.html(scanner_html, height=320)

    manual_code = st.text_input("Manuelle Barcode-Eingabe:", placeholder="4008400401829")
    if manual_code:
        prod = search_open_food_facts(manual_code)
        if prod:
            st.success(f"Gefunden: **{prod['name']}** ({prod['kcal']} kcal / 100g)")
            g_val = st.number_input("Menge (g)", value=100)
            if st.button("➕ Zu Tagestracker hinzufügen"):
                factor = g_val / 100.0
                today_log["eaten"].append({"name": f"[Scan] {prod['name']} ({g_val}g)", "kcal": int(prod['kcal']*factor), "protein": round(prod['protein']*factor, 1)})
                st.success("Erfolgreich hinzugefügt!")
                st.session_state["selected_page"] = "Essen"
                st.rerun()