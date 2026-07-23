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
logger = logging.getLogger("bot_igaming")

# ----------------------------------------------------
# Credenciais (via variáveis de ambiente)
# ----------------------------------------------------
# IMPORTANTE: define estas variáveis no ambiente (Render > Environment) em vez
# de as colocares no código. Se já expuseste o token/key antigos nalgum lado
# (chat, repositório público, etc.), gera novos:
#   - Telegram: fala com o @BotFather -> /revoke -> /token
#   - RapidAPI: no painel da tua app, gera uma nova key
TOKEN_BOT = os.environ.get("TOKEN_BOT")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

if not TOKEN_BOT or not RAPIDAPI_KEY:
    raise RuntimeError(
        "Faltam variáveis de ambiente TOKEN_BOT e/ou RAPIDAPI_KEY. "
        "Define-as no teu serviço (Render > Environment) antes de arrancar o bot."
    )

evaluator = IGamingEvaluator(default_cpa=100.0)

CACHE_API = {}
CACHE_TTL_SECONDS = 6 * 60 * 60  # 6h em vez de 24h, para não "prender" dados errados durante um dia inteiro enquanto ajustas a API

USERNAME, VIEWS, PAIS, PCT_PAIS, HOMENS = range(5)

RAPIDAPI_HOST = "instagram-public-bulk-scraper.p.rapidapi.com"

# ----------------------------------------------------
# Servidor Web Leve (Render)
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
# Procura Exaustiva de valores no JSON (genérico)
# ----------------------------------------------------
def _procurar_chave_numerica(data, chaves, _profundidade=0):
    """
    Percorre recursivamente um JSON (dict/list) à procura da primeira chave
    (de uma lista de nomes possíveis) que contenha um número > 0, ou um dict
    com sub-chave 'count'/'value'.
    Devolve None se não encontrar nada (em vez de 0), para conseguirmos
    distinguir "não encontrado" de "encontrado e é zero".
    """
    if _profundidade > 8:  # proteção contra JSON muito aninhado / recursão infinita
        return None

    if isinstance(data, dict):
        for key in chaves:
            if key in data:
                val = data[key]
                if isinstance(val, bool):
                    continue
                if isinstance(val, (int, float)) and val > 0:
                    return int(val)
                if isinstance(val, dict):
                    for sub_key in ("count", "value", "num"):
                        if sub_key in val and isinstance(val[sub_key], (int, float)):
                            return int(val[sub_key])
                if isinstance(val, str) and val.isdigit():
                    return int(val)

        for v in data.values():
            if isinstance(v, (dict, list)):
                res = _procurar_chave_numerica(v, chaves, _profundidade + 1)
                if res:
                    return res

    elif isinstance(data, list):
        for item in data:
            res = _procurar_chave_numerica(item, chaves, _profundidade + 1)
            if res:
                return res

    return None


def extrair_seguidores(data):
    chaves = [
        "follower_count", "followers_count", "followersCount",
        "followers", "edge_followed_by", "follower", "n_followers",
    ]
    resultado = _procurar_chave_numerica(data, chaves)
    return resultado or 0


def extrair_seguindo(data):
    chaves = ["following_count", "followingCount", "following", "edge_follow"]
    resultado = _procurar_chave_numerica(data, chaves)
    return resultado or 0


