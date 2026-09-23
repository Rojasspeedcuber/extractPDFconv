# Controle de Acesso Keycloak (OIDC + RBAC) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar controle de acesso por papéis (RBAC) ao login Keycloak existente: roles `convocado` (fluxo atual) e `admin` (painel de consulta somente leitura), com negação de acesso sem role, dados do usuário na sidebar, logout com fim de SSO e modo dev com roles simuladas.

**Architecture:** Módulo puro `services/authorization_service.py` decodifica o payload do `access_token` (JWT) e extrai roles (união de `realm_access` + `resource_access[client_id]`); `components/auth.py` persiste roles/nome/e-mail na sessão; `app.py` roteia a visão conforme `decidir_acesso()`; novo `components/painel_admin.py` reutiliza os renderizadores existentes refatorados para aceitar CPF explícito. Spec: `docs/superpowers/specs/2026-09-23-keycloak-rbac-design.md`.

**Tech Stack:** Python 3.12, Streamlit 1.64, streamlit-keycloak 1.1.1, pytest, MongoDB (pymongo). Sem novas dependências.

**Convenções do repositório:**
- Testes: lógica pura, sem runtime do Streamlit (padrão de `tests/test_fluxo_unificado.py`).
- Commits: mensagem em português, minúsculas, sem acentos, prefixo `feat:`/`refactor:`/`docs:`/`test:`.
- Comandos de teste usam o venv do projeto: `.\venv\Scripts\python.exe -m pytest ...` (PowerShell, na raiz do repo).

---

### Task 1: Extrair utilitários de CPF para `utils/cpf.py`

Hoje as funções de CPF vivem em `components/auth.py` (`_cpf_digitos_validos`, `_cpf_valido`, `_formatar_cpf`, `_mascara_cpf_parcial`) e serão reutilizadas pelo painel admin. Movê-las para `utils/cpf.py` (públicas, sem underscore). `services/extraction_service.py` tem algoritmo semelhante mas **permanece intocado**.

**Files:**
- Create: `utils/cpf.py`
- Create: `tests/test_cpf_utils.py`
- Modify: `components/auth.py` (remover as 4 funções privadas e importar de `utils.cpf`)

- [ ] **Step 1: Escrever o teste falho**

Criar `tests/test_cpf_utils.py`:

```python
"""Testes dos utilitários de CPF (utils/cpf.py)."""
from utils.cpf import cpf_digitos_validos, cpf_valido, formatar_cpf, mascara_cpf_parcial

CPF_VALIDO = "52998224725"
CPF_VALIDO_2 = "11144477735"
CPF_DIGITO_INVALIDO = "12345678900"


def test_cpf_valido_com_e_sem_mascara():
    assert cpf_valido(CPF_VALIDO) == CPF_VALIDO
    assert cpf_valido("529.982.247-25") == CPF_VALIDO
    assert cpf_valido(CPF_VALIDO_2) == CPF_VALIDO_2


def test_cpf_invalido_retorna_none():
    assert cpf_valido(CPF_DIGITO_INVALIDO) is None
    assert cpf_valido("11111111111") is None  # dígitos repetidos
    assert cpf_valido("123456") is None       # curto demais
    assert cpf_valido("") is None
    assert cpf_valido(None) is None


def test_cpf_digitos_validos():
    assert cpf_digitos_validos(CPF_VALIDO) is True
    assert cpf_digitos_validos(CPF_DIGITO_INVALIDO) is False


def test_formatar_cpf():
    assert formatar_cpf(CPF_VALIDO) == "529.982.247-25"
    assert formatar_cpf("123") == "123"  # não formata quando não tem 11 dígitos


def test_mascara_cpf_parcial():
    assert mascara_cpf_parcial("529") == "529"
    assert mascara_cpf_parcial("529982") == "529.982"
    assert mascara_cpf_parcial("529982247") == "529.982.247"
    assert mascara_cpf_parcial("52998224725") == "529.982.247-25"
    assert mascara_cpf_parcial("529.982.247-25") == "529.982.247-25"
    assert mascara_cpf_parcial("") == ""
```

- [ ] **Step 2: Rodar o teste e verificar que falha**

Run: `.\venv\Scripts\python.exe -m pytest tests/test_cpf_utils.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'utils.cpf'` (ou ImportError).

- [ ] **Step 3: Criar `utils/cpf.py`**

```python
"""Utilitários de validação, formatação e máscara de CPF."""
from __future__ import annotations

import re


def cpf_digitos_validos(cpf: str) -> bool:
    """Valida um CPF (11 dígitos) pelos dígitos verificadores oficiais.

    Mesmo algoritmo utilizado em ``services/extraction_service.py``.
    """
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for i in range(9, 11):
        soma = sum(int(cpf[num]) * ((i + 1) - num) for num in range(0, i))
        digito = ((soma * 10) % 11) % 10
        if digito != int(cpf[i]):
            return False
    return True


def cpf_valido(cpf_raw: str | None) -> str | None:
    """Retorna os 11 dígitos do CPF se for válido; caso contrário, None.

    Args:
        cpf_raw: CPF em qualquer formato (ex.: '123.456.789-00').

    Returns:
        str | None: CPF com apenas dígitos (11 posições) e válido, ou None.
    """
    if not cpf_raw:
        return None
    digitos = re.sub(r"\D", "", str(cpf_raw))
    if len(digitos) != 11:
        return None
    if not cpf_digitos_validos(digitos):
        return None
    return digitos


def formatar_cpf(cpf_digitos: str) -> str:
    """Formata 11 dígitos como 000.000.000-00."""
    d = re.sub(r"\D", "", cpf_digitos or "")
    if len(d) != 11:
        return cpf_digitos
    return f"{d[0:3]}.{d[3:6]}.{d[6:9]}-{d[9:11]}"


def mascara_cpf_parcial(valor: str) -> str:
    """Aplica máscara progressiva de CPF (000.000.000-00) durante a digitação."""
    d = re.sub(r"\D", "", valor or "")[:11]
    if len(d) <= 3:
        return d
    if len(d) <= 6:
        return f"{d[0:3]}.{d[3:]}"
    if len(d) <= 9:
        return f"{d[0:3]}.{d[3:6]}.{d[6:]}"
    return f"{d[0:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
```

- [ ] **Step 4: Rodar o teste e verificar que passa**

Run: `.\venv\Scripts\python.exe -m pytest tests/test_cpf_utils.py -v`
Expected: 6 testes PASS.

- [ ] **Step 5: Rewire de `components/auth.py`**

Em `components/auth.py`:

1. **Remover** as 4 funções: `_cpf_digitos_validos`, `_cpf_valido`, `_formatar_cpf`, `_mascara_cpf_parcial` (linhas ~32-86, bloco "Validação de CPF" inteiro) e o `import re` do topo.
2. **Adicionar** o import (junto aos imports existentes, após `from config.settings import settings`):

```python
from utils.cpf import cpf_valido, formatar_cpf, mascara_cpf_parcial
```

3. **Trocar os call sites** (renomear sem underscore):
   - `_persistir_sessao`: `st.session_state["cpf_usuario_fmt"] = _formatar_cpf(cpf_digitos)` → `formatar_cpf(cpf_digitos)`
   - `_render_form_cpf`: `mascarado = _mascara_cpf_parcial(cpf_input)` → `mascara_cpf_parcial(cpf_input)`; `cpf_digitos = _cpf_valido(cpf_input)` → `cpf_valido(cpf_input)`
   - `_login_keycloak`: `cpf_digitos = _cpf_valido(cpf_token)` → esta linha será substituída na Task 4; por ora apenas renomeie para `cpf_valido(cpf_token)`.

- [ ] **Step 6: Verificar que nada quebrou**

