"""Cálculos do painel: custo dos promotores × faturamento das lojas que eles atendem.

As regras ajustáveis vêm de app/regras.py (aba "Regras do cálculo"):
- tipos de nota: cada tipo soma, desconta ou fica de fora do faturamento;
- modo de rede: faturamento pelo CNPJ exato da loja, pela rede inteira (raiz do CNPJ,
  os 8 primeiros dígitos) ou pela rede dividida igualmente entre as lojas dela;
- custo: custo mensal + encargos (% do salário) + custo extra fixo, contado a partir do
  mês de admissão, e dividido entre as lojas igualmente ou pelas visitas por semana;
- faixas de cor do % de custo sobre faturamento.

Regras fixas:
- Quando várias lojas mostram o mesmo valor (CNPJ ou rede compartilhados), os totais
  contam esse valor uma vez só, para não somar o mesmo dinheiro várias vezes.
- Se uma loja tem mais de um promotor, o faturamento dela conta para cada um deles.
"""
from dataclasses import dataclass

import pandas as pd

from .importacao import normalizar_texto, vincular_roteiro
from .regras import REGRAS_PADRAO


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
    return round(custo / faturamento * 100, 1) if faturamento and faturamento > 0 else None


def meses_de_custo(admissao: str, inicio: int, fim: int) -> int:
    """Quantos meses do período o promotor já estava contratado (mês da admissão conta inteiro)."""
    comeco = inicio
    if admissao:
        data = pd.to_datetime(admissao, errors="coerce")
        if not pd.isna(data):
            comeco = max(inicio, data.year * 12 + data.month - 1)
    return max(0, fim - comeco + 1)


def raiz_cnpj(cnpj: str) -> str:
    """Os 8 primeiros dígitos identificam a empresa; todas as filiais têm a mesma raiz."""
    return cnpj[:8] if len(cnpj) == 14 else cnpj


def custo_mensal_efetivo(promotor, regras) -> float:
    salario = float(promotor.salario or 0)
    return (float(promotor.custo_mensal or 0) + salario * regras["encargos_percentual"] / 100
            + regras["custo_extra_mensal"])


def aplicar_tipos_de_nota(faturamento: pd.DataFrame, regras: dict) -> pd.DataFrame:
    """Soma, desconta ou tira cada tipo de nota conforme as regras."""
    acoes = faturamento["chave_tipo"].map(lambda c: regras["tipos_nf"].get(c, "ignora"))
    fat = faturamento[acoes != "ignora"].copy()
    acoes = acoes[acoes != "ignora"]
    fat["valor"] = fat["valor"].astype(float).where(acoes == "soma", -fat["valor"].astype(float).abs())
    fat["notas"] = fat["notas"].where(acoes == "soma", 0)
    return fat


