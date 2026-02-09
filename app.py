import streamlit as st
import os
import google.generativeai as genai
from PIL import Image

# --- CONFIGURATION PAGE ---
st.set_page_config(page_title="Agent CoPeDi", page_icon="📦", layout="wide")

# --- HEADER ---
st.title("📦 Dashboard Analyse Palette")
st.markdown("### 🔍 Agent Expert : Structure, Colisage & Dimensions")

# --- API KEY ---
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_KEY:
    st.error("🚨 Clé API manquante !")
    st.stop()

genai.configure(api_key=GEMINI_KEY)

# --- DÉTECTION AUTO DU MODÈLE ---
try:
    valid_models = []
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            valid_models.append(m.name)
    
    # Priorité au modèle Flash 1.5 pour la vitesse, sinon le Pro
    model_name = None
    for m in valid_models:
        if "flash" in m and "1.5" in m:
            model_name = m
            break
    if not model_name and valid_models:
        model_name = valid_models[0]
        
    model = genai.GenerativeModel(model_name)
    # Petit indicateur discret en bas de sidebar
    with st.sidebar:
        st.caption(f"🤖 Moteur IA : {model_name}")

except Exception as e:
    st.error(f"Erreur Google : {e}")
    st.stop()

# --- INTERFACE ---
col1, col2 = st.columns([1, 2])

with col1:
    uploaded_file = st.file_uploader("📸 Importez la photo", type=["jpg", "jpeg", "png"])
    if uploaded_file:
        image = Image.open(uploaded_file)
        # Optimisation image
        if image.width > 1024:
            ratio = 1024 / image.width
            image = image.resize((1024, int(image.height * ratio)))
        st.image(image, caption='Aperçu', use_container_width=True)

with col2:
    if uploaded_file and st.button("🚀 LANCER L'ANALYSE COMPLÈTE", type="primary", use_container_width=True):
        with st.spinner('🕵️‍♂️ Lecture des étiquettes et calcul de la structure...'):
            try:
                prompt = (
                    "Tu es un expert logistique précis. Analyse cette palette."
                    "1. LECTURE ÉTIQUETTE (CRUCIAL) : Zoom sur les étiquettes blanches. Cherche 'QTY', 'PCS', 'Item', ou un chiffre comme '6 per Carton'. C'est le nombre de pièces par carton."
                    "2. STRUCTURE : Détermine le schéma de palettisation. Combien de cartons en façade (Largeur) ? Combien en profondeur ? Combien de couches ?"
                    "3. CALCUL : (Largeur x Profondeur x Couches) + Cartons isolés sur le dessus."
                    
                    "Mise en forme OBLIGATOIRE en Markdown :"
                    "- Utilise un TABLEAU pour les dimensions."
                    "- Mets en gras les totaux."
                    "- Sois concis et professionnel."
                    
                    "Format de réponse attendu :"
                    "## 📊 RÉSULTATS D'ANALYSE\n"
                    "| Indicateur | Valeur |\n"
                    "| :--- | :--- |\n"
                    "| **📦 Nombre de Boîtes** | **[Total]** |\n"
                    "| **🔢 Pièces par Boîte** | [Qté lue sur étiquette] |\n"
                    "| **🎯 TOTAL PIÈCES** | **[Total x Qté]** |\n"
                    "| **⚖️ Poids Estimé** | [Poids Total] kg |\n\n"
                    
                    "### 🏗️ Détail de la Structure\n"
                    "- **Base** : [L] cartons (largeur) x [P] cartons (profondeur)\n"
                    "- **Hauteur** : [H] couches complètes\n"
                    "- **Vrac** : [N] cartons supplémentaires sur le dessus\n"
                    "- **Dimensions** : 120 x 80 x [Hauteur estimée] cm\n\n"
                    
                    "> **Observation** : [Une phrase sur la stabilité ou l'étiquette lue]"
                )

                response = model.generate_content([prompt, image])
                
                if response.text:
                    st.markdown(response.text)
                else:
                    st.warning("L'IA n'a pas renvoyé de résultat. Réessayez.")
                    
            except Exception as e:
                st.error(f"Erreur technique : {e}")

    elif not uploaded_file:
        st.info("👈 Commencez par charger une photo à gauche.")