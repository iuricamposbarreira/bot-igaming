class IGamingEvaluator:
    def __init__(self, default_cpa=100.0):
        self.default_cpa = default_cpa

    def evaluate_profile(self, username, followers, avg_likes, avg_comments, story_views, views_list=None, pct_homens=35.0, pais="Geral", pct_pais=85.0):
        # Definição de CPA por País
        cpa_dict = {
            "PT": 70.0, "PORTUGAL": 70.0,
            "IT": 170.0, "ITALIA": 170.0, "ITALY": 170.0,
            "DE": 170.0, "ALEMANHA": 170.0, "GERMANY": 170.0,
            "ES": 80.0, "ESPANHA": 80.0, "SPAIN": 80.0,
            "BR": 30.0, "BRASIL": 30.0, "BRAZIL": 30.0
        }
        
        pais_clean = pais.upper().strip()
        cpa = cpa_dict.get(pais_clean, self.default_cpa)

        # Cálculo de Qualificação de Audiência
        pct_homens_dec = pct_homens / 100.0
        pct_pais_dec = pct_pais / 100.0
        
        homens_absolutos = int(story_views * pct_homens_dec)
        views_uteis = int(story_views * pct_homens_dec * pct_pais_dec)

        # Taxa de Engajamento no Feed
        engagement_rate = ((avg_likes + avg_comments) / followers * 100) if followers > 0 else 0
        story_to_follower_ratio = (story_views / followers * 100) if followers > 0 else 0

        warnings = []
        risk_score = 0

        # ----------------------------------------------------
        # LÓGICA INTELIGENTE DE ANOMALIAS E RISCO
        # ----------------------------------------------------
        
        # 1. Análise de Queda de Views nos Stories (Drop-off)
        if views_list and len(views_list) >= 2:
            first_view = views_list[0]
            last_view = views_list[-1]
            if first_view > 0:
                drop_off = ((first_view - last_view) / first_view) * 100
                if drop_off > 50:
                    warnings.append(f"Queda acentuada de retenção nos Stories ({drop_off:.1f}% de perda). Audiência com leitura rápida/passiva.")
                    risk_score += 25

        # 2. Análise do Feed vs. Stories (Com proteção para perfis novos e alta retenção)
        # Só alerta para engajamento baixo se o perfil tiver mais de 2.000 seguidores E o rácio de views nos stories for baixo (<15%)
        if followers > 2000 and story_to_follower_ratio < 15.0:
            if engagement_rate < 0.5:
                warnings.append("Engajamento no feed muito baixo em relação aos seguidores (<0.5%). Risco de seguidores inativos/falsos.")
                risk_score += 25
        # Limite recalibrado com base em campanhas reais (23/07/2026): perfis
        # autênticos observados tinham rácio Views/Seguidores de 22-33%; um
        # perfil confirmado como seguidores falsos tinha 13,8%. Threshold subido
        # de 8% para 18% para apanhar esse caso. Amostra pequena (3 casos) —
        # revisitar à medida que houver mais dados reais.
        seguidores_suspeitos = False
        if followers > 10000 and story_to_follower_ratio < 18.0:
            warnings.append("Volume de Views nos Stories baixo para o total de seguidores. Risco de seguidores comprados/inativos.")
            risk_score += 30
            seguidores_suspeitos = True

        # 3. Análise de Género — combinada com engagement real, não isolada.
        # Nichos diferentes convertem de forma diferente (ex: lifestyle vs. moda),
        # por isso um público feminino só é penalizado se o engagement real
        # (likes/comentários vindos da API) também for fraco. Um perfil como o
        # liikeez (91,6% mulheres, ótimo ROI real) não deve ser penalizado só
        # pelo género quando o engagement mostra audiência genuína e ativa.
        if pct_homens < 25.0 and engagement_rate < 1.0:
            warnings.append(f"Público maioritariamente feminino ({100-pct_homens:.1f}%) combinado com engagement abaixo da média (1%). Historicamente este perfil apresenta conversão reduzida em iGaming.")
            risk_score += 15

        # ----------------------------------------------------
        # CÁLCULOS FINANCEIROS E PROJEÇÕES
        # ----------------------------------------------------
        # Coeficientes recalibrados com base em 3 campanhas reais (23/07/2026):
        # a taxa de cliques assumida (0,5%) estava a sobrestimar sempre — em
        # perfis genuínos por ~1,4-3x, e em perfis de seguidores falsos por
        # até 16x. Baixado para 0,25%, próximo da média dos casos genuínos.
        # Amostra pequena — recalibrar de novo com mais dados reais.
        expected_ftds = round(max(1.0, views_uteis * 0.0008), 1) if views_uteis > 200 else (1.0 if views_uteis > 30 else 0.5)
        expected_clicks = int(story_views * 0.0025) if story_views > 1000 else max(10, int(story_views * 0.08))

        # Penalização real (não só aviso) quando há sinal de seguidores
        # falsos/inativos: no caso real observado, um perfil sinalizado assim
        # gerou 0 FTDs apesar da fórmula prever ~18. Reduzimos a projeção em
        # vez de só mostrar o aviso, para o número não continuar otimista.
        if seguidores_suspeitos:
            expected_ftds = round(expected_ftds * 0.3, 1)
            expected_clicks = int(expected_clicks * 0.3)

        projected_revenue = expected_ftds * cpa

        # Proposta de Valores para Teste de 2 Stories
        base_offer = min(projected_revenue * 0.30, story_views * 0.015)
        max_offer = min(projected_revenue * 0.50, story_views * 0.025)

        # Ajuste para micro-perfis com bom engajamento
        if story_views < 500:
            base_offer = max(15.0, base_offer)
            max_offer = max(25.0, max_offer)

        # Classificação do Status
        if risk_score >= 50:
            status_emoji = "🔴"
            status_text = "ALTO RISCO / DESACONSELHADO"
        elif risk_score >= 20:
            status_emoji = "🟡"
            status_text = "RISCO MODERADO / ALTO POTENCIAL"
        else:
            status_emoji = "🟢"
            status_text = "PERFIL QUALIFICADO / OPORTUNIDADE"

        cpv_qualificado = round(base_offer / max(1, views_uteis), 3)

        publico_feminino_fraco = pct_homens < 30 and engagement_rate < 1.0
        recommendation = (
            f"Público maioritariamente feminino ({100-pct_homens:.1f}%) com engagement abaixo da média, mas o volume absoluto de audiência permite conversão. "
            f"Propor Teste de 2 Stories entre €{int(base_offer)} e €{int(max_offer)}."
            if publico_feminino_fraco else
            f"Público com bom potencial de conversão. Avançar com proposta de Teste de 2 Stories até €{int(base_offer)}."
        )

        return {
            "username": username,
            "followers": followers,
            "cpa_used": cpa,
            "homens_absolutos": homens_absolutos,
            "views_uteis": views_uteis,
            "status_emoji": status_emoji,
            "status_text": status_text,
            "risk_index": f"{risk_score}%",
            "expected_ftds": expected_ftds,
            "expected_clicks": expected_clicks,
            "cpv_qualificado": cpv_qualificado,
            "projected_revenue_eur": projected_revenue,
            "pack_2_stories_suggested": round(base_offer, 2),
            "pack_2_stories_max": round(max_offer, 2),
            "recommendation": recommendation,
            "warnings": warnings
        }