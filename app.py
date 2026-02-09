import streamlit as st
import os
import google.generativeai as genai
from PIL import Image

# 1. Configuration de la page
st.set_page_config(page_title="Agent CoPeDi", page_icon="📦")

st.title("📦 Agent CoPeDi")
st.write("Analysez vos palettes logistiques en une seconde.")

# 2. Récupération de la clé API
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_KEY:
    st.error("❌ Erreur : Clé API manquante dans les variables Render !")
    st.stop()

# 3. Configuration Gemini
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# 4. Interface d'upload
uploaded_file = st.file_uploader("Prenez une photo ou importez une image", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    # Affichage de l'image
    image = Image.open(uploaded_file)
    st.image(image, caption='Photo envoyée', use_container_width=True)

    # Bouton d'analyse
    if st.button("🔍 Lancer l'analyse"):
        with st.spinner('CoPeDi compte les cartons...'):
            try:
                # Le Prompt (identique à avant)
                prompt = (
                    "Analyse cette photo de palette logistique. "
                    "1. Compte le nombre de boîtes visibles et déduis le total (couches x boîtes). "
                    "2. Estime les dimensions totales (L x l x H) en utilisant la palette comme échelle. "
                    "3. Estime le poids total et le nombre de pièces si des étiquettes sont lisibles. "
                    "Réponds strictement sous ce format :\n"
                    "📦 *Nombre de boîtes :* [Nb]\n"
                    "🔢 *Nombre de pièces :* [Estimation]\n"
                    "📐 *Dimensions :* [L x l x H] cm\n"
                    "⚖️ *Poids estimé :* [X] kg\n"
                    "🔍 *Confiance :* [X]%"
                )

                # Sécurité (Anti-blocage)
                safety_settings = [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                ]

                # Appel Gemini
                response = model.generate_content([prompt, image], safety_settings=safety_settings)

                # Affichage du résultat
                if response.text:
                    st.success("Analyse terminée !")
                    st.markdown(response.text)
                else:
                    st.warning("L'IA n'a rien renvoyé. Essayez une autre photo.")

            except Exception as e:
                st.error(f"Une erreur est survenue : {e}")