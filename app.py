import streamlit as st
import pandas as pd
import requests
import json
import re
import plotly.graph_objects as go

# ==========================================
# 1. STREAMLIT CONFIG & INITIALISIERUNG
# ==========================================
st.set_page_config(
    page_title="Caloop - Fitness & Nutrition Tracker",
    page_icon="🥑",
    layout="wide"
)

# --- GEMINI CLIENT SETUP ---
gemini_client = None
if "GEMINI_API_KEY" in st.secrets:
    try:
        from google import genai
        gemini_client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    except Exception as e:
        pass

# --- SESSION STATE INITIALISIERUNG ---
if "current_page" not in st.session_state:
    st.session_state["current_page"] = "Übersicht"

if "user_goals" not in st.session_state:
    st.session_state["user_goals"] = {
        "name": "Benutzer",
        "alter": 30,
        "geschlecht": "Weiblich",
        "groesse": 170,
        "gewicht": 70.0,
        "ziel": "Gewicht halten",
        "phase": "Keine",  # Keine, Schwanger, Stillend
        "erkrankungen": "",
        "final_kcal": 2000,
        "final_wasser": 2500
    }

if "today_log" not in st.session_state:
    st.session_state["today_log"] = {
        "eaten": [],
        "bewegung_kcal": 0,
        "wasser_ml": 0
    }

if "favorites_all" not in st.session_state:
    st.session_state["favorites_all"] = []

if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []

def go_to_page(page_name):
    st.session_state["current_page"] = page_name

user_goals = st.session_state["user_goals"]
today_log = st.session_state["today_log"]
user = user_goals["name"]

# ==========================================
# 2. KI & DATENBANK-LOGIK (AUTOMATISCH)
# ==========================================

def analyze_food_auto(prompt_text):
    """Versucht zuerst die KI-Analyse, nutzt OpenFoodFacts als Backup."""
    # 1. Versuch mit Gemini KI
    if gemini_client:
        try:
            sys_prompt = """
            Du bist ein Ernährungs-Assistent. Analysiere den Freitext des Nutzers für ein Lebensmittel oder Gericht.
            Schätze die genauen Gesamtnährwerte für die angegebene Menge.
            Antworte AUSSCHLIESSLICH als JSON ohne Markdown-Formatierung:
            {
                "name": "Name des Lebensmittels/Gerichts",
                "kcal": 150,
                "protein": 8.5,
                "carbs": 12.0,
                "fat": 3.2,
                "fiber": 2.0
            }
            """
            response = gemini_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=f"{sys_prompt}\n\nEingabe: {prompt_text}"
            )
            raw_text = response.text.strip()
            if raw_text.startswith("```"):
                raw_text = re.sub(r"^```[a-z]*\n?", "", raw_text)
                raw_text = re.sub(r"\n?```$", "", raw_text)
            return json.loads(raw_text.strip())
        except Exception:
            pass

    # 2. Fallback auf OpenFoodFacts
    clean_query = re.sub(r'\b\d+([.,]\d+)?\s*(g|gr|gramm|ml|l|kg|%)\b', '', prompt_text, flags=re.IGNORECASE)
    clean_query = re.sub(r'\b\d+([.,]\d+)?\b', '', clean_query).strip()
    search_term = clean_query if clean_query else prompt_text

    try:
        url = "[https://world.openfoodfacts.org/cgi/search.pl](https://world.openfoodfacts.org/cgi/search.pl)"
        params = {"search_terms": search_term, "search_simple": 1, "action": "process", "json": 1, "page_size": 1}
        res = requests.get(url, params=params, headers={"User-Agent": "CaloopApp/2.0"}, timeout=4).json()
        
        if res.get("products"):
            prod = res["products"][0]
            nut = prod.get("nutriments", {})
            
            # Versuche Menge aus Text zu extrahieren, sonst 100g
            gramm_match = re.search(r'(\d+)\s*(g|gr|gramm|ml)', prompt_text, re.IGNORECASE)
            factor = (float(gramm_match.group(1)) / 100.0) if gramm_match else 1.0

            kcal_100 = float(nut.get("energy-kcal_100g", nut.get("energy-kcal", 0)))
            return {
                "name": prod.get("product_name", search_term.capitalize()),
                "kcal": int(kcal_100 * factor),
                "protein": round(float(nut.get("proteins_100g", 0)) * factor, 1),
                "carbs": round(float(nut.get("carbohydrates_100g", 0)) * factor, 1),
                "fat": round(float(nut.get("fat_100g", 0)) * factor, 1),
                "fiber": round(float(nut.get("fiber_100g", 0)) * factor, 1)
            }
    except Exception:
        pass

    return None

