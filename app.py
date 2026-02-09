import streamlit as st
import os
import google.generativeai as genai
from PIL import Image

# --- 1. CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="Agent CoPeDi",
    page_icon="📦",
    layout="centered"
)

st.title("📦 Agent CoPeDi")
st.info("Version Rapide (Flash) - Optimisée pour le comptage")

# --- 2. RÉCUPÉRATION DE LA CLÉ ---
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_KEY:
    st.error("🚨 Clé API manquante !")
    st.stop()

# --- 3. CONFIGURATION GEMINI (MODE GRATUIT FORCÉ) ---
genai.configure(api_key=GEMINI_KEY)
# On utilise UNIQUEMENT le modèle Flash pour éviter l'erreur 429 (Quota)
model = genai.GenerativeModel('gemini-1.5-flash')

# --- 4. INTERFACE ---
uploaded_file = st.file_uploader("📸 Chargez votre photo de palette", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    
    # --- OPTIMISATION (Anti-Crash 502) ---
    # On réduit l'image pour que le serveur gratuit tienne le coup
    max_width = 1024
    if image.width > max_width:
        ratio = max_width / image.width
        new_height = int(image.height * ratio)
        image = image.resize((max_width, new_height))
        st.caption("ℹ️ Image redimensionnée pour l'analyse rapide.")
    
    st.image(image, caption='Votre palette', use_container_width=True)

    if st.button("🚀 Compter les cartons", type="primary"):
        with st.spinner('🔍 Calcul : Base x Hauteur...'):
            try:
                # --- NOUVEAU PROMPT (LOGIQUE MATHÉMATIQUE) ---
                prompt = (
                    "Agis comme un expert logistique mathématique. Analyse cette palette."
                    "Ne compte pas juste les boîtes visibles, déduis la structure."
                    
                    "1. STRUCTURE DE BASE : Combien de boîtes y a-t-il par couche (Largeur x Profondeur) ?"
                    "2. HAUTEUR : Combien y a-t-il de couches visibles (même partielles) ?"
                    "3. CALCUL : Si la palette était pleine, combien y aurait-il de boîtes (Base x Couches) ?"
                    "4. RÉEL : Soustrais les boîtes visiblement manquantes sur la couche supérieure."
                    
                    "Réponds strictement sous ce format :"
                    "📦 **ESTIMATION TOTALE** : [Nombre final]\n"
                    "🏗️ **STRUCTURE** : [Nombre] par couche x [Nombre] couches\n"
                    "⚠️ **MANQUANTS VISIBLES** : [Nombre ou 'Aucun']\n"
                    "📏 **DIMENSIONS** : [L x l x H estimé]\n"
                    "⚖️ **POIDS** : [Estimation si étiquette visible]"
                )

                response = model.generate_content([prompt, image])

                if response.text:
                    st.success("Analyse terminée !")
                    st.markdown("---")
                    st.markdown(response.text)
                else:
                    st.warning("Réponse vide de l'IA.")

            except Exception as e:
                # Gestion propre de l'erreur de quota au cas où
                if "429" in str(e):
                    st.error("🚨 Trop de demandes ! Le serveur sature, réessayez dans 30 secondes.")
                else:
                    st.error(f"Erreur technique : {e}")