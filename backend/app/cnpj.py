"""Validação de CNPJ pelos dois dígitos verificadores (regra da Receita Federal)."""
import re

PESOS_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
PESOS_2 = [6] + PESOS_1


def _digito(base: str, pesos: list[int]) -> str:
    resto = sum(int(numero) * peso for numero, peso in zip(base, pesos)) % 11
    return "0" if resto < 2 else str(11 - resto)


def somente_digitos(valor) -> str:
    return re.sub(r"\D", "", "" if valor is None else str(valor))


def cnpj_valido(valor) -> bool:
    """True quando o CNPJ (com ou sem pontuação) tem 14 dígitos e os 2 dígitos verificadores conferem.

    CNPJ com todos os dígitos iguais (00.000.000/0000-00, 11.111.111/1111-11…) passa na conta, mas não existe:
    também é inválido.
    """
    digitos = somente_digitos(valor)
    if len(digitos) != 14 or len(set(digitos)) == 1:
        return False
    primeiro = _digito(digitos[:12], PESOS_1)
    segundo = _digito(digitos[:12] + primeiro, PESOS_2)
    return digitos[12:] == primeiro + segundo


def formatar(digitos: str) -> str:
    """00000001000136 -> 00.000.001/0001-36 (outros tamanhos voltam como vieram)."""
    if len(digitos) != 14:
        return digitos
    return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"