# ==========================================
# 3. RINGDIAGRAMM MIT WASSERSTAND (PLOTLY)
# ==========================================

def create_ring_water_chart(consumed_kcal, target_kcal, water_ml, target_water):
    # Prozentwerte berechnen
    kcal_pct = min(100, (consumed_kcal / max(1, target_kcal)) * 100)
    water_pct = min(100, (water_ml / max(1, target_water)) * 100)
    remaining_kcal = max(0, target_kcal - consumed_kcal)

    fig = go.Figure()

    # Outer Ring: Kalorien (Donut Chart)
    fig.add_trace(go.Pie(
        labels=["Aufgenommen", "Verbleibend"],
        values=[consumed_kcal, remaining_kcal],
        hole=0.68,
        marker=dict(colors=["#FF6B6B", "#E0E0E0"]),
        textinfo="none",
        hoverinfo="label+value",
        showlegend=False
    ))

    # Inner Fill: Wasserstand als blaue Form im Loch
    # Berechne Höhe des Wasserschnitts (-0.68 bis +0.68)
    water_height = -0.68 + (1.36 * (water_pct / 100.0))
    
    fig.add_shape(
        type="rect",
        xref="paper", yref="y",
        x0=0.35, x1=0.65,
        y0=-0.68, y1=water_height,
        fillcolor="rgba(52, 152, 219, 0.6)",
        line=dict(width=0),
        layer="below"
    )

    # Text in der Mitte
    fig.add_annotation(
        text=f"<b>{consumed_kcal} / {target_kcal}</b><br>kcal<br><br><span style='color:#2980B9;'>💧 {water_ml} ml</span>",
        x=0.5, y=0.5,
        showarrow=False,
        font=dict(size=16, color="#2C3E50"),
        align="center"
    )

    fig.update_layout(
        margin=dict(t=10, b=10, l=10, r=10),
        height=280,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )
    return fig

# ==========================================
# 4. SIDEBAR NAVIGATION
# ==========================================
with st.sidebar:
    st.title("🥑 Caloop")
    st.caption(f"Angemeldet als **{user}**")
    st.write("---")
    
    pages = ["Übersicht", "Essen", "Trinken", "Bewegung", "Favoriten", "Feedback", "Profil"]
    for p in pages:
        btn_type = "primary" if st.session_state["current_page"] == p else "secondary"
        if st.button(p, key=f"nav_{p}", type=btn_type, use_container_width=True):
            go_to_page(p)
            st.rerun()

selected_page = st.session_state["current_page"]

# ==========================================
# 5. REITER-STEUERUNG
# ==========================================

# ------------------------------------------
# REITER: ÜBERSICHT
# ------------------------------------------
if selected_page == "Übersicht":
    st.title(f"👋 Hallo, {user}!")
    
    tot_kcal = sum(i.get("kcal", 0) for i in today_log["eaten"])
    tot_prot = sum(i.get("protein", 0.0) for i in today_log["eaten"])
    burned = today_log["bewegung_kcal"]
    net_kcal = max(0, tot_kcal - burned)

    col_chart, col_stats = st.columns([1, 1])

    with col_chart:
        st.subheader("🎯 Kalorien & Wasser im Ring")
        chart = create_ring_water_chart(tot_kcal, user_goals["final_kcal"], today_log["wasser_ml"], user_goals["final_wasser"])
        st.plotly_chart(chart, use_container_width=True)

    with col_stats:
        st.subheader("📊 Tageswerte")
        st.metric("Gegessen", f"{tot_kcal} kcal")
        st.metric("Verbrannt (Sport)", f"{burned} kcal")
        st.metric("Netto-Kalorien", f"{net_kcal} / {user_goals['final_kcal']} kcal")
        st.metric("Protein", f"{tot_prot:.1f} g")