def extrair_posts_para_engagement(data):
    """
    Tenta encontrar uma lista de posts/media recentes para calcular
    engagement real (likes/comentários médios). Devolve (avg_likes, avg_comments)
    ou (None, None) se não encontrar nada utilizável.
    """
    candidatos_chaves_lista = [
        "edge_owner_to_timeline_media", "medias", "media", "posts",
        "items", "recent_posts", "timeline_media",
    ]

    def procurar_lista(d, _prof=0):
        if _prof > 8:
            return None
        if isinstance(d, dict):
            for k in candidatos_chaves_lista:
                if k in d:
                    v = d[k]
                    if isinstance(v, dict) and "edges" in v:
                        v = v["edges"]
                    if isinstance(v, list) and len(v) > 0:
                        return v
            for v in d.values():
                if isinstance(v, (dict, list)):
                    res = procurar_lista(v, _prof + 1)
                    if res:
                        return res
        elif isinstance(d, list):
            for item in d:
                res = procurar_lista(item, _prof + 1)
                if res:
                    return res
        return None

    posts = procurar_lista(data)
    if not posts:
        return None, None

    likes_chaves = ["like_count", "likes_count", "likes", "edge_liked_by", "edge_media_preview_like"]
    comments_chaves = ["comment_count", "comments_count", "comments", "edge_media_to_comment"]

    total_likes = []
    total_comments = []
    for post in posts[:12]:  # não vale a pena olhar para mais que ~12 posts
        node = post.get("node", post) if isinstance(post, dict) else post
        likes = _procurar_chave_numerica(node, likes_chaves)
        comments = _procurar_chave_numerica(node, comments_chaves)
        if likes is not None:
            total_likes.append(likes)
        if comments is not None:
            total_comments.append(comments)

    avg_likes = int(sum(total_likes) / len(total_likes)) if total_likes else None
    avg_comments = int(sum(total_comments) / len(total_comments)) if total_comments else None
    return avg_likes, avg_comments


def parece_privado(data):
    chaves = ["is_private", "isPrivate", "private"]
    def procurar(d, _prof=0):
        if _prof > 8:
            return False
        if isinstance(d, dict):
            for k in chaves:
                if k in d and isinstance(d[k], bool):
                    return d[k]
            for v in d.values():
                if isinstance(v, (dict, list)):
                    if procurar(v, _prof + 1):
                        return True
        elif isinstance(d, list):
            for item in d:
                if procurar(item, _prof + 1):
                    return True
        return False
    return procurar(data)


# ----------------------------------------------------
# API Instagram
# ----------------------------------------------------
def buscar_dados_instagram_api(username: str):
    """
    Devolve (followers, avg_likes, avg_comments, is_fallback, motivo)
    motivo é só para logging/diagnóstico, não é mostrado ao utilizador.
    """
    clean_username = username.replace("@", "").strip().lower()

    if clean_username in CACHE_API:
        timestamp, data = CACHE_API[clean_username]
        if time.time() - timestamp < CACHE_TTL_SECONDS:
            logger.info(f"[{clean_username}] A usar dados em cache.")
            return data

    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST,
    }

    # Combinações de (path, nome do parâmetro de query) mais comuns nesta
    # família de APIs de scraping de Instagram no RapidAPI. Se nenhuma
    # funcionar, o diagnóstico abaixo vai dizer-te exatamente porquê
    # (404 = path errado, 403 = não subscrito a esse endpoint, 200+sem dados =
    # precisamos de ver o JSON real).
    tentativas = [
        # Confirmado a funcionar em testes manuais no RapidAPI (23/07/2026):
        # GET /v1/user_info_web?username=... -> devolve data.edge_followed_by.count
        ("/v1/user_info_web", "username"),
        # Alternativas de reserva, caso o endpoint principal mude no futuro:
        ("/userinfo/", "username_or_id"),
        ("/userinfo/", "username"),
    ]

    ultimo_status = None
    ultimo_corpo = None

    for path, param_name in tentativas:
        url = f"https://{RAPIDAPI_HOST}{path}"
        params = {param_name: clean_username}
        try:
            logger.info(f"[{clean_username}] A tentar {url} com {params}")
            response = requests.get(url, headers=headers, params=params, timeout=12)
            ultimo_status = response.status_code
            ultimo_corpo = response.text[:500]

            if response.status_code == 404:
                logger.warning(f"[{clean_username}] 404 em {url} — endpoint não existe, a tentar próximo.")
                continue

            if response.status_code == 403:
                logger.error(
                    f"[{clean_username}] 403 em {url} — provavelmente não estás subscrito "
                    f"a este endpoint específico no RapidAPI, ou a key é inválida."
                )
                continue

            if response.status_code != 200:
                logger.warning(f"[{clean_username}] Status {response.status_code} em {url}: {ultimo_corpo}")
                continue

            json_data = response.json()
            # LOG COMPLETO para diagnóstico — vê isto nos logs do Render se ainda falhar.
            logger.info(f"[{clean_username}] JSON completo de {url}:\n{json_data}")

            if parece_privado(json_data):
                logger.info(f"[{clean_username}] Perfil marcado como privado no JSON.")
                resultado = (0, 0, 0, True, "perfil_privado")
                CACHE_API[clean_username] = (time.time(), resultado)
                return resultado

            followers = extrair_seguidores(json_data)
            if followers <= 0:
                logger.warning(f"[{clean_username}] Endpoint respondeu 200 mas não encontrei seguidores no JSON.")
                continue

            avg_likes, avg_comments = extrair_posts_para_engagement(json_data)
            if avg_likes is None or avg_comments is None:
                # Não conseguimos engagement real deste endpoint — usamos uma
                # estimativa conservadora, mas isto fica registado no log.
                logger.info(f"[{clean_username}] Sem posts para engagement real, a estimar.")
                avg_likes = int(followers * 0.03)
                avg_comments = int(avg_likes * 0.05)
                resultado = (followers, avg_likes, avg_comments, False, "engagement_estimado")
            else:
                resultado = (followers, avg_likes, avg_comments, False, "ok")

            CACHE_API[clean_username] = (time.time(), resultado)
            logger.info(f"[{clean_username}] Sucesso via {url}: seguidores={followers}, likes={avg_likes}, comments={avg_comments}")
            return resultado

        except requests.exceptions.Timeout:
            logger.error(f"[{clean_username}] Timeout em {url}")
        except Exception as e:
            logger.error(f"[{clean_username}] Erro no pedido API ({url}): {e}")

    logger.error(
        f"[{clean_username}] Todas as tentativas falharam. "
        f"Último status: {ultimo_status}, corpo: {ultimo_corpo}"
    )
    return 0, 0, 0, True, f"falhou_todas_tentativas(status={ultimo_status})"


