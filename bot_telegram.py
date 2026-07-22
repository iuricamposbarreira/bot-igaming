import logging
import requests
import re
import os
import threading
import time
from flask import Flask
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters
)
from avaliador import IGamingEvaluator

# Configuração de Logs
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

TOKEN_BOT = "8944907729:AAE8_GZX4Mx3EIxG67AQ_hG7mzecx87dy8M"
RAPIDAPI_KEY = "44faf2cfd5msh084db8e1cf193e2p164debjsncb95a30318a5"

evaluator = IGamingEvaluator(default_cpa=100.0)

CACHE_API = {}

USERNAME, VIEWS, PAIS, PCT_PAIS, HOMENS = range(5)

# ----------------------------------------------------
# Servidor Web Leve (Para o Render ficar sempre Online)
# ----------------------------------------------------
server = Flask(__name__)

@server.route('/')
def home():
    return "Bot iGaming Online 24/7!"

def run_flask():
    try:
        port = int(os.environ.get("PORT", 10000))
        server.run(host="0.0.0.0", port=port, use_reloader=False)
    except Exception as e:
        print(f"Aviso no servidor Flask: {e}")

# ----------------------------------------------------
# API Instagram (Corrigida para ler Seguidores Reais)
# ----------------------------------------------------
def buscar_dados_instagram_api(username: str):
    clean_username = username.replace("@", "").strip().lower()
    
    if clean_username in CACHE_API:
        timestamp, data = CACHE_API[clean_username]
        if time.time() - timestamp < 86400:
            return data

    url = f"https://instagram-public-bulk-scraper.p.rapidapi.com/user/{clean_username}"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "instagram-public-bulk-scraper.p.rapidapi.com"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=8)
        
        if response.status_code == 200:
            data = response.json()
            
            # Mapeamento exaustivo para capturar os seguidores reais da API
            followers = 0
            if isinstance(data, dict):
                followers = (
                    data.get("follower_count") or 
                    data.get("followers_count") or
                    data.get("followers") or
                    data.get("data", {}).get("follower_count") or 
                    data.get("data", {}).get("followers_count") or 
                    data.get("data", {}).get("followers") or
                    data.get("user", {}).get("follower_count") or
                    data.get("user", {}).get("followers_count") or 0
                )
            
            if followers and followers > 0:
                avg_likes = int(followers * 0.03)
                avg_comments = int(avg_likes * 0.05)
                resultado = (followers, avg_likes, avg_comments, False)
                CACHE_API[clean_username] = (time.time(), resultado)
                return resultado

        return 0, 0, 0, True
            
    except Exception:
        return 0, 0, 0, True

# ----------------------------------------------------
# Comandos Principais e Respostas Automáticas
# ----------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ajuda(update, context)

async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👋 *Olá! Sou o Avaliador de Influenciadores iGaming.*\n\n"
        "👉 Para iniciar uma nova avaliação, escreve: `/avaliar`\n"
        "🔄 Para reiniciar a qualquer momento, escreve: `/cancelar`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

# ----------------------------------------------------
# MODO GUIADO
# ----------------------------------------------------
async def iniciar_guiado_ou_rapido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "📝 *NOVA AVALIAÇÃO GUIADA*\n\n"
        "1️⃣ *Qual é o Username do Instagram?*\n\n"
        "👉 *Exemplo:* `@noemi_silipo`",
        parse_mode="Markdown"
    )
    return USERNAME

async def receber_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.startswith("@"):
        text = "@" + text
        
    context.user_data['username'] = text
    await update.message.reply_text(
        f"✅ Username: `{text}`\n\n"
        "2️⃣ *Quais são as Views dos Stories?*\n\n"
        "👉 *Exemplo:* `33859 33001 15103`",
        parse_mode="Markdown"
    )
    return VIEWS

