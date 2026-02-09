import streamlit as st
import os
import google.generativeai as genai
from PIL import Image

# --- CONFIGURATION ---
st.set_page_config(page_title="Auto-Count Universal", page_icon="🌍", layout="centered")
st.title("🌍 Auto-Count (Mode Universel)")
st.caption("Détection automatique du modèle compatible")

# --- API ---
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_KEY:
    st.error("🚨 Clé API manquante !")
    st.stop()

genai.configure(api_key=GEMINI_KEY)

# --- DÉTECTION INTELLIGENTE (ANTI-404) ---
try:
    # 1. On liste TOUS les modèles disponibles pour ton compte
    all_models = [m for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    
    # 2. On cherche le meilleur candidat (Flash > Pro > 1.5 > 1.0)
    selected_model_name = None
    
    # Stratégie : On cherche d'abord "flash" (rapide/gratuit)
    for m in all_models:
        if "flash" in m.name.lower():
            selected_model_name = m.name
            break
            
    # Si pas de flash, on cherche "pro"
    if not selected_model_name:
        for m in all_models:
            if "pro" in m.name.lower() and "1.5" in m.name:
                selected_model_name = m.name
                break
                
    # Si toujours rien, on prend le premier de la liste (roue de secours)
    if not selected_model_name and all_models:
        selected_model_name = all_models[0].name
        
    if not selected_model_name:
        st.error("🚨 Aucun modèle IA trouvé sur ce compte Google.")
        st.stop()

    # st.success(f"Connecté à : {selected_model_name}") # Décommente pour voir le nom
    model = genai.GenerativeModel(selected_model_name)

except Exception as e:
    st.error(f"Erreur de connexion Google : {e}")
    st.stop()

# --- INTERFACE ---
uploaded_file = st.file_uploader("📸 Photo de la palette", type=["jpg", "png", "jpeg"])

if uploaded_file:
    image = Image.open(uploaded_file)
    if image.width > 1024:
        ratio = 1024 / image.width
        image = image.resize((1024, int(image.height * ratio)))
    
    st.image(image, use_container_width=True)
    
    if st.button("🚀 ANALYSER LA STRUCTURE", type="primary", use_container_width=True):
        with st.spinner(f"Analyse en cours avec {selected_model_name}..."):
            try:
                # --- PROMPT LOGIQUE 5x5 ---
                prompt = """
                Tu es un expert logistique. Analyse cette palette en utilisant la symétrie.
                
                RÈGLE : Les palettes sont souvent carrées. Si tu vois 5 cartons en façade, il y a très probablement 5 cartons en profondeur (5x5), même si tu n'en vois que 4 à cause de l'angle.
                
                DÉDUCTIONS À FAIRE :
                1. Compte la façade (Largeur).
                2. Déduis la profondeur (si doute, prends la même valeur que la largeur pour faire un carré).
                3. Base = Largeur x Profondeur.
                4. Compte les couches complètes.
                5. Ajoute le vrac (dessus).
                
                Cherche aussi "6 per carton" ou "QTY" sur l'étiquette.
                
                Réponds UNIQUEMENT avec ce tableau Markdown :
                
                | Indicateur | Valeur |
                | :--- | :--- |
                | **📦 TOTAL BOÎTES** | **[Resultat]** |
                | **🧩 Structure** | [L] x [P] x [H] couches (+ [Reste]) |
                | **🔢 Pièces/Boîte** | [Qté Etiquette] |
                | **🎯 TOTAL PIÈCES** | **[Total Pièces]** |
                
                > **Note :** J'ai utilisé une base de [L]x[P] car...
                """
                
                response = model.generate_content([prompt, image])
                if response.text:
                    st.markdown(response.text)
                else:
                    st.warning("Réponse vide.")
                    
            except Exception as e:
                st.error(f"Erreur : {e}")