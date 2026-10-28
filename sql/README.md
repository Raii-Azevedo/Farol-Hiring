# As views do Farol

Duas views, construídas das views oficiais do `greenhouse_dev`:

| View | Grão | Responde |
|---|---|---|
| `vw_farol_base` | candidatura | todo o diagnóstico de funil + a oferta ajustada |
| `vw_farol_demanda` | chapter × senioridade × mês | a demanda líquida (forecast até 2027-12) |

São duas, e não uma, por um motivo concreto: **a demanda tem eixo de
tempo e o pipe não tem**. O forecast vai até 2027-12; o Greenhouse é foto
de hoje. Juntar numa view só exigiria repetir 69 mil candidaturas por mês
de forecast, ou congelar o horizonte no SQL e matar o seletor de mês do
app. No Streamlit é um `merge` em `(chapter, senioridade)`.

# vw_farol_base

Uma view, construída **só a partir das 7 views oficiais** do
`greenhouse_dev`. Não depende de tabela nova, seed externo, nem de nada
pedido ao time de Dados.

Arquivo: `vw_farol_base.sql`. É só rodar.

## Grão e por que ele

**Uma linha por candidatura** (`application_id`). É o grão mais fino que
existe nas views oficiais; as outras 6 são agregados por `job_name` e
entram penduradas na candidatura.

Isso resolve o problema que uma view agregada teria: **a média ponderada
sai de graça**. Se uma vaga tem 10 candidatos com tempo de 5d e outra tem
40 com 10d, a média simples das 50 linhas já dá 9d — o peso vem do próprio
grão. Numa view agregada por chapter seria preciso ponderar na mão, e esse
erro não levanta exceção: só devolve número errado.

## Convenção de colunas (ler antes de agregar)

| Sufixo | O que é | Pode somar? |
|---|---|---|
| `flag_*` | 0/1 por candidatura | **Sim.** Soma e média à vontade |
| `*_etapa` | métrica da vaga × etapa, repetida em cada candidatura daquela vaga/etapa | **Não.** Média sim (sai ponderada) |
| `*_vaga` | métrica da vaga, repetida em cada candidatura da vaga | **Não.** Média sim; soma só depois de `drop_duplicates("job_id")` |

É o preço de ter tudo numa view só. Os nomes foram escolhidos para o risco
ficar visível na hora de escrever o groupby.

## Impacto no Streamlit

### O que deixa de ser mock

| Tela / KPI | Status | De onde sai |
|---|---|---|
| Funil de volume por etapa | ✅ real | `SUM(flag_ativo)` por etapa |
| Conversão etapa a etapa | ✅ real¹ | `mean(conversao_etapa_pct)` |
| Tempo médio por etapa | ✅ real | `mean(tempo_medio_etapa)` |
| Gargalos e SLA | ✅ real² | `status_sla_etapa` |
| Heatmap etapa × chapter | ✅ real | contagem |
| Taxa de aceite de oferta (geral e por carreira) | ✅ real | `flag_aceite / flag_oferta` |
| Tempo médio de contratação | ✅ real | `mean(tempo_contratacao_vaga)` |
| Conversão total do pipe | ✅ real | `flag_contratado / total` |
| Pipe qualificado | ✅ real | `SUM(flag_qualificado)` |
| See You Soon (pessoas, tempo no banco, conversão) | ✅ real³ | `su_*_vaga` + `flag_see_you_soon` |
| Volume por etapa e por nível | ⚠️ real com ressalva | senioridade vem de parse (ver limitações) |
| Candidatos parados por etapa | ⚠️ real com proxy | `status_parado` (ver limitações) |

¹ pendente confirmar o separador do `job_stage_conversion_names` (QA 3).
² a meta de SLA é regra de negócio, não dado — está inline na view.
³ os nomes das pessoas no banco são reais (candidaturas em `See you soon`);
o tempo por pessoa não existe, só a média por vaga.

### O que continua mock, e por quê

| Tela | Falta | É limitação de |
|---|---|---|
| Farol de **AI Engineering** e **Software Engineering** | demanda | dado: zero linha nas duas views do Artefactory para esses chapters |
| Farol de nível **Manager+ / Director / Partner** | — | escopo: 45 FTE de demanda que não se contrata por este funil |
| Propostas recusadas (motivo + tempo até recusa) | motivo da recusa | dado: não existe em nenhuma view |
| Qualquer variação "vs. mês anterior", sparkline, seletor de mês | data | dado: **nenhuma view oficial tem data**. Tudo é foto de hoje |
| `log_alertas` (mudança de estado do farol) | farol + histórico | consequência dos dois acima |
| Tempo de banco por pessoa no See You Soon | dado por candidato | dado: só existe a média por vaga |

