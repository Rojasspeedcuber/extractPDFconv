"""Testes da lógica de bloqueio do Passo 2 no fluxo unificado."""
from types import SimpleNamespace

from components.fluxo_unificado import passo2_liberado


def _resultado(status):
    return SimpleNamespace(status=status)


def test_libera_quando_carta_processada_na_sessao():
    assert passo2_liberado(_resultado("completed"), False, None, lambda cpf: False) is True


def test_bloqueado_sem_carta_e_sem_banco():
    assert passo2_liberado(None, False, None, lambda cpf: False) is False


def test_erro_na_extracao_nao_libera_por_si():
    # status "error" não libera pela condição de sessão.
    assert passo2_liberado(_resultado("error"), False, None, lambda cpf: False) is False


def test_libera_quando_carta_existe_no_banco():
    assert passo2_liberado(None, True, "12345678900", lambda cpf: True) is True


def test_persist_desativado_ignora_banco():
    chamadas = []

    def _fn(cpf):
        chamadas.append(cpf)
        return True

    assert passo2_liberado(None, False, "12345678900", _fn) is False
    assert chamadas == []  # não consulta o banco quando PERSIST_TO_DB é False


def test_sem_cpf_ignora_banco():
    chamadas = []

    def _fn(cpf):
        chamadas.append(cpf)
        return True

    assert passo2_liberado(None, True, None, _fn) is False
    assert chamadas == []


def test_falha_no_banco_nao_quebra_e_bloqueia():
    def _fn(cpf):
        raise RuntimeError("banco indisponível")

    assert passo2_liberado(None, True, "12345678900", _fn) is False