Run: `.\venv\Scripts\python.exe -m pytest -v`
Expected: todos os testes existentes PASS (incluindo os novos de CPF).

Run: `.\venv\Scripts\python.exe -m py_compile components/auth.py utils/cpf.py`
Expected: sem saída (sucesso).

- [ ] **Step 7: Commit**

```powershell
git add utils/cpf.py tests/test_cpf_utils.py components/auth.py
git commit -m "refactor: extrair validacao e formatacao de cpf para utils/cpf.py"
```

---

### Task 2: Configurações de RBAC (`config/settings.py` + `.env.example`)

**Files:**
- Modify: `config/settings.py` (após o bloco Keycloak, ~linha 46)
- Modify: `.env.example` (após o bloco Keycloak, ~linha 22)

- [ ] **Step 1: Adicionar em `config/settings.py`** (dentro da classe `Settings`, logo após `KEYCLOAK_CLIENT_ID`):

```python
    # --- RBAC (controle de acesso por papéis) ---
    # Nomes das roles esperadas no token do Keycloak (realm roles ou client roles).
    KEYCLOAK_ROLE_ADMIN: str = os.getenv("KEYCLOAK_ROLE_ADMIN", "admin")
    KEYCLOAK_ROLE_CONVOCADO: str = os.getenv("KEYCLOAK_ROLE_CONVOCADO", "convocado")

    # Modo desenvolvimento (quando KEYCLOAK_URL está vazio): roles simuladas no
    # login por CPF, separadas por vírgula (ex.: "admin,convocado").
    DEV_ROLES: str = os.getenv("DEV_ROLES", "convocado")
```

- [ ] **Step 2: Adicionar em `.env.example`** (após `KEYCLOAK_CLIENT_ID=convocacoes-app`):

```dotenv

# --- RBAC (controle de acesso por papéis) ---
# Nomes das roles no Keycloak (realm roles ou client roles do client acima)
KEYCLOAK_ROLE_ADMIN=admin
KEYCLOAK_ROLE_CONVOCADO=convocado

# Modo desenvolvimento (com KEYCLOAK_URL vazio): roles simuladas no login por CPF.
# Ex.: DEV_ROLES=admin,convocado para testar o painel administrativo.
DEV_ROLES=convocado
```

- [ ] **Step 3: Verificar carregamento**

Run: `.\venv\Scripts\python.exe -c "from config.settings import settings; print(settings.KEYCLOAK_ROLE_ADMIN, settings.KEYCLOAK_ROLE_CONVOCADO, settings.DEV_ROLES)"`
Expected: `admin convocado convocado` (ou os valores do `.env` local, se definidos).

Run: `.\venv\Scripts\python.exe -m pytest -v`
Expected: todos PASS.

- [ ] **Step 4: Commit**

```powershell
git add config/settings.py .env.example
git commit -m "feat: configuracoes de rbac (roles do keycloak e dev_roles)"
```

---

### Task 3: Serviço de autorização (`services/authorization_service.py`)

Módulo **puro** (sem Streamlit): enum `Acesso`, dataclass `Usuario`, extração de roles do JWT, construção do usuário a partir do token/user_info e decisão de acesso.

**Files:**
- Create: `services/authorization_service.py`
- Create: `tests/test_authorization_service.py`

- [ ] **Step 1: Escrever os testes falhos**

Criar `tests/test_authorization_service.py`:

```python
"""Testes do serviço de autorização (RBAC) — lógica pura."""
import base64
import json

from services.authorization_service import (
    Acesso,
    Usuario,
    construir_usuario,
    decidir_acesso,
    extrair_roles,
    nome_de_user_info,
    parse_roles,
)

CLIENT_ID = "convocacoes-app"
CPF_VALIDO = "52998224725"


def _jwt(payload: dict) -> str:
    """Monta um JWT falso (header.payload.assinatura) com o payload informado."""
    def _b64(dados: dict) -> str:
        bruto = json.dumps(dados).encode("utf-8")
        return base64.urlsafe_b64encode(bruto).decode("ascii").rstrip("=")

    return f"{_b64({'alg': 'none'})}.{_b64(payload)}.assinatura-falsa"


# ---------------------------------------------------------------- extrair_roles

def test_extrai_roles_do_realm():
    token = _jwt({"realm_access": {"roles": ["convocado", "offline_access"]}})
    assert extrair_roles(token, CLIENT_ID) == frozenset({"convocado", "offline_access"})


def test_extrai_roles_do_client():
    token = _jwt({"resource_access": {CLIENT_ID: {"roles": ["admin"]}}})
    assert extrair_roles(token, CLIENT_ID) == frozenset({"admin"})


def test_combina_roles_de_realm_e_client():
    token = _jwt({
        "realm_access": {"roles": ["convocado"]},
        "resource_access": {CLIENT_ID: {"roles": ["admin"]}},
    })
    assert extrair_roles(token, CLIENT_ID) == frozenset({"convocado", "admin"})


def test_ignora_roles_de_outro_client():
    token = _jwt({"resource_access": {"outro-client": {"roles": ["admin"]}}})
    assert extrair_roles(token, CLIENT_ID) == frozenset()


def test_token_ausente_ou_vazio_retorna_conjunto_vazio():
    assert extrair_roles(None, CLIENT_ID) == frozenset()
    assert extrair_roles("", CLIENT_ID) == frozenset()


def test_token_malformado_nao_quebra():
    assert extrair_roles("isso-nao-e-um-jwt", CLIENT_ID) == frozenset()
    assert extrair_roles("a.b", CLIENT_ID) == frozenset()
    token_payload_nao_json = "eyJhbGciOiJub25lIn0." + base64.urlsafe_b64encode(
        b"ola"
    ).decode("ascii").rstrip("=") + ".x"
    assert extrair_roles(token_payload_nao_json, CLIENT_ID) == frozenset()


def test_estrutura_inesperada_nao_quebra():
    token = _jwt({"realm_access": " nao-e-dict", "resource_access": [1, 2]})
    assert extrair_roles(token, CLIENT_ID) == frozenset()


# --------------------------------------------------------------- decidir_acesso

def test_decidir_acesso_somente_admin():
    assert decidir_acesso(
        frozenset({"admin"}), role_admin="admin", role_convocado="convocado"
    ) == Acesso.ADMIN


def test_decidir_acesso_somente_convocado():
    assert decidir_acesso(
        frozenset({"convocado"}), role_admin="admin", role_convocado="convocado"
    ) == Acesso.CONVOCADO


def test_decidir_acesso_ambas_roles():
    assert decidir_acesso(
        frozenset({"admin", "convocado"}), role_admin="admin", role_convocado="convocado"
    ) == Acesso.AMBOS


def test_decidir_acesso_sem_roles_negado():
    assert decidir_acesso(
        frozenset(), role_admin="admin", role_convocado="convocado"
    ) == Acesso.NEGADO


def test_decidir_acesso_roles_desconhecidas_negado():
    assert decidir_acesso(
        frozenset({"default-roles-tre", "offline_access"}),
        role_admin="admin",
        role_convocado="convocado",
    ) == Acesso.NEGADO


def test_decidir_acesso_respeita_nomes_customizados():
    assert decidir_acesso(
        frozenset({"app_admin"}), role_admin="app_admin", role_convocado="app_user"
    ) == Acesso.ADMIN


# ------------------------------------------------------------------ parse_roles

def test_parse_roles_separa_por_virgula():
    assert parse_roles("admin,convocado") == frozenset({"admin", "convocado"})


def test_parse_roles_remove_espacos():
    assert parse_roles(" admin , convocado ") == frozenset({"admin", "convocado"})


def test_parse_roles_vazio_ou_none():
    assert parse_roles("") == frozenset()
    assert parse_roles(None) == frozenset()
    assert parse_roles(",,,") == frozenset()


# ------------------------------------------------------------- construir_usuario

def test_usuario_a_partir_de_preferred_username():
    token = _jwt({"realm_access": {"roles": ["convocado"]}})
    usuario = construir_usuario(
        {"preferred_username": CPF_VALIDO, "name": "Maria Silva", "email": "m@tre.jus.br"},
        token,
        CLIENT_ID,
    )
    assert usuario == Usuario(
        cpf=CPF_VALIDO,
        nome="Maria Silva",
        email="m@tre.jus.br",
        roles=frozenset({"convocado"}),
    )


def test_claim_cpf_tem_precedencia_sobre_username():
    usuario = construir_usuario(
        {"cpf": CPF_VALIDO, "preferred_username": "maria.silva"}, None, CLIENT_ID
    )
    assert usuario is not None
    assert usuario.cpf == CPF_VALIDO
    assert usuario.roles == frozenset()


def test_usuario_sem_nome_ou_email():
    usuario = construir_usuario({"preferred_username": CPF_VALIDO}, None, CLIENT_ID)
    assert usuario is not None
    assert usuario.nome is None
    assert usuario.email is None


def test_cpf_invalido_ou_ausente_retorna_none():
    assert construir_usuario({"preferred_username": "12345678900"}, None, CLIENT_ID) is None
    assert construir_usuario({"preferred_username": "maria.silva"}, None, CLIENT_ID) is None
    assert construir_usuario(None, None, CLIENT_ID) is None
    assert construir_usuario({}, None, CLIENT_ID) is None


# ------------------------------------------------------------- nome_de_user_info

def test_nome_de_user_info():
    assert nome_de_user_info({"name": "Maria Silva"}) == "Maria Silva"
    assert nome_de_user_info({"given_name": "Maria", "family_name": "Silva"}) == "Maria Silva"
    assert nome_de_user_info({"given_name": "Maria"}) == "Maria"
    assert nome_de_user_info({}) is None
    assert nome_de_user_info(None) is None


# --------------------------------------------------------------------- Usuario

def test_usuario_is_admin_e_is_convocado():
    admin = Usuario(cpf=CPF_VALIDO, roles=frozenset({"admin"}))
    assert admin.is_admin(role_admin="admin") is True
    assert admin.is_convocado(role_convocado="convocado") is False

    ambos = Usuario(cpf=CPF_VALIDO, roles=frozenset({"admin", "convocado"}))
    assert ambos.is_admin(role_admin="admin") is True
    assert ambos.is_convocado(role_convocado="convocado") is True
```

