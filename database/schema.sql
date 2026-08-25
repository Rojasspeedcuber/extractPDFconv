-- =====================================================================
-- Schema de banco de dados para o projeto extractPDFconv
-- SGBD: PostgreSQL
-- ---------------------------------------------------------------------
-- Este script cria as duas tabelas usadas para armazenar os dados
-- extraídos das cartas convocatórias eleitorais (PDFs):
--   1) instrumento_convocacao -> registro do instrumento/carta de convocação
--   2) conv                   -> controle de comparecimento por convocação
--
-- Convenção do campo "tipo" (integer) em ambas as tabelas:
--   0 = Treinamento (28/08)
--   1 = 1º Turno
--   2 = 2º Turno
--
-- Execução:
--   psql "$DATABASE_URL" -f database/schema.sql
-- =====================================================================

-- ---------------------------------------------------------------------
-- Tabela: instrumento_convocacao
-- Guarda os dados principais de cada carta/instrumento de convocação.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS instrumento_convocacao (
    id               SERIAL PRIMARY KEY,
    tipo             INTEGER      NOT NULL,          -- 0=treinamento, 1=1º turno, 2=2º turno
    data             DATE,                            -- data associada ao tipo de convocação
    responsavel      TEXT,                            -- responsável/assinante do instrumento
    convocado_cpf    VARCHAR(11),                     -- CPF do convocado (apenas dígitos)
    orgao_convocador TEXT,                            -- órgão que emitiu a convocação
    criado_em        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Índices auxiliares para consultas frequentes
CREATE INDEX IF NOT EXISTS idx_instrumento_convocacao_cpf
    ON instrumento_convocacao (convocado_cpf);
CREATE INDEX IF NOT EXISTS idx_instrumento_convocacao_tipo
    ON instrumento_convocacao (tipo);

-- ---------------------------------------------------------------------
-- Tabela: conv
-- Controle de comparecimento (uma linha por CPF + tipo de convocação).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS conv (
    id         SERIAL PRIMARY KEY,
    cpf        VARCHAR(11),                            -- CPF da pessoa (apenas dígitos)
    tipo       INTEGER      NOT NULL,                  -- 0=treinamento, 1=1º turno, 2=2º turno
    data       DATE,                                   -- data associada ao tipo
    realizado  BOOLEAN      NOT NULL DEFAULT FALSE,    -- se o comparecimento foi realizado
    criado_em  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Índice auxiliar por CPF
CREATE INDEX IF NOT EXISTS idx_conv_cpf ON conv (cpf);

-- Evita duplicar o controle de comparecimento para o mesmo CPF e tipo.
CREATE UNIQUE INDEX IF NOT EXISTS uq_conv_cpf_tipo
    ON conv (cpf, tipo)
    WHERE cpf IS NOT NULL;
