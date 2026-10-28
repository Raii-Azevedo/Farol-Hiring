-- =====================================================================
-- vw_farol_base — a view única que alimenta o Farol
-- =====================================================================
-- Consolida as 7 views oficiais do greenhouse_dev numa estrutura só,
-- pronta para o Streamlit ler com um pd.read_gbq e agregar em pandas.
--
-- GRÃO: uma linha por CANDIDATURA (application_id).
--
-- Por que esse grão: é o mais fino que existe nas views oficiais, e todas
-- as outras 6 são agregados por job_name. Pendurando os agregados na
-- candidatura, duas coisas boas acontecem:
--
--   1. Tudo cabe numa tabela só, sem formato chave-valor e sem aninhar.
--   2. A média ponderada sai de graça. Se uma vaga tem 10 candidatos com
--      tempo de 5d e outra tem 40 com 10d, a média simples das 50 LINHAS
--      já dá 9d — o peso vem do próprio grão. Com uma view agregada por
--      chapter seria preciso ponderar na mão, e esse erro não levanta
--      exceção, só devolve número errado.
--
-- CONVENÇÃO DE COLUNAS — importante para não somar errado:
--
--   flag_*        0/1 por candidatura. Pode SOMAR e tirar média à vontade.
--   *_etapa       métrica da vaga × etapa, REPETIDA em cada candidatura
--                 daquela vaga/etapa. Pode tirar MÉDIA (sai ponderada).
--                 NUNCA somar.
--   *_vaga        métrica da vaga, REPETIDA em cada candidatura da vaga.
--                 Média OK. Soma só depois de um ANY_VALUE por vaga.
--
-- Nada aqui depende de tabela nova, seed externo ou pedido ao time de
-- Dados: só das 7 views oficiais. O de-para de etapa e de carreira está
-- inline como CTE justamente para a view ser autocontida.
--
-- Descobertas #2 (separador) e #3 (domínios de status) já confirmadas
-- contra o dado em out/2026; o que ainda falta está marcado CONFIRMAR.
-- =====================================================================

CREATE OR REPLACE VIEW `br-in-dataplatform.greenhouse_dev.vw_farol_base` AS

WITH
-- ---------------------------------------------------------------------
-- De-para de etapa: o Greenhouse usa 19 nomes para ~9 etapas reais
-- (variação de caixa, de acento, três nomes para a conversa final, e o
-- pipeline default em inglês em vagas nunca configuradas). Sem isso, um
-- join por string derruba volume em silêncio.
-- As metas de SLA são regra de negócio (STF/RH), não dado — estão aqui
-- como ponto único de ajuste.
-- ---------------------------------------------------------------------
etapa_depara AS (
  SELECT * FROM UNNEST([
    STRUCT('Avaliação de currículo'  AS stage_name, 'Avaliação de currículo'  AS etapa, 1 AS ordem_etapa, 'funil'     AS tipo_etapa, 2 AS meta_sla_dias),
    STRUCT('Curriculo selecionado',                 'Avaliação de currículo',       1,  'funil',     2),
    STRUCT('Application Review',                    'Avaliação de currículo',       1,  'funil',     2),
    STRUCT('Envio do Case Escrito',                 'Envio do Case Escrito',        2,  'funil',     3),
    STRUCT('Avaliação case escrito',                'Avaliação case escrito',       3,  'funil',     3),
    STRUCT('Entrevista Fit',                        'Entrevista Fit',               4,  'funil',     3),
    STRUCT('Entrevista Técnica 1',                  'Entrevista Técnica 1',         5,  'funil',     5),
    STRUCT('Entrevista Técnica 2',                  'Entrevista Técnica 2',         6,  'funil',     5),
    -- mesma etapa, três nomes. Canonizada sem nome de pessoa: se o André
    -- ou a Marina saírem do processo, o dashboard não quebra.
    STRUCT('Conversa com André',                    'Conversa Final',               7,  'funil',     4),
    STRUCT('Conversa Final',                        'Conversa Final',               7,  'funil',     4),
    STRUCT('Conversa com a Marina',                 'Conversa Final',               7,  'funil',     4),
    STRUCT('Offer',                                 'Oferta',                       8,  'funil',     3),
    -- backlog paralelo, não é etapa do funil
    STRUCT('See you soon',                          'See You Soon',              NULL,  'paralelo', NULL),
    STRUCT('See you Soon',                          'See You Soon',              NULL,  'paralelo', NULL),
    -- pipeline default do Greenhouse, em vagas nunca configuradas com o
    -- processo da Artefact: 70 candidaturas (0,10%). Ficam fora do funil
    -- até o RH dizer se 'Interview #3' é Técnica 2 ou Conversa Final.
    STRUCT('Interview #1', NULL, NULL, 'fora', NULL),
    STRUCT('Interview #2', NULL, NULL, 'fora', NULL),
    STRUCT('Interview #3', NULL, NULL, 'fora', NULL),
    STRUCT('Interview #4', NULL, NULL, 'fora', NULL),
    STRUCT('Interview #5', NULL, NULL, 'fora', NULL)
  ])
),

