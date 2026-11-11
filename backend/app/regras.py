"""Regras do cálculo que o usuário ajusta na tela (aba "Regras do cálculo").

Só o que o documento de requisitos deixa configurável:
- o que conta como faturamento (seção 6.3): coluna de valor, tipos de nota e RECEITA;
- como dividir o custo do promotor entre as lojas dele (seção 8, item 7);
- o limite de % de custo sobre faturamento que destaca a loja (seção 7.1), sem valor fixo.

Ficam gravadas no banco (tabela configuracoes, chave "regras"). Quando ainda não
foram salvas, valem os valores de REGRAS_PADRAO.
"""
from . import db

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
    # Como dividir o custo do promotor entre as lojas dele: visitas (proporcional) | igual.
    "rateio_custo": "visitas",
    # % de custo sobre faturamento a partir do qual a loja fica destacada. Vazio = sem destaque.
    "limite_percentual": None,
    # Margem da 101 sobre o que vende às lojas (%). Com ela, cada promotor mostra se "se paga": lucro estimado
    # das lojas dele (faturamento × margem) menos o custo dele. Vazio = ainda não informada (aba Promotores).
    "margem_percentual": None,
}


def ler_regras() -> dict:
    salvas = db.ler_configuracao("regras", {}) or {}
    if salvas and "tipos_nf_padrao" not in salvas:
        # Regras salvas antes desta opção existir: tipo fora da lista ficava de fora.
        salvas = {**salvas, "tipos_nf_padrao": "ignora"}
    # Ignora opções de versões anteriores que não existem mais.
    return {**REGRAS_PADRAO, **{k: v for k, v in salvas.items() if k in REGRAS_PADRAO}}


def validar_regras(dados: dict) -> dict:
    regras = {**REGRAS_PADRAO, **{k: v for k, v in dados.items() if k in REGRAS_PADRAO}}
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
    limite = regras["limite_percentual"]
    if limite in (None, ""):
        regras["limite_percentual"] = None
    else:
        try:
            regras["limite_percentual"] = float(limite)
        except (TypeError, ValueError):
            raise ValueError("O limite de % precisa ser um número.")
        if not 0 < regras["limite_percentual"] <= 1000:
            raise ValueError("O limite de % precisa ficar entre 0 e 1000.")
    margem = regras["margem_percentual"]
    if margem in (None, ""):
        regras["margem_percentual"] = None
    else:
        try:
            regras["margem_percentual"] = float(str(margem).replace(",", "."))
        except (TypeError, ValueError):
            raise ValueError("A margem precisa ser um número (ex.: 12,5).")
        if not 0 < regras["margem_percentual"] < 100:
            raise ValueError("A margem precisa ficar entre 0 e 100%.")
    return regras


def gravar_regras(dados: dict) -> dict:
    regras = validar_regras(dados)
    db.gravar_configuracao("regras", regras)
    return regras
