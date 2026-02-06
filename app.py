import os
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import google.generativeai as genai

# --- BLOC DE DEBUG ---
print("🔍 LISTE DES MODÈLES DISPONIBLES :")
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f" -> {m.name}")
except Exception as e:
    print(f"⚠️ Impossible de lister les modèles : {e}")
print("-------------------------------")
# ---------------------

# 1. Configuration des logs et des clés
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

# 2. Configuration de l'IA Gemini
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash-001')

async def analyze_palette(update: Update, context: ContextTypes.DEFAULT_TYPE):
# Message de patience
status_msg = await update.message.reply_text("⏳ CoPeDi analyse votre palette... Un instant.")

try:
    # Récupération de la photo
    photo_file = await update.message.photo[-1].get_file()
    photo_path = "temp_palette.jpg"
    await photo_file.download_to_drive(photo_path)

    # Prompt
    prompt = (
        "Analyse cette photo de palette logistique. "
        "1. Compte le nombre de boîtes visibles et déduis le total. "
        "2. Estime les dimensions (L x l x H). "
        "3. Estime le poids total. "
        "Réponds strictement sous ce format :\n"
        "📦 *Nombre de boîtes :* [Nb]\n"
        "🔢 *Nombre de pièces :* [Estimation]\n"
        "📐 *Dimensions :* [L x l x H] cm\n"
        "⚖️ *Poids estimé :* [X] kg\n"
        "🔍 *Confiance :* [X]%"
    )

    # --- NOUVEAU : Réglages de sécurité pour éviter les blocages ---
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]
    # -------------------------------------------------------------

    # Envoi à Gemini avec les paramètres de sécurité
    from PIL import Image
    img = Image.open(photo_path)
    response = model.generate_content([prompt, img], safety_settings=safety_settings)
    
    # Vérification avant envoi pour éviter l'erreur Telegram
    if response.text and response.text.strip():
        await status_msg.edit_text(response.text, parse_mode='Markdown')
    else:
        await status_msg.edit_text("⚠️ L'IA a analysé l'image mais la réponse est vide (Blocage sécurité ou erreur modèle).")
        
    os.remove(photo_path) # Nettoyage

except Exception as e:
    # En cas d'erreur technique (comme un blocage complet)
    error_message = f"❌ Erreur : {str(e)}"
    if "safety" in str(e).lower():
        error_message = "❌ Erreur : L'image a été bloquée par le filtre de sécurité de Google."
    await status_msg.edit_text(error_message)

def main():
    if not TOKEN or not GEMINI_KEY:
        print("Erreur : Clés API manquantes dans l'environnement !")
        return

    app = Application.builder().token(TOKEN).build()
    
    # Gère les photos envoyées
    app.add_handler(MessageHandler(filters.PHOTO, analyze_palette))
    # Gère le texte pour dire bonjour
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, 
        lambda u, c: u.message.reply_text("Envoyez-moi une photo de palette pour analyse.")))

    print("Agent CoPeDi prêt !")
    app.run_polling()

if __name__ == "__main__":
    main()