-- ---------------------------------------------------------------------
-- Carreira e nível saem do job_name, que é o único lugar onde existem nas
-- views oficiais. O padrão real é o código entre colchetes — muito mais
-- confiável que procurar palavra solta no texto:
--     [DS BR] - Data Scientist Brazil            -> Data Science, Pleno
--     [DS BR] - Intern Data Scientist Brazil     -> Data Science, Estagiário
--     [DS BR] - Senior Data Scientist Brazil     -> Data Science, Senior
-- Os níveis observados são só três: Intern, sem marca, e Senior.
-- Vaga sem código de chapter do farol (ex.: Strategy Consulting Manager,
-- [MD BR], 'Teste') fica com chapter NULL e sai das telas por chapter.
-- ---------------------------------------------------------------------
chapter_depara AS (
  SELECT * FROM UNNEST([
    STRUCT('AE' AS codigo, 'Analytics Engineering' AS chapter),
    STRUCT('DS', 'Data Science'),
    STRUCT('DE', 'Data Engineering'),
    STRUCT('DC', 'Data Consultant'),
    STRUCT('SE', 'Software Engineering'),
    STRUCT('AI', 'AI Engineering')
  ])
),

-- TRIM em tudo: dois job_name vêm com espaço à esquerda, e um deles tem
-- 452 candidaturas de um chapter do farol. job_name é a chave de todo
-- join (as views de etapa e SU não têm job_id), então sem TRIM essas
-- vagas somem sem erro nenhum.
vaga AS (
  SELECT
    a.job_id,
    TRIM(a.job_name) AS job_name,
    cd.chapter,
    CASE
      WHEN cd.chapter IS NULL THEN NULL
      WHEN REGEXP_CONTAINS(a.job_name, r'(?i)\b(intern|estagi[áa]ri[oa])\b')  THEN 'Estagiário'
      WHEN REGEXP_CONTAINS(a.job_name, r'(?i)(\bsenior\b|\bs[êe]nior\b|\bsr\b)') THEN 'Senior'
      ELSE 'Pleno'
    END AS senioridade
  FROM (SELECT DISTINCT job_id, job_name FROM `br-in-dataplatform.greenhouse_dev.greenhouse_v_applications`) a
  LEFT JOIN chapter_depara cd
    ON cd.codigo = SPLIT(REGEXP_EXTRACT(TRIM(a.job_name), r'^\[([^\]]+)\]'), ' ')[SAFE_OFFSET(0)]
),

