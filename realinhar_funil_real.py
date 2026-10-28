"""
Realinha o funil mock ao funil REAL do Greenhouse.

Motivo: a descoberta #1 (sql/passo1_descoberta.sql) mostrou que o processo real
tem duas etapas que o protótipo não modelava (o case escrito) e que a
conversa final aparece com três nomes diferentes no Greenhouse.

De -> para aplicado em funil_pipe.csv:

    Envio de Currículo    -> Avaliação de currículo
    (nova)                -> Envio do Case Escrito
    (nova)                -> Avaliação case escrito
    Entrevista Fit        -> Entrevista Fit
    Técnica 1             -> Entrevista Técnica 1
    Técnica 2             -> Entrevista Técnica 2
    Conversa com André    -> Conversa Final     (nome de pessoa em etapa
                                                 quebra quando a pessoa sai)
    Oferta                -> Oferta
    Contratação           -> Contratação        (no Greenhouse real isso é
                                                 status, não etapa)

Os volumes das etapas que já existiam são PRESERVADOS. As duas etapas novas
entram por interpolação geométrica entre o volume de currículos e o da
Entrevista Fit, mantendo o funil monotonicamente decrescente e com números
legíveis — o funil real cai de 65.840 para 279 nesse trecho, o que num mock
de protótipo viraria zero.

conversao_pct é RECALCULADA a partir dos volumes em todas as etapas: a
Entrevista Fit agora recebe candidatos do case, não da triagem, então o
valor antigo deixou de valer. Isso também deixa a última barra
(Oferta -> Contratação) exatamente igual à taxa de aceite de oferta, que é
o que a legenda do gráfico afirma.

Depois de rodar este script, rodar também:
    python gerar_mocks_extra.py          (funil_pipe_nivel.csv)
    python gerar_candidatos_parados.py   (candidatos_parados.csv)

Rodar uma vez só — é idempotente (detecta se o funil já está realinhado).
"""

import random

import pandas as pd

SEED = 23
CRITICO_MARGEM = 5  # dias acima da meta a partir dos quais vira crítico

RENOMES = {
    "Envio de Currículo": "Avaliação de currículo",
    "Técnica 1": "Entrevista Técnica 1",
    "Técnica 2": "Entrevista Técnica 2",
    "Conversa com André": "Conversa Final",
}

# etapas novas, na ordem em que entram entre a triagem e a Entrevista Fit
ETAPAS_CASE = [
    ("Envio do Case Escrito", 3),    # (etapa, meta_sla_dias)
    ("Avaliação case escrito", 3),
]

ORDEM_NOVA = [
    "Avaliação de currículo",
    "Envio do Case Escrito",
    "Avaliação case escrito",
    "Entrevista Fit",
    "Entrevista Técnica 1",
    "Entrevista Técnica 2",
    "Conversa Final",
    "Oferta",
    "Contratação",
]


def tempo_para_etapa(rng, meta):
    """Tempo médio plausível para uma etapa nova: a maioria perto da meta,
    alguns casos acima (para as telas de SLA e gargalo terem sinal)."""
    sorteio = rng.random()
    if sorteio < 0.12:                       # crítico
        return round(meta + CRITICO_MARGEM + rng.uniform(0.5, 4.0), 1)
    if sorteio < 0.45:                       # atenção
        return round(meta + rng.uniform(0.2, CRITICO_MARGEM - 0.5), 1)
    return round(max(meta - rng.uniform(0.1, 1.2), 0.5), 1)  # dentro da meta


def status_sla(tempo, meta):
    if pd.isna(tempo) or pd.isna(meta):
        return None
    if tempo > meta + CRITICO_MARGEM:
        return "critico"
    if tempo > meta:
        return "atencao"
    return "ok"


def main():
    rng = random.Random(SEED)
    pipe = pd.read_csv("funil_pipe.csv")

    if "Avaliação de currículo" in set(pipe["etapa"]):
        print("funil_pipe.csv já está realinhado — nada a fazer.")
        return

    pipe["etapa"] = pipe["etapa"].replace(RENOMES)

    linhas_novas = []
    for (mes, chapter), grupo in pipe.groupby(["mes", "chapter"], sort=False):
        por_etapa = grupo.set_index("etapa")
        cv = por_etapa.loc["Avaliação de currículo", "candidatos"]
        fit = por_etapa.loc["Entrevista Fit", "candidatos"]
        mes_label = grupo["mes_label"].iloc[0]

        # interpolação geométrica: 3 passos de cv até fit
        razao = (fit / cv) ** (1 / 3) if cv else 0
        volumes = [max(int(round(cv * razao ** (i + 1))), int(fit) + 1) for i in range(2)]

        for (etapa, meta), candidatos in zip(ETAPAS_CASE, volumes):
            tempo = tempo_para_etapa(rng, meta)
            linhas_novas.append(
                {
                    "mes": mes,
                    "mes_label": mes_label,
                    "chapter": chapter,
                    "etapa": etapa,
                    "ordem_etapa": 0,          # recalculado abaixo
                    "candidatos": candidatos,
                    "conversao_pct": None,     # recalculado abaixo
                    "tempo_medio_dias": tempo,
                    "meta_sla_dias": meta,
                    "excesso_dias": round(tempo - meta, 1),
                    "status_sla": status_sla(tempo, meta),
                }
            )

    pipe = pd.concat([pipe, pd.DataFrame(linhas_novas)], ignore_index=True)

    # ordem canônica
    ordem = {e: i + 1 for i, e in enumerate(ORDEM_NOVA)}
    faltando = set(pipe["etapa"]) - set(ordem)
    if faltando:
        raise SystemExit(f"etapa fora da ordem canônica: {faltando}")
    pipe["ordem_etapa"] = pipe["etapa"].map(ordem)
    pipe = pipe.sort_values(["mes", "chapter", "ordem_etapa"]).reset_index(drop=True)

    # conversão recalculada a partir do volume, dentro de cada (mes, chapter)
    pipe["conversao_pct"] = None
    for _, idx in pipe.groupby(["mes", "chapter"], sort=False).groups.items():
        bloco = pipe.loc[idx].sort_values("ordem_etapa")
        anterior = None
        for i, row in bloco.iterrows():
            if anterior is not None and anterior > 0:
                pipe.at[i, "conversao_pct"] = round(row["candidatos"] / anterior * 100, 1)
            anterior = row["candidatos"]

    pipe.to_csv("funil_pipe.csv", index=False)

    # ---- sanidade -----------------------------------------------------
    for (mes, chapter), grupo in pipe.groupby(["mes", "chapter"]):
        g = grupo.sort_values("ordem_etapa")
        vols = g["candidatos"].tolist()
        assert vols == sorted(vols, reverse=True), f"funil não decrescente em {mes}/{chapter}: {vols}"
        assert g["etapa"].tolist() == ORDEM_NOVA, f"etapas faltando em {mes}/{chapter}"
    conv = pipe.dropna(subset=["conversao_pct"])["conversao_pct"].astype(float)
    assert conv.between(0, 100).all(), "conversão fora de 0-100"

    print(f"funil_pipe.csv realinhado: {len(pipe)} linhas, {pipe['etapa'].nunique()} etapas")
    amostra = pipe[(pipe["mes"] == pipe["mes"].max()) & (pipe["chapter"] == "Data Science")]
    print(amostra[["etapa", "candidatos", "conversao_pct", "tempo_medio_dias",
                   "meta_sla_dias", "status_sla"]].to_string(index=False))


if __name__ == "__main__":
    main()
