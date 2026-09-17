"""
Gera candidatos_parados.csv — quem são os candidatos parados em cada etapa.

Dado mock, no mesmo espírito de su_banco_talentos.csv (nomes fictícios): o
Greenhouse hoje não expõe "tempo parado por candidato" de forma direta, mas a
Visão do Pipe precisa responder "quem está parado e há quanto tempo", não só
"quantos". O volume é ancorado no funil_pipe.csv: etapas com excesso de SLA
naquele mês concentram mais candidatos parados; etapas dentro da meta quase
não têm.

Regra de status (a mesma do resto do app):
    dias na etapa > meta                -> atenção
    dias na etapa > meta + 5            -> crítico

Rodar de novo:

    python gerar_candidatos_parados.py
"""

import random

import pandas as pd

SEED = 11
CRITICO_MARGEM = 5  # dias acima da meta a partir dos quais vira crítico

# Cada chapter tem vagas abertas; o candidato parado pertence a uma delas.
VAGAS = {
    "AI Engineering": [
        ("AI Engineer · Pleno", "Squad GenAI"),
        ("AI Engineer · Sênior", "Projeto Atlas"),
    ],
    "Analytics Engineering": [
        ("Analytics Engineer · Júnior", "Squad BI"),
        ("Analytics Engineer · Sênior", "Projeto Orion"),
    ],
    "Data Consultant": [
        ("Data Consultant · Pleno", "Squad Retail"),
        ("Data Consultant · Sênior", "Projeto Atlas"),
    ],
    "Data Engineering": [
        ("Data Engineer · Pleno", "Plataforma de Dados"),
        ("Data Engineer · Sênior", "Squad Growth"),
    ],
    "Data Science": [
        ("Data Scientist · Pleno", "Squad Growth"),
        ("Data Scientist · Sênior", "Projeto Orion"),
    ],
    "Software Engineering": [
        ("Software Engineer · Pleno", "Plataforma de Dados"),
        ("Software Engineer · Sênior", "Squad GenAI"),
    ],
}

SENIORIDADE_DA_VAGA = {
    "Júnior": "Junior",
    "Pleno": "Pleno",
    "Sênior": "Senior",
    "Staff": "Staff",
}

PRIMEIROS = [
    "Ana", "Bruno", "Camila", "Diego", "Elisa", "Fabio", "Gabriel", "Helena",
    "Igor", "Julia", "Kaique", "Larissa", "Marcelo", "Natalia", "Otavio",
    "Paula", "Rafael", "Sofia", "Thiago", "Vanessa", "Caio", "Mariana",
    "Lucas", "Beatriz", "Renato", "Isabela", "Vitor", "Carolina", "Andre",
    "Patricia", "Leonardo", "Fernanda",
]
SOBRENOMES = [
    "Almeida", "Barbosa", "Cardoso", "Duarte", "Esteves", "Ferreira", "Gomes",
    "Henriques", "Ibrahim", "Junqueira", "Klein", "Lopes", "Martins", "Nunes",
    "Oliveira", "Pacheco", "Queiroz", "Ribeiro", "Souza", "Teixeira",
    "Vasconcelos", "Xavier", "Azevedo", "Bittencourt",
]


def quantos_parados(rng, status_sla, candidatos):
    """Quantos candidatos ficam parados numa (chapter, etapa) do mês.

    Etapas estouradas no SLA concentram mais gente parada; etapas dentro da
    meta ainda podem ter um caso isolado. Nunca passa do volume da etapa."""
    if status_sla == "critico":
        n = rng.randint(2, 4)
    elif status_sla == "atencao":
        n = rng.randint(1, 3)
    else:
        n = 1 if rng.random() < 0.25 else 0
    return min(n, int(candidatos))


def main():
    rng = random.Random(SEED)
    pipe = pd.read_csv("funil_pipe.csv")

    # "Contratação" é o fim do funil (já contratado) — ninguém fica parado lá.
    ativo = pipe[
        pipe["meta_sla_dias"].notna()
        & pipe["candidatos"].notna()
        & (pipe["etapa"] != "Contratação")
    ].copy()

    usados = set()
    linhas = []

    for row in ativo.sort_values(["mes", "chapter", "ordem_etapa"]).itertuples(index=False):
        vagas_chapter = VAGAS.get(row.chapter)
        if not vagas_chapter:
            continue
        n = quantos_parados(rng, row.status_sla, row.candidatos)
        meta = float(row.meta_sla_dias)
        for _ in range(n):
            vaga, squad = vagas_chapter[rng.randrange(len(vagas_chapter))]
            senioridade = SENIORIDADE_DA_VAGA[vaga.split("·")[-1].strip()]

            # crítico só aparece de verdade onde a etapa já estourou a meta
            if row.status_sla == "critico":
                critico = rng.random() < 0.7
            elif row.status_sla == "atencao":
                critico = rng.random() < 0.2
            else:
                critico = False

            if critico:
                dias = meta + CRITICO_MARGEM + rng.randint(1, 9)
                status = "critico"
            else:
                dias = meta + rng.randint(1, CRITICO_MARGEM)
                status = "atencao"

            for _tentativa in range(40):
                nome = f"{rng.choice(PRIMEIROS)} {rng.choice(SOBRENOMES)}"
                if nome not in usados:
                    break
            usados.add(nome)

            linhas.append(
                {
                    "mes": row.mes,
                    "mes_label": row.mes_label,
                    "chapter": row.chapter,
                    "vaga": vaga,
                    "squad": squad,
                    "senioridade": senioridade,
                    "etapa": row.etapa,
                    "ordem_etapa": int(row.ordem_etapa),
                    "candidato": nome,
                    "dias_na_etapa": int(dias),
                    "meta_sla_dias": int(meta),
                    "status": status,
                }
            )

    df = pd.DataFrame(linhas)
    df = df.sort_values(
        ["mes", "ordem_etapa", "status", "dias_na_etapa"], ascending=[True, True, True, False]
    )
    df.to_csv("candidatos_parados.csv", index=False)

    # sanidade: status coerente com dias vs meta, e etapas/chapters válidos
    assert (df.loc[df["status"] == "critico", "dias_na_etapa"]
            > df.loc[df["status"] == "critico", "meta_sla_dias"] + CRITICO_MARGEM).all()
    assert (df.loc[df["status"] == "atencao", "dias_na_etapa"]
            > df.loc[df["status"] == "atencao", "meta_sla_dias"]).all()
    assert (df.loc[df["status"] == "atencao", "dias_na_etapa"]
            <= df.loc[df["status"] == "atencao", "meta_sla_dias"] + CRITICO_MARGEM).all()
    assert set(df["etapa"]) <= set(pipe["etapa"])
    assert set(df["chapter"]) <= set(pipe["chapter"])

    print(f"candidatos_parados.csv: {len(df)} linhas, {df['candidato'].nunique()} candidatos")
    print(df.groupby(["mes", "status"]).size().unstack(fill_value=0))


if __name__ == "__main__":
    main()
