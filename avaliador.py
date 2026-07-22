class IGamingEvaluator:
    def __init__(self, default_cpa: float = 100.0):
        self.default_cpa = default_cpa

        # CPAs Reais Oficiais da Operação
        self.tier_cpa = {
            "austria": 130.0, "at": 130.0,
            "belgica": 300.0, "belgium": 300.0, "be": 300.0,
            "franca": 100.0, "france": 100.0, "fr": 100.0,
            "alemanha": 170.0, "germany": 170.0, "deutschland": 170.0, "de": 170.0,
            "italia": 170.0, "italy": 170.0, "it": 170.0,
            "luxemburgo": 300.0, "luxembourg": 300.0, "lu": 300.0,
            "portugal": 70.0, "pt": 70.0,
            "espanha": 120.0, "spain": 120.0, "es": 120.0,
            "suica": 110.0, "switzerland": 110.0, "ch": 110.0,
        }

    def evaluate_profile(
        self,
        username: str,
        followers: int,
        avg_likes: int,
        avg_comments: int,
        story_views: float,
        views_list: list = None,
        pct_homens: float = 35.0,  # Padrão flexível se não for informado
        pais: str = "Geral",
        pct_pais: float = 85.0     # Padrão flexível se não for informado
    ) -> dict:

        # 1. Obter CPA exato
        pais_clean = pais.lower().strip()
        cpa_real = self.tier_cpa.get(pais_clean, self.default_cpa)

        # 2. Views Qualificadas e Segmentação
        views_no_pais = story_views * (pct_pais / 100.0)
        homens_absolutos = views_no_pais * (pct_homens / 100.0)
        mulheres_absolutas = views_no_pais - homens_absolutos

        # 3. Análise de Retenção (Drop-off entre Stories)
        drop_off_warning = False
        if views_list and len(views_list) > 1:
            max_v = max(views_list)
            min_v = min(views_list)
            if max_v > 0 and (min_v / max_v) < 0.35:
                drop_off_warning = True

        # 4. Auditoria de Engajamento e Fakes
        risk_index = 0
        warnings = []
        if followers > 0:
            engagement_rate = ((avg_likes + avg_comments) / followers) * 100
            if engagement_rate < 0.3:
                risk_index += 25
                warnings.append("Engajamento no feed baixo (<0.3%). Risco de seguidores inativos/falsos.")

        if drop_off_warning:
            risk_index += 20
            warnings.append("Queda de retenção entre Stories (Efeito Viral/Fofoca). Tráfego de passagem.")

        # 5. Algoritmo de Conversão Equilibrado (Homens + Mulheres)
        # Considera que homens convertem com taxa base e mulheres com ~40% do potencial masculino
        weighted_views = homens_absolutos + (mulheres_absolutas * 0.40)
        
        if drop_off_warning:
            conversion_rate = 0.00025
        else:
            conversion_rate = 0.00045

        expected_ftds = weighted_views * conversion_rate
        if expected_ftds < 1.0:
            expected_ftds = 1.0

        projected_revenue = expected_ftds * cpa_real
        expected_clicks = int(views_no_pais * 0.008)
        if expected_clicks < 40: expected_clicks = 40

        # Margens Comerciais para 2 Stories
        raw_suggested = projected_revenue * 0.30
        raw_max = projected_revenue * 0.50

        # 6. Cálculo de CPV Qualificado (Métrica de Eficiência)
        # Estima custo por visualização útil em relação ao valor teto recomendado
        cpv_qualificado = (raw_suggested / weighted_views) if weighted_views > 0 else 0.0

        # 7. Classificação Visual e Nível de Risco
        if risk_index >= 45 or (pct_homens < 10 and homens_absolutos < 500):
            status_emoji = "⛔"
            status_text = "REPROVADO"
            pack_2_stories_suggested = 0.0
            pack_2_stories_max = 0.0
            recommendation = "Indicadores fracos de engajamento ou audiência sem expressão. Não avançar com teste."

        elif pct_homens < 20 or drop_off_warning or risk_index >= 25:
            status_emoji = "🟡"
            status_text = "RISCO MODERADO / ALTO POTENCIAL"
            pack_2_stories_suggested = min(raw_suggested, 220.0)
            pack_2_stories_max = min(raw_max, 350.0)
            recommendation = (
                f"Público maioritariamente feminino ({100 - pct_homens:.1f}%), mas o volume absoluto de audiência permite conversão. "
                f"Propor Teste de 2 Stories entre €{int(pack_2_stories_suggested)} e €{int(pack_2_stories_max)}."
            )

        elif pct_homens < 45:
            status_emoji = "🟠"
            status_text = "OPORTUNIDADE MISTA"
            pack_2_stories_suggested = min(raw_suggested, 350.0)
            pack_2_stories_max = min(raw_max, 500.0)
            recommendation = f"Público equilibrado. Avançar com proposta de Teste de 2 Stories até €{int(pack_2_stories_suggested)}."

        else:
            status_emoji = "🟢"
            status_text = "APROVADO PARA TESTE"
            pack_2_stories_suggested = raw_suggested
            pack_2_stories_max = raw_max
            recommendation = f"Excelente densidade de público qualificado. Propor teste de 2 Stories por €{int(pack_2_stories_suggested)}."

        return {
            "username": username,
            "followers": followers,
            "status_emoji": status_emoji,
            "status_text": status_text,
            "risk_index": f"{risk_index}%",
            "cpa_used": cpa_real,
            "declared_views": int(story_views),
            "views_no_pais": int(views_no_pais),
            "homens_absolutos": int(homens_absolutos),
            "expected_ftds": round(expected_ftds, 1),
            "expected_clicks": expected_clicks,
            "cpv_qualificado": round(cpv_qualificado, 3),
            "projected_revenue_eur": round(projected_revenue, 2),
            "pack_2_stories_suggested": round(pack_2_stories_suggested, 2),
            "pack_2_stories_max": round(pack_2_stories_max, 2),
            "recommendation": recommendation,
            "warnings": warnings
        }