- [ ] **Step 2: Rodar os testes e verificar que falham**

Run: `.\venv\Scripts\python.exe -m pytest tests/test_authorization_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.authorization_service'`.

- [ ] **Step 3: Criar `services/authorization_service.py`**

```python
"""Serviço de autorização: extração de roles e decisão de acesso (RBAC).

Módulo de lógica pura (sem Streamlit), testável com pytest.

As roles vêm do ``access_token`` (JWT) emitido pelo Keycloak: união de
``realm_access.roles`` com ``resource_access[client_id].roles`` (aceita tanto
realm roles quanto client roles). O payload é decodificado **sem verificação de
assinatura** — o token chega diretamente do Keycloak via TLS pelo componente
keycloak-js e o enforcement é UI-level, coerente com a arquitetura atual
(ver ``docs/superpowers/specs/2026-09-23-keycloak-rbac-design.md``).
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from config.settings import settings
from utils.cpf import cpf_valido

logger = logging.getLogger(__name__)


class Acesso(str, Enum):
    """Resultado da decisão de acesso baseada nas roles do usuário."""

    ADMIN = "admin"
    CONVOCADO = "convocado"
    AMBOS = "ambos"
    NEGADO = "negado"


@dataclass(frozen=True)
class Usuario:
    """Usuário autenticado (dados do token Keycloak)."""

    cpf: str
    nome: str | None = None
    email: str | None = None
    roles: frozenset[str] = field(default_factory=frozenset)

    def is_admin(self, role_admin: str = settings.KEYCLOAK_ROLE_ADMIN) -> bool:
        return role_admin in self.roles

    def is_convocado(
        self, role_convocado: str = settings.KEYCLOAK_ROLE_CONVOCADO
    ) -> bool:
        return role_convocado in self.roles


def parse_roles(raw: str | None) -> frozenset[str]:
    """Converte uma lista separada por vírgulas (ex.: DEV_ROLES) em conjunto.

    Remove espaços e itens vazios; preserva maiúsculas/minúsculas (nomes de
    roles no Keycloak são case-sensitive).
    """
    if not raw:
        return frozenset()
    return frozenset(p.strip() for p in raw.split(",") if p.strip())


def _decodificar_payload_jwt(token: str) -> dict[str, Any] | None:
    """Decodifica o payload (parte do meio) de um JWT, sem verificar assinatura.

    Returns:
        dict com o payload, ou None se o token for ausente/malformado.
    """
    try:
        partes = token.split(".")
        if len(partes) < 2:
            return None
        payload_b64 = partes[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)  # padding base64url
        conteudo = json.loads(base64.urlsafe_b64decode(payload_b64.encode("ascii")))
        return conteudo if isinstance(conteudo, dict) else None
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        logger.warning("Falha ao decodificar payload do token: %s", exc)
        return None


def extrair_roles(access_token: str | None, client_id: str) -> frozenset[str]:
    """Extrai as roles do access_token (realm + client), sem lançar exceção."""
    if not access_token:
        return frozenset()
    payload = _decodificar_payload_jwt(access_token)
    if payload is None:
        return frozenset()

    roles: set[str] = set()

    realm_access = payload.get("realm_access")
    if isinstance(realm_access, dict):
        roles.update(r for r in (realm_access.get("roles") or []) if isinstance(r, str))

    resource_access = payload.get("resource_access")
    if isinstance(resource_access, dict):
        do_client = resource_access.get(client_id)
        if isinstance(do_client, dict):
            roles.update(r for r in (do_client.get("roles") or []) if isinstance(r, str))

    return frozenset(roles)


def nome_de_user_info(info: dict | None) -> str | None:
    """Monta o nome de exibição a partir do UserInfo (``name`` ou given+family)."""
    info = info or {}
    nome = info.get("name")
    if nome:
        return str(nome)
    partes = [info.get("given_name"), info.get("family_name")]
    composto = " ".join(str(p) for p in partes if p)
    return composto or None


def construir_usuario(
    user_info: dict | None,
    access_token: str | None,
    client_id: str,
) -> Usuario | None:
    """Monta o ``Usuario`` a partir do UserInfo e do access_token do Keycloak.

    O CPF é lido das claims ``cpf`` → ``preferred_username`` → ``username``
    (a primeira com CPF válido vence). Roles vêm do access_token.

    Returns:
        Usuario, ou None quando não há CPF válido no token.
    """
    info = user_info or {}
    cpf_raw = info.get("cpf") or info.get("preferred_username") or info.get("username")
    cpf = cpf_valido(cpf_raw if isinstance(cpf_raw, str) else None)
    if not cpf:
        return None

    email = info.get("email")
    return Usuario(
        cpf=cpf,
        nome=nome_de_user_info(info),
        email=str(email) if email else None,
        roles=extrair_roles(access_token, client_id),
    )


def decidir_acesso(
    roles: frozenset[str],
    role_admin: str = settings.KEYCLOAK_ROLE_ADMIN,
    role_convocado: str = settings.KEYCLOAK_ROLE_CONVOCADO,
) -> Acesso:
    """Decide a visão do sistema a partir das roles do usuário.

    Roles desconhecidas (ex.: ``default-roles-*``, ``offline_access``) são
    ignoradas; sem nenhuma das duas roles esperadas o acesso é NEGADO.
    """
    tem_admin = role_admin in roles
    tem_convocado = role_convocado in roles
    if tem_admin and tem_convocado:
        return Acesso.AMBOS
    if tem_admin:
        return Acesso.ADMIN
    if tem_convocado:
        return Acesso.CONVOCADO
    return Acesso.NEGADO
```

