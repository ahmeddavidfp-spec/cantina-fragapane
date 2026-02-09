import streamlit as st
import os
import google.generativeai as genai
from PIL import Image

# --- CONFIGURATION ---
st.set_page_config(page_title="Agent CoPeDi", page_icon="📦")
st.title("📦 Agent CoPeDi (Standard)")

# --- API KEY ---
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_KEY:
    st.error("🚨 Clé API manquante !")
    st.stop()

# --- MODÈLE UNIVERSEL (Anti-404) ---
genai.configure(api_key=GEMINI_KEY)
# On utilise 'gemini-pro' qui est disponible partout sans erreur 404
model = genai.GenerativeModel('gemini-pro')

# --- INTERFACE ---
uploaded_file = st.file_uploader("📸 Chargez votre photo", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    
    # Optimisation taille (Anti-Crash 502)
    max_width = 1024
    if image.width > max_width:
        ratio = max_width / image.width
        new_height = int(image.height * ratio)
        image = image.resize((max_width, new_height))
    
    st.image(image, caption='Votre palette', use_container_width=True)

    if st.button("🚀 Compter les cartons", type="primary"):
        with st.spinner('🔍 Analyse structurelle en cours...'):
            try:
                # Prompt spécial "Structure" pour trouver les 80 boites
                prompt = (
                    "Agis comme un expert logistique. Analyse la structure de cette palette."
                    "1. STRUCTURE : Combien de boîtes en largeur x profondeur par couche ?"
                    "2. HAUTEUR : Combien de couches au total (y compris celle du haut) ?"
                    "3. CALCUL : (Boîtes par couche) x (Nombre de couches)."
                    "4. RÉEL : Le calcul théorique moins les éventuels manquants visibles."
                    
                    "Réponds sous ce format :"
                    "📦 **ESTIMATION TOTALE** : [Nombre final]\n"
                    "🏗️ **STRUCTURE** : [Nb] par couche x [Nb] couches\n"
                    "⚠️ **MANQUANTS** : [Nombre visiblement absent ou 'Aucun']\n"
                    "📏 **DIMENSIONS** : [L x l x H estimé]\n"
                    "⚖️ **POIDS** : [Estimation]"
                )

                response = model.generate_content([prompt, image])
                if response.text:
                    st.success("Analyse terminée !")
                    st.markdown(response.text)
                else:
                    st.warning("Réponse vide.")

            except Exception as e:
                st.error(f"Erreur : {e}")