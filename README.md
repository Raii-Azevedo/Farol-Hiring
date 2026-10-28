# 🚦 Farol de Hiring

Protótipo de produto do **Farol de Hiring** — a ferramenta que calcula o gap entre a
demanda de projetos (Artefactory) e a oferta ajustada do funil de contratação
(Greenhouse), traduzindo isso num semáforo por **chapter × senioridade**.

Uso interno do time de **RH/People da Artefact**. Não é um ATS nem um cockpit de
Talent Acquisition genérico — é uma leitura calculada de "acelerar, manter ou
pausar" a contratação, complementar ao Greenhouse.

> O app lê **dados oficiais do BigQuery** (views `vw_farol_base` e
> `vw_farol_demanda` em `br-in-dataplatform.greenhouse_dev`) — não há mais
> mock nem fallback para CSV. O que ainda falta de dado está em
> [Pendências](#pendências-antes-de-ir-para-produção).
>
> ⚠️ O controle de acesso (login Google + allowlist) está implementado mas
> precisa ser **configurado antes de publicar**: sem `[auth]` no
> `secrets.toml` o app roda em modo aberto, e aí qualquer pessoa com o link
> vê nome de candidato. Ver [Autenticação e controle de acesso](#autenticação-e-controle-de-acesso).

## Como rodar

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # depois preencha com credenciais reais
streamlit run app.py
```

Abre em `http://localhost:8501`. A pasta `assets/` e a pasta `.streamlit/`
precisam estar na mesma pasta que o `app.py`.

O app lê os dados direto do **BigQuery**, das duas views em
`br-in-dataplatform.greenhouse_dev` (ver `sql/`). Antes de rodar, autentique:

```bash
gcloud auth application-default login
```

Sem credencial válida ou sem acesso de leitura ao dataset, o app mostra o erro
e para — não existe mais fallback para CSV.

Sem `.streamlit/secrets.toml` preenchido, o app roda em **modo aberto** (sem
checagem de login) e mostra um aviso visível na tela — útil para desenvolver
localmente, mas nunca deve ir para produção assim.

## Estrutura do projeto

```
app.py                          → aplicação Streamlit (3 abas: Visão Gerencial, Farol Executivo e Visão do Pipe)
auth.py                         → autenticação (Google OAuth) + autorização (allowlist no BigQuery)
bq.py                           → cliente BigQuery compartilhado por app.py e auth.py
requirements.txt                → dependências Python (streamlit, Authlib, pandas, plotly, Pillow)
.streamlit/config.toml          → tema claro forçado (evita texto ilegível em tabelas no modo escuro)
.streamlit/secrets.toml.example → modelo de configuração do Google OAuth (copiar → secrets.toml)
.gitignore                      → garante que .streamlit/secrets.toml nunca seja commitado
assets/                         → logo da Artefact extraída do Branding Guide oficial (Nov/2024)

sql/                            → o SQL das views que alimentam o app:
  vw_farol_base.sql               grão candidatura — funil, SLA, candidatos parados,
                                  See You Soon, ofertas e a oferta ajustada
  vw_farol_demanda.sql            grão chapter × senioridade × mês — demanda líquida
                                  (forecast do Artefactory até 2027-12)
  passo1_descoberta.sql           queries que levantaram o de-para de etapa e carreira
  README.md                       o que cada view responde e o que ainda é limitação de dado

Os CSVs mock antigos continuam na pasta, mas o app não lê mais nenhum deles.

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
  a tabela **`br-in-dataplatform.greenhouse_dev.greenhouse_dash_access`**
  (`email`, `role`, `created_at`), mantida pelo time de Dados. Ter conta
  Google válida **não** dá acesso automático: o e-mail (normalizado — sem
  espaços, lowercase) precisa estar na tabela. Estar na tabela **é** a
  autorização; não há coluna de ativo/inativo, então revogar acesso é apagar
  a linha.

Se a allowlist não puder ser lida (credencial sem permissão, tabela
renomeada), o app **bloqueia o acesso** em vez de liberar — com uma tela que
explica que a verificação falhou, não que a pessoa foi negada. Isso tem uma
consequência de permissão: a credencial de leitura precisa valer para o
**dataset inteiro**, não só para as duas views do farol, porque a allowlist
mora no mesmo dataset.

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
5. Peça ao time de Dados para inserir os e-mails liberados em
   `greenhouse_dash_access` (revogar = apagar a linha).

Sem `secrets.toml` configurado, o app roda em **modo aberto** com um aviso
visível — pensado para desenvolvimento local, nunca para produção.

A leitura da allowlist é cacheada por 60s (`st.cache_data(ttl=60)`): uma
inclusão feita no BigQuery vale no minuto seguinte, sem redeploy.

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

**Visão do Pipe** — KPIs de topo (conversão total do pipe, taxa de aceite de
oferta geral, taxa de aceite e tempo médio no banco do See You Soon), funil de
volume por etapa, conversão etapa a etapa, taxa de aceite por carreira (geral
e See You Soon), heatmap de candidatos por etapa × chapter, tabela de volume
por etapa e por nível (com filtro de carreira/senioridade e flag de excesso de
volume), a seção "Candidatos parados por etapa" (tabela status × etapa no
mesmo formato do mock: clicar num número abre o detalhamento por vaga e, de
lá, a lista de quem está parado e há quantos dias), resumo de status e tabela
e de gargalos e SLA.

Os detalhamentos abrem sempre pelo clique no próprio visual, como no mock:
nos gráficos de conversão etapa a etapa e de tempo médio por etapa, clicando
numa barra; em "Candidatos parados por etapa", clicando no número da célula.
Abaixo de cada um há uma mini legenda indicando que ali tem detalhamento. Os
modais seguem o tema claro/escuro da página (o chrome nativo do Streamlit é
sempre claro, então o fundo do modal é forçado via CSS a acompanhar o tema
ativo).

As etapas do funil seguem os nomes reais do processo, agora validados contra
o Greenhouse (ver `sql/passo1_descoberta.sql`): Avaliação de currículo → Envio do
Case Escrito → Avaliação case escrito → Entrevista Fit → Entrevista Técnica 1
→ Entrevista Técnica 2 → Conversa Final → Oferta → Contratação, com o **See
You Soon** como backlog paralelo de reativação.

O Greenhouse usa 19 nomes diferentes para essas etapas (variações de caixa e
de acento, três nomes para a conversa final, e o pipeline default em inglês
em algumas vagas). O de-para está em `sql/passo2_seeds.sql` (`d_farol_etapa`), que é
também onde moram a ordem das etapas e as metas de SLA. "Contratação" é etapa
aqui, mas no Greenhouse é *status* da candidatura, não stage.

O funil mock foi realinhado a esses nomes pelo `realinhar_funil_real.py`;
os volumes das etapas que já existiam foram preservados e as duas etapas do
case entraram por interpolação.

## Fórmula do farol

```
Oferta ajustada = (candidatos em etapas finais × conversão residual)
                + (candidatos em etapas iniciais × conversão acumulada)
                + (candidatos no SU × taxa de reativação)

Gap = Demanda líquida − Oferta ajustada

⚪ Sem dado  → sem demanda registrada no período
🟡 Manter    → |Gap| < 1 pessoa (falta ou sobra menos de uma vaga),
               qualquer que seja o percentual
🔴 Pausar    → demanda líquida ≤ 0 (desalocações superam pedidos)
🟢 Acelerar  → Gap > 20% da demanda
🟡 Manter    → Gap entre −10% e +20%
🔴 Pausar    → Gap < −10%

As regras valem nessa ordem. A trava de 1 pessoa existe porque, com
demanda de 0,5 FTE e oferta zero, o gap percentual dá +100% e o farol
mandaria "acelerar" para abrir meia vaga.
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
- **Service account com acesso ao dataset** — enquanto o app depender da
  credencial da máquina (`gcloud auth application-default login`), ele só
  funciona rodando local. Publicado, precisa de `[gcp_service_account]` no
  `secrets.toml`, com `roles/bigquery.dataViewer` no dataset `greenhouse_dev`
  e `roles/bigquery.jobUser` no projeto.
- **Mapeamento job → chapter/senioridade** — deduzido do `job_name` dentro da
  `vw_farol_base` (código entre colchetes + palavra de nível). É heurística,
  não cadastro: job com nome fora do padrão fica sem chapter e sai do farol.
- **Histórico mensal** — as views do Greenhouse são um retrato do presente;
  precisa de um job agendado gravando snapshots ao longo do tempo para o
  seletor de mês funcionar com dado real.
- **Dados de demanda (Artefactory)** — nenhuma das views compartilhadas até
  agora cobre isso; sem demanda não existe gap, e sem gap não existe farol.

Detalhes completos de cada decisão (por que RH-only, por que essas
visualizações, o que ficou para V1/V2/V3, benchmark com Greenhouse/Ashby/
Linear/Workday etc.) estão em `Farol de Hiring - Discovery.docx`.
