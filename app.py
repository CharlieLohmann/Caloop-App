import streamlit as st
import pandas as pd
import requests
import json
import re
from datetime import datetime

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
        st.warning("Gemini SDK konnte nicht initialisiert werden. KI-Funktionen sind deaktiviert.")

# --- SESSION STATE INITIALISIERUNG ---
if "current_page" not in st.session_state:
    st.session_state["current_page"] = "Übersicht"

if "user_goals" not in st.session_state:
    st.session_state["user_goals"] = {
        "name": "Benutzer",
        "gewicht": 75.0,
        "ziel": "Halten",
        "final_kcal": 2200,
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

# Helfer zur Seitennavigation
def go_to_page(page_name):
    st.session_state["current_page"] = page_name

# Short-Handles für einfacheren Zugriff im Code
user_goals = st.session_state["user_goals"]
today_log = st.session_state["today_log"]
user = user_goals["name"]

# ==========================================
# 2. HELFER-FUNKTIONEN (KI & DATENBANK)
# ==========================================

def analyze_food_with_ai(prompt_text):
    """Sendet die Speiseanfrage an Gemini und erwartet eine strukturierte JSON-Antwort."""
    if not gemini_client:
        return None
    try:
        sys_prompt = """
        Du bist ein präziser Ernährungs-Assistent. Analysiere die Eingabe für ein Lebensmittel oder ein Gericht.
        Schätze die Gesamtnährwerte für die angegebene Menge.
        Antworte AUSSCHLIESSLICH im folgenden JSON-Format ohne zusätzlichen Text oder Markdown-Blöcke:
        {
            "name": "Name des Gerichts/Lebensmittels",
            "gramm": 200,
            "kcal": 120,
            "protein": 8.0,
            "carbs": 10.0,
            "fat": 3.6,
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
    except Exception as e:
        print(f"Gemini API Fehler: {e}")
        return None

def search_open_food_facts(query_text):
    """Durchsucht OpenFoodFacts. Bereinigt Mengenangaben aus dem Suchstring für bessere Ergebnisse."""
    # Entfernt Zahlen, Einheiten und Prozente aus dem Suchbegriff
    clean_query = re.sub(r'\b\d+([.,]\d+)?\s*(g|gr|gramm|ml|l|kg|%)\b', '', query_text, flags=re.IGNORECASE)
    clean_query = re.sub(r'\b\d+([.,]\d+)?\b', '', clean_query).strip()
    search_term = clean_query if clean_query else query_text

    url = "[https://world.openfoodfacts.org/cgi/search.pl](https://world.openfoodfacts.org/cgi/search.pl)"
    params = {
        "search_terms": search_term,
        "search_simple": 1,
        "action": "process",
        "json": 1,
        "page_size": 3
    }
    headers = {"User-Agent": "CaloopApp/2.0"}
    
    try:
        res = requests.get(url, params=params, headers=headers, timeout=4)
        data = res.json()
        if data.get("products"):
            prod = data["products"][0]
            nut = prod.get("nutriments", {})
            
            kcal_100 = float(nut.get("energy-kcal_100g", nut.get("energy-kcal", 0)))
            prot_100 = float(nut.get("proteins_100g", 0.0))
            carbs_100 = float(nut.get("carbohydrates_100g", 0.0))
            fat_100 = float(nut.get("fat_100g", 0.0))
            fiber_100 = float(nut.get("fiber_100g", 0.0))

            return {
                "name": prod.get("product_name", search_term.capitalize()),
                "kcal": kcal_100,
                "protein": prot_100,
                "carbs": carbs_100,
                "fat": fat_100,
                "fiber": fiber_100
            }
    except Exception as e:
        print(f"OpenFoodFacts Fehler: {e}")
    return None

# ==========================================
# 3. SIDEBAR NAVIGATION & LOGO
# ==========================================
with st.sidebar:
    st.title("🥑 Caloop")
    st.caption(f"Angemeldet als **{user}**")
    st.write("---")
    
    # Navigations-Buttons
    pages = ["Übersicht", "Essen", "Trinken", "Bewegung", "Favoriten", "Feedback", "Profil"]
    for p in pages:
        btn_style = "primary" if st.session_state["current_page"] == p else "secondary"
        if st.button(p, key=f"nav_{p}", type=btn_style, use_container_width=True):
            go_to_page(p)
            st.rerun()

selected_page = st.session_state["current_page"]

# ==========================================
# 4. REITER-STEUERUNG
# ==========================================

# ------------------------------------------
# REITER: ÜBERSICHT
# ------------------------------------------
if selected_page == "Übersicht":
    st.title(f"👋 Hallo, {user}!")
    st.write("Hier ist deine heutige Tagesbilanz:")

    tot_kcal = sum(i.get("kcal", 0) for i in today_log["eaten"])
    tot_prot = sum(i.get("protein", 0.0) for i in today_log["eaten"])
    burned = today_log["bewegung_kcal"]
    net_kcal = max(0, tot_kcal - burned)
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Aufgenommen", f"{tot_kcal} kcal")
    col2.metric("Verbrannt", f"{burned} kcal")
    col3.metric("Netto-Kalorien", f"{net_kcal} / {user_goals['final_kcal']} kcal")
    col4.metric("Protein", f"{tot_prot:.1f} g")

    st.write("---")
    
    c_left, c_right = st.columns(2)
    with c_left:
        st.subheader("🥤 Wasser-Tracker")
        st.progress(min(1.0, today_log["wasser_ml"] / max(1, user_goals["final_wasser"])))
        st.write(f"**{today_log['wasser_ml']} / {user_goals['final_wasser']} ml**")
        if st.button("➕ 250 ml getrunken"):
            today_log["wasser_ml"] += 250
            st.rerun()

    with c_right:
        st.subheader("⚡ Schnellauswahl")
        c1, c2 = st.columns(2)
        if c1.button("🍽️ Essen erfassen", use_container_width=True):
            go_to_page("Essen")
            st.rerun()
        if c2.button("🏃 Bewegung erfassen", use_container_width=True):
            go_to_page("Bewegung")
            st.rerun()

# ------------------------------------------
# REITER: ESSEN (Optimierte Eingabe)
# ------------------------------------------
elif selected_page == "Essen":
    if st.button("⬅️ Zurück zur Übersicht"):
        go_to_page("Übersicht")
        st.rerun()

    st.title("🍽️ Essen erfassen")

    if st.button("📷 Barcode scannen"):
        go_to_page("Barcodescanner")
        st.rerun()

    st.write("---")
    
    target_dest = st.radio("Speichern in:", ["Tagestracker", "Favoriten"], horizontal=True)
    kat = st.selectbox("Mahlzeit", ["Frühstück", "Mittagessen", "Abendessen", "Snack"])

    tab1, tab2 = st.tabs(["🤖 KI & Produktsuche", "✏️ Manuell"])

    with tab1:
        txt = st.text_input("Zutat / Lebensmittel", placeholder="z. B. Joghurt 1,8% oder Haferflocken")
        
        c_menge, c_einheit = st.columns([1, 1])
        with c_menge:
            menge_val = st.number_input("Menge", min_value=1, value=200, step=10)
        with c_einheit:
            einheit_val = st.selectbox("Einheit", ["g", "ml", "Stück", "EL", "TL", "Portion", "Prise"])

        if st.button("🔍 Suchen & Erfassen", type="primary"):
            if txt:
                full_prompt = f"{menge_val} {einheit_val} {txt}"
                
                # 1. KI-Analyse
                ai_result = None
                if gemini_client:
                    with st.spinner("Nährwerte werden ermittelt..."):
                        ai_result = analyze_food_with_ai(full_prompt)
                
                if ai_result:
                    p_name = ai_result.get("name", txt)
                    p_kcal = ai_result.get("kcal", 0)
                    p_prot = ai_result.get("protein", 0.0)
                    p_carbs = ai_result.get("carbs", 0.0)
                    p_fat = ai_result.get("fat", 0.0)
                    p_fiber = ai_result.get("fiber", 0.0)

                    item_data = {
                        "name": f"[{kat}] {p_name} ({menge_val}{einheit_val})",
                        "kcal": p_kcal,
                        "protein": p_prot,
                        "carbs": p_carbs,
                        "fat": p_fat,
                        "fiber": p_fiber
                    }

                    if target_dest == "Tagestracker":
                        today_log["eaten"].append(item_data)
                        st.success(f"✅ **{p_name}** ({menge_val}{einheit_val}) ~{p_kcal} kcal hinzugefügt!")
                    else:
                        st.session_state["favorites_all"].append({"typ": "Mahlzeit", **item_data})
                        st.success(f"⭐ **{p_name}** zu Favoriten hinzugefügt!")
                
                # 2. Fallback: OpenFoodFacts
                else:
                    with st.spinner("Suche in Lebensmittel-Datenbank..."):
                        prod = search_open_food_facts(txt)
                    
                    if prod:
                        unit_weights = {"g": 1, "ml": 1, "Stück": 100, "EL": 15, "TL": 5, "Portion": 150, "Prise": 2}
                        calc_gramm = menge_val * unit_weights.get(einheit_val, 1)
                        factor = calc_gramm / 100.0
                        
                        calc_kcal = int(prod['kcal'] * factor)
                        calc_prot = round(prod['protein'] * factor, 1)
                        calc_carbs = round(prod['carbs'] * factor, 1)
                        calc_fat = round(prod['fat'] * factor, 1)
                        calc_fiber = round(prod['fiber'] * factor, 1)

                        item_data = {
                            "name": f"[{kat}] {prod['name']} ({menge_val}{einheit_val})",
                            "kcal": calc_kcal,
                            "protein": calc_prot,
                            "carbs": calc_carbs,
                            "fat": calc_fat,
                            "fiber": calc_fiber
                        }

                        if target_dest == "Tagestracker":
                            today_log["eaten"].append(item_data)
                            st.success(f"✅ Datenbank-Treffer: **{prod['name']}** ({calc_kcal} kcal) hinzugefügt!")
                        else:
                            st.session_state["favorites_all"].append({"typ": "Zutat", **item_data})
                            st.success(f"⭐ Zu Favoriten hinzugefügt!")
                    else:
                        st.error("Kein Treffer gefunden. Nutze bitte die manuelle Eingabe.")

    with tab2:
        m_name = st.text_input("Name der Speise")
        m_kcal = st.number_input("Kalorien (kcal)", min_value=0, value=250)
        m_prot = st.number_input("Protein (g)", min_value=0.0, value=10.0, step=0.5)
        m_carbs = st.number_input("Kohlenhydrate (g)", min_value=0.0, value=20.0, step=0.5)
        m_fat = st.number_input("Fett (g)", min_value=0.0, value=5.0, step=0.5)

        if st.button("Speichern"):
            if m_name:
                item_data = {
                    "name": f"[{kat}] {m_name}",
                    "kcal": m_kcal,
                    "protein": m_prot,
                    "carbs": m_carbs,
                    "fat": m_fat,
                    "fiber": 0.0
                }
                if target_dest == "Tagestracker":
                    today_log["eaten"].append(item_data)
                    st.success(f"✅ {m_name} hinzugefügt!")
                else:
                    st.session_state["favorites_all"].append({"typ": "Mahlzeit", **item_data})
                    st.success(f"⭐ Zu Favoriten hinzugefügt!")

# ------------------------------------------
# REITER: TRINKEN
# ------------------------------------------
elif selected_page == "Trinken":
    st.title("🥤 Wasser-Tracker")
    
    st.metric("Bereits getrunken", f"{today_log['wasser_ml']} ml", f"Ziel: {user_goals['final_wasser']} ml")
    st.progress(min(1.0, today_log["wasser_ml"] / max(1, user_goals["final_wasser"])))

    st.write("---")
    c1, c2, c3 = st.columns(3)
    if c1.button("➕ 250 ml (Glas)", use_container_width=True):
        today_log["wasser_ml"] += 250
        st.rerun()
    if c2.button("➕ 500 ml (Flasche)", use_container_width=True):
        today_log["wasser_ml"] += 500
        st.rerun()
    if c3.button("➕ 750 ml (Große Flasche)", use_container_width=True):
        today_log["wasser_ml"] += 750
        st.rerun()

# ------------------------------------------
# REITER: BEWEGUNG
# ------------------------------------------
elif selected_page == "Bewegung":
    st.title("🏃 Bewegung & Sport")
    
    aktivitaeten = {
        "Gehen (normal)": 3.5,
        "Joggen": 8.0,
        "Radfahren": 6.0,
        "Krafttraining": 5.0,
        "Schwimmen": 7.0
    }
    
    act = st.selectbox("Aktivität wählen", list(aktivitaeten.keys()))
    duration = st.number_input("Dauer in Minuten", min_value=5, value=30, step=5)
    
    # MET-Berechnung: (MET * 3.5 * Gewicht_kg / 200) * Minuten
    met = aktivitaeten[act]
    burned_kcal = int((met * 3.5 * user_goals["gewicht"] / 200) * duration)
    
    st.info(f"Geschätzter Verbrauch: **~{burned_kcal} kcal**")
    
    if st.button("Aktivität eintragen", type="primary"):
        today_log["bewegung_kcal"] += burned_kcal
        st.success(f"✅ {duration} Min. {act} ({burned_kcal} kcal) verbucht!")

# ------------------------------------------
# REITER: FAVORITEN
# ------------------------------------------
elif selected_page == "Favoriten":
    st.title("⭐ Favoriten")
    
    if not st.session_state["favorites_all"]:
        st.info("Du hast noch keine Favoriten gespeichert. Du kannst beim Erfassen von Essen neue Favoriten anlegen.")
    else:
        for idx, fav in enumerate(st.session_state["favorites_all"]):
            c_info, c_act = st.columns([3, 1])
            with c_info:
                st.write(f"**{fav['name']}** ({fav.get('kcal', 0)} kcal, {fav.get('protein', 0)}g Protein)")
            with c_act:
                if st.button("➕ Hinzufügen", key=f"add_fav_{idx}"):
                    today_log["eaten"].append(fav)
                    st.success(f"{fav['name']} hinzugefügt!")

# ------------------------------------------
# REITER: FEEDBACK (Detail-Analyse & KI-Coach)
# ------------------------------------------
elif selected_page == "Feedback":
    st.title("📊 Nährstoff-Feedback & Tagesanalyse")

    weight = user_goals["gewicht"]
    target_kcal = user_goals["final_kcal"]
    
    # Automatische Richtwerte
    target_protein_g = round(weight * 1.5, 1)
    target_fat_g = round((target_kcal * 0.30) / 9.0, 1)
    target_carbs_g = round((target_kcal - (target_protein_g * 4) - (target_fat_g * 9)) / 4.0, 1)
    target_fiber_g = 30.0

    # Aufsummierung
    tot_kcal = sum(i.get("kcal", 0) for i in today_log["eaten"])
    tot_prot = sum(i.get("protein", 0.0) for i in today_log["eaten"])
    tot_carbs = sum(i.get("carbs", 0.0) for i in today_log["eaten"])
    tot_fat = sum(i.get("fat", 0.0) for i in today_log["eaten"])
    tot_fiber = sum(i.get("fiber", 0.0) for i in today_log["eaten"])
    
    net_kcal = max(0, tot_kcal - today_log["bewegung_kcal"])

    # 1. Getrackte Speisen
    st.subheader("🍽️ Heute verzehrte Speisen")
    if today_log["eaten"]:
        food_df = pd.DataFrame(today_log["eaten"])
        show_cols = [c for c in ["name", "kcal", "protein", "carbs", "fat"] if c in food_df.columns]
        food_df_display = food_df[show_cols].rename(columns={
            "name": "Gericht / Zutat",
            "kcal": "Kalorien (kcal)",
            "protein": "Protein (g)",
            "carbs": "Kohlenhydrate (g)",
            "fat": "Fett (g)"
        })
        st.dataframe(food_df_display, use_container_width=True, hide_index=True)
    else:
        st.info("Heute wurden noch keine Speisen im Tagestracker erfasst.")

    st.write("---")

    # 2. Makro & Mikro Prozentübersicht
    st.subheader("🎯 Erreichung des Tagesbedarfs")

    col_m1, col_m2 = st.columns(2)

    with col_m1:
        st.markdown("### 🥗 Makronährstoffe")
        
        kcal_pct = min(100, int((net_kcal / max(1, target_kcal)) * 100))
        st.write(f"**Kalorien (Netto):** {net_kcal} / {target_kcal} kcal ({kcal_pct}%)")
        st.progress(kcal_pct / 100)

        prot_pct = min(100, int((tot_prot / max(1, target_protein_g)) * 100))
        st.write(f"**Protein:** {tot_prot:.1f}g / {target_protein_g}g ({prot_pct}%)")
        st.progress(prot_pct / 100)

        carbs_pct = min(100, int((tot_carbs / max(1, target_carbs_g)) * 100))
        st.write(f"**Kohlenhydrate:** {tot_carbs:.1f}g / {target_carbs_g}g ({carbs_pct}%)")
        st.progress(carbs_pct / 100)

        fat_pct = min(100, int((tot_fat / max(1, target_fat_g)) * 100))
        st.write(f"**Fett:** {tot_fat:.1f}g / {target_fat_g}g ({fat_pct}%)")
        st.progress(fat_pct / 100)

    with col_m2:
        st.markdown("### 🌾 Mikronährstoffe & Wasser")

        tot_w = today_log["wasser_ml"]
        target_w = user_goals["final_wasser"]
        water_pct = min(100, int((tot_w / max(1, target_w)) * 100))
        st.write(f"**Wasser:** {tot_w} / {target_w} ml ({water_pct}%)")
        st.progress(water_pct / 100)

        fiber_pct = min(100, int((tot_fiber / max(1, target_fiber_g)) * 100))
        st.write(f"**Ballaststoffe:** {tot_fiber:.1f}g / {target_fiber_g}g ({fiber_pct}%)")
        st.progress(fiber_pct / 100)

    st.write("---")

    # 3. KI-Coach Chatbot
    st.subheader("🤖 Caloop Feedback Coach")

    if not st.session_state["chat_history"]:
        intro = f"Hallo {user}! 👋 Hier ist dein Tagesüberblick:\n\n"
        intro += f"- **Kalorien:** {net_kcal} / {target_kcal} kcal ({kcal_pct}%)\n"
        intro += f"- **Protein:** {tot_prot:.1f} / {target_protein_g}g ({prot_pct}%)\n\n"
        intro += "Frag mich gerne nach Empfehlungen für deine nächsten Mahlzeiten!"
        st.session_state["chat_history"].append({"role": "assistant", "content": intro})

    for msg in st.session_state["chat_history"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if user_prompt := st.chat_input("Frage an den Coach stellen..."):
        st.session_state["chat_history"].append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        prompt_low = user_prompt.lower()
        if "essen" in prompt_low or "rezept" in prompt_low or "hunger" in prompt_low:
            if tot_prot < target_protein_g:
                reply = f"Dir fehlen noch ca. {round(target_protein_g - tot_prot, 1)}g Protein. Perfekt wären jetzt Magerquark, Hähnchenbrust oder ein Proteinshake!"
            else:
                reply = "Dein Proteinziel ist bereits erreicht! Greif zu frischem Gemüse oder Nüssen."
        else:
            reply = f"Du hast bisher {net_kcal} kcal ({kcal_pct}% deines Tagesbedarfs) erreicht."

        st.session_state["chat_history"].append({"role": "assistant", "content": reply})
        st.rerun()

# ------------------------------------------
# REITER: PROFIL
# ------------------------------------------
elif selected_page == "Profil":
    st.title("⚙️ Einstellungen & Profil")
    
    user_goals["name"] = st.text_input("Dein Name", value=user_goals["name"])
    user_goals["gewicht"] = st.number_input("Gewicht (kg)", min_value=30.0, value=float(user_goals["gewicht"]), step=0.5)
    user_goals["final_kcal"] = st.number_input("Tagesziel Kalorien (kcal)", min_value=1000, value=int(user_goals["final_kcal"]), step=50)
    user_goals["final_wasser"] = st.number_input("Tagesziel Wasser (ml)", min_value=1000, value=int(user_goals["final_wasser"]), step=100)

    if st.button("Speichern", type="primary"):
        st.success("Profil erfolgreich aktualisiert!")