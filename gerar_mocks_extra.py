"""
Gera funil_pipe_nivel.csv e su_ofertas.csv a partir dos CSVs mock existentes.

Não substitui um "build_mocks.py" completo (que não está neste repositório) —
cobre só os dois CSVs derivados usados pela seção ampliada da Visão do Pipe:

- funil_pipe_nivel.csv: quebra funil_pipe.csv (mês × chapter × etapa) por
  senioridade, com o volume de cada (mês, chapter, etapa) preservado
  exatamente (soma por senioridade == valor original em funil_pipe.csv).
- su_ofertas.csv: histórico mensal de ofertas/aceites de candidatos vindos do
  banco See You Soon, por chapter — dado mock, não existe hoje no Greenhouse
  de forma separada da oferta "normal".

Rodar de novo (por exemplo, depois de editar farol_executivo.csv ou
funil_pipe.csv manualmente):

    python gerar_mocks_extra.py
"""

import pandas as pd
import numpy as np

np.random.seed(7)

pipe = pd.read_csv("funil_pipe.csv")
farol = pd.read_csv("farol_executivo.csv")

FAROL_CHAPTERS = sorted(farol["chapter"].unique())
SENIORIDADES = ["Junior", "Pleno", "Senior", "Staff"]
BASE_W = {"Junior": 0.32, "Pleno": 0.38, "Senior": 0.25, "Staff": 0.05}

def weights_for_stage(ordem_etapa):
    # conforme a etapa avança, o peso desloca de Junior para Senior/Staff
    # (candidatos junior tendem a cair mais cedo no funil).
    shift = min(0.02 * (ordem_etapa - 1), 0.14)
    w = {
        "Junior": max(BASE_W["Junior"] - shift, 0.06),
        "Pleno": BASE_W["Pleno"],
        "Senior": BASE_W["Senior"] + shift * 0.7,
        "Staff": BASE_W["Staff"] + shift * 0.3,
    }
    total = sum(w.values())
    return {k: v / total for k, v in w.items()}

def largest_remainder_split(total, weights_dict):
    keys = list(weights_dict.keys())
    raw = {k: total * weights_dict[k] for k in keys}
    floors = {k: int(np.floor(v)) for k, v in raw.items()}
    remainder = total - sum(floors.values())
    fracs = sorted(keys, key=lambda k: raw[k] - floors[k], reverse=True)
    for k in fracs[:remainder]:
        floors[k] += 1
    return floors

rows = []
sub = pipe[pipe["chapter"].isin(FAROL_CHAPTERS)]
for _, r in sub.iterrows():
    w = weights_for_stage(int(r["ordem_etapa"]))
    split = largest_remainder_split(int(r["candidatos"]), w)
    for sen in SENIORIDADES:
        rows.append({
            "mes": r["mes"], "mes_label": r["mes_label"], "chapter": r["chapter"],
            "senioridade": sen, "etapa": r["etapa"], "ordem_etapa": r["ordem_etapa"],
            "candidatos": split[sen],
        })

nivel_df = pd.DataFrame(rows)
# valida: soma por (mes,chapter,etapa) bate com funil_pipe.csv original
check = nivel_df.groupby(["mes", "chapter", "etapa"])["candidatos"].sum().reset_index()
merged = check.merge(sub[["mes", "chapter", "etapa", "candidatos"]], on=["mes", "chapter", "etapa"], suffixes=("_nivel", "_orig"))
assert (merged["candidatos_nivel"] == merged["candidatos_orig"]).all(), "totais nao batem!"
nivel_df.to_csv("funil_pipe_nivel.csv", index=False)
print("funil_pipe_nivel.csv OK ->", nivel_df.shape)

# ---------------------------------------------------------------------------
# su_ofertas.csv — histórico mensal de ofertas/aceites vindas do banco See You
# Soon, por chapter. Mock: taxa de aceite SYS deliberadamente mais baixa que a
# geral (candidatos que já ficaram de fora antes), calibrada perto da média de
# probabilidade_reativacao_pct do su_banco_talentos.csv (~60%) mas com ruído.
# ---------------------------------------------------------------------------
MESES = sorted(farol["mes"].unique())
MES_LABELS = farol.drop_duplicates("mes").set_index("mes")["mes_label"].to_dict()
rows_su = []
base_rate = {"Data Science": 0.42, "Data Engineering": 0.55, "Data Consultant": 0.33, "Analytics Engineering": 0.38}
for mi, mes in enumerate(MESES):
    for ch in FAROL_CHAPTERS:
        ofertas = int(np.random.randint(1, 5))
        rate = np.clip(base_rate[ch] + np.random.uniform(-0.08, 0.08) + mi * 0.01, 0.15, 0.75)
        aceites = int(round(ofertas * rate))
        rows_su.append({"mes": mes, "mes_label": MES_LABELS[mes], "chapter": ch, "ofertas_sys": ofertas, "aceites_sys": aceites})

su_df = pd.DataFrame(rows_su)
su_df.to_csv("su_ofertas.csv", index=False)
print("su_ofertas.csv OK ->", su_df.shape)
print(su_df.groupby("mes")[["ofertas_sys", "aceites_sys"]].sum())
