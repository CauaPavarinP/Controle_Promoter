"""Regras do cálculo que o usuário ajusta na tela (aba "Regras do cálculo").

Ficam gravadas no banco (tabela configuracoes, chave "regras"). Quando ainda não
foram salvas, valem os valores de REGRAS_PADRAO.
"""
from . import db

MODOS_REDE = {"cnpj", "rede_total", "rede_dividido"}
COLUNAS_VALOR = {"total_venda", "vlr_total"}
MODOS_RATEIO = {"igual", "visitas"}
ACOES_TIPO = {"soma", "subtrai", "ignora"}

REGRAS_PADRAO = {
    # Padrão igual à planilha: soma TOTAL VENDA de todas as linhas, sem filtrar tipo de nota nem RECEITA.
    "valor_faturamento": "total_venda",   # total_venda (coluna AL) | vlr_total (coluna AD)
    # Tipo de nota (sem acento, maiúsculo) -> soma | subtrai | ignora.
    "tipos_nf": {},
    "tipos_nf_padrao": "soma",            # o que fazer com tipos que não estão na lista acima
    "somente_receita": False,             # True: só linhas com RECEITA = SIM
    # cnpj: só o CNPJ exato da loja | rede_total: rede inteira (raiz do CNPJ) em cada loja |
    # rede_dividido: faturamento da rede dividido igualmente entre as lojas dela.
    "modo_rede": "cnpj",
    # Como dividir o custo do promotor entre as lojas dele: igual | visitas (proporcional).
    "rateio_custo": "igual",
    "encargos_percentual": 0.0,   # % sobre o salário (INSS, FGTS, férias…)
    "custo_extra_mensal": 0.0,    # R$ por promotor por mês (celular, combustível…)
    "faixa_alerta": 15.0,         # % de custo sobre faturamento a partir do qual fica amarelo
    "faixa_critico": 30.0,        # … e vermelho
    "semanas_por_mes": 4.33,
}


def ler_regras() -> dict:
    salvas = db.ler_configuracao("regras", {}) or {}
    if salvas and "tipos_nf_padrao" not in salvas:
        # Regras salvas antes desta opção existir: tipo fora da lista ficava de fora.
        salvas = {**salvas, "tipos_nf_padrao": "ignora"}
    return {**REGRAS_PADRAO, **salvas}


def _numero(dados, campo, minimo, maximo):
    try:
        valor = float(dados[campo])
    except (TypeError, ValueError):
        raise ValueError(f"'{campo}' precisa ser um número.")
    if not minimo <= valor <= maximo:
        raise ValueError(f"'{campo}' precisa ficar entre {minimo} e {maximo}.")
    return valor


def validar_regras(dados: dict) -> dict:
    regras = {**REGRAS_PADRAO, **{k: v for k, v in dados.items() if k in REGRAS_PADRAO}}
    if regras["modo_rede"] not in MODOS_REDE:
        raise ValueError("Modo de rede inválido.")
    if regras["rateio_custo"] not in MODOS_RATEIO:
        raise ValueError("Forma de rateio inválida.")
    if regras["valor_faturamento"] not in COLUNAS_VALOR:
        raise ValueError("Coluna de valor inválida.")
    if regras["tipos_nf_padrao"] not in ACOES_TIPO:
        raise ValueError("Ação padrão de tipo de nota inválida.")
    regras["somente_receita"] = bool(regras["somente_receita"])
    tipos = regras["tipos_nf"]
    if not isinstance(tipos, dict) or any(a not in ACOES_TIPO for a in tipos.values()):
        raise ValueError("Ação de tipo de nota inválida (use soma, subtrai ou ignora).")
    regras["encargos_percentual"] = _numero(regras, "encargos_percentual", 0, 300)
    regras["custo_extra_mensal"] = _numero(regras, "custo_extra_mensal", 0, 1_000_000)
    regras["faixa_alerta"] = _numero(regras, "faixa_alerta", 0, 1000)
    regras["faixa_critico"] = _numero(regras, "faixa_critico", 0, 1000)
    regras["semanas_por_mes"] = _numero(regras, "semanas_por_mes", 1, 6)
    if regras["faixa_alerta"] >= regras["faixa_critico"]:
        raise ValueError("A faixa de alerta (amarelo) precisa ser menor que a crítica (vermelho).")
    return regras


def gravar_regras(dados: dict) -> dict:
    regras = validar_regras(dados)
    db.gravar_configuracao("regras", regras)
    return regras