- [ ] **Step 4: Rodar os testes e verificar que passam**

Run: `.\venv\Scripts\python.exe -m pytest tests/test_authorization_service.py -v`
Expected: ~24 testes PASS.

- [ ] **Step 5: Rodar a suíte completa**

Run: `.\venv\Scripts\python.exe -m pytest -v`
Expected: todos PASS.

- [ ] **Step 6: Commit**

```powershell
git add services/authorization_service.py tests/test_authorization_service.py
git commit -m "feat: servico de autorizacao com extracao de roles do token keycloak"
```

---

### Task 4: Integração do login (`components/auth.py`)

Reescrever `components/auth.py`: extrai roles/nome/e-mail do token, persiste na sessão, adiciona tela de **acesso negado**, aviso de logout SSO e helpers usados pelo `app.py`. Substituir o conteúdo do arquivo por:

**Files:**
- Modify: `components/auth.py` (reescrita completa)

- [ ] **Step 1: Novo conteúdo de `components/auth.py`**

```python
"""Componente de autenticação e acesso do Sistema de Convocações Eleitorais (TRE-PE).

Dois fluxos de login são suportados:

1. **Keycloak (produção):** quando ``settings.KEYCLOAK_URL`` está configurado,
   usa ``streamlit_keycloak.login()`` para autenticação OIDC — o usuário digita
   **CPF (username) + senha** na página do Keycloak, que também oferece a
   recuperação de senha por e-mail ("Esqueceu a senha?"). Após o login, o app
   extrai do token o CPF, o nome, o e-mail e as **roles** (RBAC).

2. **CPF direto (desenvolvimento):** quando o Keycloak não está configurado,
   aceita qualquer CPF válido (dígitos verificadores corretos); as roles vêm de
   ``settings.DEV_ROLES``.

Estado de sessão gravado:
    - ``st.session_state["autenticado"]``     -> bool
    - ``st.session_state["cpf_usuario"]``      -> str (11 dígitos, sem máscara)
    - ``st.session_state["cpf_usuario_fmt"]``  -> str (000.000.000-00)
    - ``st.session_state["roles_usuario"]``    -> list[str] (roles ordenadas)
    - ``st.session_state["nome_usuario"]``     -> str | None
    - ``st.session_state["email_usuario"]``    -> str | None
    - ``st.session_state["kc_id_token"]``      -> str | None (logout no Keycloak)
"""
from __future__ import annotations

import logging
from urllib.parse import urlencode

import streamlit as st

from config.settings import settings
from services.authorization_service import (
    Usuario,
    construir_usuario,
    extrair_roles,
    nome_de_user_info,
    parse_roles,
)
from utils.cpf import cpf_valido, formatar_cpf, mascara_cpf_parcial

logger = logging.getLogger(__name__)

# Cor institucional (azul escuro TRE-PE)
COR_PRIMARIA = "#1e3a8a"

# Chaves de sessão gravadas no login (removidas no logout)
_CHAVES_SESSAO_AUTH = (
    "autenticado",
    "cpf_usuario",
    "cpf_usuario_fmt",
    "roles_usuario",
    "nome_usuario",
    "email_usuario",
    "kc_id_token",
)


# ---------------------------------------------------------------------------
# Sessão de autenticação
# ---------------------------------------------------------------------------
def _persistir_sessao(
    cpf_digitos: str,
    roles: frozenset[str] = frozenset(),
    nome: str | None = None,
    email: str | None = None,
    id_token: str | None = None,
) -> None:
    """Grava os dados do usuário autenticado no session_state."""
    st.session_state["cpf_usuario"] = cpf_digitos
    st.session_state["cpf_usuario_fmt"] = formatar_cpf(cpf_digitos)
    st.session_state["autenticado"] = True
    st.session_state["roles_usuario"] = sorted(roles)
    st.session_state["nome_usuario"] = nome
    st.session_state["email_usuario"] = email
    if id_token:
        st.session_state["kc_id_token"] = id_token
    st.session_state.pop("_kc_id_token_logout", None)
    logger.info(
        "Usuário autenticado com CPF %s (roles: %s).",
        cpf_digitos,
        sorted(roles) or "—",
    )


def limpar_sessao_autenticacao() -> None:
    """Remove do session_state todas as chaves de autenticação."""
    for chave in _CHAVES_SESSAO_AUTH:
        st.session_state.pop(chave, None)


def usuario_autenticado() -> Usuario | None:
    """Reconstrói o ``Usuario`` a partir do session_state (ou None)."""
    cpf = st.session_state.get("cpf_usuario")
    if not st.session_state.get("autenticado") or not cpf:
        return None
    return Usuario(
        cpf=cpf,
        nome=st.session_state.get("nome_usuario"),
        email=st.session_state.get("email_usuario"),
        roles=frozenset(st.session_state.get("roles_usuario") or ()),
    )


def url_logout_keycloak(id_token: str | None = None) -> str | None:
    """Monta a URL de end-session do Keycloak (encerra também a sessão SSO).

    Returns:
        str | None: URL, ou None quando o Keycloak não está configurado.
    """
    if not settings.KEYCLOAK_URL:
        return None
    if id_token is None:
        id_token = st.session_state.get("kc_id_token")
    params = {"client_id": settings.KEYCLOAK_CLIENT_ID}
    if id_token:
        params["id_token_hint"] = id_token
    base = settings.KEYCLOAK_URL.rstrip("/")
    return (
        f"{base}/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/logout"
        f"?{urlencode(params)}"
    )


# ---------------------------------------------------------------------------
# Estilo / cabeçalho das telas
# ---------------------------------------------------------------------------
def _render_cabecalho_login(subtitulo_modo: str = "") -> None:
    """Renderiza o cabeçalho visual (ícone, título e subtítulo) do login."""
    st.markdown(
        f"""
        <div style="text-align:center; margin: 8px auto 4px auto;">
            <div style="font-size:3.2rem; line-height:1;">🗳️</div>
            <div style="font-size:1.6rem; font-weight:800; color:{COR_PRIMARIA};
                        margin-top:6px;">
                Sistema de Convocações Eleitorais
            </div>
            <div style="font-size:1.05rem; font-weight:600; color:#334155;
                        letter-spacing:0.08em; margin-top:2px;">
                TRE-PE
            </div>
            <div style="height:3px; width:120px; background:{COR_PRIMARIA};
                        border-radius:2px; margin:12px auto 0 auto; opacity:0.85;"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if subtitulo_modo:
        st.markdown(
            f"<div style='text-align:center; color:#64748b; font-size:0.85rem; "
            f"margin-top:8px;'>{subtitulo_modo}</div>",
            unsafe_allow_html=True,
        )


def _render_aviso_logout() -> None:
    """Após 'Sair', oferece o encerramento da sessão SSO no Keycloak."""
    id_token = st.session_state.get("_kc_id_token_logout")
    if not id_token:
        return
    url = url_logout_keycloak(id_token)
    if not url:
        st.session_state.pop("_kc_id_token_logout", None)
        return
    st.warning(
        "Você saiu do sistema. Para **trocar de usuário**, "
        f"[encerre também a sessão no Keycloak]({url}) — caso contrário, o login "
        "anterior pode ser retomado automaticamente (SSO)."
    )


# ---------------------------------------------------------------------------
# Formulário de CPF (compartilhado pelos dois fluxos)
# ---------------------------------------------------------------------------
def _render_form_cpf(titulo: str, ajuda: str = "", **dados_sessao) -> bool:
    """Renderiza o formulário de CPF e trata a submissão.

    Args:
        titulo: título exibido acima do campo.
        ajuda: texto de ajuda do campo CPF.
        **dados_sessao: repassados a ``_persistir_sessao`` (roles, nome, email,
            id_token).

    Returns:
        bool: True se o CPF foi validado e a sessão foi criada.
    """
    st.markdown(
        f"<div style='font-weight:600; color:{COR_PRIMARIA}; margin-bottom:4px;'>"
        f"{titulo}</div>",
        unsafe_allow_html=True,
    )

    with st.form("form_login_cpf", clear_on_submit=False):
        cpf_input = st.text_input(
            "CPF",
            value=st.session_state.get("_cpf_input_raw", ""),
            max_chars=14,
            placeholder="000.000.000-00",
            help=ajuda or "Informe seu CPF (apenas você tem acesso aos seus registros).",
            label_visibility="collapsed",
        )
        enviar = st.form_submit_button("Entrar", type="primary", use_container_width=True)

    # Aplica máscara em tempo real para exibição na próxima renderização
    mascarado = mascara_cpf_parcial(cpf_input)
    if mascarado != st.session_state.get("_cpf_input_raw"):
        st.session_state["_cpf_input_raw"] = mascarado

    if enviar:
        cpf_digitos = cpf_valido(cpf_input)
        if cpf_digitos is None:
            st.markdown(
                "<div style='color:#dc2626; font-weight:600; margin-top:8px;'>"
                "❌ CPF inválido. Verifique os números digitados e tente novamente."
                "</div>",
                unsafe_allow_html=True,
            )
            return False
        _persistir_sessao(cpf_digitos, **dados_sessao)
        st.rerun()

    return False


# ---------------------------------------------------------------------------
# Fluxos de login
# ---------------------------------------------------------------------------
def _login_keycloak() -> bool:
    """Fluxo de autenticação via Keycloak (OIDC).

    Após a autenticação, extrai do token: CPF, nome, e-mail e roles (RBAC).
    Se o token não trouxer um CPF válido, solicita a confirmação do CPF.
    """
    try:
        from streamlit_keycloak import login as keycloak_login
    except ImportError:
        st.error(
            "Dependência 'streamlit-keycloak' não instalada. "
            "Execute: pip install streamlit-keycloak"
        )
        logger.error("streamlit-keycloak não está instalado.")
        return False

    keycloak = keycloak_login(
        url=settings.KEYCLOAK_URL,
        realm=settings.KEYCLOAK_REALM,
        client_id=settings.KEYCLOAK_CLIENT_ID,
    )

    if not getattr(keycloak, "authenticated", False):
        st.info("🔐 Redirecionando para a autenticação segura (Keycloak)…")
        return False

    access_token = getattr(keycloak, "access_token", None)
    id_token = getattr(keycloak, "id_token", None)
    user_info = getattr(keycloak, "user_info", None) or {}

    usuario = construir_usuario(user_info, access_token, settings.KEYCLOAK_CLIENT_ID)
    if usuario is not None:
        _persistir_sessao(
            usuario.cpf,
            roles=usuario.roles,
            nome=usuario.nome,
            email=usuario.email,
            id_token=id_token,
        )
        st.rerun()
        return True

    # Token sem CPF válido: extrai roles/dados e pede a confirmação do CPF
    roles = extrair_roles(access_token, settings.KEYCLOAK_CLIENT_ID)
    st.success("✅ Autenticado com sucesso. Confirme seu CPF para continuar.")
    return _render_form_cpf(
        "Confirme seu CPF",
        roles=roles,
        nome=nome_de_user_info(user_info),
        email=user_info.get("email"),
        id_token=id_token,
    )


def _login_cpf_direto() -> bool:
    """Fluxo de login direto (desenvolvimento) baseado apenas no CPF.

    As roles do usuário vêm de ``settings.DEV_ROLES``.
    """
    st.markdown(
        "<div style='text-align:center; background:#fef9c3; border:1px solid #fde047; "
        "color:#854d0e; border-radius:8px; padding:6px 10px; font-size:0.8rem; "
        "margin-bottom:14px;'>⚠️ Modo de desenvolvimento – sem Keycloak</div>",
        unsafe_allow_html=True,
    )
    return _render_form_cpf(
        "Acesse com seu CPF",
        ajuda="Modo desenvolvimento: qualquer CPF válido é aceito.",
        roles=parse_roles(settings.DEV_ROLES),
    )


# ---------------------------------------------------------------------------
# Acesso negado (RBAC)
# ---------------------------------------------------------------------------
def render_acesso_negado() -> None:
    """Tela para usuários autenticados sem a role exigida (acesso negado)."""
    roles = st.session_state.get("roles_usuario") or []
    roles_txt = ", ".join(sorted(roles)) if roles else "nenhuma"

    _, col_centro, _ = st.columns([1, 1.4, 1])
    with col_centro:
        with st.container(border=True):
            _render_cabecalho_login()
            st.markdown(
                """
                <div style="text-align:center; margin-top:18px;">
                    <div style="font-size:2.4rem;">🚫</div>
                    <div style="font-weight:700; color:#b91c1c; font-size:1.15rem;
                                margin-top:6px;">
                        Acesso negado
                    </div>
                    <div style="color:#334155; margin-top:8px;">
                        Sua conta não possui permissão para usar este sistema.<br>
                        Contate o administrador.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.caption(f"Papéis encontrados na sua conta: **{roles_txt}**")

            col_btn, col_link = st.columns(2)
            with col_btn:
                if st.button("🚪 Sair", type="primary", use_container_width=True):
                    id_token = st.session_state.get("kc_id_token")
                    limpar_sessao_autenticacao()
                    if id_token:
                        st.session_state["_kc_id_token_logout"] = id_token
                    st.rerun()
            with col_link:
                url = url_logout_keycloak()
                if url:
                    st.markdown(
                        f"<div style='text-align:center; padding-top:8px;'>"
                        f"<a href='{url}' target='_blank' rel='noopener'>"
                        f"Encerrar sessão no Keycloak</a></div>",
                        unsafe_allow_html=True,
                    )

            st.markdown(
                "<div style='text-align:center; color:#94a3b8; font-size:0.72rem; "
                "margin-top:16px;'>Tribunal Regional Eleitoral de Pernambuco</div>",
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------
def render_login_page() -> bool:
    """Renderiza a página de login e retorna o estado de autenticação.

    Returns:
        bool: True se o usuário já está autenticado, False caso contrário.
    """
    if st.session_state.get("autenticado") and st.session_state.get("cpf_usuario"):
        return True

    usa_keycloak = bool(settings.KEYCLOAK_URL)

    # Layout centralizado (card com sombra)
    _, col_centro, _ = st.columns([1, 1.4, 1])
    with col_centro:
        with st.container(border=True):
            _render_cabecalho_login(
                subtitulo_modo="Autenticação segura via Keycloak" if usa_keycloak else ""
            )
            _render_aviso_logout()
            st.markdown("<div style='margin-top:14px;'></div>", unsafe_allow_html=True)

            if usa_keycloak:
                autenticado = _login_keycloak()
            else:
                autenticado = _login_cpf_direto()

            st.markdown(
                "<div style='text-align:center; color:#94a3b8; font-size:0.72rem; "
                "margin-top:16px;'>Tribunal Regional Eleitoral de Pernambuco</div>",
                unsafe_allow_html=True,
            )

    return bool(autenticado or st.session_state.get("autenticado"))
```

