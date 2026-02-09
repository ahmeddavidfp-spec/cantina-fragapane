import streamlit as st
import os
import google.generativeai as genai
from PIL import Image

# --- CONFIGURATION ---
st.set_page_config(page_title="Auto-Count Flash", page_icon="⚡", layout="centered")

# --- STYLE CSS (Tableau de bord) ---
st.markdown("""
    <style>
    .result-container { background-color: #f0f2f6; padding: 20px; border-radius: 10px; border-left: 5px solid #ff4b4b; }
    .metric { text-align: center; }
    .metric-value { font-size: 40px; font-weight: bold; color: #000; }
    .metric-label { font-size: 14px; color: #666; }
    </style>
""", unsafe_allow_html=True)

st.title("⚡ Auto-Count (Version Illimitée)")
st.info("Modèle : Gemini 1.5 Flash (Rapide & Gratuit)")

# --- API ---
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_KEY:
    st.error("🚨 Clé API manquante !")
    st.stop()

# --- MODÈLE FORCÉ SUR FLASH (Anti-Erreur 429) ---
genai.configure(api_key=GEMINI_KEY)
# On ne cherche plus, on impose le modèle gratuit.
model = genai.GenerativeModel('gemini-1.5-flash')

# --- INTERFACE ---
uploaded_file = st.file_uploader("📸 Photo de la palette", type=["jpg", "png", "jpeg"])

if uploaded_file:
    image = Image.open(uploaded_file)
    # Optimisation taille
    if image.width > 1024:
        ratio = 1024 / image.width
        image = image.resize((1024, int(image.height * ratio)))
    
    st.image(image, use_container_width=True)
    
    if st.button("🚀 LANCER L'ANALYSE AUTOMATIQUE", type="primary", use_container_width=True):
        with st.spinner("⚡ Flash analyse la symétrie 5x5..."):
            try:
                # --- PROMPT SPÉCIAL "SYMÉTRIE 5x5" ---
                prompt = """
                Tu es un expert logistique. Analyse cette palette.
                
                RÈGLE DE DÉDUCTION (SYMÉTRIE) :
                Sur ce type de palette, la structure est souvent CARRÉE au sol.
                - Si tu comptes 5 cartons en façade (largeur), tu DOIS supposer qu'il y en a 5 en profondeur.
                - Donc la Base = 5 x 5 = 25 cartons par couche.
                
                INSTRUCTIONS DE CALCUL :
                1. Base : Confirme le 5x5 (ou 4x4 selon la photo) -> Calcule le nombre par couche.
                2. Hauteur : Compte les couches complètes.
                3. Reste : Compte les cartons isolés sur le dessus.
                4. Total : (Base x Hauteur) + Reste.
                5. Pièces : Cherche "6 per carton", "QTY 6", ou similaire sur l'étiquette.
                
                Réponds UNIQUEMENT avec ce format Markdown exact :
                
                ### 📊 RÉSULTAT ANALYSE
                | Indicateur | Valeur |
                | :--- | :--- |
                | **📦 TOTAL BOÎTES** | **[TOTAL]** |
                | **🧩 Structure** | [LARGEUR] x [PROFONDEUR] x [COUCHES] (+ [RESTE]) |
                | **🔢 Pièces / Boîte** | [QTY] |
                | **🎯 TOTAL PIÈCES** | **[TOTAL_PIECES]** |
                
                > **Détail du calcul :** ([LARGEUR] x [PROFONDEUR] = [BASE]/couche). [BASE] x [COUCHES] couches + [RESTE] vrac = [TOTAL].
                """
                
                response = model.generate_content([prompt, image])
                
                if response.text:
                    st.markdown(response.text)
                else:
                    st.warning("Réponse vide.")
                    
            except Exception as e:
                if "429" in str(e):
                    st.error("⏳ Ralentissez ! Trop de requêtes à la minute.")
                else:
                    st.error(f"Erreur : {e}")