-- =====================================================================
-- 20 — VIEWS UNIFICADAS DO FAROL  (escopo Greenhouse)
-- =====================================================================
-- Farol de Hiring
--
-- 7 views do greenhouse_dev  ->  6 views do farol, uma por grão:
--
--   vw_farol_job                 vaga                  (dimensão)
--   vw_farol_funil               vaga × etapa          (foto de hoje)
--   vw_farol_funil_chapter       chapter × etapa × mês (o app lê esta)
--   vw_farol_candidatos_parados  candidato
--   vw_farol_see_you_soon        vaga
--   vw_farol_ofertas             chapter
--
-- Ordem: passo1_descoberta.sql -> passo2_seeds.sql -> este arquivo.
--
-- REGRA DE DESENHO: uma view por grão que alguém consome de fora. View
-- intermediária que só existe para outra view ler virou CTE. View que era
-- "a mesma coisa + duas colunas derivadas" virou subquery. E agregação
-- fica em SQL onde ela é sutil (média ponderada por volume) e vai para o
-- pandas onde é trivial (SUM).
--
-- Tudo marcado com "CONFIRMAR" depende de um resultado do passo1_descoberta.
-- =====================================================================

-- rótulo de mês em português, como o app usa ("Mar/2026")
CREATE OR REPLACE FUNCTION `br-in-dataplatform.greenhouse_dev.fn_farol_mes_label`(d DATE) AS (
  CASE EXTRACT(MONTH FROM d)
    WHEN 1 THEN 'Jan' WHEN 2 THEN 'Fev' WHEN 3 THEN 'Mar' WHEN 4 THEN 'Abr'
    WHEN 5 THEN 'Mai' WHEN 6 THEN 'Jun' WHEN 7 THEN 'Jul' WHEN 8 THEN 'Ago'
    WHEN 9 THEN 'Set' WHEN 10 THEN 'Out' WHEN 11 THEN 'Nov' WHEN 12 THEN 'Dez'
  END || '/' || CAST(EXTRACT(YEAR FROM d) AS STRING)
);


