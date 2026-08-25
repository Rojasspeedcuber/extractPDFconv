# 🔌 Guia de Integração com DBeaver

## 📋 Informações do Banco de Dados

**SGBD:** PostgreSQL 18.6  
**Banco de Dados:** `convocacoes`  
**Usuário:** `eleicoes_user`  
**Senha:** `senha123`  
**Host:** `localhost` (ou IP do servidor onde o banco está rodando)  
**Porta:** `5432`

---

## 🛠️ Como Conectar no DBeaver

### 1. Abrir o DBeaver
- Inicie o DBeaver no seu computador

### 2. Criar Nova Conexão
1. Clique em **"Nova Conexão"** (ícone de plugue com um "+")
2. Selecione **"PostgreSQL"**
3. Clique em **"Avançar"**

### 3. Configurar a Conexão

Preencha os campos:

| Campo | Valor |
|-------|-------|
| **Host** | `localhost` (ou o IP do servidor) |
| **Port** | `5432` |
| **Database** | `convocacoes` |
| **Username** | `eleicoes_user` |
| **Password** | `senha123` |

### 4. Testar Conexão
- Clique em **"Test Connection"**
- Se aparecer "Connected", a conexão está funcionando! ✅
- Clique em **"Finish"**

---

## 📊 Estrutura das Tabelas

### Tabela: `instrumento_convocacao`

Armazena os dados da carta de convocação eleitoral.

```sql
SELECT * FROM instrumento_convocacao;
```

**Campos:**
- `id` - Identificador único (auto increment)
- `tipo` - Tipo de evento (0=Treinamento, 1=1º Turno, 2=2º Turno)
- `data` - Data do evento
- `responsavel` - Nome do responsável pela convocação
- `convocado_cpf` - CPF da pessoa convocada (11 dígitos)
- `orgao_convocador` - Órgão que emitiu a convocação
- `criado_em` - Data/hora de inserção no banco

### Tabela: `conv`

Controla os comparecimentos aos eventos eleitorais.

```sql
SELECT * FROM conv;
```

**Campos:**
- `id` - Identificador único (auto increment)
- `cpf` - CPF da pessoa (11 dígitos)
- `tipo` - Tipo de evento (0=Treinamento, 1=1º Turno, 2=2º Turno)
- `data` - Data do evento
- `realizado` - Se compareceu (TRUE) ou não (FALSE)
- `criado_em` - Data/hora de inserção no banco

---

## 🔍 Consultas Úteis no DBeaver

### Ver todas as convocações
```sql
SELECT 
    id,
    CASE tipo
        WHEN 0 THEN 'Treinamento'
        WHEN 1 THEN '1º Turno'
        WHEN 2 THEN '2º Turno'
    END as tipo_evento,
    data,
    responsavel,
    convocado_cpf,
    orgao_convocador
FROM instrumento_convocacao
ORDER BY data;
```

### Ver registros de comparecimento
```sql
SELECT 
    cpf,
    CASE tipo
        WHEN 0 THEN 'Treinamento'
        WHEN 1 THEN '1º Turno'
        WHEN 2 THEN '2º Turno'
    END as tipo_evento,
    data,
    CASE realizado
        WHEN true THEN 'Compareceu'
        WHEN false THEN 'Faltou'
    END as status
FROM conv
ORDER BY data, cpf;
```

### Estatísticas de comparecimento
```sql
SELECT 
    CASE tipo
        WHEN 0 THEN 'Treinamento'
        WHEN 1 THEN '1º Turno'
        WHEN 2 THEN '2º Turno'
    END as evento,
    COUNT(*) as total_convocados,
    SUM(CASE WHEN realizado THEN 1 ELSE 0 END) as compareceram,
    SUM(CASE WHEN NOT realizado THEN 1 ELSE 0 END) as faltaram
FROM conv
GROUP BY tipo
ORDER BY tipo;
```

### Buscar convocações por CPF
```sql
SELECT * FROM instrumento_convocacao 
WHERE convocado_cpf = '12345678900';
```

### Marcar comparecimento como realizado
```sql
UPDATE conv 
SET realizado = true 
WHERE cpf = '12345678900' AND tipo = 1;
```

---

## 🔄 Como Funciona a Integração

### 1. Extração de PDF → Banco de Dados

Quando você processa um PDF na aplicação:

1. **Upload do PDF** → Interface Streamlit ou CLI
2. **Extração de Dados** → Sistema identifica CPF, datas, responsável, órgão
3. **Persistência Automática** → Dados são salvos nas tabelas do PostgreSQL
4. **Prevenção de Duplicatas** → Sistema não insere registros duplicados (mesmo CPF + tipo)

### 2. Visualização no DBeaver

Após processar PDFs, você pode:

✅ Ver todos os dados extraídos em tempo real  
✅ Fazer consultas SQL personalizadas  
✅ Exportar relatórios em CSV/Excel  
✅ Marcar comparecimentos manualmente  
✅ Gerar estatísticas de presença  

---

## 🚀 Processamento de PDFs

### Via Interface Web (Streamlit)
```bash
cd /caminho/do/projeto
streamlit run app.py
```

Acesse `http://localhost:8501` e faça upload dos PDFs.

### Via Linha de Comando (CLI)
```bash
# Processar um PDF
python ingest_pdfs.py caminho/do/arquivo.pdf

# Processar todos os PDFs de uma pasta
python ingest_pdfs.py --dir caminho/da/pasta

# Testar conexão
python ingest_pdfs.py --test-conn

# Inicializar schema (criar tabelas)
python ingest_pdfs.py --init-db
```

---

## 🔐 Segurança

⚠️ **IMPORTANTE:** As credenciais neste guia são para **ambiente de desenvolvimento/teste**.

Para **produção**, você deve:

1. Usar senhas fortes e únicas
2. Configurar SSL/TLS para conexões
3. Restringir acesso por firewall
4. Usar variáveis de ambiente (nunca commitar credenciais)
5. Fazer backup regular do banco

---

## 📝 Variáveis de Ambiente

O arquivo `.env` já está configurado:

```env
DATABASE_URL=postgresql://eleicoes_user:senha123@localhost:5432/convocacoes
PERSIST_TO_DB=true
```

Para conectar a um banco **remoto**, edite o `.env`:

```env
DATABASE_URL=postgresql://usuario:senha@IP_DO_SERVIDOR:5432/convocacoes
```

---

## ✅ Validação da Integração

Execute este comando para verificar se tudo está funcionando:

```bash
python -c "from database import db; print('✅ Banco conectado!' if db.test_connection() else '❌ Erro de conexão')"
```

---

## 📞 Suporte

- **Documentação completa:** Veja `README.md`
- **Schema SQL:** `database/schema.sql`
- **Código de conexão:** `database/db.py`
- **Camada de persistência:** `database/persistence_service.py`

---

**Data de criação deste guia:** 25/08/2026  
**Versão do PostgreSQL:** 18.6  
**Versão do Python:** 3.11+
