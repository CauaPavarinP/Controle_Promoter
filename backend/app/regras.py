"""Regras do cálculo que o usuário ajusta na tela (aba "Regras do cálculo").

Só o que o documento de requisitos deixa configurável:
- o que conta como faturamento (seção 6.3): coluna de valor, tipos de nota e RECEITA;
- como dividir o custo do promotor entre as lojas dele (seção 8, item 7);
- o limite de % de custo sobre o faturamento bruto: até ele o atendimento "vale a pena" (padrão 3%, decisão do
  Maurício: o promotor de loja pode custar no máximo 3% do que as lojas dele compram).

Ficam gravadas no banco (tabela configuracoes, chave "regras"). Quando ainda não
foram salvas, valem os valores de REGRAS_PADRAO.
"""
from . import db

COLUNAS_VALOR = {"total_venda", "vlr_total"}
MODOS_RATEIO = {"igual", "visitas"}
ACOES_TIPO = {"soma", "subtrai", "ignora"}

REGRAS_PADRAO = {
    # Valor do faturamento: VLR TOTAL, que vem do ERP (o TOTAL VENDA era uma coluna feita à mão na planilha antiga).
    "valor_faturamento": "vlr_total",     # vlr_total (coluna VLR TOTAL do ERP) | total_venda
    # Tipo de nota (sem acento, maiúsculo) -> soma | subtrai | ignora.
    "tipos_nf": {},
    "tipos_nf_padrao": "soma",            # o que fazer com tipos que não estão na lista acima
    "somente_receita": False,             # True: só linhas com RECEITA = SIM
    # Como dividir o custo do promotor entre as lojas dele: visitas (proporcional) | igual.
    "rateio_custo": "visitas",
    # Custo máximo, em % do faturamento bruto das lojas, para o atendimento valer a pena.
    "limite_percentual": 3.0,
}
LIMITE_PADRAO = 3.0


def ler_regras() -> dict:
    salvas = db.ler_configuracao("regras", {}) or {}
    if salvas and "tipos_nf_padrao" not in salvas:
        # Regras salvas antes desta opção existir: tipo fora da lista ficava de fora.
        salvas = {**salvas, "tipos_nf_padrao": "ignora"}
    # Ignora opções de versões anteriores que não existem mais (ex.: margem_percentual).
    regras = {**REGRAS_PADRAO, **{k: v for k, v in salvas.items() if k in REGRAS_PADRAO}}
    if regras["limite_percentual"] is None:   # salvo vazio numa versão anterior
        regras["limite_percentual"] = LIMITE_PADRAO
    return regras


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
        regras["limite_percentual"] = LIMITE_PADRAO
    else:
        try:
            regras["limite_percentual"] = float(str(limite).replace(",", "."))
        except (TypeError, ValueError):
            raise ValueError("O limite precisa ser um número (ex.: 3 ou 2,5).")
        if not 0 < regras["limite_percentual"] <= 100:
            raise ValueError("O limite precisa ficar entre 0 e 100%.")
    return regras


def gravar_regras(dados: dict) -> dict:
    regras = validar_regras(dados)
    db.gravar_configuracao("regras", regras)
    return regras
