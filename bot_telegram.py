import logging
import requests
import re
import os
import threading
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

# Estados da Conversa Guiada
USERNAME, VIEWS, PAIS, PCT_PAIS, HOMENS = range(5)

# ----------------------------------------------------
# Servidor Web Leve (Para o Render ficar sempre Online)
# ----------------------------------------------------
server = Flask(__name__)

@server.route('/')
def home():
    return "Bot iGaming Online 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    server.run(host="0.0.0.0", port=port)

# ----------------------------------------------------
# Funções de Apoio
# ----------------------------------------------------
def buscar_dados_instagram_api(username: str):
    clean_username = username.replace("@", "").strip()
    url = "https://instagram-scraper-stable-api.p.rapidapi.com/ig_get_fb_profile_v3.php"
    payload = f"username_or_url={clean_username}"
    headers = {
        "content-type": "application/x-www-form-urlencoded",
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "instagram-scraper-stable-api.p.rapidapi.com"
    }
    
    response = requests.post(url, data=payload, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        followers = data.get("follower_count", 0) or data.get("user", {}).get("follower_count", 0)
        
        # Se não encontrar seguidores ou perfil inválido
        if not followers and "user" not in data and "follower_count" not in data:
            raise Exception("Perfil não encontrado ou privado no Instagram.")
            
        posts = data.get("timeline_media", {}).get("edges", []) or data.get("user", {}).get("edge_owner_to_timeline_media", {}).get("edges", [])
        
        total_likes = sum([p.get("node", {}).get("edge_liked_by", {}).get("count", 0) for p in posts[:10]])
        total_comments = sum([p.get("node", {}).get("edge_media_to_comment", {}).get("count", 0) for p in posts[:10]])
        
        count = len(posts[:10])
        avg_likes = int(total_likes / count) if count > 0 else 0
        avg_comments = int(total_comments / count) if count > 0 else 0
        
        return followers, avg_likes, avg_comments
    else:
        raise Exception(f"Perfil não encontrado ou erro na API ({response.status_code})")

# ----------------------------------------------------
# Comandos Principais
# ----------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ajuda(update, context)

async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📖 *AVALIADOR DE TESTE DE IGAMING*\n\n"
        "🎯 *Modo Guiado (Passo a Passo):*\n"
        "Escreve apenas `/avaliar` para responderes às perguntas uma a uma!\n\n"
        "⚡️ *Atalho Rápido (Tudo em 1 linha):*\n"
        "`/avaliar @noemi_silipo 33859 33001 15103`\n"
        "`/avaliar @noemi_silipo 33859 33001 15103 pais=it %pais=94.6 homens=15.9`\n\n"
        "❌ *Cancelar / Reiniciar:* Escreve `/avaliar` a qualquer momento para recomeçar do zero!"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

# ----------------------------------------------------
# MODO GUIADO (PASSO A PASSO)
# ----------------------------------------------------
async def iniciar_guiado_ou_rapido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Se o utilizador enviou argumentos na mesma linha, usa o modo rápido
    if context.args:
        return await avaliar_rapido(update, context)
    
    # Caso contrário, limpa dados anteriores e inicia/reinicia o modo guiado
    context.user_data.clear()
    await update.message.reply_text(
        "📝 *NOVA AVALIAÇÃO GUIADA*\n\n"
        "1️⃣ *Qual é o Username do Instagram?*\n\n"
        "👉 *Exemplo:* `@noemi_silipo`\n"
        "*(Escreve com o @ no início)*",
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
        "2️⃣ *Quais são as Views dos Stories?*\n"
        "Podes mandar vários números separados por espaço para o bot calcular a média.\n\n"
        "👉 *Exemplo:* `33859 33001 15103`",
        parse_mode="Markdown"
    )
    return VIEWS

async def receber_views(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    views_list = [int(v) for v in re.findall(r'\d+', text)]
    
    if not views_list:
        await update.message.reply_text(
            "❌ Não encontrei nenhum número de views válido.\n"
            "👉 *Exemplo correto:* `33859 33001 15103`",
            parse_mode="Markdown"
        )
        return VIEWS

    context.user_data['views_list'] = views_list
    avg_views = sum(views_list) // len(views_list)
    context.user_data['avg_views'] = avg_views

    await update.message.reply_text(
        f"✅ Views processadas (Média: `{avg_views:,}`)\n\n"
        "3️⃣ *Qual é o País principal da audiência?*\n"
        "Escreve a sigla ou o nome do país.\n\n"
        "👉 *Exemplo:* `IT` (ou `Portugal`, `Alemanha`, `BR`)",
        parse_mode="Markdown"
    )
    return PAIS

async def receber_pais(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    context.user_data['pais'] = text
    
    await update.message.reply_text(
        f"✅ País: `{text.upper()}`\n\n"
        "4️⃣ *Qual é a Percentagem (%) desse País?*\n"
        "Apenas o número da percentagem.\n\n"
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
        await update.message.reply_text(
            "❌ Por favor, insere apenas um número.\n"
            "👉 *Exemplo:* `85` ou `94.6`",
            parse_mode="Markdown"
        )
        return PCT_PAIS

    await update.message.reply_text(
        f"✅ % País: `{pct}%`\n\n"
        "5️⃣ *Qual é a Percentagem (%) de Homens?*\n"
        "Apenas o número da percentagem de homens.\n\n"
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
        await update.message.reply_text(
            "❌ Por favor, insere apenas um número.\n"
            "👉 *Exemplo:* `35` ou `15.9`",
            parse_mode="Markdown"
        )
        return HOMENS

    username = context.user_data['username']
    views_list = context.user_data['views_list']
    avg_story_views = context.user_data['avg_views']
    pais = context.user_data['pais']
    pct_pais = context.user_data['pct_pais']

    msg_espera = await update.message.reply_text("🔎 *A extrair dados e calcular viabilidade do teste...*", parse_mode="Markdown")

    try:
        followers, avg_likes, avg_comments = buscar_dados_instagram_api(username)

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
            f"👤 *Perfil:* `{relatorio['username']}` | 👥 `{followers:,}` segs\n"
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
            resposta += "\n🚨 *Alertas de Risco / Anomalias:*\n"
            for w in relatorio['warnings']:
                resposta += f"• {w}\n"

        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_espera.message_id)
        await update.message.reply_text(resposta, parse_mode="Markdown")

    except Exception as e:
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_espera.message_id)
        await update.message.reply_text(f"❌ *Erro:* {str(e)}\n\n_Verifica se o username está correto ou escreve `/avaliar` para tentar de novo._", parse_mode="Markdown")

    context.user_data.clear()
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("🚫 Avaliação cancelada. Escreve `/avaliar` quando quiseres recomeçar.", parse_mode="Markdown")
    return ConversationHandler.END

# ----------------------------------------------------
# Modo Rápido (Se colar tudo na mesma linha)
# ----------------------------------------------------
async def avaliar_rapido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    username_match = re.search(r'@[A-Za-z0-9_.]+', text)
    if not username_match:
        await update.message.reply_text("❌ Não foi encontrado o username com `@`.", parse_mode="Markdown")
        return

    username = username_match.group(0)
    raw_tokens = text.replace(username, "").split()
    views_list = []
    
    pais = "Geral"
    pct_pais = 85.0
    pct_homens = 35.0

    for token in raw_tokens:
        if "=" in token:
            chave, valor = token.split("=", 1)
            chave = chave.lower()
            if chave == "pais":
                pais = valor
            elif chave in ["%pais", "pct_pais"]:
                pct_pais = float(valor)
            elif chave in ["homens", "%homens", "homem"]:
                pct_homens = float(valor)
        else:
            if token.isdigit():
                views_list.append(int(token))

    avg_story_views = sum(views_list) // len(views_list) if views_list else 1000

    msg_espera = await update.message.reply_text("🔎 *A extrair dados e calcular viabilidade do teste...*", parse_mode="Markdown")

    try:
        followers, avg_likes, avg_comments = buscar_dados_instagram_api(username)

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
            f"👤 *Perfil:* `{relatorio['username']}` | 👥 `{followers:,}` segs\n"
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
            resposta += "\n🚨 *Alertas de Risco / Anomalias:*\n"
            for w in relatorio['warnings']:
                resposta += f"• {w}\n"

        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_espera.message_id)
        await update.message.reply_text(resposta, parse_mode="Markdown")

    except Exception as e:
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_espera.message_id)
        await update.message.reply_text(f"❌ *Erro:* {str(e)}", parse_mode="Markdown")

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

    print("🚀 Bot Atualizado com Suporte a Reinício!")
    app.run_polling()