- [ ] **Step 2: Verificar sintaxe e imports**

Run: `.\venv\Scripts\python.exe -m py_compile components/auth.py`
Expected: sem saída (sucesso).

Run: `.\venv\Scripts\python.exe -c "import components.auth; print('ok')"`
Expected: `ok` (importar o módulo não executa UI; chamadas `st.*` só ocorrem dentro de funções).

- [ ] **Step 3: Rodar a suíte completa**

Run: `.\venv\Scripts\python.exe -m pytest -v`
Expected: todos PASS.

- [ ] **Step 4: Commit**

```powershell
git add components/auth.py
git commit -m "feat: login keycloak com roles, dados do usuario e logout sso"
```

---

### Task 5: Refatorar `render_registros_usuario` (CPF explícito)

**Files:**
- Modify: `components/results.py:269-283`

- [ ] **Step 1: Alterar a assinatura e o início da função**

Em `components/results.py`, substituir:

```python
def render_registros_usuario() -> None:
    """Renderiza a seção "📋 Seus Registros no Banco" para o CPF logado."""
    cpf = st.session_state.get("cpf_usuario")
    cpf_fmt = st.session_state.get("cpf_usuario_fmt")
    if not cpf:
        return

    st.divider()
    st.markdown("### 📋 Seus Registros no Banco")
```