-- =====================================================================
-- 1. vw_farol_job — dimensão de vaga (o desbloqueador)
-- =====================================================================
-- Nenhuma view do Greenhouse tem carreira nem nível; todas são por
-- job_name. É esta view que dá chapter/senioridade para o resto, e sem
-- ela nada no farol pode ser agrupado como o negócio pensa.
--
-- Deduz do texto do job_name e deixa o seed d_farol_job_carreira sobrescrever o
-- que o parse errar. A coluna origem_classificacao mede quanto está sendo
-- adivinhado (QA 9.1).
-- =====================================================================
CREATE OR REPLACE VIEW `br-in-dataplatform.greenhouse_dev.vw_farol_job` AS
WITH jobs AS (
  SELECT DISTINCT job_id, TRIM(job_name) AS job_name
  FROM `br-in-dataplatform.greenhouse_dev.greenhouse_v_applications`
),
parse AS (
  SELECT
    job_id,
    job_name,
    CASE
      WHEN REGEXP_CONTAINS(job_name, r'(?i)\bstaff\b')                                  THEN 'Staff'
      WHEN REGEXP_CONTAINS(job_name, r'(?i)\b(s[êe]nior|senior|sr\.?)\b')               THEN 'Senior'
      WHEN REGEXP_CONTAINS(job_name, r'(?i)\b(pleno|mid|middle)\b')                     THEN 'Pleno'
      WHEN REGEXP_CONTAINS(job_name, r'(?i)\b(j[úu]nior|junior|jr\.?|entry|trainee)\b') THEN 'Junior'
      ELSE NULL
    END AS senioridade_parse,
    NULLIF(TRIM(REGEXP_REPLACE(
      job_name,
      r'(?i)\s*[·|\-–—,/]?\s*\b(staff|s[êe]nior|senior|sr\.?|pleno|mid|middle|j[úu]nior|junior|jr\.?|entry|trainee)\b\s*',
      ' '
    )), '') AS chapter_parse
  FROM jobs
)
SELECT
  p.job_id,
  p.job_name,
  COALESCE(o.chapter, p.chapter_parse)         AS chapter,
  COALESCE(o.senioridade, p.senioridade_parse) AS senioridade,
  CASE
    WHEN o.job_name IS NOT NULL          THEN 'override'
    WHEN p.senioridade_parse IS NOT NULL THEN 'parse'
    ELSE 'indefinido'
  END                                          AS origem_classificacao,
  -- PENDENTE (descoberta #6): vagas abertas. Sem o Artefactory é a única
  -- fonte de demanda que sobra, e o que decide se há farol de verdade ou
  -- só diagnóstico de funil. Trocar o NULL pela coluna real.
  CAST(NULL AS INT64)                          AS openings
FROM parse p
LEFT JOIN `br-in-dataplatform.greenhouse_dev.d_farol_job_carreira` o
  ON TRIM(o.job_name) = p.job_name;


-- =====================================================================
-- 2. vw_farol_funil — vaga × etapa, foto de hoje
-- =====================================================================
-- O fato base do funil: volume (v_applications) + tempo
-- (v_stage_average_time) + conversão (v_stage_conversion_by_job) + metas
-- (d_farol_etapa), num grão só.
--
-- É esta que vai para o snapshot, no grão mais fino de propósito:
-- histórico guardado já agregado por chapter congelaria a definição de
-- hoje para sempre, e mudar a regra depois exigiria reescrever o passado.
-- =====================================================================
CREATE OR REPLACE VIEW `br-in-dataplatform.greenhouse_dev.vw_farol_funil` AS
WITH
-- Grade canônica de etapas. O DISTINCT é obrigatório: o d_farol_etapa mapeia
-- VÁRIOS stage_name do Greenhouse para a MESMA etapa (as três variantes da
-- conversa final), e sem ele o CROSS JOIN triplicaria o funil.
grade AS (
  SELECT DISTINCT etapa, ordem_etapa, meta_sla_dias
  FROM `br-in-dataplatform.greenhouse_dev.d_farol_etapa`
  WHERE tipo = 'funil' AND etapa IS NOT NULL
),
volume AS (
  SELECT
    a.job_id,
    e.etapa,
    COUNT(DISTINCT a.application_id) AS candidatos
  FROM `br-in-dataplatform.greenhouse_dev.greenhouse_v_applications` a
  JOIN `br-in-dataplatform.greenhouse_dev.d_farol_etapa` e
    ON e.stage_name = a.stage_name AND e.tipo = 'funil'
  -- CONFIRMAR (descoberta #3): qual valor marca candidatura viva
  WHERE LOWER(a.application_status) IN ('active', 'ativo', 'ativa')
  GROUP BY 1, 2
),
tempo AS (
  -- AVG porque a mesma etapa canônica pode vir em mais de uma linha
  -- (nomes diferentes para a mesma conversa final, variantes de caixa)
  SELECT
    TRIM(t.job_name) AS job_name,
    e.etapa,
    AVG(t.average_days_in_stage) AS tempo_medio_dias
  FROM `br-in-dataplatform.greenhouse_dev.greenhouse_v_stage_average_time` t
  JOIN `br-in-dataplatform.greenhouse_dev.d_farol_etapa` e
    ON e.stage_name = t.job_stage_name AND e.tipo = 'funil'
  GROUP BY 1, 2
),
conversao AS (
  -- Conversão é ARESTA (etapa anterior -> destino), tempo é NÓ. A convenção
  -- do app é pendurar a conversão na etapa DESTINO ("% que chegou da etapa
  -- anterior"), por isso o lado direito do split.
  -- CONFIRMAR (descoberta #2) o separador: se não for "->", o gráfico de
  -- conversão desalinha uma etapa em silêncio (QA 9.3 detecta).
  -- CONFIRMAR: se conversion_rate já vier 0-100, tirar o "* 100".
  SELECT
    TRIM(c.job_name) AS job_name,
    e.etapa,
    AVG(c.conversion_rate) * 100 AS conversao_pct
  FROM `br-in-dataplatform.greenhouse_dev.greenhouse_v_stage_conversion_by_job` c
  JOIN `br-in-dataplatform.greenhouse_dev.d_farol_etapa` e
    ON e.stage_name = TRIM(SPLIT(c.job_stage_conversion_names, '->')[SAFE_OFFSET(1)])
   AND e.tipo = 'funil'
  GROUP BY 1, 2
)
SELECT
  CURRENT_DATE()                                              AS snapshot_date,
  FORMAT_DATE('%Y-%m', CURRENT_DATE())                        AS mes,
  `br-in-dataplatform.greenhouse_dev.fn_farol_mes_label`(CURRENT_DATE()) AS mes_label,
  j.job_id,
  j.job_name,
  j.chapter,
  j.senioridade,
  g.etapa,
  g.ordem_etapa,
  COALESCE(v.candidatos, 0)                                   AS candidatos,
  ROUND(c.conversao_pct, 1)                                   AS conversao_pct,
  ROUND(t.tempo_medio_dias, 1)                                AS tempo_medio_dias,
  g.meta_sla_dias,
  ROUND(t.tempo_medio_dias - g.meta_sla_dias, 1)              AS excesso_dias,
  CASE
    WHEN t.tempo_medio_dias IS NULL OR g.meta_sla_dias IS NULL THEN NULL
    WHEN t.tempo_medio_dias > g.meta_sla_dias + 5 THEN 'critico'
    WHEN t.tempo_medio_dias > g.meta_sla_dias     THEN 'atencao'
    ELSE 'ok'
  END                                                         AS status_sla
-- CROSS JOIN para a grade ficar completa: toda vaga com todas as etapas,
-- inclusive as de volume zero, que é o que o funil do app espera.
FROM `br-in-dataplatform.greenhouse_dev.vw_farol_job` j
CROSS JOIN grade g
LEFT JOIN volume    v ON v.job_id   = j.job_id   AND v.etapa = g.etapa
LEFT JOIN tempo     t ON t.job_name = j.job_name AND t.etapa = g.etapa
LEFT JOIN conversao c ON c.job_name = j.job_name AND c.etapa = g.etapa;


-- PENDENTE (descoberta #3) — a última linha do funil.
-- "Contratação" não existe como stage_name no Greenhouse: contratado é
-- STATUS da candidatura. Quando a #3 devolver o valor certo ('hired'?),
-- acrescentar este UNION ALL ao SELECT acima e a linha 'Contratação'
-- (ordem 9, meta NULL, tipo 'funil') no d_farol_etapa:
--
--   SELECT CURRENT_DATE(), FORMAT_DATE('%Y-%m', CURRENT_DATE()),
--          fn_farol_mes_label(CURRENT_DATE()), j.job_id, j.job_name, j.chapter,
--          j.senioridade, 'Contratação', 9,
--          COUNT(DISTINCT a.application_id), NULL, NULL, NULL, NULL, NULL
--   FROM greenhouse_v_applications a
--   JOIN vw_farol_job j ON j.job_id = a.job_id
--   WHERE LOWER(a.application_status) = '<valor de contratado>'
--   GROUP BY 4, 5, 6, 7


-- =====================================================================
-- 3. vw_farol_candidatos_parados — grão candidato
-- =====================================================================
-- RESSALVA: isto é um PROXY, não a medida certa.
--
-- O que a tela precisa: dias parado NA ETAPA ATUAL.
-- O que existe hoje: total_days_in_pipe (tempo no pipe INTEIRO).
--
-- O proxy: soma acumulada do tempo médio das etapas até a etapa atual
-- daquela vaga = quantos dias era "esperado" que o candidato já tivesse
-- gasto para estar onde está. Quem está muito acima está travado. Pega
-- atraso acumulado, não atraso da etapa — quem voou nas primeiras etapas e
-- empacou na atual pode não aparecer.
--
-- Substituir quando a greenhouse_v_stage_history existir (pedido nº 2).
-- =====================================================================
CREATE OR REPLACE VIEW `br-in-dataplatform.greenhouse_dev.vw_farol_candidatos_parados` AS
WITH tempo_etapa AS (
  SELECT
    TRIM(t.job_name) AS job_name,
    e.etapa,
    e.ordem_etapa,
    AVG(t.average_days_in_stage) AS average_days_in_stage
  FROM `br-in-dataplatform.greenhouse_dev.greenhouse_v_stage_average_time` t
  JOIN `br-in-dataplatform.greenhouse_dev.d_farol_etapa` e
    ON e.stage_name = t.job_stage_name AND e.tipo = 'funil'
  GROUP BY 1, 2, 3
),
esperado AS (
  SELECT
    job_name,
    etapa,
    SUM(average_days_in_stage) OVER (
      PARTITION BY job_name
      ORDER BY ordem_etapa
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS dias_esperados_ate_aqui
  FROM tempo_etapa
)
SELECT
  CURRENT_DATE()                                              AS snapshot_date,
  FORMAT_DATE('%Y-%m', CURRENT_DATE())                        AS mes,
  `br-in-dataplatform.greenhouse_dev.fn_farol_mes_label`(CURRENT_DATE()) AS mes_label,
  j.chapter,
  j.senioridade,
  TRIM(a.job_name)                                            AS vaga,
  e.etapa,
  e.ordem_etapa,
  a.candidate_id,
  a.candidate_name                                            AS candidato,
  a.total_days_in_pipe,
  ROUND(es.dias_esperados_ate_aqui, 1)                        AS dias_esperados_ate_aqui,
  ROUND(a.total_days_in_pipe - es.dias_esperados_ate_aqui, 1) AS dias_acima_do_esperado,
  CASE
    WHEN es.dias_esperados_ate_aqui IS NULL THEN NULL
    WHEN a.total_days_in_pipe > es.dias_esperados_ate_aqui + 5 THEN 'critico'
    WHEN a.total_days_in_pipe > es.dias_esperados_ate_aqui     THEN 'atencao'
    ELSE 'ok'
  END                                                         AS status
FROM `br-in-dataplatform.greenhouse_dev.greenhouse_v_applications` a
JOIN `br-in-dataplatform.greenhouse_dev.d_farol_etapa` e
  ON e.stage_name = a.stage_name AND e.tipo = 'funil'
LEFT JOIN `br-in-dataplatform.greenhouse_dev.vw_farol_job` j
  ON j.job_id = a.job_id
LEFT JOIN esperado es
  ON es.job_name = TRIM(a.job_name) AND es.etapa = e.etapa
-- CONFIRMAR (descoberta #3)
WHERE LOWER(a.application_status) IN ('active', 'ativo', 'ativa');


-- =====================================================================
-- 4. HISTÓRICO — a parte com prazo
-- =====================================================================
-- Nenhuma view do Greenhouse tem data, e as de conversão/tempo já chegam
-- agregadas: histórico NÃO é reconstruível depois. Cada dia sem snapshot é
-- um dia que o farol nunca vai poder comparar.
--
-- A view é a foto, a tabela particionada acumula as fotos. Agendar os dois
-- INSERTs como scheduled query diária; o NOT EXISTS deixa idempotente.
-- =====================================================================
CREATE TABLE IF NOT EXISTS `br-in-dataplatform.greenhouse_dev.f_farol_funil_snapshot`
PARTITION BY snapshot_date AS
SELECT * FROM `br-in-dataplatform.greenhouse_dev.vw_farol_funil` WHERE FALSE;

CREATE TABLE IF NOT EXISTS `br-in-dataplatform.greenhouse_dev.f_farol_parados_snapshot`
PARTITION BY snapshot_date AS
SELECT * FROM `br-in-dataplatform.greenhouse_dev.vw_farol_candidatos_parados` WHERE FALSE;

INSERT INTO `br-in-dataplatform.greenhouse_dev.f_farol_funil_snapshot`
SELECT * FROM `br-in-dataplatform.greenhouse_dev.vw_farol_funil`
WHERE NOT EXISTS (
  SELECT 1 FROM `br-in-dataplatform.greenhouse_dev.f_farol_funil_snapshot`
  WHERE snapshot_date = CURRENT_DATE()
);

INSERT INTO `br-in-dataplatform.greenhouse_dev.f_farol_parados_snapshot`
SELECT * FROM `br-in-dataplatform.greenhouse_dev.vw_farol_candidatos_parados`
WHERE NOT EXISTS (
  SELECT 1 FROM `br-in-dataplatform.greenhouse_dev.f_farol_parados_snapshot`
  WHERE snapshot_date = CURRENT_DATE()
);


-- =====================================================================
-- 5. vw_farol_funil_chapter — chapter × etapa × mês (o app lê esta)
-- =====================================================================
-- Equivalente exato do funil_pipe.csv, header por header. Lê do snapshot,
-- então já vem com histórico: uma linha por mês, a última foto de cada mês.
--
-- A agregação por chapter fica AQUI, em SQL, e não no pandas, porque a
-- média é PONDERADA por volume: média simples entre vagas daria o mesmo
-- peso a uma vaga com 1 candidato e outra com 40. É a classe de erro que
-- não levanta exceção, só devolve número errado.
--
-- Já a quebra por senioridade (o funil_pipe_nivel.csv do protótipo) é SUM
-- puro, sem ponderação: essa o app faz com um groupby na vw_farol_funil, e
-- por isso não existe view própria para ela.
--
-- Depende do primeiro INSERT da seção 3 já ter rodado.
-- =====================================================================
CREATE OR REPLACE VIEW `br-in-dataplatform.greenhouse_dev.vw_farol_funil_chapter` AS
WITH ultima_foto_do_mes AS (
  SELECT * EXCEPT(rn) FROM (
    SELECT *, ROW_NUMBER() OVER (
      PARTITION BY mes, job_id, etapa ORDER BY snapshot_date DESC
    ) AS rn
    FROM `br-in-dataplatform.greenhouse_dev.f_farol_funil_snapshot`
  )
  WHERE rn = 1
),
agregado AS (
  SELECT
    mes,
    mes_label,
    chapter,
    etapa,
    ordem_etapa,
    SUM(candidatos)    AS candidatos,
    MAX(meta_sla_dias) AS meta_sla_dias,
    ROUND(COALESCE(
      SAFE_DIVIDE(SUM(conversao_pct * candidatos),
                  SUM(IF(conversao_pct IS NULL, NULL, candidatos))),
      AVG(conversao_pct)       -- sem volume na etapa, cai para média simples
    ), 1)              AS conversao_pct,
    ROUND(COALESCE(
      SAFE_DIVIDE(SUM(tempo_medio_dias * candidatos),
                  SUM(IF(tempo_medio_dias IS NULL, NULL, candidatos))),
      AVG(tempo_medio_dias)
    ), 1)              AS tempo_medio_dias
  FROM ultima_foto_do_mes
  WHERE chapter IS NOT NULL
  GROUP BY mes, mes_label, chapter, etapa, ordem_etapa
)
-- excesso e status derivam do tempo JÁ agregado — daí a subquery, em vez de
-- uma segunda view só para acrescentar duas colunas.
SELECT
  mes, mes_label, chapter, etapa, ordem_etapa, candidatos,
  conversao_pct, tempo_medio_dias, meta_sla_dias,
  ROUND(tempo_medio_dias - meta_sla_dias, 1) AS excesso_dias,
  CASE
    WHEN tempo_medio_dias IS NULL OR meta_sla_dias IS NULL THEN NULL
    WHEN tempo_medio_dias > meta_sla_dias + 5 THEN 'critico'
    WHEN tempo_medio_dias > meta_sla_dias     THEN 'atencao'
    ELSE 'ok'
  END                                        AS status_sla
FROM agregado;


-- =====================================================================
-- 6. vw_farol_see_you_soon — grão vaga
-- =====================================================================
-- Funde as duas views de SU. Grão de vaga é o máximo possível hoje; para a
-- "visão por pessoa" que o RH pediu, falta a view de SU no grão de
-- candidato (pedido nº 3).
--
-- As colunas *_geral trazem o total ponderado repetido em toda linha, de
-- propósito: é para ninguém calcular média de médias por vaga do lado de
-- fora. Isso era uma view separada (_kpi); virou window function.
-- =====================================================================
CREATE OR REPLACE VIEW `br-in-dataplatform.greenhouse_dev.vw_farol_see_you_soon` AS
WITH conversao AS (
  SELECT
    TRIM(job_name) AS job_name,
    SUM(number_of_applications) AS candidaturas_su,
    -- CONFIRMAR (descoberta #3) os valores de offer_status
    SUM(IF(LOWER(CAST(offer_status AS STRING)) LIKE '%accept%'
        OR LOWER(CAST(offer_status AS STRING)) LIKE '%aceit%',
        number_of_applications, 0)) AS aceites_su,
    SUM(IF(offer_status IS NULL, 0, number_of_applications)) AS ofertas_su
  FROM `br-in-dataplatform.greenhouse_dev.greenhouse_v_see_you_soon_conversion`
  GROUP BY 1
)
SELECT
  CURRENT_DATE()                                              AS snapshot_date,
  FORMAT_DATE('%Y-%m', CURRENT_DATE())                        AS mes,
  `br-in-dataplatform.greenhouse_dev.fn_farol_mes_label`(CURRENT_DATE()) AS mes_label,
  j.chapter,
  j.senioridade,
  c.job_name,
  c.candidaturas_su,
  c.ofertas_su                                                AS ofertas_sys,
  c.aceites_su                                                AS aceites_sys,
  t.days_in_see_you_soon                                      AS dias_no_banco_medio,
  ROUND(SAFE_DIVIDE(c.aceites_su, c.ofertas_su) * 100, 1)     AS taxa_aceite_sys_pct,
  SUM(c.candidaturas_su) OVER ()                              AS pessoas_no_banco_geral,
  ROUND(SAFE_DIVIDE(
    SUM(t.days_in_see_you_soon * c.candidaturas_su) OVER (),
    SUM(IF(t.days_in_see_you_soon IS NULL, NULL, c.candidaturas_su)) OVER ()
  ), 1)                                                       AS dias_no_banco_medio_geral,
  ROUND(SAFE_DIVIDE(SUM(c.aceites_su) OVER (),
                    SUM(c.ofertas_su) OVER ()) * 100, 1)      AS taxa_aceite_sys_pct_geral
FROM conversao c
LEFT JOIN `br-in-dataplatform.greenhouse_dev.greenhouse_v_see_you_soon_average_time_by_job` t
  ON TRIM(t.job_name) = c.job_name
LEFT JOIN `br-in-dataplatform.greenhouse_dev.vw_farol_job` j
  ON j.job_name = c.job_name;


-- =====================================================================
-- 7. vw_farol_ofertas — oferta -> aceite, por carreira
-- =====================================================================
-- Sai da v_applications (grão candidatura), não da v_offers, para existir
-- UMA definição de "oferta enviada" e "oferta aceita". A v_offers fica
-- como reconciliação (QA 9.4).
--
-- Também corrige o cálculo do protótipo, que dividia contratações por
-- ofertas dentro do funil do mês — coortes diferentes: as ofertas feitas em
-- junho não são as mesmas pessoas que assinaram em junho.
-- =====================================================================
CREATE OR REPLACE VIEW `br-in-dataplatform.greenhouse_dev.vw_farol_ofertas` AS
SELECT
  CURRENT_DATE()                                              AS snapshot_date,
  FORMAT_DATE('%Y-%m', CURRENT_DATE())                        AS mes,
  `br-in-dataplatform.greenhouse_dev.fn_farol_mes_label`(CURRENT_DATE()) AS mes_label,
  j.chapter,
  j.senioridade,
  COUNTIF(a.offer_status IS NOT NULL)                         AS ofertas,
  -- CONFIRMAR (descoberta #3)
  COUNTIF(LOWER(CAST(a.offer_status AS STRING)) LIKE '%accept%'
       OR LOWER(CAST(a.offer_status AS STRING)) LIKE '%aceit%') AS aceites,
  ROUND(SAFE_DIVIDE(
    COUNTIF(LOWER(CAST(a.offer_status AS STRING)) LIKE '%accept%'
         OR LOWER(CAST(a.offer_status AS STRING)) LIKE '%aceit%'),
    COUNTIF(a.offer_status IS NOT NULL)) * 100, 1)            AS taxa_aceite_pct
FROM `br-in-dataplatform.greenhouse_dev.greenhouse_v_applications` a
LEFT JOIN `br-in-dataplatform.greenhouse_dev.vw_farol_job` j
  ON j.job_id = a.job_id
GROUP BY snapshot_date, mes, mes_label, j.chapter, j.senioridade;


-- =====================================================================
-- 8. QA — rodar depois de criar tudo
-- =====================================================================

-- 9.1 Quanto da classificação de carreira/nível está sendo adivinhada.
--     'indefinido' alto => cadastrar esses job_name no d_farol_job_carreira.
SELECT origem_classificacao, COUNT(*) AS vagas
FROM `br-in-dataplatform.greenhouse_dev.vw_farol_job`
GROUP BY 1 ORDER BY vagas DESC;

SELECT job_name, chapter, senioridade
FROM `br-in-dataplatform.greenhouse_dev.vw_farol_job`
WHERE origem_classificacao = 'indefinido'
ORDER BY job_name;

-- 9.3 O MAIS IMPORTANTE: conversões cujo destino não casou com o d_farol_etapa.
--     Esperado: zero. Se vier linha, o separador do
--     job_stage_conversion_names não é "->" e o gráfico de conversão fica
--     silenciosamente errado.
SELECT DISTINCT
  c.job_stage_conversion_names,
  TRIM(SPLIT(c.job_stage_conversion_names, '->')[SAFE_OFFSET(1)]) AS destino_extraido
FROM `br-in-dataplatform.greenhouse_dev.greenhouse_v_stage_conversion_by_job` c
LEFT JOIN `br-in-dataplatform.greenhouse_dev.d_farol_etapa` e
  ON e.stage_name = TRIM(SPLIT(c.job_stage_conversion_names, '->')[SAFE_OFFSET(1)])
WHERE e.stage_name IS NULL;

-- 9.4 Reconciliação: ofertas pela v_applications vs. greenhouse_v_offers.
SELECT
  (SELECT SUM(ofertas) FROM `br-in-dataplatform.greenhouse_dev.vw_farol_ofertas`) AS ofertas_via_applications,
  (SELECT COUNT(*) FROM `br-in-dataplatform.greenhouse_dev.greenhouse_v_offers`) AS linhas_v_offers;

-- 9.5 Sanidade do funil: o volume tem que cair etapa a etapa.
SELECT etapa, ordem_etapa, SUM(candidatos) AS candidatos
FROM `br-in-dataplatform.greenhouse_dev.vw_farol_funil`
GROUP BY 1, 2 ORDER BY ordem_etapa;

-- 9.6 Quanto volume está ficando FORA do funil (pipeline default do
--     Greenhouse + stage_name vazio). Na descoberta #1 eram 122 de 68.987
--     (0,18%). Se crescer, rediscutir o mapeamento de 'Interview #N'.
SELECT
  COALESCE(e.tipo, 'sem mapeamento') AS situacao,
  COALESCE(a.stage_name, '(vazio)')  AS stage_name,
  COUNT(*)                           AS candidaturas
FROM `br-in-dataplatform.greenhouse_dev.greenhouse_v_applications` a
LEFT JOIN `br-in-dataplatform.greenhouse_dev.d_farol_etapa` e
  ON e.stage_name = a.stage_name
WHERE e.tipo IS NULL OR e.tipo <> 'funil'
GROUP BY 1, 2
ORDER BY candidaturas DESC;

-- 9.7 Etapa nova no Greenhouse que ainda não está no d_farol_etapa.
--     Esperado: zero. Aparece aqui antes de sumir do funil em silêncio.
SELECT DISTINCT a.stage_name
FROM `br-in-dataplatform.greenhouse_dev.greenhouse_v_applications` a
LEFT JOIN `br-in-dataplatform.greenhouse_dev.d_farol_etapa` e ON e.stage_name = a.stage_name
WHERE e.stage_name IS NULL AND a.stage_name IS NOT NULL
UNION DISTINCT
SELECT DISTINCT t.job_stage_name
FROM `br-in-dataplatform.greenhouse_dev.greenhouse_v_stage_average_time` t
LEFT JOIN `br-in-dataplatform.greenhouse_dev.d_farol_etapa` e ON e.stage_name = t.job_stage_name
WHERE e.stage_name IS NULL;

-- 9.8 O snapshot está rodando? Sem isso o histórico para de acumular.
SELECT MAX(snapshot_date) AS ultima_foto,
       DATE_DIFF(CURRENT_DATE(), MAX(snapshot_date), DAY) AS dias_sem_rodar
FROM `br-in-dataplatform.greenhouse_dev.f_farol_funil_snapshot`;
