# Design: Controle de Acesso via Keycloak (OIDC + RBAC)

- **Data:** 2026-09-23
- **Escopo:** Autenticação/autorização (`components/auth.py`, `app.py`, `services/authorization_service.py` — novo), painel administrativo (`components/painel_admin.py` — novo), refatorações pontuais (`components/results.py`, `components/comprovantes.py`), configuração (`config/settings.py`, `.env.example`) e docs (`README.md`)
- **Status:** Aprovado pelo usuário (brainstorming)

## 1. Contexto

A aplicação (Streamlit 1.64) já possui integração básica com Keycloak:

- `components/auth.py`: fluxo OIDC via `streamlit-keycloak` 1.1.1 quando
  `KEYCLOAK_URL` está configurado; modo "CPF direto" (desenvolvimento) quando vazio.
- `app.py`: gate de autenticação (`render_login_page()` + `st.stop()`) e sidebar com
  CPF do usuário e botão "Sair" (limpa apenas o `session_state`).
- Toda a aplicação é **escopada pelo CPF da sessão**: o usuário vê apenas os próprios
  instrumentos de convocação, comparecimentos, comprovantes e dias ganhos.
- O `.env` atual mantém o Keycloak comentado (modo desenvolvimento ativo).

Lacunas atuais:

1. Qualquer CPF válido entra no sistema (modo dev) e, no modo Keycloak, qualquer
   usuário autenticado no realm acessa tudo — **não há autorização (RBAC)**.
2. As informações do usuário (nome, e-mail) obtidas do token não são exibidas.
3. O botão "Sair" não encerra a sessão SSO no Keycloak.
4. Não existe visão administrativa para servidores do TRE consultarem registros.

## 2. Objetivo

Implementar controle de acesso por papéis (RBAC) usando o Keycloak já existente,
com login **CPF (username) + senha** na página do Keycloak, recuperação de senha
por e-mail e dois papéis:

- **`convocado`** (eleitor): fluxo unificado atual, somente seus dados.
- **`admin`** (servidor TRE): painel administrativo **somente consulta** por CPF.

Decisões confirmadas com o usuário:

- **Abordagem de login:** fluxo OIDC padrão (página de login hospedada no
  Keycloak, tematizável), via `streamlit-keycloak` — a senha nunca passa pelo app.
- **Servidor Keycloak:** já existe (institucional). Nada de docker-compose para
  Keycloak; apenas configuração de realm/client documentada.
- **Papéis:** 2 (`convocado`, `admin`), com views separadas; usuário com as duas
  roles escolhe a visão pela barra lateral.
- **Sem a role exigida:** acesso negado com mensagem e botão de sair.
- **CPF no Keycloak:** campo `username` do usuário é o CPF (11 dígitos); o app lê
  `preferred_username` (com fallback para claim `cpf`).
- **Painel admin:** somente leitura (consulta por CPF).
- **Mensagem de credencial inválida:** "Usuário ou senha não encontrados" —
  configurada no realm (localization), não no código do app.