### O farol fecha — para 4 dos 6 chapters

Com a `f_resource_request_manual` e a `f_staffing_rate_manual`, o cálculo
central do projeto passa a ser computável:

```
demanda_liquida  = staffing_monthly_total - staff_deallocated   (FTE, por mês)
oferta_ajustada  = SUM(contrib_oferta_ajustada)                 (pipe x conversão)
                   filtrado por dias_ate_contratacao <= horizonte
gap              = demanda_liquida - oferta_ajustada
```

```python
demanda = pd.read_gbq("SELECT * FROM `...greenhouse_dev.vw_farol_demanda`", project_id="...")

HORIZONTE = 45   # dias — o "~1,5 mês" do discovery
oferta = (base[base.dias_ate_contratacao.le(HORIZONTE)]
          .groupby(["chapter", "senioridade"], as_index=False)
          .agg(oferta_ajustada=("contrib_oferta_ajustada", "sum")))

farol = (demanda[demanda.mes.eq(mes_sel)]
         .merge(oferta, on=["chapter", "senioridade"], how="left")
         .fillna({"oferta_ajustada": 0}))
farol["gap"] = farol.demanda_liquida_fte - farol.oferta_ajustada
```

**Demanda líquida real, por chapter (FTE):**

| chapter | 2026-10 | 2026-11 | 2026-12 | 2027-01 |
|---|---|---|---|---|
| Data Engineering | −5,3 | **15,4** | 16,7 | 17,6 |
| Data Science | −1,8 | **12,9** | 7,2 | 8,0 |
| Data Consultant | −6,8 | **6,2** | 8,6 | 12,8 |
| Analytics Engineering | −1,6 | **0,5** | 0,1 | −0,5 |

Outubro é negativo em todo chapter porque o mês já está no fim e as
desalocações superam o que resta de pedido — o sinal útil começa em
novembro. Analytics Engineering com demanda ~zero por quatro meses é
sinal real de "pausar", não falta de dado.

### Resumo honesto

**A aba Visão do Pipe vira real inteira.** O **Farol Executivo passa a ser
real para Data Engineering, Data Science, Data Consultant e Analytics
Engineering** — 4 dos 6 chapters. AI Engineering e Software Engineering
têm pipe mas nenhuma demanda cadastrada, então para esses dois só existe
o diagnóstico de funil. A Visão Gerencial fica real nos 4 KPIs.

Dos 8 CSVs mock: 6 substituídos, 1 parcial, 1 continua mock
(`propostas_recusadas`, por falta do motivo da recusa).

## Como consumir no app

```python
base = pd.read_gbq(
    "SELECT * FROM `br-in-dataplatform.greenhouse_dev.vw_farol_base`",
    project_id="br-in-dataplatform",
)

# funil_pipe.csv  (chapter x etapa)
funil = (
    base[base.tipo_etapa.eq("funil") & base.chapter.notna()]
    .groupby(["chapter", "etapa", "ordem_etapa"], as_index=False)
    .agg(candidatos=("flag_ativo", "sum"),
         conversao_pct=("conversao_etapa_pct", "mean"),   # média já sai ponderada
         tempo_medio_dias=("tempo_medio_etapa", "mean"),
         meta_sla_dias=("meta_sla_etapa", "max"))
)

# funil_pipe_nivel.csv
nivel = (
    base[base.tipo_etapa.eq("funil")]
    .groupby(["chapter", "senioridade", "etapa", "ordem_etapa"], as_index=False)
    .agg(candidatos=("flag_ativo", "sum"))
)

# candidatos_parados.csv
parados = base[base.flag_ativo.eq(1) & base.status_parado.isin(["atencao", "critico"])]

# taxa de aceite por chapter
aceite = base.groupby("chapter", as_index=False).agg(
    ofertas=("flag_oferta", "sum"), aceites=("flag_aceite", "sum"))

# See You Soon — a armadilha: su_*_vaga é REPETIDO por candidatura.
# Dedupe por vaga ANTES de somar.
su = (base.drop_duplicates("job_id")
          [["job_id", "chapter", "su_candidaturas_vaga",
            "su_ofertas_vaga", "su_aceites_vaga", "su_dias_no_banco_vaga"]])
pessoas_no_banco = su.su_candidaturas_vaga.sum()
```

