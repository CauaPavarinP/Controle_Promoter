"""Funções de cálculo usadas pelo Resumo e pela aba Faturamento.

- Período (AAAA-MM) e percentuais.
- Tipos de nota e coluna de valor do faturamento (regras ajustáveis em app/regras.py).
- Aba Faturamento (resumo_faturamento): o que o ERP faturou por UF e por cliente.

O custo × faturamento por loja, promotor, agência e UF fica em app/calculo_atendimento.py.
"""
import re

import pandas as pd

from .importacao import normalizar_texto


def indice_mes(ano_mes: str) -> int:
    """'2026-03' -> ano × 12 + mês − 1. Recusa (ValueError) mês 00, 13, texto fora do formato e ano absurdo."""
    achado = re.fullmatch(r"(\d{4})-(\d{2})", str(ano_mes).strip())
    if not achado:
        raise ValueError("Período inválido. Use AAAA-MM.")
    ano, mes = int(achado.group(1)), int(achado.group(2))
    if not 1 <= mes <= 12 or not 2000 <= ano <= 2100:
        raise ValueError("Período inválido. Use AAAA-MM com mês de 01 a 12.")
    return ano * 12 + mes - 1


def _arredondar(valor):
    return None if valor is None or pd.isna(valor) else round(float(valor), 2)


def _percentual(custo, faturamento):
    return round(custo / faturamento * 100, 1) if faturamento and faturamento > 0 else None


def aplicar_tipos_de_nota(faturamento: pd.DataFrame, regras: dict) -> pd.DataFrame:
    """Escolhe a coluna de valor e soma, desconta ou tira cada tipo de nota conforme as regras."""
    fat = faturamento.copy()
    if "valor" not in fat:
        coluna = regras["valor_faturamento"]
        fat["valor"] = fat[coluna] if coluna in fat else fat["total_venda"]
    if regras["somente_receita"] and "receita" in fat:
        fat = fat[fat["receita"].map(normalizar_texto).isin({"SIM", "S"})]
    acoes = fat["chave_tipo"].map(lambda c: regras["tipos_nf"].get(c, regras["tipos_nf_padrao"]))
    fat = fat[acoes != "ignora"].copy()
    acoes = acoes[acoes != "ignora"]
    fat["valor"] = fat["valor"].astype(float).where(acoes == "soma", -fat["valor"].astype(float).abs())
    fat["notas"] = fat["notas"].where(acoes == "soma", 0)
    if "cod_cliente" not in fat:
        fat["cod_cliente"] = ""
    return fat


def tipos_de_nota(faturamento: pd.DataFrame, regras: dict) -> list:
    """Tipos de nota existentes no faturamento importado, com a ação de cada um."""
    if faturamento.empty:
        return []
    coluna = regras["valor_faturamento"]
    tipos = (faturamento.groupby("chave_tipo")
                        .agg(tipo=("tipo_nf", "first"), notas=("notas", "sum"), valor=(coluna, "sum"))
                        .reset_index().sort_values("valor", ascending=False))
    return [{"chave": t.chave_tipo, "tipo": t.tipo, "notas": int(t.notas), "valor": _arredondar(t.valor),
             "acao": regras["tipos_nf"].get(t.chave_tipo, regras["tipos_nf_padrao"]),
             "na_lista": t.chave_tipo in regras["tipos_nf"]} for t in tipos.itertuples()]


def resumo_faturamento(faturamento: pd.DataFrame, regras: dict, cnpjs_no_roteiro: set[str]) -> dict:
    """Aba Faturamento: tudo o que veio do ERP no período, por UF e por cliente, mês a mês.

    Mostra todos os clientes, atendidos por promotor ou não (coluna "no_roteiro").
    """
    fat = aplicar_tipos_de_nota(faturamento, regras)
    if fat.empty:
        return {"meses": [], "por_uf": [], "totais": {"total": 0.0}, "clientes": []}
    fat["rotulo"] = [f"{int(a)}-{int(m):02d}" for a, m in zip(fat["ano"], fat["mes"])]
    meses = sorted(fat["rotulo"].unique())
    fat["uf"] = fat["uf"].str.upper().replace("", "—")

    def tabela(indice):
        return fat.pivot_table(index=indice, columns="rotulo", values="valor", aggfunc="sum", fill_value=0.0)

    contagem = fat.groupby("uf")["cnpj"].nunique()
    por_uf = [{"uf": uf, "meses": {m: _arredondar(v) for m, v in linha.items()}, "total": _arredondar(linha.sum()),
               "clientes": int(contagem[uf])}
              for uf, linha in tabela("uf").iterrows()]
    por_uf.sort(key=lambda l: (l["uf"] == "—", l["uf"]))
    por_mes = fat.groupby("rotulo")["valor"].sum()
    totais = {m: _arredondar(por_mes.get(m, 0.0)) for m in meses}
    total = _arredondar(por_mes.sum())

    # Razão social, cidade e UF do último mês em que o cliente comprou.
    dados = fat.sort_values(["ano", "mes"]).drop_duplicates("cnpj", keep="last").set_index("cnpj")
    notas = fat.groupby("cnpj")["notas"].sum()
    # Montado a partir de listas e dicionários: iterrows/.at do pandas nas ~6 mil linhas levavam ~1 s.
    info = dados[["razao_social", "cidade", "uf"]].to_dict("index")
    notas = notas.to_dict()
    por_cliente = tabela("cnpj")
    colunas = list(por_cliente.columns)
    clientes = [{"cnpj": cnpj, "razao_social": info[cnpj]["razao_social"], "cidade": info[cnpj]["cidade"],
                 "uf": info[cnpj]["uf"], "meses": {m: round(float(v), 2) for m, v in zip(colunas, linha)},
                 "total": round(float(linha.sum()), 2), "notas": int(notas[cnpj]), "no_roteiro": cnpj in cnpjs_no_roteiro}
                for cnpj, linha in zip(por_cliente.index, por_cliente.to_numpy())]
    clientes.sort(key=lambda c: -c["total"])
    return {"meses": meses, "por_uf": por_uf, "totais": {**totais, "total": total}, "clientes": clientes}