- **Recuperação de senha por e-mail:** fluxo nativo do Keycloak ("Esqueceu a
  senha?"), habilitado por configuração de realm (Forgot Password + SMTP) — sem
  código no app.

## 3. Abordagem escolhida

**Abordagem 1 — Gating por roles no app atual (single-page).** Após o login OIDC,
o payload do `access_token` é decodificado para extrair as roles; o resultado fica
no `session_state` e o `app.py` roteia a visão conforme o papel.

Alternativas descartadas:

- **2 (multi-page nativo do Streamlit com `pages/`):** Streamlit não tem permissão
  por página; cada página precisaria do mesmo guard, e o estado de sessão teria de
  ser reestruturado. Custo alto, benefício cosmético.
- **3 (backend resource server — FastAPI validando JWT por request):** enforcement
  real na camada de dados, mas muda a arquitetura inteira (hoje o Streamlit fala
  direto com o Mongo). Overkill para o estágio atual; fica como evolução futura.

### Limitação conhecida (fronteira de segurança)

O enforcement de roles é **UI-level**, coerente com a arquitetura atual (app
monolítico Streamlit ↔ MongoDB direto). O payload do JWT é decodificado **sem
verificação de assinatura** — aceitável aqui porque o token chega diretamente do
Keycloak via TLS pelo componente `keycloak-js`, e todo acesso a dados continua
escopado pelo CPF vindo do token. Um usuário malicioso com conhecimento do
componente poderia forjar roles no cliente; mitigar isso exigiria a abordagem 3
(resource server) e está fora do escopo.

## 4. Arquitetura

### 4.1 Novo módulo puro: `services/authorization_service.py`

Sem dependência de Streamlit (testável com pytest puro, estilo dos serviços atuais):

```python
class Acesso(str, Enum):
    ADMIN = "admin"
    CONVOCADO = "convocado"
    AMBOS = "ambos"
    NEGADO = "negado"

@dataclass(frozen=True)
class Usuario:
    cpf: str            # 11 dígitos
    nome: str | None
    email: str | None
    roles: frozenset[str]

    def is_admin(self, role_admin: str = settings.KEYCLOAK_ROLE_ADMIN) -> bool: ...
    def is_convocado(self, role_convocado: str = settings.KEYCLOAK_ROLE_CONVOCADO) -> bool: ...

def parse_roles(raw: str | None) -> frozenset[str]:
    """Converte 'admin,convocado' (DEV_ROLES) em conjunto normalizado."""

def extrair_roles(access_token: str | None, client_id: str) -> frozenset[str]:
    """Decodifica o payload (base64url, sem verificação) do access_token e
    retorna a união de realm_access.roles + resource_access[client_id].roles.
    Token ausente/inválido -> conjunto vazio (nunca lança exceção)."""

def construir_usuario(user_info: dict | None, access_token: str | None,
                      client_id: str) -> Usuario | None:
    """Monta o Usuario a partir do token/user_info: CPF de 'cpf' ou
    'preferred_username' (validado), nome ('name' ou given+family), 'email'
    e roles. Retorna None se não houver CPF válido."""

def decidir_acesso(roles: frozenset[str],
                   role_admin: str = settings.KEYCLOAK_ROLE_ADMIN,
                   role_convocado: str = settings.KEYCLOAK_ROLE_CONVOCADO) -> Acesso:
    """ADMIN se tem só a role admin; CONVOCADO se só a role convocado;
    AMBOS se as duas; NEGADO caso contrário (roles desconhecidas são ignoradas)."""
```

Os nomes esperados das roles vêm de `settings.KEYCLOAK_ROLE_ADMIN` /
`settings.KEYCLOAK_ROLE_CONVOCADO`, usados como **defaults dos parâmetros** das
funções (`decidir_acesso`, `Usuario.is_admin/is_convocado`); os testes chamam com
literais explícitos, mantendo a lógica pura e desacoplada.

### 4.2 `components/auth.py` (alterações)

**Fluxo Keycloak (`_login_keycloak`)** — após `keycloak.authenticated`:

1. `usuario = construir_usuario(keycloak.user_info, keycloak.access_token, settings.KEYCLOAK_CLIENT_ID)`
2. Se `usuario` é None (token sem CPF válido): mantém o fallback atual —
   formulário "Confirme seu CPF"; nesse caso as roles ainda são extraídas do
   token e o restante dos dados (nome/e-mail) também.
3. `_persistir_sessao(usuario)` grava no `session_state`:
   - `autenticado` (bool), `cpf_usuario`, `cpf_usuario_fmt` (já existem)
   - **novos:** `roles_usuario` (list), `nome_usuario`, `email_usuario`,
     `kc_id_token` (para o link de logout)
4. `st.rerun()`.

**Fluxo desenvolvimento (`_login_cpf_direto`)** — mantém o formulário de CPF;
as roles vêm de `settings.DEV_ROLES` (parse_roles). Sem `DEV_ROLES`, default
`convocado` (comportamento atual preservado).

**Nova função `render_acesso_negado()`** — card centralizado no padrão visual do
login (mesmas cores/estilo do cabeçalho TRE-PE):

- Mensagem: "🚫 Acesso negado — sua conta não possui permissão para usar este
  sistema. Contate o administrador."
- Exibe as roles encontradas (se houver) para facilitar o diagnóstico.
- Botão "Sair" (limpa sessão) + link para encerrar a sessão no Keycloak.

**Logout** — o botão "Sair" (sidebar) passa a:

1. Limpar as chaves de sessão (existente).
2. Exibir link "Encerrar sessão no Keycloak" apontando para
   `{KEYCLOAK_URL}/realms/{realm}/protocol/openid-connect/logout?id_token_hint={kc_id_token}&client_id={client_id}`
   (abre em nova aba; Keycloak mostra a confirmação de logout). Sem
   `post_logout_redirect_uri` para não exigir configuração extra no client —
   documentado como opcional.

### 4.3 `app.py` (gate + roteamento)

```text
não autenticado                -> render_login_page(); st.stop()
autenticado, decidir_acesso == NEGADO -> render_acesso_negado(); st.stop()
AMBOS   -> seletor na sidebar ("🗳️ Convocado" | "🛡️ Administrativo") decide a visão
ADMIN   -> render_painel_admin()
CONVOCADO -> render_fluxo_unificado() (inalterado)
```

A sidebar exibe o bloco do usuário: **nome**, CPF formatado, **e-mail** e badge do
papel (🛡️ Admin / 🗳️ Convocado). O toggle "Modo Mock", "Limpar Sessão" e o bloco
"Sobre" permanecem apenas na visão do convocado.

### 4.4 Novo componente: `components/painel_admin.py`

`render_painel_admin()` — somente consulta:

1. **Busca por CPF:** `st.text_input` com máscara progressiva e validação de
   dígitos (reutilizar `_cpf_valido`/`_mascara_cpf_parcial` de `components/auth.py`,
   movendo-os para `utils/cpf.py` e importando nos dois lugares — evita duplicação,
   já que o mesmo algoritmo existe também em `services/extraction_service.py`,
   que permanece intocado).
2. **Resultados para o CPF consultado** (via `database/db.py` existente):
   - Instrumentos de convocação + comparecimentos: `buscar_registros_cpf(cpf)`
     renderizados pela mesma função da visão do convocado (refatorada, ver 4.5).
   - Comprovantes + dias ganhos: `comprovantes_registrados(cpf=..., incluir_sessao=False)`
     alimentando `render_painel_dias_ganhos(...)`.
3. **Tratamento de erros:** CPF inválido → erro inline; banco indisponível →
   `st.warning` (padrão existente); nenhum registro → `st.info`.

### 4.5 Refatorações (compatíveis)

- `components/results.py` → `render_registros_usuario(cpf: str | None = None, cpf_fmt: str | None = None)`:
  parâmetros opcionais; sem argumentos, lê do `session_state` (comportamento atual).
- `components/comprovantes.py` → `comprovantes_registrados(cpf: str | None = None, incluir_sessao: bool = True)`:
  idem; admin chama com CPF explícito e `incluir_sessao=False` (vê apenas dados
  persistidos, nunca rascunhos de sessão de terceiros — que nem existem no contexto).
- Novo `utils/cpf.py` com `cpf_valido`, `formatar_cpf`, `mascara_cpf_parcial`
  (extraídos de `components/auth.py`, que passa a importá-los).

### 4.6 `config/settings.py` + `.env.example`

Novas configurações:

```dotenv
# Nomes das roles no Keycloak (realm ou client roles)
KEYCLOAK_ROLE_ADMIN=admin
KEYCLOAK_ROLE_CONVOCADO=convocado
# Modo desenvolvimento (sem KEYCLOAK_URL): roles simuladas no login por CPF
DEV_ROLES=convocado
```

## 5. Fluxo de dados (login → visão)

```text
1. Usuário clica em entrar -> keycloak-js redireciona para a página do Keycloak
2. Keycloak: CPF (username) + senha
   - inválidos -> mensagem do realm "Usuário ou senha não encontrados"
   - "Esqueceu a senha?" -> e-mail de redefinição (SMTP do realm)
3. Sucesso -> redirect de volta; componente retorna Keycloak(authenticated=True,
   access_token, id_token, user_info)
4. App decodifica access_token -> roles; user_info -> cpf/nome/email
5. session_state: autenticado, cpf_usuario(_fmt), roles_usuario, nome_usuario,
   email_usuario, kc_id_token
6. Gate decide: NEGADO -> tela de acesso negado | ADMIN/CONVOCADO/AMBOS -> view
7. Consultas ao Mongo continuam escopadas pelo CPF (convocado) ou pelo CPF
   digitado na busca (admin)
```

## 6. Configuração necessária no servidor Keycloak (documentar no README)

Sem código — pré-requisitos de infraestrutura:

1. **Client** (ex.: `convocacoes-app`): público, Authorization Code Flow (Standard
   Flow habilitado), *Valid redirect URIs* e *Web origins* apontando para o host do
   app (ex.: `https://app.tre-pe.jus.br/*`; local: `http://localhost:8501/*`).
2. **Usuários:** `username` = CPF (11 dígitos), com `email` preenchido (necessário
   para a recuperação de senha) e nome completo.
3. **Roles:** criar `convocado` e `admin` (recomendado: client roles do
   `convocacoes-app`; o código também aceita realm roles) e atribuir aos usuários.
   Usuário sem nenhuma das duas → tela de acesso negado.
4. **Recuperação de senha:** Realm → *Authentication* → habilitar fluxo *Reset
   credentials* ("Forgot password"); Realm → *Email* → configurar SMTP. O link
   "Esqueceu a senha?" aparece automaticamente na página de login.
5. **Mensagem de erro pt-BR:** Realm → *Localization* → pt-BR → sobrescrever
   `invalidUsernameOrPasswordMessage` com "Usuário ou senha não encontrados".
6. **Opcional:** tema personalizado com a identidade TRE-PE; *post logout redirect
   URIs* se desejar retorno ao app após o logout.

## 7. Tratamento de erros

| Cenário | Comportamento |
|---|---|
| Credenciais inválidas | Mensagem do realm na página do Keycloak (config 6.5) |
| Token sem CPF válido | Formulário "Confirme seu CPF" (fallback já existente) |
| `access_token` ausente/malformado | `extrair_roles` retorna vazio → acesso negado (nunca quebra) |
| Autenticado sem role `convocado`/`admin` | `render_acesso_negado()` + `st.stop()` |
| Servidor Keycloak indisponível | Componente exibe erro; app permanece na tela de login |
| Mongo indisponível no painel admin | `st.warning` (padrão já usado na visão do convocado) |
| CPF de busca inválido (admin) | Erro inline no formulário |

## 8. Testes (pytest, lógica pura — padrão existente)

`tests/test_authorization_service.py`:

- `extrair_roles`: JWT sintético (header/payload base64url, sem assinatura) com
  realm roles, client roles, ambas (união), nenhuma; token malformado/vazio → `frozenset()`.
- `decidir_acesso`: 4 ramos (ADMIN, CONVOCADO, AMBOS, NEGADO) + roles
  desconhecidas ignoradas (ex.: `{"default-roles-x", "offline_access"}` → NEGADO).
- `construir_usuario`: CPF vindo de `preferred_username` e de claim `cpf`;
  CPF inválido → None; nome composto `given_name`+`family_name`; e-mail ausente.
- `parse_roles`: string com espaços/vazia/None.

`tests/test_cpf_utils.py` (novo): comportamento de `cpf_valido`, `formatar_cpf` e
`mascara_cpf_parcial` após a mudança para `utils/cpf.py` (mesmos casos já
cobertos implicitamente; garante que a extração não quebrou nada).

Testes existentes (`pytest -v`) devem continuar verdes — as refatorações são
compatíveis (parâmetros opcionais).

## 9. Arquivos afetados

| Arquivo | Ação |
|---|---|
| `services/authorization_service.py` | **novo** — lógica pura de roles/usuário |
| `utils/cpf.py` | **novo** — validação/formatação/máscara de CPF |
| `components/painel_admin.py` | **novo** — painel de consulta por CPF |
| `components/auth.py` | alterar — extração de roles/user_info, acesso negado, logout |
| `components/results.py` | alterar — `render_registros_usuario(cpf=None, ...)` |
| `components/comprovantes.py` | alterar — `comprovantes_registrados(cpf=None, incluir_sessao=True)` |
| `app.py` | alterar — gate por roles + roteamento de visão + sidebar |
| `config/settings.py` | alterar — `KEYCLOAK_ROLE_*`, `DEV_ROLES` |
| `.env.example` | alterar — novas variáveis |
| `README.md` | alterar — seção Keycloak (roles, SMTP, localization, client) |
| `tests/test_authorization_service.py` | **novo** |
| `tests/test_cpf_utils.py` | **novo** |

## 10. Critérios de sucesso

1. Login com CPF + senha via Keycloak; credencial inválida exibe "Usuário ou senha
   não encontrados" (mensagem do realm).
2. "Esqueceu a senha?" envia e-mail de redefinição (configuração de realm).
3. Role `convocado` → fluxo unificado atual, inalterado e escopado ao próprio CPF.
4. Role `admin` → painel de consulta por CPF (instrumentos, comparecimentos,
   dias ganhos, comprovantes), somente leitura.
5. Autenticado sem roles → tela de acesso negado, sem vazar conteúdo do sistema.
6. Sidebar exibe nome, CPF, e-mail e papel do usuário; "Sair" encerra a sessão
   local e oferece encerramento no Keycloak.
7. Modo desenvolvimento (sem `KEYCLOAK_URL`) continua funcionando, com roles
   simuladas via `DEV_ROLES`.
8. `pytest -v` verde (novos testes + existentes).
