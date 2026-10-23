"""Cálculos do painel: custo dos promotores × faturamento das lojas que eles atendem.

Regras (algumas PROVISÓRIAS, ver README):
- O período é sempre um intervalo de meses (um mês só = início igual ao fim).
- Custo do promotor = custo mensal × meses do período a partir do mês de admissão.
- O faturamento é por CNPJ. Quando várias lojas do roteiro têm o mesmo CNPJ (rede que
  compra pela matriz), cada loja mostra o valor do CNPJ inteiro, mas os totais contam
  cada CNPJ uma vez só, para não somar o mesmo dinheiro várias vezes.
- Se uma loja tem mais de um promotor, o faturamento dela conta para cada um deles.
"""
from dataclasses import dataclass

import pandas as pd

from .importacao import normalizar_texto, vincular_roteiro


@dataclass
class Filtros:
    inicio: str            # "AAAA-MM"
    fim: str               # "AAAA-MM"
    supervisor: str = ""
    promotor: str = ""     # código do promotor
    uf: str = ""
    cidade: str = ""


def indice_mes(ano_mes: str) -> int:
    ano, mes = ano_mes.split("-")
    return int(ano) * 12 + int(mes) - 1


def _arredondar(valor):
    return None if valor is None or pd.isna(valor) else round(float(valor), 2)


def _percentual(custo, faturamento):
    return round(custo / faturamento * 100, 1) if faturamento else None


def meses_de_custo(admissao: str, inicio: int, fim: int) -> int:
    """Quantos meses do período o promotor já estava contratado (mês da admissão conta inteiro)."""
    comeco = inicio
    if admissao:
        data = pd.to_datetime(admissao, errors="coerce")
        if not pd.isna(data):
            comeco = max(inicio, data.year * 12 + data.month - 1)
    return max(0, fim - comeco + 1)


