import logging
import requests
import re
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from avaliador import IGamingEvaluator

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

TOKEN_BOT = "8944907729:AAE8_GZX4Mx3EIxG67AQ_hG7mzecx87dy8M"
RAPIDAPI_KEY = "44faf2cfd5msh084db8e1cf193e2p164debjsncb95a30318a5"

evaluator = IGamingEvaluator(default_cpa=100.0)

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
        posts = data.get("timeline_media", {}).get("edges", []) or data.get("user", {}).get("edge_owner_to_timeline_media", {}).get("edges", [])
        
        total_likes = sum([p.get("node", {}).get("edge_liked_by", {}).get("count", 0) for p in posts[:10]])
        total_comments = sum([p.get("node", {}).get("edge_media_to_comment", {}).get("count", 0) for p in posts[:10]])
        
        count = len(posts[:10])
        avg_likes = int(total_likes / count) if count > 0 else 0
        avg_comments = int(total_comments / count) if count > 0 else 0
        
        return followers, avg_likes, avg_comments
    else:
        raise Exception(f"Erro na API ({response.status_code})")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ajuda(update, context)

async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📖 *AVALIADOR DE TESTE DE 2 STORIES (SISTEMA FLEXÍVEL)*\n\n"
        "⚡️ *Atalho Rápido (Apenas Views):*\n"
        "`/avaliar @noemi_silipo 33859 33001 15103`\n\n"
        "🎯 *Avaliação Detalhada (Com Prints):*\n"
        "`/avaliar @noemi_silipo 33859 33001 15103 pais=it %pais=94.6 homens=15.9`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def avaliar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("❌ Envia o username e as views! Escreve `/ajuda` para ver o guia.", parse_mode="Markdown")
        return

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
    app = ApplicationBuilder().token(TOKEN_BOT).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ajuda", ajuda))
    app.add_handler(CommandHandler("avaliar", avaliar))
    print("🚀 Bot Atualizado e Pronto!")
    app.run_polling()