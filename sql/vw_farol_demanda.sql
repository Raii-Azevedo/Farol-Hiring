-- =====================================================================
-- vw_farol_demanda — o lado da demanda do Farol
-- =====================================================================
-- Funde f_resource_request_manual (demanda) e f_staffing_rate_manual
-- (desalocações) no vocabulário do farol.
--
-- GRÃO: chapter × senioridade × mês.
--
-- Por que é uma view separada da vw_farol_base, e não mais uma coluna
-- nela: a demanda tem EIXO DE TEMPO (forecast até 2027-12) e o pipe não
-- tem data nenhuma — é foto de hoje. Juntar as duas numa view só exigiria
-- ou repetir 69 mil candidaturas por mês de forecast, ou congelar o
-- horizonte dentro do SQL e perder o seletor de mês do app. São duas
-- perguntas diferentes, em dois grãos diferentes.
--
-- No app: ler as duas e juntar com um merge em (chapter, senioridade).
--
--   demanda_liquida = staffing_monthly_total - staff_deallocated
--
-- As duas fontes são `_manual` (upload), então a cadência do farol fica
-- presa à cadência desse upload.
-- =====================================================================

CREATE OR REPLACE VIEW `br-in-dataplatform.greenhouse_dev.vw_farol_demanda` AS

WITH
-- ---------------------------------------------------------------------
-- De-para de carreira. O Artefactory e o Greenhouse falam vocabulários
-- diferentes, e a interseção é menor do que parece:
--
--   Artefactory tem demanda para 4 carreiras: Analytics Engineer,
--   Consulting, Data Engineering, Data Science.
--
--   CRM, Front-End Dev, Marketing, PPC/SEA e SEO aparecem só nas
--   desalocações (zero demanda) e não têm chapter no farol.
--
--   AI Engineering e Software Engineering têm PIPE no Greenhouse mas
--   ZERO linha nas duas views de demanda — para esses dois o farol não
--   fecha, só o diagnóstico de funil.
--
-- CONFIRMAR com STF: 'Consulting' do Artefactory é o mesmo chapter que
-- 'Data Consultant' do Greenhouse? É a maior incerteza deste de-para.
-- ---------------------------------------------------------------------
carreira_depara AS (
  SELECT * FROM UNNEST([
    STRUCT('Analytics Engineer' AS career_description, 'Analytics Engineering' AS chapter),
    STRUCT('Data Engineering',  'Data Engineering'),
    STRUCT('Data Science',      'Data Science'),
    STRUCT('Consulting',        'Data Consultant')   -- CONFIRMAR
  ])
),

-- ---------------------------------------------------------------------
-- De-para de nível. O Artefactory tem 16 níveis; o Greenhouse só permite
-- deduzir 3 do job_name (Estagiário / Pleno / Senior). Então a demanda
-- precisa ser dobrada para esses 3.
--
-- Manager, Director, Associate Director e Partner ficam de FORA: são 45
-- FTE de demanda que não se contrata por este funil (promoção interna ou
-- executive search). Sem essa exclusão, o farol mandaria "acelerar" num
-- pipe que nunca vai preencher essas vagas.
--
-- CONFIRMAR com RH: 'Entry 1/2/3' e 'Associate 2/3' são o mesmo nível de
-- contratação que o Greenhouse chama de Pleno (vaga sem marcador no
-- nome)? É a segunda maior incerteza.
-- ---------------------------------------------------------------------
nivel_depara AS (
  SELECT * FROM UNNEST([
    STRUCT('Intern'      AS level_description, 'Estagiário' AS senioridade),
    STRUCT('Entry 1',     'Pleno'),     -- CONFIRMAR
    STRUCT('Entry 2',     'Pleno'),     -- CONFIRMAR
    STRUCT('Entry 3',     'Pleno'),     -- CONFIRMAR
    STRUCT('Associate 2', 'Pleno'),     -- CONFIRMAR
    STRUCT('Associate 3', 'Pleno'),     -- CONFIRMAR
    STRUCT('Senior 1',    'Senior'),
    STRUCT('Senior 2',    'Senior'),
    STRUCT('Senior 3',    'Senior')
    -- Manager 1/2, Director 1/2/3, Associate Director, Partner: fora
  ])
),

