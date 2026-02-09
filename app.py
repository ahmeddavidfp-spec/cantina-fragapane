import streamlit as st
import os
import google.generativeai as genai
from PIL import Image

# --- CONFIGURATION ---
st.set_page_config(page_title="Auto-Count Réaliste", page_icon="🧐", layout="centered")
st.title("🧐 Auto-Count (Mode Réaliste Strict)")
st.caption("Compte ce qui est visible, estime prudemment le caché. Fini d'inventer.")

# --- API ---
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_KEY:
    st.error("🚨 Clé API manquante !")
    st.stop()

genai.configure(api_key=GEMINI_KEY)

# --- DÉTECTION INTELLIGENTE DU MODÈLE ---
try:
    all_models = [m for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    # On préfère le Pro pour le raisonnement complexe, sinon le Flash
    selected_model_name = None
    for m in all_models:
        if "pro" in m.name.lower() and "1.5" in m.name:
            selected_model_name = m.name
            break
    if not selected_model_name:
         for m in all_models:
            if "flash" in m.name.lower():
                selected_model_name = m.name
                break
    if not selected_model_name and all_models:
        selected_model_name = all_models[0].name
        
    if not selected_model_name:
        st.error("🚨 Aucun modèle IA trouvé.")
        st.stop()

    model = genai.GenerativeModel(selected_model_name)

except Exception as e:
    st.error(f"Erreur de connexion Google : {e}")
    st.stop()

# --- INTERFACE ---
uploaded_file = st.file_uploader("📸 Photo du stock/palette", type=["jpg", "png", "jpeg"])

if uploaded_file:
    image = Image.open(uploaded_file)
    # Optimisation taille
    if image.width > 1024:
        ratio = 1024 / image.width
        image = image.resize((1024, int(image.height * ratio)))
    
    st.image(image, use_container_width=True)
    
    if st.button("🚀 COMPTER RÉELLEMENT (Sans inventer)", type="primary", use_container_width=True):
        with st.spinner(f"Analyse stricte en cours avec {selected_model_name}..."):
            try:
                # --- NOUVEAU PROMPT "RÉALISTE STRICT" ---
                prompt = """
                Tu es un auditeur d'inventaire strict. Analyse cette image.
                
                RÈGLE ABSOLUE : N'INVENTE PAS DE STRUCTURE. Ne suppose pas que c'est une palette carrée parfaite si ça ressemble à du vrac sur une étagère.

                TA MISSION :
                1. **Comptage Visuel (Façade)** : Compte précisément combien de faces de boîtes sont clairement visibles au premier plan.
                2. **Estimation Profondeur (Caché)** : Regarde les angles et les ombres. Combien de rangées semble-t-il y avoir en profondeur ? Estime combien de boîtes sont complètement cachées derrière. Soyez prudent dans cette estimation.
                3. **Total** : Somme des visibles + estimés cachés. Donnez une fourchette si c'est incertain (ex: 45-50).
                4. **Étiquette** : Cherche une quantité (Qté, Pcs) sur une boîte visible.

                Réponds UNIQUEMENT avec ce tableau Markdown :
                
                | Indicateur | Valeur (Prudente) |
                | :--- | :--- |
                | **👀 Visibles en façade** | [Nombre exact compté] |
                | **🕵️ Estimés cachés** | [Nombre estimé derrière] |
                | **📦 TOTAL ESTIMÉ** | **[Total ou Fourchette]** |
                | **🔢 Pièces/Boîte** | [Qté lue ou "Non visible"] |
                
                > **Note de l'auditeur :** [Explique brièvement ton calcul. Ex: "J'ai compté 30 boîtes devant. Vu la profondeur de l'étagère, j'estime une rangée identique derrière, soit +30." OU "C'est du vrac irrégulier, j'ai compté les visibles et ajouté environ 10% pour le caché."]
                """
                
                response = model.generate_content([prompt, image])
                if response.text:
                    st.markdown(response.text)
                else:
                    st.warning("Réponse vide.")
                    
            except Exception as e:
                st.error(f"Erreur : {e}")