async def receber_views(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    views_list = [int(v) for v in re.findall(r'\d+', text)]
    
    if not views_list:
        await update.message.reply_text(
            "❌ Não encontrei nenhum número válido. Envia apenas números de views.\n"
            "👉 *Exemplo:* `33859 33001 15103`",
            parse_mode="Markdown"
        )
        return VIEWS

    context.user_data['views_list'] = views_list
    avg_views = sum(views_list) // len(views_list)
    context.user_data['avg_views'] = avg_views

    await update.message.reply_text(
        f"✅ Views processadas (Média: `{avg_views:,}`)\n\n"
        "3️⃣ *Qual é o País principal da audiência?*\n\n"
        "👉 *Exemplo:* `IT` (ou `PT`, `DE`, `BR`)",
        parse_mode="Markdown"
    )
    return PAIS

async def receber_pais(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    context.user_data['pais'] = text
    
    await update.message.reply_text(
        f"✅ País: `{text.upper()}`\n\n"
        "4️⃣ *Qual é a Percentagem (%) desse País?*\n\n"
        "👉 *Exemplo:* `85` (ou `94.6`)",
        parse_mode="Markdown"
    )
    return PCT_PAIS

async def receber_pct_pais(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.replace("%", "").replace(",", ".").strip()
    try:
        pct = float(text)
        context.user_data['pct_pais'] = pct
    except ValueError:
        await update.message.reply_text("❌ Insere apenas o número da percentagem. Ex: `85`", parse_mode="Markdown")
        return PCT_PAIS

    await update.message.reply_text(
        f"✅ % País: `{pct}%`\n\n"
        "5️⃣ *Qual é a Percentagem (%) de Homens?*\n\n"
        "👉 *Exemplo:* `35` (ou `15.9`)",
        parse_mode="Markdown"
    )
    return HOMENS

async def receber_homens_e_gerar_relatorio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.replace("%", "").replace(",", ".").strip()
    try:
        pct_homens = float(text)
        context.user_data['pct_homens'] = pct_homens
    except ValueError:
        await update.message.reply_text("❌ Insere apenas o número da percentagem. Ex: `35`", parse_mode="Markdown")
        return HOMENS

    username = context.user_data['username']
    views_list = context.user_data['views_list']
    avg_story_views = context.user_data['avg_views']
    pais = context.user_data['pais']
    pct_pais = context.user_data['pct_pais']

    msg_espera = await update.message.reply_text("🔎 *A processar auditoria...*", parse_mode="Markdown")

    try:
        followers, avg_likes, avg_comments, is_fallback = buscar_dados_instagram_api(username)

        relatorio = evaluator.evaluate_profile(
            username=username,
            followers=followers,
            avg_likes=avg_likes,
            avg_comments=avg_comments,
            story_views=avg_story_views,
            views_list=views_list,
            pct_homens=pct_homens,
            pais=pais,
            pct_pais=pct_pais
        )
        
        resposta = (
            f"📊 *RELATÓRIO DE AUDITORIA (2 STORIES)*\n"
            f"👤 *Perfil:* `{relatorio['username']}`\n"
            f"📲 *Média Views Stories:* `{avg_story_views:,}`\n"
            f"🌍 *País:* `{pais.upper()}` ({pct_pais}%) → *CPA:* €{relatorio['cpa_used']}\n"
            f"👨 *Homens:* `{pct_homens}%` (~{relatorio['homens_absolutos']:,} homens/story)\n"
            f"-----------------------------------\n"
            f"Status: {relatorio['status_emoji']} *{relatorio['status_text']}*\n"
            f"⚠️ Índice de Risco: *{relatorio['risk_index']}*\n\n"
            f"📈 *FTDs Estimados:* `~{relatorio['expected_ftds']} depósitos`\n"
            f"🔗 *Cliques Mínimos Esperados:* `{relatorio['expected_clicks']} cliques`\n"
            f"💡 *Custo Estimado/View Útil:* `€{relatorio['cpv_qualificado']}/view`\n"
            f"💶 *Retorno Esperado em CPA:* `€{relatorio['projected_revenue_eur']:,.2f}`\n\n"
            f"🎬 *VALOR RECOMENDADO PARA TESTE (2 STORIES):*\n"
            f"💰 *Oferta Inicial Recomendada:* `€{relatorio['pack_2_stories_suggested']:,.2f}` (Total)\n"
            f"🛑 *Preço Teto Máximo:* `€{relatorio['pack_2_stories_max']:,.2f}` (Total)\n"
            f"-----------------------------------\n"
            f"📋 *Decisão:* {relatorio['recommendation']}\n"
        )

        if relatorio['warnings']:
            resposta += "\n🚨 *Alertas de Risco:*\n"
            for w in relatorio['warnings']:
                resposta += f"• {w}\n"

        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_espera.message_id)
        await update.message.reply_text(resposta, parse_mode="Markdown")

    except Exception as e:
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_espera.message_id)
        await update.message.reply_text(f"❌ Ocorreu um erro ao gerar o relatório. Escreve `/avaliar` para tentar de novo.", parse_mode="Markdown")

    context.user_data.clear()
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("🚫 Avaliação cancelada. Escreve `/avaliar` para recomeçar.", parse_mode="Markdown")
    return ConversationHandler.END

if __name__ == '__main__':
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

    app = ApplicationBuilder().token(TOKEN_BOT).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("avaliar", iniciar_guiado_ou_rapido)],
        states={
            USERNAME: [
                CommandHandler("avaliar", iniciar_guiado_ou_rapido),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receber_username)
            ],
            VIEWS: [
                CommandHandler("avaliar", iniciar_guiado_ou_rapido),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receber_views)
            ],
            PAIS: [
                CommandHandler("avaliar", iniciar_guiado_ou_rapido),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receber_pais)
            ],
            PCT_PAIS: [
                CommandHandler("avaliar", iniciar_guiado_ou_rapido),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receber_pct_pais)
            ],
            HOMENS: [
                CommandHandler("avaliar", iniciar_guiado_ou_rapido),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receber_homens_e_gerar_relatorio)
            ],
        },
        fallbacks=[
            CommandHandler("cancelar", cancelar),
            CommandHandler("avaliar", iniciar_guiado_ou_rapido)
        ],
        allow_reentry=True
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ajuda", ajuda))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ajuda))

    print("🚀 Bot Atualizado e Protegido!")
    app.run_polling()