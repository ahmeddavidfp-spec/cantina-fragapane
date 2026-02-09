import streamlit as st
import os
import google.generativeai as genai
from PIL import Image

st.set_page_config(page_title="Agent CoPeDi", page_icon="📦")
st.title("📦 Agent CoPeDi (Auto-Détection)")

# --- CLÉ API ---
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_KEY:
    st.error("🚨 Clé API manquante !")
    st.stop()

genai.configure(api_key=GEMINI_KEY)

# --- DÉTECTION AUTOMATIQUE DU MODÈLE (Anti-404) ---
# On ne devine plus le nom, on prend celui que Google nous donne.
try:
    valid_models = []
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            valid_models.append(m.name)
    
    # Stratégie : On cherche "flash" (rapide/gratuit), sinon on prend le premier dispo
    model_name = None
    for m in valid_models:
        if "flash" in m and "1.5" in m: # Priorité au 1.5 Flash
            model_name = m
            break
    
    if not model_name and valid_models:
        model_name = valid_models[0] # Roue de secours : le premier de la liste
        
    if not model_name:
        st.error("🚨 Aucun modèle disponible pour votre clé API. Vérifiez votre compte Google AI.")
        st.stop()
        
    # On affiche le modèle trouvé pour info (en petit)
    st.caption(f"✅ Connecté au modèle : `{model_name}`")
    model = genai.GenerativeModel(model_name)

except Exception as e:
    st.error(f"Erreur de connexion Google : {e}")
    st.stop()

# --- INTERFACE ---
uploaded_file = st.file_uploader("📸 Chargez votre photo", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    
    # Optimisation (Anti-Crash)
    if image.width > 1024:
        ratio = 1024 / image.width
        image = image.resize((1024, int(image.height * ratio)))
    
    st.image(image, caption='Votre palette', use_container_width=True)

    if st.button("🚀 Compter les cartons", type="primary"):
        with st.spinner('🔍 Analyse structurelle en cours...'):
            try:
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
                st.error(f"Erreur pendant l'analyse : {e}")