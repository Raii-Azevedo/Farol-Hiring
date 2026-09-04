# 🚦 Farol de Hiring

Protótipo de produto do **Farol de Hiring** — a ferramenta que calcula o gap entre a
demanda de projetos (Artefactory) e a oferta ajustada do funil de contratação
(Greenhouse), traduzindo isso num semáforo por **chapter × senioridade**.

Uso interno do time de **RH/People da Artefact**. Não é um ATS nem um cockpit de
Talent Acquisition genérico — é uma leitura calculada de "acelerar, manter ou
pausar" a contratação, complementar ao Greenhouse.

> ⚠️ Este repositório roda hoje sobre **dados mock**. Não está conectado ao
> pipeline real (BigQuery / Greenhouse / Artefactory) — ver [Pendências](#pendências-antes-de-ir-para-produção)
> antes de usar com dado real. O controle de acesso (login Google + allowlist)
> já está implementado — ver [Autenticação e controle de acesso](#autenticação-e-controle-de-acesso) para configurar.

## Como rodar

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # depois preencha com credenciais reais
streamlit run app.py
```

Abre em `http://localhost:8501`. Os arquivos `.csv`, a pasta `assets/` e a pasta
`.streamlit/` precisam estar na mesma pasta que o `app.py` — todos os caminhos
são relativos ao arquivo.

Sem `.streamlit/secrets.toml` preenchido, o app roda em **modo aberto** (sem
checagem de login) e mostra um aviso visível na tela — útil para desenvolver
localmente, mas nunca deve ir para produção assim.

## Estrutura do projeto

```
app.py                          → aplicação Streamlit (3 abas: Visão Gerencial, Farol Executivo e Visão do Pipe)
auth.py                         → autenticação (Google OAuth) + autorização (allowlist)
authorized_users.csv            → allowlist mock: quem pode acessar o dashboard
requirements.txt                → dependências Python (streamlit, Authlib, pandas, plotly, Pillow)
.streamlit/config.toml          → tema claro forçado (evita texto ilegível em tabelas no modo escuro)
.streamlit/secrets.toml.example → modelo de configuração do Google OAuth (copiar → secrets.toml)
.gitignore                      → garante que .streamlit/secrets.toml nunca seja commitado
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

## Autenticação e controle de acesso

O acesso segue: **login com Google → identifica o e-mail → consulta a
allowlist → autoriza ou nega**. Os dois conceitos são resolvidos em lugares
diferentes:

- **Autenticação** ("quem é você?") — resolvida pelo Google, via `st.login()`
  nativo do Streamlit (OIDC/Authlib). O app nunca vê nem guarda senha nenhuma.
- **Autorização** ("você pode acessar?") — resolvida em `auth.py`, consultando
  `authorized_users.csv` (colunas: `email`, `name`, `active`, `role`,
  `created_at`, `updated_at`). Ter conta Google válida **não** dá acesso
  automático — o e-mail (normalizado: sem espaços, lowercase) precisa estar
  na lista com `active = true`.

A checagem acontece no servidor: como o Streamlit reexecuta o script inteiro
a cada sessão, um `st.stop()` dentro de `auth.py` impede que o HTML e os dados
do dashboard cheguem a ser montados/enviados ao navegador quando a autorização
falha — não é uma validação só de frontend.

**Para configurar de verdade** (login real do Google):

1. Crie/abra um projeto em [Google Cloud Console](https://console.cloud.google.com/auth/overview).
2. Configure a tela de consentimento ("Branding") e, enquanto o app estiver em
   modo *Testing*, adicione os e-mails de teste em "Audience".
3. Em "Clients", crie um client tipo *Web application* com redirect URI
   `http://localhost:8501/oauth2callback` (ou o domínio real, em produção).
4. Copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml` e
   preencha `client_id`, `client_secret` e um `cookie_secret` aleatório forte.
5. Adicione/edite linhas em `authorized_users.csv` para liberar ou revogar
   acesso (revogar = `active = false`, sem precisar apagar a linha).

Sem `secrets.toml` configurado, o app roda em **modo aberto** com um aviso
visível — pensado para desenvolvimento local, nunca para produção.

Quando o pipeline real existir, `authorized_users.csv` deve virar uma tabela
BigQuery (`authorized_users`, mesmo schema) mantida pelo Data Eng, e
`auth._load_authorized_users()` passa a consultar essa tabela em vez do CSV —
o resto da lógica de autorização não muda.

Para regenerar os CSVs mock (por exemplo depois de ajustar algum número em
`build_mocks.py`):

```bash
python build_mocks.py
```

## O que o app mostra hoje

**Visão Gerencial** — resumo executivo do mês: necessidade de contratação
líquida, pipe qualificado atual (candidatos da Entrevista Fit até a Oferta),
tempo médio de contratação e taxa de aceite de oferta, cada um com a variação
frente ao mês anterior. Pensada como a primeira leitura antes de entrar no
detalhe por chapter ou por etapa do funil.

**Farol Executivo** — cards com semáforo por chapter (🟢 acelerar / 🟡 manter /
🔴 pausar / ⚪ sem dado), com tooltip explicando o motivo do status ao passar o
mouse, drill-down por senioridade com bullet chart (oferta ajustada vs. demanda
líquida de referência). Cada card também mostra o pipe qualificado daquele
chapter no mês.

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

- **Credenciais reais do Google OAuth** — o código de login/autorização já
  está implementado (ver seção acima); falta só criar o client OAuth real no
  Google Cloud Console da Artefact e preencher `.streamlit/secrets.toml`.
- **Allowlist em BigQuery** — hoje `authorized_users.csv` é mock local;
  precisa virar tabela mantida pelo Data Eng antes de ir para produção com
  dado real de candidatos.
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