def calcular_painel(faturamento: pd.DataFrame, promotores: pd.DataFrame,
                    roteiro: pd.DataFrame, filtros: Filtros, regras: dict | None = None) -> dict:
    regras = {**REGRAS_PADRAO, **(regras or {})}
    inicio, fim = indice_mes(filtros.inicio), indice_mes(filtros.fim)
    if inicio > fim:
        inicio, fim = fim, inicio
    total_meses = fim - inicio + 1
    por_rede = regras["modo_rede"] != "cnpj"
    dividido = regras["modo_rede"] == "rede_dividido"
    chave_de = raiz_cnpj if por_rede else (lambda c: c)

    roteiro, _ = vincular_roteiro(roteiro, promotores)
    roteiro = roteiro.copy()
    roteiro["chave"] = roteiro["cnpj"].fillna("").map(chave_de)
    # Quantas lojas do roteiro (inteiro) dividem o mesmo CNPJ/rede.
    lojas_por_chave = roteiro[roteiro["chave"] != ""].drop_duplicates(["chave", "loja"])["chave"].value_counts()

    # --- Faturamento do período por CNPJ ou rede ---------------------------
    fat = aplicar_tipos_de_nota(faturamento, regras)
    fat["indice"] = fat["ano"].astype(int) * 12 + fat["mes"].astype(int) - 1
    fat = fat[(fat["indice"] >= inicio) & (fat["indice"] <= fim)]
    fat["chave"] = fat["cnpj"].map(chave_de)
    por_mes = fat.groupby(["chave", "indice"])["valor"].sum().reset_index()
    por_chave = fat.groupby("chave").agg(faturamento=("valor", "sum"), notas=("notas", "sum")).reset_index()
    meses_com_compra = por_mes[por_mes["valor"] > 0].groupby("chave")["indice"].nunique()
    por_chave["meses_com_compra"] = por_chave["chave"].map(meses_com_compra).fillna(0)

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

    lojas = lojas.merge(por_chave, on="chave", how="left")
    lojas[["faturamento", "notas", "meses_com_compra"]] = (
        lojas[["faturamento", "notas", "meses_com_compra"]].fillna(0))
    lojas["lojas_mesma_chave"] = lojas["chave"].map(lojas_por_chave).fillna(1).astype(int)
    lojas.loc[lojas["chave"] == "", "lojas_mesma_chave"] = 1
    if dividido:
        lojas["faturamento"] = lojas["faturamento"] / lojas["lojas_mesma_chave"]
    # Valor compartilhado: a loja mostra o total do CNPJ/rede, que vale para várias lojas.
    lojas["compartilhado"] = (lojas["lojas_mesma_chave"] > 1) & (not dividido)

    def somar_faturamento(df):
        com_chave = df[df["chave"] != ""]
        unicos = com_chave.drop_duplicates(["chave", "loja"] if dividido else ["chave"])
        return unicos["faturamento"].sum()

    # --- Custo de cada loja (rateio do custo do promotor) --------------------
    lojas["custo_periodo"] = 0.0
    lojas["custo_mensal"] = 0.0
    custos_promotor = {}
    for p in proms.itertuples():
        mensal = custo_mensal_efetivo(p, regras)
        periodo = mensal * meses_de_custo(p.admissao, inicio, fim)
        custos_promotor[p.codigo] = (mensal, periodo)
        doele = lojas.index[lojas["codigo_promotor"] == p.codigo]
        if len(doele) == 0:
            continue
        visitas = lojas.loc[doele, "visitas_semana"]
        if regras["rateio_custo"] == "visitas" and visitas.notna().all() and visitas.sum() > 0:
            pesos = visitas.astype(float)
        else:
            pesos = pd.Series(1.0, index=doele)
        lojas.loc[doele, "custo_periodo"] = periodo * pesos / pesos.sum()
        lojas.loc[doele, "custo_mensal"] = mensal * pesos / pesos.sum()

    nomes = dict(zip(proms["codigo"], proms["nome"]))
    supervisores = dict(zip(proms["codigo"], proms["supervisor"]))

    # --- Tabela por promotor -------------------------------------------------
    linhas_promotores = []
    for p in proms.itertuples():
        lojas_p = lojas[lojas["codigo_promotor"] == p.codigo]
        fat_p = somar_faturamento(lojas_p)
        mensal, custo_p = custos_promotor[p.codigo]
        visitas = lojas_p["visitas_semana"].dropna()
        linhas_promotores.append({
            "codigo": p.codigo, "nome": p.nome, "supervisor": p.supervisor, "municipio": p.municipio,
            "custo_mensal": _arredondar(mensal), "custo_periodo": _arredondar(custo_p),
            "lojas": int(lojas_p["loja"].nunique()),
            "lojas_sem_compra": int((lojas_p["faturamento"] <= 0).sum()),
            "visitas_semana": _arredondar(visitas.sum()) if not visitas.empty else None,
            "faturamento": _arredondar(fat_p),
            "percentual_custo": _percentual(custo_p, fat_p),
        })
    linhas_promotores.sort(key=lambda l: (l["percentual_custo"] is None, -(l["percentual_custo"] or 0)))

    # --- Tabela por loja -----------------------------------------------------
    semanas = regras["semanas_por_mes"]
    linhas_lojas = []
    for l in lojas.itertuples():
        visitas_mes = (l.visitas_semana or 0) * semanas if not pd.isna(l.visitas_semana) else 0
        linhas_lojas.append({
            "loja": l.loja, "cnpj": l.cnpj, "cidade": l.cidade, "uf": l.uf,
            "codigo_promotor": l.codigo_promotor, "promotor": nomes.get(l.codigo_promotor, ""),
            "supervisor": supervisores.get(l.codigo_promotor, ""),
            "visitas_semana": _arredondar(l.visitas_semana),
            "faturamento": _arredondar(l.faturamento), "notas": int(l.notas),
            "meses_com_compra": int(l.meses_com_compra),
            "lojas_mesmo_cnpj": int(l.lojas_mesma_chave),
            "compartilhado": bool(l.compartilhado),
            "custo_periodo": _arredondar(l.custo_periodo),
            # Com valor compartilhado, o % da loja comparando com o total da rede não faz sentido.
            "percentual_custo": None if l.compartilhado else _percentual(l.custo_periodo, l.faturamento),
            "custo_por_visita": _arredondar(l.custo_mensal / visitas_mes) if visitas_mes > 0 else None,
        })
    linhas_lojas.sort(key=lambda l: l["faturamento"])

    # --- Resumo --------------------------------------------------------------
    custo_total = sum(l["custo_periodo"] for l in linhas_promotores)
    fat_total = somar_faturamento(lojas)
    unicas = lojas.drop_duplicates(["chave", "loja"])
    resumo = {
        "meses": total_meses,
        "promotores": len(linhas_promotores),
        "lojas": int(len(unicas)),
        "lojas_sem_compra": int((unicas["faturamento"] <= 0).sum()),
        "custo": _arredondar(custo_total),
        "faturamento": _arredondar(fat_total),
        "percentual_custo": _percentual(custo_total, fat_total),
        "cnpjs_compartilhados": int(unicas[unicas["compartilhado"]]["chave"].nunique()),
    }
    regras_usadas = {c: regras[c] for c in ("modo_rede", "rateio_custo", "faixa_alerta", "faixa_critico")}
    return {"resumo": resumo, "promotores": linhas_promotores, "lojas": linhas_lojas, "regras": regras_usadas}


def tipos_de_nota(faturamento: pd.DataFrame, regras: dict) -> list:
    """Tipos de nota existentes no faturamento importado, com a ação de cada um."""
    if faturamento.empty:
        return []
    tipos = (faturamento.groupby("chave_tipo")
                        .agg(tipo=("tipo_nf", "first"), notas=("notas", "sum"), valor=("valor", "sum"))
                        .reset_index().sort_values("valor", ascending=False))
    return [{"chave": t.chave_tipo, "tipo": t.tipo, "notas": int(t.notas), "valor": _arredondar(t.valor),
             "acao": regras["tipos_nf"].get(t.chave_tipo, "ignora")} for t in tipos.itertuples()]


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
