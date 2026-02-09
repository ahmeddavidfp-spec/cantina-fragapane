import streamlit as st
import os
import google.generativeai as genai
from PIL import Image

st.set_page_config(page_title="Agent CoPeDi", page_icon="📦")
st.title("📦 Agent CoPeDi (Expert Logistique)")

# --- CLÉ API ---
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
    
    # On cherche le meilleur modèle disponible
    model_name = None
    for m in valid_models:
        if "flash" in m and "1.5" in m:
            model_name = m
            break
    if not model_name and valid_models:
        model_name = valid_models[0]
        
    st.caption(f"✅ Connecté au modèle : `{model_name}`")
    model = genai.GenerativeModel(model_name)

except Exception as e:
    st.error(f"Erreur Google : {e}")
    st.stop()

# --- INTERFACE ---
uploaded_file = st.file_uploader("📸 Chargez votre photo", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    
    # Optimisation
    if image.width > 1024:
        ratio = 1024 / image.width
        image = image.resize((1024, int(image.height * ratio)))
    
    st.image(image, caption='Votre palette', use_container_width=True)

    if st.button("🚀 Lancer l'analyse complète", type="primary"):
        with st.spinner('🔍 Analyse : Structure, Pièces et Poids...'):
            try:
                prompt = (
                    "Agis comme un expert logistique. Analyse cette palette en détail."
                    "1. STRUCTURE : Analyse le maillage (largeur x profondeur) et le nombre de couches."
                    "2. COMPTAGE : Calcule le total (Base x Hauteur - Manquants)."
                    "3. PIÈCES : Cherche sur les étiquettes la quantité par carton (ex: QTY, PCS, COUNTS). Multiplie par le nombre de boîtes pour avoir le total de pièces."
                    "4. POIDS & DIMENSIONS : Estime les dimensions standards et le poids total."
                    
                    "Réponds strictement sous ce format structuré :"
                    "📦 **ESTIMATION TOTALE** : [Nombre de boîtes] boîtes\n"
                    "🔢 **NOMBRE DE PIÈCES** : [Total pièces] (Calcul: [Nb boîtes] x [Qté/boîte])\n"
                    "🏗️ **STRUCTURE** : [Nb] boîtes par couche ([L] en largeur x [P] en profondeur) x [Nb] couches\n"
                    "⚠️ **MANQUANTS** : [Nombre] boîtes (par rapport à une palette pleine)\n"
                    "📏 **DIMENSIONS** : L [120] cm x l [80] cm x H [H] cm\n"
                    "⚖️ **POIDS** : [Poids] kg (estimation)"
                )

                response = model.generate_content([prompt, image])
                if response.text:
                    st.success("Analyse terminée !")
                    st.markdown(response.text)
                else:
                    st.warning("Réponse vide.")
            except Exception as e:
                st.error(f"Erreur : {e}")