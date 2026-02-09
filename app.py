import streamlit as st
import os
import google.generativeai as genai
from PIL import Image

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="Agent CoPeDi",
    page_icon="📦",
    layout="centered"
)

st.title("📦 Agent CoPeDi")
st.write("### L'Expert en Analyse de Palettes")

# --- RÉCUPÉRATION DE LA CLÉ API ---
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_KEY:
    st.error("🚨 ERREUR : Clé API manquante sur Render !")
    st.stop()

genai.configure(api_key=GEMINI_KEY)

# --- SÉLECTION DU MODÈLE (La Solution Anti-404) ---
# On demande à Google : "Dis-moi ce que j'ai le droit d'utiliser"
try:
    available_models = []
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            # On nettoie le nom (ex: models/gemini-pro -> gemini-pro)
            available_models.append(m.name.replace("models/", ""))
    
    # On met un modèle par défaut intelligent
    default_index = 0
    if "gemini-1.5-flash" in available_models:
        default_index = available_models.index("gemini-1.5-flash")
    elif "gemini-1.5-pro" in available_models:
        default_index = available_models.index("gemini-1.5-pro")
        
    # Le menu déroulant magique
    model_name = st.selectbox(
        "🧠 Modèle IA (Si erreur, changez ici)", 
        available_models, 
        index=default_index
    )
    
    model = genai.GenerativeModel(model_name)

except Exception as e:
    st.error(f"Erreur de connexion Google : {e}")
    st.stop()

# --- INTERFACE D'UPLOAD ---
uploaded_file = st.file_uploader("📸 Chargez votre photo ici", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    st.image(image, caption='Votre palette', use_container_width=True)

    if st.button("🚀 Lancer l'analyse", type="primary"):
        with st.spinner('🔍 Analyse en cours...'):
            try:
                prompt = (
                    "Agis comme un expert logistique. Analyse cette photo de palette. "
                    "1. Compte précisément le nombre de boîtes visibles. "
                    "2. Estime les dimensions (L x l x H) standard. "
                    "3. Estime le poids si possible. "
                    "Réponds avec une mise en page claire :"
                    "\n\n"
                    "📦 **NOMBRE DE BOÎTES** : [Total estimé]\n"
                    "📏 **DIMENSIONS ESTIMÉES** : [L x l x H]\n"
                    "⚖️ **POIDS ESTIMÉ** : [Poids]\n"
                    "💡 **OBSERVATION** : [État ou type de marchandise]"
                )

                response = model.generate_content([prompt, image])

                if response.text:
                    st.success("✅ Analyse terminée !")
                    st.markdown("---")
                    st.markdown(response.text)
                else:
                    st.warning("⚠️ Réponse vide. Changez de modèle dans le menu.")

            except Exception as e:
                st.error(f"Erreur : {e}")