# ------------------------------------------
# REITER: ESSEN (AUTOMATISCH & EINFACH)
# ------------------------------------------
elif selected_page == "Essen":
    st.title("🍽️ Essen erfassen")
    
    target_dest = st.radio("Speichern in:", ["Tagestracker", "Favoriten"], horizontal=True)
    kat = st.selectbox("Mahlzeit", ["Frühstück", "Mittagessen", "Abendessen", "Snack"])

    st.write("---")
    
    food_input = st.text_input("Was hast du gegessen?", placeholder="z. B. 200 g Joghurt 1,8% Fett oder 2 Scheiben Vollkornbrot mit Käse")

    if st.button("🚀 Automatisch erfassen", type="primary", use_container_width=True):
        if food_input:
            with st.spinner("Nährwerte werden ermittelt..."):
                result = analyze_food_auto(food_input)
            
            if result:
                item_data = {
                    "name": f"[{kat}] {result['name']}",
                    "kcal": result.get("kcal", 0),
                    "protein": result.get("protein", 0.0),
                    "carbs": result.get("carbs", 0.0),
                    "fat": result.get("fat", 0.0),
                    "fiber": result.get("fiber", 0.0)
                }

                if target_dest == "Tagestracker":
                    today_log["eaten"].append(item_data)
                    st.success(f"✅ **{result['name']}** ({result['kcal']} kcal, {result['protein']}g Protein) verbucht!")
                else:
                    st.session_state["favorites_all"].append({"typ": "Mahlzeit", **item_data})
                    st.success(f"⭐ **{result['name']}** zu Favoriten hinzugefügt!")
            else:
                st.error("Konnte nicht verarbeitet werden. Bitte versuche es genauer zu beschreiben.")

# ------------------------------------------
# REITER: TRINKEN
# ------------------------------------------
elif selected_page == "Trinken":
    st.title("🥤 Wasser-Tracker")
    st.metric("Bereits getrunken", f"{today_log['wasser_ml']} ml", f"Ziel: {user_goals['final_wasser']} ml")
    
    c1, c2, c3 = st.columns(3)
    if c1.button("➕ 250 ml", use_container_width=True):
        today_log["wasser_ml"] += 250
        st.rerun()
    if c2.button("➕ 500 ml", use_container_width=True):
        today_log["wasser_ml"] += 500
        st.rerun()
    if c3.button("➕ 750 ml", use_container_width=True):
        today_log["wasser_ml"] += 750
        st.rerun()

# ------------------------------------------
# REITER: BEWEGUNG
# ------------------------------------------
elif selected_page == "Bewegung":
    st.title("🏃 Bewegung")
    act = st.selectbox("Aktivität", ["Gehen", "Joggen", "Radfahren", "Krafttraining", "Schwimmen"])
    duration = st.number_input("Dauer (Minuten)", min_value=5, value=30, step=5)
    
    mets = {"Gehen": 3.5, "Joggen": 8.0, "Radfahren": 6.0, "Krafttraining": 5.0, "Schwimmen": 7.0}
    burned = int((mets[act] * 3.5 * user_goals["gewicht"] / 200) * duration)
    
    if st.button(f"Eintragen (~{burned} kcal)"):
        today_log["bewegung_kcal"] += burned
        st.success("Aktivität verbucht!")

