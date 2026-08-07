# 🚦 Farol de Hiring

Protótipo de produto do **Farol de Hiring** — a ferramenta que calcula o gap entre a
demanda de projetos (Artefactory) e a oferta ajustada do funil de contratação
(Greenhouse), traduzindo isso num semáforo por **chapter × senioridade**.

Uso interno do time de **RH/People da Artefact**. Não é um ATS nem um cockpit de
Talent Acquisition genérico — é uma leitura calculada de "acelerar, manter ou
pausar" a contratação, complementar ao Greenhouse.

> ⚠️ Este repositório roda hoje sobre **dados mock**. Não está conectado ao
> pipeline real (BigQuery / Greenhouse / Artefactory) nem tem controle de
> acesso implementado — ver [Pendências](#pendências-antes-de-ir-para-produção)
> antes de usar com dado real.

## Como rodar

```bash
pip install -r requirements.txt
streamlit run app.py
```

Abre em `http://localhost:8501`. Os arquivos `.csv`, a pasta `assets/` e a pasta
`.streamlit/` precisam estar na mesma pasta que o `app.py` — todos os caminhos
são relativos ao arquivo.

## Estrutura do projeto

```
app.py                          → aplicação Streamlit (2 abas: Farol Executivo e Visão do Pipe)
requirements.txt                → dependências Python (streamlit, pandas, plotly, Pillow)
.streamlit/config.toml          → tema claro forçado (evita texto ilegível em tabelas no modo escuro)
assets/                         → logo da Artefact extraída do Branding Guide oficial (Nov/2024)

farol_executivo.csv             → grão: mês × chapter × senioridade — demanda, oferta, gap, farol
funil_pipe.csv                  → grão: mês × chapter × etapa — volume, conversão, SLA
su_banco_talentos.csv           → grão: candidato — banco de "See You Soon" e score de reativação
log_alertas.csv                 → grão: evento — histórico de mudanças de farol (auditoria do Google Chat)
propostas_recusadas.csv         → grão: proposta recusada — motivo e tempo até a recusa

build_mocks.py                  → script que gera os 5 CSVs acima (dados fictícios, mas com a
                                   mesma estrutura planejada para os dados reais)

CONTEXTO.txt                    → plano-base original do projeto (fórmula do gap, fontes, riscos)
"Farol de Hiring - Discovery.docx" → documento de discovery (arquitetura, KPIs, visualizações,
                                   UX, inteligência, roadmap MVP→V3, benchmark)
farol-contratacao.html          → mock visual de referência (base do design do app.py)
farol-hiring-mock.html          → mock visual alternativo (tema escuro, inspirou o drill-down por card)
```

Para regenerar os CSVs mock (por exemplo depois de ajustar algum número em
`build_mocks.py`):

```bash
python build_mocks.py
```

## O que o app mostra hoje

**Farol Executivo** — cards com semáforo por chapter (🟢 acelerar / 🟡 manter /
🔴 pausar / ⚪ sem dado), com tooltip explicando o motivo do status ao passar o
mouse, drill-down por senioridade com bullet chart (oferta ajustada vs. demanda
líquida de referência).

**Visão do Pipe** — funil de volume por etapa, conversão etapa a etapa, heatmap
de candidatos por etapa × chapter, tabela de gargalos e SLA, e uma seção de
propostas recusadas (motivo + tempo até a recusa).

As etapas do funil seguem os nomes reais do processo (conforme o deck *Projeto
Farol de Contratação*, jun/2026): Envio de Currículo → Entrevista Fit →
Técnica 1 → Técnica 2 → Conversa com André → Oferta → Contratação, com o
**See You Soon** como backlog paralelo de reativação.

## Fórmula do farol

```
Oferta ajustada = (candidatos em etapas finais × conversão residual)
                + (candidatos em etapas iniciais × conversão acumulada)
                + (candidatos no SU × taxa de reativação)

Gap = Demanda líquida − Oferta ajustada

🟢 Acelerar  → Gap > 20% da demanda
🟡 Manter    → Gap entre −10% e +20%
🔴 Pausar    → Gap < −10%
⚪ Sem dado  → sem demanda registrada no período
```

## Arquitetura planejada (real, não implementada aqui)

```
Greenhouse API + Artefactory (via IDP)
        ↓
   Bronze → Prata (BigQuery, script Python ou dbt)
        ↓
   Calcula Gap() por chapter × senioridade
        ↓
   Exposição do visual (este app / Looker Studio)  +  Alerta no Google Chat
```

Views do Greenhouse já mapeadas e disponíveis em
`br-in-dataplatform.greenhouse_dev`: `greenhouse_v_applications`,
`greenhouse_v_hire_average_time`, `greenhouse_v_stage_average_time`,
`greenhouse_v_stage_conversion_by_job`. Ainda faltam: mapeamento `job_name →
chapter + senioridade`, histórico mensal (as views hoje são um snapshot do
presente, não histórico), e os dados de demanda do lado Artefactory.

## Pendências antes de ir para produção

- **Controle de acesso** — login via Google SSO (reaproveitando a identidade
  corporativa) + tabela de e-mails pré-aprovados no BigQuery, controlada pelo
  Data Eng. Isso é bloqueador, não item de roadmap: o app não deve rodar com
  dado real de candidatos sem essa camada.
- **Mapeamento job → chapter/senioridade** — nenhuma view do Greenhouse tem
  essa informação hoje.
- **Histórico mensal** — as views do Greenhouse são um retrato do presente;
  precisa de um job agendado gravando snapshots ao longo do tempo para o
  seletor de mês funcionar com dado real.
- **Dados de demanda (Artefactory)** — nenhuma das views compartilhadas até
  agora cobre isso; sem demanda não existe gap, e sem gap não existe farol.

Detalhes completos de cada decisão (por que RH-only, por que essas
visualizações, o que ficou para V1/V2/V3, benchmark com Greenhouse/Ashby/
Linear/Workday etc.) estão em `Farol de Hiring - Discovery.docx`.