por:

```python
def render_registros_usuario(
    cpf: str | None = None,
    cpf_fmt: str | None = None,
    titulo: str = "📋 Seus Registros no Banco",
) -> None:
    """Renderiza instrumentos + comparecimentos de um CPF.

    Sem argumentos, usa o CPF da sessão (visão do convocado). O painel
    administrativo passa o CPF consultado explicitamente.
    """
    cpf = cpf or st.session_state.get("cpf_usuario")
    cpf_fmt = cpf_fmt or st.session_state.get("cpf_usuario_fmt") or cpf
    if not cpf:
        return

    st.divider()
    st.markdown(f"### {titulo}")
```

O restante da função (badge de CPF, consulta ao banco, renderização) permanece **inalterado**.

- [ ] **Step 2: Verificar**

Run: `.\venv\Scripts\python.exe -m py_compile components/results.py`
Expected: sem saída.

Run: `.\venv\Scripts\python.exe -m pytest -v`
Expected: todos PASS (chamadas existentes sem argumentos seguem compatíveis).

- [ ] **Step 3: Commit**

```powershell
git add components/results.py
git commit -m "refactor: render_registros_usuario aceita cpf e titulo explicitos"
```

---

### Task 6: Refatorar `comprovantes_registrados` (CPF explícito)

**Files:**
- Modify: `components/comprovantes.py:40-72`

- [ ] **Step 1: Substituir a função**

Em `components/comprovantes.py`, substituir `comprovantes_registrados` por:

```python
def comprovantes_registrados(
    cpf: str | None = None,
    incluir_sessao: bool = True,
) -> dict[int, dict[str, Any]]:
    """Consolida os comprovantes registrados (banco de dados + sessão).

    Quando a integração com o banco está ativa, os registros persistidos têm
    precedência; os registros apenas em sessão são usados como complemento
    (ex.: banco indisponível ou persistência desativada).

    Args:
        cpf: CPF a consultar; sem argumento, usa o CPF da sessão. Um CPF
            **explícito** sempre consulta o banco (uso do painel admin),
            independentemente de ``PERSIST_TO_DB``.
        incluir_sessao: se False, ignora os comprovantes mantidos apenas em
            sessão (o painel admin consulta somente dados persistidos).
    """
    consolidado: dict[int, dict[str, Any]] = {}

    # 1. Registros apenas em sessão
    if incluir_sessao:
        consolidado.update(_comprovantes_da_sessao())

    # 2. Registros persistidos no banco (precedência)
    cpf_explicito = cpf is not None
    cpf = cpf or st.session_state.get("cpf_usuario")
    if cpf and (cpf_explicito or settings.PERSIST_TO_DB):
        try:
            from database.db import buscar_documentos_cpf

            for registro in buscar_documentos_cpf(cpf):
                consolidado[registro["tipo"]] = {
                    "nome_arquivo": registro.get("nome_arquivo"),
                    "codigo_verificador": registro.get("codigo_verificador"),
                    "codigo_crc": registro.get("codigo_crc"),
                    "url_conferencia": registro.get("url_conferencia"),
                    "dias_ganhos": registro.get("dias_ganhos", 0),
                    "persistido": True,
                }
        except ImportError:
            pass
        except Exception as exc:  # noqa: BLE001 - indisponibilidade do banco não quebra a UI
            st.caption(f"Não foi possível consultar os comprovantes no banco: {exc}")

    return consolidado
```

Callers existentes (`_render_resumo` em `fluxo_unificado.py` e `render_secao_comprovantes`) chamam sem argumentos — comportamento inalterado.

- [ ] **Step 2: Verificar**

Run: `.\venv\Scripts\python.exe -m py_compile components/comprovantes.py`
Expected: sem saída.

Run: `.\venv\Scripts\python.exe -m pytest -v`
Expected: todos PASS.

- [ ] **Step 3: Commit**

```powershell
git add components/comprovantes.py
git commit -m "refactor: comprovantes_registrados aceita cpf explicito e flag de sessao"
```

---

### Task 7: Painel administrativo (`components/painel_admin.py`)

**Files:**
- Create: `components/painel_admin.py`

- [ ] **Step 1: Criar o componente**

```python
"""Painel administrativo (role ``admin``): consulta de registros por CPF.

Visão **somente leitura** para servidores do TRE: a busca por CPF exibe os
instrumentos de convocação, os comparecimentos, os comprovantes armazenados e
os dias ganhos calculados. Reutiliza os renderizadores da visão do convocado,
passando o CPF consultado explicitamente.
"""
from __future__ import annotations

import logging

import streamlit as st

from components.comprovantes import comprovantes_registrados, render_painel_dias_ganhos
from components.results import render_registros_usuario
from utils.cpf import cpf_valido, formatar_cpf, mascara_cpf_parcial

logger = logging.getLogger(__name__)


def _render_busca_cpf() -> str | None:
    """Formulário de busca por CPF (com máscara progressiva).

    Returns:
        str | None: CPF (11 dígitos) em consulta, ou None se ainda não houve
        busca válida.
    """
    with st.form("form_busca_cpf_admin", clear_on_submit=False):
        cpf_input = st.text_input(
            "CPF do convocado",
            value=st.session_state.get("_cpf_busca_admin_raw", ""),
            max_chars=14,
            placeholder="000.000.000-00",
            help="Consulte instrumentos, comparecimentos, comprovantes e dias ganhos de qualquer CPF.",
        )
        buscar = st.form_submit_button("🔎 Consultar", type="primary", use_container_width=True)

    mascarado = mascara_cpf_parcial(cpf_input)
    if mascarado != st.session_state.get("_cpf_busca_admin_raw"):
        st.session_state["_cpf_busca_admin_raw"] = mascarado

    if buscar:
        digitos = cpf_valido(cpf_input)
        if digitos is None:
            st.error("❌ CPF inválido. Verifique os números digitados.")
            st.session_state.pop("_cpf_consultado_admin", None)
            return None
        st.session_state["_cpf_consultado_admin"] = digitos

    return st.session_state.get("_cpf_consultado_admin")


def render_painel_admin() -> None:
    """Renderiza o painel administrativo (somente consulta)."""
    st.title("🛡️ Painel Administrativo")
    st.markdown(
        "Consulta **somente leitura** dos registros de qualquer convocado: "
        "instrumentos de convocação, comparecimentos, comprovantes armazenados "
        "e dias ganhos."
    )
    st.markdown("---")

    cpf = _render_busca_cpf()
    if not cpf:
        st.info("Informe um CPF válido para consultar os registros.")
        return

    st.markdown(f"### 📄 Registros de {formatar_cpf(cpf)}")

    # Erros de banco são tratados internamente pelos renderizadores (st.warning)
    render_registros_usuario(
        cpf=cpf,
        cpf_fmt=formatar_cpf(cpf),
        titulo="📋 Registros do Convocado",
    )
    render_painel_dias_ganhos(
        comprovantes_registrados(cpf=cpf, incluir_sessao=False)
    )
```