# ------------------------------------------
# REITER: FAVORITEN
# ------------------------------------------
elif selected_page == "Favoriten":
    st.title("⭐ Favoriten")
    if not st.session_state["favorites_all"]:
        st.info("Noch keine Favoriten vorhanden.")
    else:
        for idx, fav in enumerate(st.session_state["favorites_all"]):
            c_info, c_act = st.columns([3, 1])
            c_info.write(f"**{fav['name']}** ({fav.get('kcal', 0)} kcal)")
            if c_act.button("➕ Essen", key=f"fav_{idx}"):
                today_log["eaten"].append(fav)
                st.success("Hinzugefügt!")

# ------------------------------------------
# REITER: FEEDBACK
# ------------------------------------------
elif selected_page == "Feedback":
    st.title("📊 Feedback & Nährstoffe")
    
    if today_log["eaten"]:
        st.dataframe(pd.DataFrame(today_log["eaten"])[["name", "kcal", "protein", "carbs", "fat"]], use_container_width=True)
    else:
        st.info("Noch keine Speisen heute getrackt.")

# ------------------------------------------
# REITER: PROFIL (UMFASSENDE PERSÖNLICHE DATEN)
# ------------------------------------------
elif selected_page == "Profil":
    st.title("⚙️ Profil & Gesundheitseinstellungen")
    
    with st.form("profile_form"):
        st.subheader("Persönliche Stammdaten")
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("Name", value=user_goals["name"])
            alter = st.number_input("Alter", min_value=10, max_value=120, value=user_goals["alter"])
            geschlecht = st.selectbox("Geschlecht", ["Weiblich", "Männlich", "Divers"], index=["Weiblich", "Männlich", "Divers"].index(user_goals["geschlecht"]))
        with c2:
            groesse = st.number_input("Größe (cm)", min_value=100, max_value=230, value=user_goals["groesse"])
            gewicht = st.number_input("Gewicht (kg)", min_value=30.0, max_value=250.0, value=float(user_goals["gewicht"]), step=0.5)
            ziel = st.selectbox("Ziel", ["Gewicht halten", "Abnehmen", "Zunehmen"], index=["Gewicht halten", "Abnehmen", "Zunehmen"].index(user_goals["ziel"]))

        st.write("---")
        st.subheader("Frauengesundheit & Besondere Phasen")
        phase = st.selectbox("Aktuelle Lebensphase", ["Keine", "Schwangerschaft (1. Trimester)", "Schwangerschaft (2./3. Trimester)", "Stillzeit"], index=0)

        st.write("---")
        st.subheader("Gesundheit & Erkrankungen")
        erkrankungen = st.text_area("Vorerkrankungen / Hinweise (z. B. Diabetes, Schilddrüsenunterfunktion, Unverträglichkeiten)", value=user_goals["erkrankungen"], placeholder="Hier eintragen...")

        submit = st.form_submit_button("Speichern & Ziele berechnen", type="primary")

        if submit:
            # BMR Berechnung (Harris-Benedict)
            if geschlecht == "Männlich":
                bmr = 88.362 + (13.397 * gewicht) + (4.799 * groesse) - (5.677 * alter)
            else:
                bmr = 447.593 + (9.247 * gewicht) + (3.098 * groesse) - (4.330 * alter)

            calc_kcal = bmr * 1.35  # Leichte Aktivität
            calc_wasser = gewicht * 35.0  # 35ml pro kg

            # Aufschläge Schwangerschaft / Stillzeit
            if "2./3. Trimester" in phase:
                calc_kcal += 300
                calc_wasser += 300
            elif "Stillzeit" in phase:
                calc_kcal += 500
                calc_wasser += 600

            # Anpassung Ziel
            if ziel == "Abnehmen":
                calc_kcal -= 400
            elif ziel == "Zunehmen":
                calc_kcal += 300

            user_goals.update({
                "name": name, "alter": alter, "geschlecht": geschlecht,
                "groesse": groesse, "gewicht": gewicht, "ziel": ziel,
                "phase": phase, "erkrankungen": erkrankungen,
                "final_kcal": int(calc_kcal),
                "final_wasser": int(calc_wasser)
            })
            st.success("Profil erfolgreich gespeichert und Tagesbedarf neu berechnet!")