-- LEFT(...,7) aguenta tanto year_month_date STRING ('2026-10') quanto
-- DATE ('2026-10-01'), que é como o BigQuery costuma devolver.
demanda AS (
  SELECT
    career_description,
    level_description,
    LEFT(CAST(year_month_date AS STRING), 7) AS mes,
    SUM(staffing_monthly_total)              AS demanda_bruta
  FROM `br-in-dataplatform.greenhouse_dev.f_resource_request_manual`
  GROUP BY 1, 2, 3
),
saida AS (
  SELECT
    career_description,
    level_description,
    LEFT(CAST(year_month_date AS STRING), 7) AS mes,
    SUM(staff_deallocated)                   AS desalocado
  FROM `br-in-dataplatform.greenhouse_dev.f_staffing_rate_manual`
  GROUP BY 1, 2, 3
),
-- FULL OUTER: um mês pode ter desalocação sem pedido novo (e vice-versa)
juntas AS (
  SELECT
    COALESCE(d.career_description, s.career_description) AS career_description,
    COALESCE(d.level_description,  s.level_description)  AS level_description,
    COALESCE(d.mes, s.mes)                               AS mes,
    COALESCE(d.demanda_bruta, 0)                         AS demanda_bruta,
    COALESCE(s.desalocado, 0)                            AS desalocado
  FROM demanda d
  FULL OUTER JOIN saida s
    ON  s.career_description = d.career_description
    AND s.level_description  = d.level_description
    AND s.mes                = d.mes
)

SELECT
  j.mes,
  cd.chapter,
  nd.senioridade,
  -- os valores são FTE fracionário (alocação), não headcount. Comparar
  -- com o pipe (que é gente) assume 1 FTE = 1 pessoa — convenção a
  -- ratificar com o STF.
  ROUND(SUM(j.demanda_bruta), 2)                        AS demanda_bruta_fte,
  ROUND(SUM(j.desalocado), 2)                           AS desalocado_fte,
  ROUND(SUM(j.demanda_bruta) - SUM(j.desalocado), 2)    AS demanda_liquida_fte,
  -- rastro do que foi agregado, para auditar o de-para
  STRING_AGG(DISTINCT j.level_description ORDER BY j.level_description) AS niveis_origem
FROM juntas j
JOIN carreira_depara cd ON cd.career_description = j.career_description
JOIN nivel_depara    nd ON nd.level_description  = j.level_description
GROUP BY 1, 2, 3;


-- =====================================================================
-- QA
-- =====================================================================

-- 1) Quanto de demanda está sendo DESCARTADO pelo de-para, e por quê.
--    Serve para ninguém achar que o farol cobre a empresa inteira.
WITH tudo AS (
  SELECT career_description, level_description,
         LEFT(CAST(year_month_date AS STRING), 7) AS mes,
         staffing_monthly_total AS fte
  FROM `br-in-dataplatform.greenhouse_dev.f_resource_request_manual`
)
SELECT
  CASE
    WHEN career_description NOT IN ('Analytics Engineer','Data Engineering','Data Science','Consulting')
      THEN 'carreira sem chapter no farol'
    WHEN level_description NOT IN ('Intern','Entry 1','Entry 2','Entry 3','Associate 2','Associate 3',
                                   'Senior 1','Senior 2','Senior 3')
      THEN 'nível que não se contrata por este funil'
    ELSE 'dentro do farol'
  END                        AS situacao,
  ROUND(SUM(fte), 1)         AS fte_demanda,
  COUNT(*)                   AS linhas
FROM tudo
GROUP BY 1 ORDER BY fte_demanda DESC;

-- 2) A curva de demanda líquida por chapter, mês a mês.
SELECT mes, chapter, ROUND(SUM(demanda_liquida_fte), 1) AS liquida
FROM `br-in-dataplatform.greenhouse_dev.vw_farol_demanda`
GROUP BY 1, 2 ORDER BY mes, chapter;

-- 3) Chapters com pipe no Greenhouse mas sem NENHUMA demanda.
--    Esperado hoje: AI Engineering e Software Engineering.
SELECT DISTINCT b.chapter
FROM `br-in-dataplatform.greenhouse_dev.vw_farol_base` b
LEFT JOIN `br-in-dataplatform.greenhouse_dev.vw_farol_demanda` d
  ON d.chapter = b.chapter
WHERE b.chapter IS NOT NULL AND d.chapter IS NULL;
