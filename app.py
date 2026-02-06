import os
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import google.generativeai as genai

# 1. Configuration des logs et des clés
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

# 2. Configuration de l'IA Gemini
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

async def analyze_palette(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Message de patience
    status_msg = await update.message.reply_text("⏳ CoPeDi analyse votre palette... Un instant.")
    
    try:
        # Récupération de la photo
        photo_file = await update.message.photo[-1].get_file()
        photo_path = "temp_palette.jpg"
        await photo_file.download_to_drive(photo_path)

        # Prompt d'analyse "Aveugle"
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

        # Envoi à Gemini
        from PIL import Image
        img = Image.open(photo_path)
        response = model.generate_content([prompt, img])
        
        # Envoi du résultat
        await status_msg.edit_text(response.text, parse_mode='Markdown')
        os.remove(photo_path) # Nettoyage

    except Exception as e:
        await status_msg.edit_text(f"❌ Erreur d'analyse : {str(e)}")

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