def calcular_painel(faturamento: pd.DataFrame, promotores: pd.DataFrame,
                    roteiro: pd.DataFrame, filtros: Filtros) -> dict:
    inicio, fim = indice_mes(filtros.inicio), indice_mes(filtros.fim)
    if inicio > fim:
        inicio, fim = fim, inicio
    total_meses = fim - inicio + 1

    roteiro, _ = vincular_roteiro(roteiro, promotores)
    # Quantas lojas do roteiro (inteiro) compartilham o mesmo CNPJ.
    lojas_por_cnpj = roteiro[roteiro["cnpj"] != ""].drop_duplicates(["cnpj", "loja"])["cnpj"].value_counts()

    # --- Faturamento do período por CNPJ -----------------------------------
    fat = faturamento.copy()
    fat["indice"] = fat["ano"].astype(int) * 12 + fat["mes"].astype(int) - 1
    fat = fat[(fat["indice"] >= inicio) & (fat["indice"] <= fim)]
    por_cnpj = (fat.groupby("cnpj")
                   .agg(faturamento=("valor", "sum"), notas=("notas", "sum"),
                        meses_com_compra=("indice", "nunique"))
                   .reset_index())

    # --- Promotores no filtro ----------------------------------------------
    proms = promotores.copy()
    if filtros.supervisor:
        proms = proms[proms["supervisor"].map(normalizar_texto) == normalizar_texto(filtros.supervisor)]
    if filtros.promotor:
        proms = proms[proms["codigo"] == filtros.promotor]

    # --- Lojas no filtro -----------------------------------------------------
    lojas = roteiro[roteiro["codigo_promotor"].isin(proms["codigo"])]
    if filtros.uf:
        lojas = lojas[lojas["uf"].str.upper() == filtros.uf.upper()]
    if filtros.cidade:
        lojas = lojas[lojas["cidade"].map(normalizar_texto) == normalizar_texto(filtros.cidade)]
    if filtros.uf or filtros.cidade:
        # Filtrando por local, só interessam os promotores que atendem ali.
        proms = proms[proms["codigo"].isin(lojas["codigo_promotor"])]

    lojas = lojas.merge(por_cnpj, on="cnpj", how="left")
    lojas[["faturamento", "notas", "meses_com_compra"]] = (
        lojas[["faturamento", "notas", "meses_com_compra"]].fillna(0))
    lojas["lojas_mesmo_cnpj"] = lojas["cnpj"].map(lojas_por_cnpj).fillna(1).astype(int)
    nomes = dict(zip(proms["codigo"], proms["nome"]))
    supervisores = dict(zip(proms["codigo"], proms["supervisor"]))

    # --- Tabela por promotor -------------------------------------------------
    linhas_promotores = []
    for p in proms.itertuples():
        lojas_p = lojas[lojas["codigo_promotor"] == p.codigo]
        fat_p = lojas_p[lojas_p["cnpj"] != ""].drop_duplicates("cnpj")["faturamento"].sum()
        custo_p = float(p.custo_mensal) * meses_de_custo(p.admissao, inicio, fim)
        visitas = lojas_p["visitas_semana"].dropna()
        linhas_promotores.append({
            "codigo": p.codigo, "nome": p.nome, "supervisor": p.supervisor, "municipio": p.municipio,
            "custo_mensal": _arredondar(p.custo_mensal), "custo_periodo": _arredondar(custo_p),
            "lojas": int(lojas_p["loja"].nunique()),
            "lojas_sem_compra": int((lojas_p["faturamento"] <= 0).sum()),
            "visitas_semana": _arredondar(visitas.sum()) if not visitas.empty else None,
            "faturamento": _arredondar(fat_p),
            "percentual_custo": _percentual(custo_p, fat_p),
        })
    linhas_promotores.sort(key=lambda l: (l["percentual_custo"] is None, -(l["percentual_custo"] or 0)))

    # --- Tabela por loja -----------------------------------------------------
    linhas_lojas = [{
        "loja": l.loja, "cnpj": l.cnpj, "cidade": l.cidade, "uf": l.uf,
        "codigo_promotor": l.codigo_promotor, "promotor": nomes.get(l.codigo_promotor, ""),
        "supervisor": supervisores.get(l.codigo_promotor, ""),
        "visitas_semana": _arredondar(l.visitas_semana),
        "faturamento": _arredondar(l.faturamento), "notas": int(l.notas),
        "meses_com_compra": int(l.meses_com_compra),
        "lojas_mesmo_cnpj": int(l.lojas_mesmo_cnpj),
    } for l in lojas.itertuples()]
    linhas_lojas.sort(key=lambda l: l["faturamento"])

    # --- Resumo --------------------------------------------------------------
    custo_total = sum(l["custo_periodo"] for l in linhas_promotores)
    fat_total = lojas[lojas["cnpj"] != ""].drop_duplicates("cnpj")["faturamento"].sum()
    resumo = {
        "meses": total_meses,
        "promotores": len(linhas_promotores),
        "lojas": int(lojas.drop_duplicates(["cnpj", "loja"]).shape[0]),
        "lojas_sem_compra": int((lojas.drop_duplicates(["cnpj", "loja"])["faturamento"] <= 0).sum()),
        "custo": _arredondar(custo_total),
        "faturamento": _arredondar(fat_total),
        "percentual_custo": _percentual(custo_total, fat_total),
        "cnpjs_compartilhados": int((lojas.drop_duplicates("cnpj")["lojas_mesmo_cnpj"] > 1).sum()),
    }
    return {"resumo": resumo, "promotores": linhas_promotores, "lojas": linhas_lojas}


def opcoes_de_filtro(faturamento: pd.DataFrame, promotores: pd.DataFrame, roteiro: pd.DataFrame) -> dict:
    roteiro, sem_vinculo = vincular_roteiro(roteiro, promotores)
    meses = sorted({f"{int(a)}-{int(m):02d}" for a, m in zip(faturamento["ano"], faturamento["mes"])})
    locais = (roteiro[["uf", "cidade"]].replace("", pd.NA).dropna()
              .drop_duplicates().sort_values(["uf", "cidade"]))
    return {
        "meses": meses,
        "supervisores": sorted(s for s in promotores["supervisor"].unique() if s),
        "promotores": [{"codigo": p.codigo, "nome": p.nome, "supervisor": p.supervisor}
                       for p in promotores.sort_values("nome").itertuples()],
        "ufs": sorted(locais["uf"].unique().tolist()),
        "cidades": [{"uf": l.uf, "cidade": l.cidade} for l in locais.itertuples()],
        "roteiro_sem_vinculo": sem_vinculo,
    }