# ----------------------------------------------------
# Comandos
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
# MODO GUIADO (5 PASSOS)
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

    msg_espera = await update.message.reply_text("🔎 *A consultar Instagram e a gerar auditoria...*", parse_mode="Markdown")

    try:
        followers, avg_likes, avg_comments, is_fallback, motivo = buscar_dados_instagram_api(username)
        logger.info(f"Motivo do resultado da API para {username}: {motivo}")

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

        if followers > 0:
            txt_seguidores = f"{followers:,}"
            er_val = round(((avg_likes + avg_comments) / followers) * 100, 2)
            txt_er = f"{er_val}%"
        elif motivo == "perfil_privado":
            txt_seguidores = "Não obtido (Perfil privado)"
            txt_er = "N/A"
        else:
            txt_seguidores = "Não obtido (falha na API — ver logs)"
            txt_er = "N/A"

        # Etiqueta de proveniência: dados confirmados via API vs. inseridos manualmente.
        # Isto não muda os cálculos — só deixa claro no relatório o que é verificado
        # e o que é autodeclarado, para quem decide saber onde confiar mais.
        origem_seguidores = "✅ via API" if followers > 0 else "⚠️ falhou"

        resposta = (
            f"📊 *RELATÓRIO DE AUDITORIA (2 STORIES)*\n"
            f"👤 *Perfil:* `{relatorio['username']}`\n"
            f"👥 *Seguidores Instagram:* `{txt_seguidores}` ({origem_seguidores})\n"
            f"📊 *Engajamento Est.:* `{txt_er}` ({origem_seguidores})\n"
            f"📲 *Média Views Stories:* `{avg_story_views:,}` (✍️ autodeclarado)\n"
            f"🌍 *País:* `{pais.upper()}` ({pct_pais}%) → *CPA:* €{relatorio['cpa_used']} (✍️ autodeclarado)\n"
            f"👨 *Homens:* `{pct_homens}%` (~{relatorio['homens_absolutos']:,} homens/story) (✍️ autodeclarado)\n"
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
        logger.exception(f"Erro ao gerar relatório para {username}")
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

    print("🚀 Bot Atualizado!")
    app.run_polling()