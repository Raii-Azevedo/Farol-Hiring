-- =====================================================================
-- 10 — SEEDS  (as duas tabelas que não vêm de dado nenhum)
-- =====================================================================
-- Farol de Hiring · escopo Greenhouse
--
-- Rodar depois do passo1_descoberta.sql e antes do passo3_views.sql.
--
-- Dataset de escrita: ajuste `br-in-dataplatform.greenhouse_dev` se o farol
-- for morar em outro lugar (as views do 20 usam o mesmo).
-- =====================================================================


-- O dataset de destino precisa existir antes de tudo. Se o farol for morar
-- em outro lugar, trocar `greenhouse_dev` aqui e nos outros scripts.
-- ---------------------------------------------------------------------
-- d_farol_etapa — faz quatro trabalhos de uma vez:
--
--   1. VOCABULÁRIO: traduz os nomes que o Greenhouse usa (stage_name)
--      para o nome canônico do farol (etapa). Os dados reais mostraram
--      19 nomes distintos para ~9 etapas, com variação de caixa, de
--      acento e três nomes para a mesma conversa final. Sem esta tabela,
--      um join por string derrubaria silenciosamente metade do funil.
--   2. ORDEM: nenhuma view do Greenhouse entrega ordem de etapa, e sem
--      ordem não existe funil nem conversão "da etapa anterior".
--   3. TIPO: separa o que é funil, o que é backlog paralelo (See You
--      Soon) e o que fica fora do farol — explicitamente, para a exclusão
--      ser auditável em vez de acontecer por omissão num join.
--   4. META DE SLA: regra de negócio, não dado. Duas telas do app
--      dependem dela (Gargalos/SLA e Candidatos parados).
--
-- Preenchido com o resultado real da descoberta #1 (68.987 candidaturas).
-- As METAS continuam a definir — ver "A DEFINIR" abaixo.
--
-- Owner: esta tabela é mantida pelo SQL (CREATE OR REPLACE).
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE `br-in-dataplatform.greenhouse_dev.d_farol_etapa` AS
SELECT * FROM UNNEST([
  STRUCT(
    'Avaliação de currículo' AS stage_name,
    'Avaliação de currículo' AS etapa,
    1                        AS ordem_etapa,
    'funil'                  AS tipo,
    2                        AS meta_sla_dias,
    '95% de todas as candidaturas estão aqui — é o topo do funil' AS observacao
  ),
  -- mesmo passo, nomes diferentes: 'Curriculo selecionado' (sem acento,
  -- 8 candidaturas) e o default em inglês do Greenhouse
  STRUCT('Curriculo selecionado', 'Avaliação de currículo', 1, 'funil',  2, 'variante sem acento, volume baixo'),
  STRUCT('Application Review',    'Avaliação de currículo', 1, 'funil',  2, 'default do Greenhouse, equivalente à triagem de CV'),

  -- ETAPAS NOVAS: o case escrito não existe no funil do app hoje, e são
  -- 2.293 candidaturas (3,3%) — mais que todo o resto do funil somado
  -- depois da triagem. O mock visual já tinha a coluna "Case".
  STRUCT('Envio do Case Escrito',  'Envio do Case Escrito',  2, 'funil',  3, 'A DEFINIR: meta sugerida pelo mock (Atenção 3-5d)'),
  STRUCT('Avaliação case escrito', 'Avaliação case escrito', 3, 'funil',  3, 'A DEFINIR'),

  STRUCT('Entrevista Fit',       'Entrevista Fit',       4, 'funil',  3, NULL),
  STRUCT('Entrevista Técnica 1', 'Entrevista Técnica 1', 5, 'funil',  5, NULL),
  STRUCT('Entrevista Técnica 2', 'Entrevista Técnica 2', 6, 'funil',  5, NULL),

  -- MESMA ETAPA, TRÊS NOMES. Canonizado como "Conversa Final" (nome que o
  -- mock visual usa) em vez do nome de uma pessoa: se o André ou a Marina
  -- saírem do processo, o dashboard não quebra.
  STRUCT('Conversa com André',    'Conversa Final', 7, 'funil', 4, 'nome mais usado hoje (40 candidaturas)'),
  STRUCT('Conversa Final',        'Conversa Final', 7, 'funil', 4, 'nome novo/renomeado'),
  STRUCT('Conversa com a Marina', 'Conversa Final', 7, 'funil', 4, 'aparece em 2 vagas na v_stage_average_time'),

  STRUCT('Offer', 'Oferta', 8, 'funil', 3, 'Greenhouse usa o nome em inglês'),

  -- "Contratação" NÃO EXISTE como etapa no Greenhouse — contratado é
  -- STATUS da candidatura, não stage. A última linha do funil do app tem
  -- que vir do application_status, não daqui. Ver o bloco marcado no
  -- passo3_views.sql (depende da descoberta #3).

  -- Backlog paralelo, não etapa do funil. Duas variantes de caixa.
  STRUCT('See you soon', 'See You Soon', NULL, 'paralelo', NULL, '32 candidaturas'),
  STRUCT('See you Soon', 'See You Soon', NULL, 'paralelo', NULL, 'variante de caixa, 1 candidatura'),

  -- Pipeline default do Greenhouse, em vagas que nunca foram configuradas
  -- com o processo da Artefact. São 70 candidaturas (0,10% do total), e
  -- mapear "Interview #3" para Técnica 2 ou para Conversa Final é palpite
  -- que muda o funil. Ficam FORA até o RH confirmar — o QA 9.6 mostra
  -- quanto volume isso representa.
  STRUCT('Interview #1', NULL, NULL, 'fora', NULL, 'A DEFINIR com RH'),
  STRUCT('Interview #2', NULL, NULL, 'fora', NULL, 'A DEFINIR com RH'),
  STRUCT('Interview #3', NULL, NULL, 'fora', NULL, 'A DEFINIR com RH'),
  STRUCT('Interview #4', NULL, NULL, 'fora', NULL, 'A DEFINIR com RH'),
  STRUCT('Interview #5', NULL, NULL, 'fora', NULL, 'A DEFINIR com RH')
]);

-- As 52 candidaturas com stage_name vazio/NULL também ficam fora: não dá
-- para posicioná-las no funil. O QA 9.2 mantém isso visível.

-- Se o STF quiser meta por carreira (hoje o protótipo varia a conversa
-- final entre 3 e 4 dias por chapter), acrescentar a coluna chapter aqui
-- e no join do v_farol_funil_job.


-- ---------------------------------------------------------------------
-- d_farol_job_carreira — de-para job_name -> chapter + senioridade
--
-- O v_farol_job tenta deduzir carreira e nível do texto do job_name. Esta
-- tabela é o override: tudo que o parse errar ou não souber classificar
-- entra aqui na mão e ganha prioridade sobre o parse.
--
-- Owner: RH. Por isso é CREATE TABLE IF NOT EXISTS — rodar este script de
-- novo NÃO apaga o que o RH cadastrou.
--
-- Fluxo: rodar o QA 9.1 no fim do passo3_views.sql, ver o que saiu como
-- 'indefinido', e cadastrar só esses aqui.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `br-in-dataplatform.greenhouse_dev.d_farol_job_carreira` (
  job_name     STRING NOT NULL OPTIONS(description="job_name exatamente como vem do Greenhouse"),
  chapter      STRING OPTIONS(description="carreira, no vocabulário do farol"),
  senioridade  STRING OPTIONS(description="Junior | Pleno | Senior | Staff"),
  observacao   STRING OPTIONS(description="por que foi classificado na mão")
);

-- Exemplo de cadastro (descomentar e adaptar):
-- INSERT INTO `br-in-dataplatform.greenhouse_dev.d_farol_job_carreira`
--   (job_name, chapter, senioridade, observacao)
-- VALUES
--   ('AE - Squad BI', 'Analytics Engineering', 'Junior', 'nome abreviado, parse nao pega');