## Limitações, explícitas

**Sem data em nenhuma view oficial.** A view é uma foto de hoje. Para ter
série mensal, materializar numa tabela particionada, uma vez por dia:

```sql
CREATE TABLE IF NOT EXISTS `br-in-dataplatform.greenhouse_dev.f_farol_base_snapshot`
PARTITION BY snapshot_date AS
SELECT * FROM `br-in-dataplatform.greenhouse_dev.vw_farol_base` WHERE FALSE;

INSERT INTO `br-in-dataplatform.greenhouse_dev.f_farol_base_snapshot`
SELECT * FROM `br-in-dataplatform.greenhouse_dev.vw_farol_base`
WHERE NOT EXISTS (SELECT 1 FROM `br-in-dataplatform.greenhouse_dev.f_farol_base_snapshot`
                  WHERE snapshot_date = CURRENT_DATE());
```

As views de conversão e tempo já chegam agregadas, então **histórico não é
reconstruível depois**: cada dia sem isso rodando é um dia que o farol
nunca vai poder comparar.

**"Candidato parado" é proxy.** O certo seria dias na etapa atual; as
views oficiais só têm `total_days_in_pipe` (pipe inteiro). A view compara
o total de dias com o esperado até a etapa onde o candidato está. Pega
atraso acumulado, não atraso da etapa — quem voou no começo e empacou
agora pode não aparecer.

**Senioridade vem de parse do `job_name`.** O padrão real é o código entre
colchetes (`[DS BR] - Intern Data Scientist Brazil`), e os níveis
observados são só três: **Estagiário, Pleno (sem marca) e Senior** — não
os quatro que o protótipo usa. O `SENIORIDADE_ORDER` do `app.py` precisa
virar esses três.

**Chapter idem.** Os 6 chapters do farol saem dos códigos `AE`, `DS`,
`DE`, `DC`, `SE`, `AI`. Vaga sem esses códigos (`[MD BR]`,
`Strategy Consulting Manager`, `Teste`) fica com `chapter` nulo e sai das
telas por carreira — o QA 1 mostra quanto volume é.

**Meta de SLA é decisão, não dado.** Está inline na view, como ponto único
de ajuste, mas quem define é STF/RH.

**0,18% do volume fica fora do funil**: as candidaturas no pipeline default
do Greenhouse (`Interview #1..#5`) e as 52 com etapa vazia. Ficam
`tipo_etapa = 'fora'` / `'sem mapeamento'` até o RH confirmar o
mapeamento. O QA 2 monitora.

## Decisões de negócio embutidas no de-para da demanda

O Artefactory e o Greenhouse falam vocabulários diferentes, e eu tive que
inferir. Os três pontos abaixo mudam números do farol e precisam de
ratificação — estão marcados `CONFIRMAR` no SQL:

1. **`Consulting` (Artefactory) = chapter `Data Consultant` (Greenhouse)?**
   É a maior incerteza. Se não for, o chapter Data Consultant fica sem
   demanda e o farol dele cai junto.
2. **`Entry 1/2/3` e `Associate 2/3` = o "Pleno" do Greenhouse?** O
   Artefactory tem 16 níveis e o Greenhouse só permite deduzir 3 do
   `job_name`. Toda a quebra por senioridade depende disso.
3. **FTE = pessoa?** A demanda vem em FTE fracionário (0,45; 12,68) e o
   pipe vem em gente. Somar os dois assume 1 FTE = 1 contratação.

Enquanto o 1 e o 2 não forem ratificados, **o farol por chapter já é
confiável** (o de-para de carreira é quase 1-para-1); a quebra por
senioridade é que fica provisória.

## Ainda pendente de confirmação

Duas queries do `passo1_descoberta.sql` não voltaram, e as duas afetam
números desta view:

- **#2 — formato do `job_stage_conversion_names`.** Se o separador não for
  `->`, a conversão desalinha uma etapa **em silêncio**. O QA 3 detecta.
- **#3 — domínios de `application_status` e `offer_status`.** Definem os
  `flag_*`. Hoje estão com `'hired'` / `'%accept%'` como palpite; se
  estiverem errados, os flags voltam zero e o funil fica sem a linha de
  Contratação.