-- ---------------------------------------------------------------------
-- Agregados por vaga × etapa (greenhouse_v_stage_average_time e
-- greenhouse_v_stage_conversion_by_job). AVG porque vários stage_name
-- caem na mesma etapa canônica.
-- ---------------------------------------------------------------------
tempo_etapa AS (
  SELECT TRIM(t.job_name) AS job_name, e.etapa,
         AVG(t.average_days_in_stage) AS tempo_medio_dias
  FROM `br-in-dataplatform.greenhouse_dev.greenhouse_v_stage_average_time` t
  JOIN etapa_depara e ON e.stage_name = t.job_stage_name AND e.tipo_etapa = 'funil'
  GROUP BY 1, 2
),
conversao_etapa AS (
  -- Conversão é ARESTA (etapa anterior -> destino), tempo é NÓ. A
  -- convenção é pendurar a conversão na etapa DESTINO ("% que chegou da
  -- etapa anterior"), por isso o lado direito do split.
  -- O separador real é '-->' (descoberta #2, out/2026). Se mudar, isso
  -- desalinha uma etapa EM SILÊNCIO. Rodar o QA 3 no fim do arquivo.
  -- conversion_rate vem como fração (média ~0,86), mas há valores > 1
  -- (máx. 15) — CONFIRMAR com o time de Dados o que significam.
  SELECT TRIM(c.job_name) AS job_name, e.etapa,
         AVG(c.conversion_rate) * 100 AS conversao_pct
  FROM `br-in-dataplatform.greenhouse_dev.greenhouse_v_stage_conversion_by_job` c
  JOIN etapa_depara e
    ON e.stage_name = TRIM(SPLIT(c.job_stage_conversion_names, '-->')[SAFE_OFFSET(1)])
   AND e.tipo_etapa = 'funil'
  GROUP BY 1, 2
),
-- Quantos dias era "esperado" que o candidato já tivesse gasto para estar
-- na etapa em que está: soma acumulada do tempo médio das etapas
-- anteriores daquela vaga. Base do proxy de "candidato parado".
esperado AS (
  SELECT job_name, etapa,
         SUM(tempo_medio_dias) OVER (
           PARTITION BY job_name ORDER BY ordem
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
         ) AS dias_esperados_ate_etapa
  FROM (
    SELECT te.job_name, te.etapa, MAX(e.ordem_etapa) AS ordem, MAX(te.tempo_medio_dias) AS tempo_medio_dias
    FROM tempo_etapa te
    JOIN etapa_depara e ON e.etapa = te.etapa
    GROUP BY 1, 2
  )
),

-- ---------------------------------------------------------------------
-- O "ajustado por conversão e tempo" — o cálculo que o farol sempre quis.
--
-- prob_contratacao: chance de um candidato NESTA etapa chegar à
--   contratação = produto das conversões de todas as etapas SEGUINTES
--   daquela vaga. (BigQuery não tem PRODUCT; sai por EXP(SUM(LN)).)
-- dias_ate_contratacao: soma do tempo médio desta etapa até o fim.
--
-- Duas premissas, explícitas:
--   - etapa sem conversão no dado = assume nenhuma perda (otimista);
--   - conta o tempo CHEIO da etapa atual, como se o candidato tivesse
--     acabado de entrar nela (conservador no prazo).
-- ---------------------------------------------------------------------
projecao AS (
  SELECT
    job_name, etapa,
    COALESCE(EXP(SUM(LN(GREATEST(COALESCE(taxa, 1.0), 0.001))) OVER (
      PARTITION BY job_name ORDER BY ordem_etapa DESC
      ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)), 1.0) AS prob_contratacao,
    SUM(tempo) OVER (
      PARTITION BY job_name ORDER BY ordem_etapa DESC
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)        AS dias_ate_contratacao
  FROM (
    SELECT te.job_name, te.etapa,
           MAX(e.ordem_etapa)        AS ordem_etapa,
           MAX(te.tempo_medio_dias)  AS tempo,
           MAX(ce.conversao_pct)/100 AS taxa
    FROM tempo_etapa te
    JOIN etapa_depara e ON e.etapa = te.etapa
    LEFT JOIN conversao_etapa ce ON ce.job_name = te.job_name AND ce.etapa = te.etapa
    GROUP BY 1, 2
  )
),

-- ---------------------------------------------------------------------
-- Agregados por vaga (greenhouse_v_hire_average_time e as duas de SU)
-- ---------------------------------------------------------------------
tempo_contratacao AS (
  SELECT TRIM(job_name) AS job_name, AVG(total_days_in_pipe) AS dias
  FROM `br-in-dataplatform.greenhouse_dev.greenhouse_v_hire_average_time`
  GROUP BY 1
),
su_vaga AS (
  SELECT
    TRIM(c.job_name) AS job_name,
    SUM(c.number_of_applications) AS candidaturas,
    -- offer_status real: 'N/A' (texto) para quem não recebeu oferta
    SUM(IF(LOWER(CAST(c.offer_status AS STRING)) LIKE '%accept%'
        OR LOWER(CAST(c.offer_status AS STRING)) LIKE '%aceit%',
        c.number_of_applications, 0)) AS aceites,
    SUM(IF(COALESCE(UPPER(CAST(c.offer_status AS STRING)), 'N/A') = 'N/A',
        0, c.number_of_applications)) AS ofertas,
    MAX(t.days_in_see_you_soon) AS dias_no_banco
  FROM `br-in-dataplatform.greenhouse_dev.greenhouse_v_see_you_soon_conversion` c
  LEFT JOIN `br-in-dataplatform.greenhouse_dev.greenhouse_v_see_you_soon_average_time_by_job` t
    ON TRIM(t.job_name) = TRIM(c.job_name)
  GROUP BY 1
)

-- =====================================================================
SELECT
  -- ---- quando ----------------------------------------------------
  -- Nenhuma view oficial tem data: isto é uma FOTO DE HOJE. Para ter
  -- série mensal, materializar esta view numa tabela particionada por
  -- snapshot_date, uma vez por dia (ver README).
  CURRENT_DATE()                              AS snapshot_date,

  -- ---- chaves ----------------------------------------------------
  a.application_id,
  a.candidate_id,
  a.candidate_name                            AS candidato,
  v.job_id,
  v.job_name                                  AS vaga,

  -- ---- dimensão --------------------------------------------------
  v.chapter,
  v.senioridade,
  a.stage_name                                AS etapa_origem,
  -- contratado não é etapa no Greenhouse, é status — mas o funil precisa
  -- da última linha, então entra aqui. O stage_name do contratado vem
  -- vazio, então o tipo_etapa também tem que ser forçado: sem isso ele
  -- cai em 'sem mapeamento' e o app, que só lê 'funil', zera Contratação.
  CASE WHEN LOWER(a.application_status) = 'hired' THEN 'Contratação'
       ELSE e.etapa END                       AS etapa,
  CASE WHEN LOWER(a.application_status) = 'hired' THEN 9
       ELSE e.ordem_etapa END                 AS ordem_etapa,
  CASE WHEN LOWER(a.application_status) = 'hired' THEN 'funil'
       ELSE COALESCE(e.tipo_etapa, 'sem mapeamento') END AS tipo_etapa,
  a.application_status,
  a.offer_status,

  -- ---- flags: 0/1 por candidatura. PODE SOMAR. -------------------
  -- Domínios reais (descoberta #3, out/2026):
  --   application_status: in_process | rejected | hired
  --   offer_status:       N/A | Accepted | Rejected | Created | Deprecated
  -- 'N/A' é texto, não NULL: tratar como "sem oferta", senão toda
  -- candidatura conta como oferta.
  IF(LOWER(a.application_status) = 'in_process', 1, 0)                    AS flag_ativo,
  IF(LOWER(a.application_status) = 'hired', 1, 0)                          AS flag_contratado,
  IF(COALESCE(UPPER(CAST(a.offer_status AS STRING)), 'N/A') != 'N/A', 1, 0) AS flag_oferta,
  IF(LOWER(CAST(a.offer_status AS STRING)) LIKE '%accept%'
     OR LOWER(CAST(a.offer_status AS STRING)) LIKE '%aceit%', 1, 0)        AS flag_aceite,
  -- "pipe qualificado": já passou da triagem e do case
  IF(e.ordem_etapa BETWEEN 4 AND 8, 1, 0)                                  AS flag_qualificado,
  IF(e.tipo_etapa = 'paralelo', 1, 0)                                      AS flag_see_you_soon,

  -- ---- métrica da candidatura ------------------------------------
  a.total_days_in_pipe,

  -- ---- métricas da vaga × etapa. MÉDIA sim, SOMA não. ------------
  ROUND(te.tempo_medio_dias, 1)               AS tempo_medio_etapa,
  ROUND(ce.conversao_pct, 1)                  AS conversao_etapa_pct,
  e.meta_sla_dias                             AS meta_sla_etapa,
  ROUND(te.tempo_medio_dias - e.meta_sla_dias, 1) AS excesso_sla_etapa,
  CASE
    WHEN te.tempo_medio_dias IS NULL OR e.meta_sla_dias IS NULL THEN NULL
    WHEN te.tempo_medio_dias > e.meta_sla_dias + 5 THEN 'critico'
    WHEN te.tempo_medio_dias > e.meta_sla_dias     THEN 'atencao'
    ELSE 'ok'
  END                                         AS status_sla_etapa,

  -- ---- "candidato parado": PROXY, não a medida certa -------------
  -- O certo seria dias na etapa ATUAL; as views oficiais só têm
  -- total_days_in_pipe (pipe inteiro). Isto compara o total de dias do
  -- candidato com o esperado até a etapa onde ele está. Pega atraso
  -- ACUMULADO, não atraso da etapa: quem voou no começo e empacou agora
  -- pode não aparecer.
  ROUND(es.dias_esperados_ate_etapa, 1)       AS dias_esperados_ate_etapa,
  ROUND(a.total_days_in_pipe - es.dias_esperados_ate_etapa, 1) AS dias_acima_do_esperado,
  CASE
    WHEN es.dias_esperados_ate_etapa IS NULL THEN NULL
    WHEN a.total_days_in_pipe > es.dias_esperados_ate_etapa + 5 THEN 'critico'
    WHEN a.total_days_in_pipe > es.dias_esperados_ate_etapa     THEN 'atencao'
    ELSE 'ok'
  END                                         AS status_parado,

  -- ---- oferta ajustada: estas PODEM somar (são por candidatura) ---
  ROUND(pr.prob_contratacao, 3)               AS prob_contratacao,
  ROUND(pr.dias_ate_contratacao, 1)           AS dias_ate_contratacao,
  -- contribuição deste candidato para a "oferta ajustada" do chapter.
  -- SOMAR isto por chapter/senioridade = oferta ajustada por conversão.
  -- Para ajustar também por TEMPO, filtrar antes por dias_ate_contratacao
  -- <= horizonte do farol (~45 dias).
  ROUND(IF(LOWER(a.application_status) = 'in_process',
           pr.prob_contratacao, 0), 3)        AS contrib_oferta_ajustada,

  -- ---- métricas da vaga. MÉDIA sim; SOMA só após ANY_VALUE. ------
  ROUND(tc.dias, 1)                           AS tempo_contratacao_vaga,
  su.dias_no_banco                            AS su_dias_no_banco_vaga,
  su.candidaturas                             AS su_candidaturas_vaga,
  su.ofertas                                  AS su_ofertas_vaga,
  su.aceites                                  AS su_aceites_vaga

FROM `br-in-dataplatform.greenhouse_dev.greenhouse_v_applications` a
LEFT JOIN vaga              v  ON v.job_id    = a.job_id
LEFT JOIN etapa_depara      e  ON e.stage_name = a.stage_name
LEFT JOIN tempo_etapa       te ON te.job_name = v.job_name AND te.etapa = e.etapa
LEFT JOIN conversao_etapa   ce ON ce.job_name = v.job_name AND ce.etapa = e.etapa
LEFT JOIN esperado          es ON es.job_name = v.job_name AND es.etapa = e.etapa
LEFT JOIN projecao          pr ON pr.job_name = v.job_name AND pr.etapa = e.etapa
LEFT JOIN tempo_contratacao tc ON tc.job_name = v.job_name
LEFT JOIN su_vaga           su ON su.job_name = v.job_name;


-- =====================================================================
-- QA — rodar depois de criar
-- =====================================================================

-- 1) Cobertura de chapter/senioridade. O que ficar com chapter NULL sai
--    das telas por carreira. Esperado: as vagas fora dos 6 chapters.
SELECT chapter, senioridade, COUNT(*) AS candidaturas
FROM `br-in-dataplatform.greenhouse_dev.vw_farol_base`
GROUP BY 1, 2 ORDER BY 1, 2;

-- 2) Etapa que não casou com o de-para. Esperado: zero (fora os vazios).
SELECT etapa_origem, tipo_etapa, COUNT(*) AS candidaturas
FROM `br-in-dataplatform.greenhouse_dev.vw_farol_base`
WHERE tipo_etapa = 'sem mapeamento'
GROUP BY 1, 2 ORDER BY candidaturas DESC;

-- 3) O MAIS IMPORTANTE: destino da conversão que não casou. Esperado:
--    só os 'Interview #n' do pipeline default. Se vier outra coisa, o
--    separador do job_stage_conversion_names não é mais '-->' e o
--    gráfico de conversão fica errado sem dar erro.
SELECT DISTINCT
  c.job_stage_conversion_names,
  TRIM(SPLIT(c.job_stage_conversion_names, '-->')[SAFE_OFFSET(1)]) AS destino_extraido