- [ ] **Step 2: Verificar**

Run: `.\venv\Scripts\python.exe -m py_compile components/painel_admin.py`
Expected: sem saída.

Run: `.\venv\Scripts\python.exe -c "import components.painel_admin; print('ok')"`
Expected: `ok`.

Run: `.\venv\Scripts\python.exe -m pytest -v`
Expected: todos PASS.

- [ ] **Step 3: Commit**

```powershell
git add components/painel_admin.py
git commit -m "feat: painel administrativo de consulta por cpf (somente leitura)"
```

---

### Task 8: Gate RBAC e roteamento de visões (`app.py`)

**Files:**
- Modify: `app.py` (reescrita completa)

- [ ] **Step 1: Novo conteúdo de `app.py`**

```python
"""Aplicação Principal Streamlit para Upload e Extração de Informações de PDF."""
import logging
import streamlit as st
from config.settings import settings
from components.auth import (
    limpar_sessao_autenticacao,
    render_acesso_negado,
    render_login_page,
    usuario_autenticado,
)
from components.fluxo_unificado import render_fluxo_unificado
from components.painel_admin import render_painel_admin
from services.authorization_service import Acesso, decidir_acesso

# Configuração de Logging centralizado
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("pdf_extractor_app")

# Configuração da página Streamlit
st.set_page_config(
    page_title="PDF Extractor - Processamento e Extração",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicialização segura do estado de sessão (st.session_state)
for _chave, _valor in {
    "doc_info": None,
    "extraction_result": None,
    "current_file_name": None,
    "is_processing": False,
    "mock_mode": settings.USE_MOCK_EXTRACTION,
    "autenticado": False,
    "cpf_usuario": None,
    "roles_usuario": [],
    "nome_usuario": None,
    "email_usuario": None,
}.items():
    if _chave not in st.session_state:
        st.session_state[_chave] = _valor

# --- GATE DE AUTENTICAÇÃO ---
# Bloqueia todo o conteúdo principal enquanto o usuário não estiver autenticado.
if not render_login_page():
    st.stop()

# --- GATE DE AUTORIZAÇÃO (RBAC) ---
# Usuário autenticado sem a role exigida não acessa nenhum conteúdo.
usuario = usuario_autenticado()
acesso = decidir_acesso(usuario.roles) if usuario else Acesso.NEGADO

if acesso == Acesso.NEGADO:
    render_acesso_negado()
    st.stop()

# --- BARRA LATERAL (USUÁRIO E CONTROLES) ---
with st.sidebar:
    st.title("⚙️ Painel de Controle")
    st.caption("Configurações do ambiente de extração")

    # Bloco do usuário autenticado
    st.markdown("---")
    papeis = []
    if usuario.is_admin():
        papeis.append("🛡️ Admin")
    if usuario.is_convocado():
        papeis.append("🗳️ Convocado")
    st.markdown(f"👤 **Usuário:** {usuario.nome or '—'}")
    st.markdown(f"🆔 **CPF:** {st.session_state.get('cpf_usuario_fmt') or usuario.cpf}")
    if usuario.email:
        st.markdown(f"✉️ **E-mail:** {usuario.email}")
    st.markdown(f"**Papel:** {' • '.join(papeis) or '—'}")
    if st.button("🚪 Sair", use_container_width=True):
        id_token = st.session_state.get("kc_id_token")
        limpar_sessao_autenticacao()
        if id_token:
            st.session_state["_kc_id_token_logout"] = id_token
        st.rerun()

    # Usuário com as duas roles escolhe a visão ativa
    visao_admin = acesso == Acesso.ADMIN
    if acesso == Acesso.AMBOS:
        st.markdown("---")
        opcao_visao = st.radio(
            "Visão",
            ["🗳️ Convocado", "🛡️ Administrativo"],
            help="Alterne entre o fluxo do convocado e o painel administrativo.",
        )
        visao_admin = opcao_visao == "🛡️ Administrativo"

    # Controles exclusivos da visão do convocado
    if not visao_admin:
        st.markdown("---")
        mock_toggle = st.toggle(
            "Ativar Modo Mock",
            value=st.session_state.mock_mode,
            help="Quando ativado, retorna dados de demonstração sem processar o texto real do documento."
        )
        if mock_toggle != st.session_state.mock_mode:
            st.session_state.mock_mode = mock_toggle
            settings.USE_MOCK_EXTRACTION = mock_toggle
            st.rerun()

        st.markdown("---")
        st.markdown("### ℹ️ Sobre o Sistema")
        st.markdown(
            f"""
            - **Tecnologia:** 100% Python + Streamlit
            - **Motor de Leitura:** pypdf
            - **Limite de Arquivo:** {settings.MAX_FILE_SIZE_MB} MB
            - **Porta do Servidor:** {settings.PORT}
            - **Status:** Operacional
            """
        )

        if st.button("🔄 Limpar Sessão", use_container_width=True):
            st.session_state.doc_info = None
            st.session_state.extraction_result = None
            st.session_state.current_file_name = None
            st.session_state.is_processing = False
            st.session_state.comprovantes_sessao = {}
            st.rerun()

# --- CONTEÚDO PRINCIPAL (CONFORME O PAPEL) ---
if visao_admin:
    render_painel_admin()
else:
    # --- CABEÇALHO PRINCIPAL ---
    st.title("📄 PDF Extractor")
    st.markdown(
        "Plataforma inteligente em **Python** para upload, validação e extração de dados "
        "da **carta convocatória** e dos **comprovantes de participação** — em um único "
        "fluxo guiado."
    )
    st.markdown("---")

    # --- FLUXO UNIFICADO (Passo 1 → Passo 2 → Resumo) ---
    render_fluxo_unificado()

# --- RODAPÉ ---
st.markdown("<br><br>", unsafe_allow_html=True)
st.caption("PDF Extractor • Arquitetura 100% Python modular • Pronto para EasyPanel / Docker")
```

- [ ] **Step 2: Verificar**

Run: `.\venv\Scripts\python.exe -m py_compile app.py`
Expected: sem saída.

Run: `.\venv\Scripts\python.exe -m pytest -v`
Expected: todos PASS.

- [ ] **Step 3: Commit**

```powershell
git add app.py
git commit -m "feat: gate de rbac e roteamento de visoes por papel no app"
```

---

### Task 9: Documentação (`README.md`)

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Atualizar a árvore do projeto**

Na seção "🏛️ Arquitetura do Projeto", adicionar as novas linhas na árvore (mantendo a ordem):

- Em `components/`: `│   ├── auth.py                 # Autenticação (Keycloak OIDC / CPF) e telas de acesso` e `│   ├── painel_admin.py         # Painel administrativo (role admin, somente consulta)`
- Em `services/`: `│   ├── authorization_service.py # RBAC: extração de roles e decisão de acesso`
- Em `utils/`: `│   ├── cpf.py                  # Validação, formatação e máscara de CPF`
- Em `tests/`: `│   ├── test_authorization_service.py` e `│   ├── test_cpf_utils.py`

- [ ] **Step 2: Adicionar a seção de autenticação**

Inserir **antes** da seção "## 🗄️ Integração com Banco de Dados MongoDB":

````markdown
## 🔐 Autenticação e Controle de Acesso (Keycloak)

O sistema suporta dois modos de autenticação, definidos pela variável `KEYCLOAK_URL`:

