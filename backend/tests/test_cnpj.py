"""Validação do CNPJ pelos dígitos verificadores (app/cnpj.py)."""
import pytest

from app.cnpj import cnpj_valido, formatar


@pytest.mark.parametrize("cnpj", [
    "11.222.333/0001-81",
    "11222333000181",
    "00.000.001/0001-36",
    "09.477.652/0042-64",
    "77.752.293/0107-46",
    " 11.222.333/0001-81 ",
])
def test_cnpj_valido(cnpj):
    assert cnpj_valido(cnpj)


@pytest.mark.parametrize("cnpj", [
    "09.447.652/0020-59",    # COMPER CD: dígitos verificadores errados
    "11.222.333/0001-80",    # último dígito errado
    "11.222.333/0001-91",    # penúltimo dígito errado
    "00.000.001/0001-01",    # os CNPJs antigos dos exemplos
    "00.000.000/0000-00",    # todos iguais
    "11.111.111/1111-11",
    "1122233300018",         # 13 dígitos
    "112223330001810",       # 15 dígitos
    "",
    None,
    "não informado",
])
def test_cnpj_invalido(cnpj):
    assert not cnpj_valido(cnpj)


def test_formatar():
    assert formatar("00000001000136") == "00.000.001/0001-36"
    assert formatar("123") == "123"