FROM `br-in-dataplatform.greenhouse_dev.greenhouse_v_stage_conversion_by_job` c
WHERE TRIM(SPLIT(c.job_stage_conversion_names, '-->')[SAFE_OFFSET(1)]) NOT IN (
  'Avaliação de currículo','Curriculo selecionado','Application Review',
  'Envio do Case Escrito','Avaliação case escrito','Entrevista Fit',
  'Entrevista Técnica 1','Entrevista Técnica 2','Conversa com André',
  'Conversa Final','Conversa com a Marina','Offer','See you soon','See you Soon'
);

-- 4) Sanidade do funil: o volume tem que cair etapa a etapa.
SELECT etapa, ordem_etapa, SUM(flag_ativo) AS ativos, COUNT(*) AS total
FROM `br-in-dataplatform.greenhouse_dev.vw_farol_base`
WHERE tipo_etapa = 'funil'
GROUP BY 1, 2 ORDER BY ordem_etapa;

-- 5) Os flags batem? Esperado: aceites <= ofertas, contratados <= aceites,
--    e ativos > 0 (se zerar, o domínio de application_status mudou).
SELECT SUM(flag_oferta) AS ofertas, SUM(flag_aceite) AS aceites,
       SUM(flag_contratado) AS contratados, SUM(flag_ativo) AS ativos,
       COUNT(*) AS candidaturas
FROM `br-in-dataplatform.greenhouse_dev.vw_farol_base`;
