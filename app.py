import streamlit as st
import os
import google.generativeai as genai
from PIL import Image

# --- CONFIGURATION PAGE ---
st.set_page_config(page_title="Agent CoPeDi", page_icon="📦", layout="wide")

# --- HEADER ---
st.title("📦 Dashboard Analyse Palette")
st.markdown("### 🔍 Agent Expert : Calcul Structurel & Colisage")

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
    
    # On force le modèle le plus intelligent disponible (Pro ou Flash 1.5)
    model_name = None
    for m in valid_models:
        if "flash" in m and "1.5" in m:
            model_name = m
            break
    if not model_name and valid_models:
        model_name = valid_models[0]
        
    model = genai.GenerativeModel(model_name)
    with st.sidebar:
        st.success(f"Cerveau connecté : {model_name}")

except Exception as e:
    st.error(f"Erreur Google : {e}")
    st.stop()

# --- INTERFACE ---
col1, col2 = st.columns([1, 2])

with col1:
    uploaded_file = st.file_uploader("📸 Importez la photo", type=["jpg", "jpeg", "png"])
    if uploaded_file:
        image = Image.open(uploaded_file)
        if image.width > 1024:
            ratio = 1024 / image.width
            image = image.resize((1024, int(image.height * ratio)))
        st.image(image, caption='Aperçu', use_container_width=True)

with col2:
    if uploaded_file and st.button("🚀 CALCULER LA STRUCTURE (Base x Hauteur)", type="primary", use_container_width=True):
        with st.spinner('📐 Analyse géométrique en cours...'):
            try:
                # --- PROMPT MATHÉMATIQUE STRICT ---
                prompt = (
                    "Tu es un expert en mathématiques logistiques. Ne compte pas les boîtes une par une (c'est interdit)."
                    "Utilise la méthode de MULTIPLICATION STRUCTURELLE :"
                    
                    "1. ANALYSE LA BASE (Le Sol) : Compte combien de cartons il y a sur la rangée de façade (Largeur) et sur la rangée de côté (Profondeur)."
                    "   -> Exemple : 4 en façade x 5 en profondeur = 20 par couche."
                    
                    "2. ANALYSE LA HAUTEUR : Compte le nombre de couches COMPLÈTES empilées les unes sur les autres."
                    "   -> Exemple : 4 couches."
                    
                    "3. LE RESTE : Ajoute les cartons isolés posés tout en haut."
                    
                    "4. LECTURE ÉTIQUETTE : Confirme le 'Qty per Carton' (ex: 6)."
                    
                    "5. CALCUL FINAL : (Largeur x Profondeur x Couches) + Reste = Total Boîtes."
                    
                    "Mise en forme Markdown stricte :"
                    "## 📊 RÉSULTATS CALCULÉS\n"
                    "| Indicateur | Valeur |\n"
                    "| :--- | :--- |\n"
                    "| **📦 Total Boîtes** | **[Résultat du calcul]** |\n"
                    "| **🔢 Pièces/Boîte** | [Lu sur étiquette] |\n"
                    "| **🎯 TOTAL PIÈCES** | **[Total Boîtes x Pièces/Boîte]** |\n"
                    "| **⚖️ Poids Estimé** | [Poids Total] kg |\n\n"
                    
                    "### 📐 Détail du Calcul\n"
                    "- **Grille au sol** : [L] (façade) x [P] (profondeur) = **[Base] boîtes/couche**\n"
                    "- **Hauteur** : x [H] couches complètes\n"
                    "- **Vrac** : + [Reste] boîtes sur le toit\n"
                    "- **Formule** : ([L] x [P] x [H]) + [Reste] = [Total]"
                )

                response = model.generate_content([prompt, image])
                
                if response.text:
                    st.markdown(response.text)
                else:
                    st.warning("Erreur d'analyse.")
                    
            except Exception as e:
                st.error(f"Erreur technique : {e}")

    elif not uploaded_file:
        st.info("👈 Chargez une photo pour commencer.")