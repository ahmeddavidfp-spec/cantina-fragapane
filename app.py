import streamlit as st
import os
import google.generativeai as genai
from PIL import Image

# --- CONFIGURATION ---
st.set_page_config(page_title="Auto-Count AI", page_icon="📦", layout="centered")

# --- STYLE CSS (Pour rendre le résultat clair) ---
st.markdown("""
    <style>
    .result-card { background-color: #f0f2f6; padding: 20px; border-radius: 10px; margin-bottom: 20px; text-align: center; }
    .big-number { font-size: 3em; font-weight: bold; color: #1f77b4; margin: 0; }
    .label { font-size: 1.2em; color: #555; }
    .details { text-align: left; background-color: white; padding: 15px; border-radius: 5px; border: 1px solid #ddd; }
    </style>
""", unsafe_allow_html=True)

st.title("📦 Auto-Count AI")
st.caption("Mode : Déduction Structurelle Automatique")

# --- API ---
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_KEY:
    st.error("🚨 Clé API manquante !")
    st.stop()

genai.configure(api_key=GEMINI_KEY)

# --- CHOIX INTELLIGENT DU MODÈLE ---
try:
    valid_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    # On cherche le modèle Pro (plus intelligent pour la logique) ou Flash 1.5
    model_name = next((m for m in valid_models if "gemini-1.5-pro" in m), None)
    if not model_name:
        model_name = next((m for m in valid_models if "gemini-pro" in m), valid_models[0])
    
    model = genai.GenerativeModel(model_name)
    # st.toast(f"Cerveau activé : {model_name}") # Optionnel : pour debug
except:
    st.error("Erreur connexion Google.")
    st.stop()

# --- INTERFACE ---
uploaded_file = st.file_uploader("📸 Photo de la palette", type=["jpg", "png", "jpeg"])

if uploaded_file:
    image = Image.open(uploaded_file)
    # Optimisation (pour que ça passe vite)
    if image.width > 1024:
        ratio = 1024 / image.width
        image = image.resize((1024, int(image.height * ratio)))
    
    st.image(image, use_container_width=True)
    
    if st.button("🚀 ANALYSER LA STRUCTURE (AUTO)", type="primary", use_container_width=True):
        with st.spinner("🧠 L'IA déduit les rangées cachées..."):
            try:
                # --- LE SECRET EST DANS CE PROMPT ---
                # On force l'IA à "deviner" la partie cachée par symétrie
                prompt = """
                Tu es un expert en logistique industrielle. Ta mission est de déduire le nombre TOTAL de cartons sur cette palette, y compris ceux qui sont cachés au centre ou derrière.
                
                RÈGLE D'OR : Les palettes sont construites par COUCHES complètes et symétriques.
                Si tu vois 5 cartons en façade, et que la profondeur semble similaire, c'est probablement une grille de 5x5, même si tu ne vois que 4 cartons sur le côté à cause de l'angle.
                
                ÉTAPES DE DÉDUCTION :
                1. IDENTIFIE LA GRILLE AU SOL (Base) :
                   - Compte les cartons visibles en Largeur (Façade).
                   - Estime les cartons en Profondeur (Côté).
                   - ATTENTION : Si c'est ambigu entre 4 et 5 en profondeur, choisis la symétrie (ex: 5x5 est plus standard que 5x4 pour des petits cartons).
                   - Calcul de la Base = Largeur x Profondeur.
                
                2. COMPTE LES COUCHES :
                   - Combien de couches complètes sont empilées ?
                
                3. LE RESTE (VRAC) :
                   - Combien de cartons isolés sur la toute dernière couche incomplète ?
                
                4. CALCUL FINAL : (Base x Couches Complètes) + Reste.
                
                5. ÉTIQUETTE : Cherche "QTY", "PCS" ou "6 per carton" pour le nombre de pièces.
                
                Réponds UNIQUEMENT avec ce format exact (Markdown) :
                
                <div class="result-card">
                    <div class="label">Total Estimé</div>
                    <div class="big-number">[TOTAL_BOITES]</div>
                    <p>📦 [TOTAL_PIECES] Pièces (x[QTY_PAR_BOITE])</p>
                </div>
                
                <div class="details">
                    <strong>🏗️ Analyse Structurelle :</strong>
                    <ul>
                        <li><strong>Grille (Base) :</strong> [LARGEUR] x [PROFONDEUR] = <strong>[BASE]</strong> cartons/couche</li>
                        <li><strong>Hauteur :</strong> [COUCHES] couches complètes</li>
                        <li><strong>Dessus :</strong> + [RESTE] cartons</li>
                        <li><strong>Formule :</strong> ([BASE] x [COUCHES]) + [RESTE] = [TOTAL_BOITES]</li>
                    </ul>
                    <p><em>💡 Note IA : [Explique en une phrase pourquoi tu as choisi cette profondeur, ex: "J'ai déduit une profondeur de 5 car la palette semble carrée."]</em></p>
                </div>
                """
                
                response = model.generate_content([prompt, image])
                
                if response.text:
                    st.markdown(response.text, unsafe_allow_html=True)
                else:
                    st.warning("L'IA n'a pas réussi à conclure.")
                    
            except Exception as e:
                st.error(f"Erreur technique : {e}")