| Modo | Quando | Comportamento |
|------|--------|---------------|
| **Keycloak (produção)** | `KEYCLOAK_URL` preenchida | Login OIDC: o usuário informa **CPF (username) + senha** na página do Keycloak, com recuperação de senha por e-mail ("Esqueceu a senha?") |
| **CPF direto (desenvolvimento)** | `KEYCLOAK_URL` vazia | Qualquer CPF válido entra; as roles vêm de `DEV_ROLES` |

### Papéis (RBAC)

| Role | Visão | Permissões |
|------|-------|------------|
| `convocado` | Fluxo unificado | Upload da carta convocatória e dos comprovantes; consulta **apenas dos próprios registros** |
| `admin` | Painel Administrativo | Consulta **somente leitura** de qualquer CPF (instrumentos, comparecimentos, comprovantes e dias ganhos) |
| ambas | Seletor na barra lateral | Alterna entre as duas visões |
| nenhuma | — | 🚫 Tela de **acesso negado** |

Os nomes das roles são configuráveis (`KEYCLOAK_ROLE_ADMIN`, `KEYCLOAK_ROLE_CONVOCADO`).
O código aceita **realm roles** e **client roles** (união das duas).

### Variáveis de ambiente

```dotenv
KEYCLOAK_URL=https://auth.exemplo.com.br
KEYCLOAK_REALM=tre-pe
KEYCLOAK_CLIENT_ID=convocacoes-app
KEYCLOAK_ROLE_ADMIN=admin
KEYCLOAK_ROLE_CONVOCADO=convocado
DEV_ROLES=convocado   # usado apenas com KEYCLOAK_URL vazia
```

### Configuração necessária no servidor Keycloak

1. **Client** (ex.: `convocacoes-app`): tipo *public*, Standard Flow (Authorization
   Code) habilitado; em *Valid redirect URIs* e *Web origins*, incluir o host do
   app (ex.: `https://app.tre-pe.jus.br/*`; em desenvolvimento, `http://localhost:8501/*`).
2. **Usuários:** o campo `username` deve ser o **CPF (11 dígitos)** — o app lê a
   claim `preferred_username`. Preencher também **e-mail** (obrigatório para a
   recuperação de senha) e nome completo.
3. **Roles:** criar `convocado` e `admin` (recomendado: *client roles* do
   `convocacoes-app`) e atribuí-las aos usuários. Usuário autenticado **sem**
   nenhuma das duas roles vê a tela de acesso negado.
4. **Recuperação de senha por e-mail:** em *Realm → Authentication*, habilitar o
   fluxo **"Forgot password"** (Reset credentials); em *Realm → Email*, configurar
   o SMTP. O link "Esqueceu a senha?" aparece automaticamente na página de login.
5. **Mensagem de credencial inválida (pt-BR):** em *Realm → Localization* (pt-BR),
   sobrescrever a chave `invalidUsernameOrPasswordMessage` com
   **"Usuário ou senha não encontrados"**.
6. **Opcional:** tema personalizado com a identidade visual do TRE-PE e
   *Valid post logout redirect URIs* no client (se desejar retorno ao app após o
   logout).

### Logout e SSO

O botão **Sair** encerra a sessão local do app. Como o Keycloak mantém a sessão
SSO no navegador, a tela seguinte oferece o link **"Encerrar sessão no Keycloak"**
(end-session) — necessário para **trocar de usuário** no mesmo navegador.
````

- [ ] **Step 3: Commit**

```powershell
git add README.md
git commit -m "docs: readme com autenticacao keycloak, rbac e painel administrativo"
```

---

### Task 10: Verificação final

**Files:** nenhum (validação)

- [ ] **Step 1: Suíte completa de testes**

Run: `.\venv\Scripts\python.exe -m pytest -v`
Expected: todos PASS (existentes + `test_cpf_utils.py` + `test_authorization_service.py`).

- [ ] **Step 2: Smoke test — modo desenvolvimento (convocado)**

Garantir que o `.env` local NÃO define `KEYCLOAK_URL` (comentada) e que `DEV_ROLES` está ausente ou `convocado`.

Run: `streamlit run app.py` (ou `.\venv\Scripts\streamlit.exe run app.py`)

Checklist manual no navegador (`http://localhost:8501`):
1. Tela de login com aviso "Modo de desenvolvimento – sem Keycloak".
2. Login com CPF válido (ex.: `529.982.247-25`) → fluxo unificado (Passo 1/2/Resumo) idêntico ao anterior.
3. Sidebar exibe Usuário/CPF/Papel `🗳️ Convocado`; CPF inválido (`12345678900`) → erro inline.
4. Botão "Sair" retorna ao login.

- [ ] **Step 3: Smoke test — admin e acesso negado**

1. Definir temporariamente no `.env`: `DEV_ROLES=admin` → reiniciar o Streamlit → logar → **Painel Administrativo**: busca por CPF com máscara; CPF inválido → erro; CPF válido → seções de registros/dias ganhos (ou avisos de banco indisponível, se MongoDB offline).
2. Definir `DEV_ROLES=admin,convocado` → logar → seletor "Visão" na sidebar alterna Convocado/Administrativo.
3. Definir `DEV_ROLES=` (vazio) → logar → 🚫 **Acesso negado** com botão Sair.
4. **Restaurar o `.env`** para o estado original (`DEV_ROLES` ausente ou `convocado`).

- [ ] **Step 4: Smoke test — Keycloak (servidor real, quando disponível)**

Com `KEYCLOAK_URL`/`KEYCLOAK_REALM`/`KEYCLOAK_CLIENT_ID` apontando para o servidor:

1. Login com CPF + senha corretos → entra com nome/e-mail/papel na sidebar.
2. Senha incorreta → mensagem "Usuário ou senha não encontrados" (após configurar localization, item 5 da Task 9).
3. "Esqueceu a senha?" → e-mail de redefinição (após configurar SMTP + Forgot password, item 4 da Task 9).
4. Usuário com role `admin` → painel; com `convocado` → fluxo; sem roles → acesso negado.
5. "Sair" → link "Encerrar sessão no Keycloak" encerra o SSO (trocar de usuário exige nova senha).

- [ ] **Step 5: Commit final (se houver ajustes dos smoke tests)**

```powershell
git status --short
# se houver mudanças:
git add -A; git commit -m "fix: ajustes finos do controle de acesso keycloak"
```

---

## Self-Review do Plano (checklist executado pelo autor)

- **Cobertura do spec:** §4.1→Task 3; §4.2→Task 4; §4.3→Task 8; §4.4→Task 7; §4.5→Tasks 1/5/6; §4.6→Task 2; §6→Task 9 (README); §7 (erros)→código das Tasks 3/4/7; §8 (testes)→Tasks 1/3; §10 (critérios)→Task 10. ✔
- **Placeholders:** nenhum "TBD"/"implementar depois"; todo passo de código contém o código completo. ✔
- **Consistência de tipos/assinaturas:** `extrair_roles(access_token, client_id)`, `construir_usuario(user_info, access_token, client_id)`, `decidir_acesso(roles, role_admin, role_convocado)`, `parse_roles(raw)`, `nome_de_user_info(info)`, `Usuario(cpf, nome, email, roles)`, `Acesso.{ADMIN,CONVOCADO,AMBOS,NEGADO}` — usadas com as mesmas assinaturas nas Tasks 3, 4 e 8. `render_registros_usuario(cpf, cpf_fmt, titulo)` (Task 5) e `comprovantes_registrados(cpf, incluir_sessao)` (Task 6) — chamadas compatíveis na Task 7. `url_logout_keycloak`, `limpar_sessao_autenticacao`, `usuario_autenticado`, `render_acesso_negado` (Task 4) — importados na Task 8. ✔
- **CPF de teste:** `52998224725` e `11144477735` são válidos pelo algoritmo; `12345678900` é inválido (dígitos verificadores errados) — verificado manualmente contra o algoritmo de `utils/cpf.py`. ✔
