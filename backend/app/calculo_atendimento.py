"""Custo × faturamento a partir das duas fontes do sistema: o arquivo do ERP e os arquivos das agências.

- Custo: o valor que a agência (ou MEI, ou a própria 101) cobrou por loja no mês (tabela atendimentos).
- Faturamento: o que o CNPJ da loja comprou da 101 no mês, pelo ERP (coluna escolhida nas regras; padrão VLR TOTAL).
- Ligação: pelo CNPJ e pelo mês. Só conta o faturamento dos meses em que a loja teve atendimento.
- CNPJ de várias lojas no mesmo mês (rede que compra pelo CNPJ da matriz ou do CD): o faturamento do CNPJ é dividido
  em partes iguais entre essas lojas, e dentro da loja entre os promotores/agências dela, para a soma por promotor
  (ou agência, UF, loja) bater com o total sem contar a mesma compra duas vezes.
- "Vale a pena?": custo ÷ faturamento bruto (VLR TOTAL, sem descontar devolução nem bonificação). Até o limite
  (padrão 3%, editável) vale a pena; acima, não. Decisão do Maurício: o promotor de loja pode custar no máximo 3%
  do que as lojas dele compram. (Margem e lucro ficam para depois.)
"""
from dataclasses import dataclass

import pandas as pd

from .calculos import _percentual, aplicar_tipos_de_nota, indice_mes
from .regras import LIMITE_PADRAO


@dataclass
class FiltrosAtendimento:
    inicio: str            # "AAAA-MM"
    fim: str               # "AAAA-MM"
    agencia: str = ""      # chave da agência
    promotor: str = ""     # chave do promotor
    uf: str = ""
    cidade: str = ""
    loja: str = ""         # nome da loja
    tipo: str = ""         # Agência | CLT | MEI | Freelancer
    supervisor: str = ""   # nome do supervisor (como veio no arquivo)


def _rotulo(indice: int) -> str:
    return f"{indice // 12}-{indice % 12 + 1:02d}"


def _dinheiro(valor) -> float:
    return round(float(valor or 0), 2)


def _juntar(valores) -> str:
    return ", ".join(sorted({v for v in valores if v}))


def faturamento_por_cnpj_mes(faturamento: pd.DataFrame, regras: dict) -> pd.DataFrame:
    """Faturamento do ERP somado por CNPJ e mês (índice ano × 12 + mês − 1), com as regras de tipo de nota."""
    if faturamento.empty:
        return pd.DataFrame(columns=["indice", "cnpj", "fat_cnpj"])
    fat = aplicar_tipos_de_nota(faturamento, regras)
    fat["indice"] = fat["ano"].astype(int) * 12 + fat["mes"].astype(int) - 1
    return fat.groupby(["indice", "cnpj"], as_index=False)["valor"].sum().rename(columns={"valor": "fat_cnpj"})


def atribuir_faturamento(atend: pd.DataFrame, fat_mes: pd.DataFrame) -> pd.DataFrame:
    """Cada linha de atendimento recebe a sua parte do faturamento do CNPJ naquele mês."""
    a = atend.copy()
    a["indice"] = a["ano"].astype(int) * 12 + a["mes"].astype(int) - 1
    com_cnpj = a["cnpj"] != ""
    lojas = (a[com_cnpj].groupby(["indice", "cnpj"])["loja_chave"].nunique().rename("lojas_cnpj").reset_index())
    linhas_loja = (a.groupby(["indice", "cnpj", "loja_chave"]).size().rename("linhas_loja").reset_index())
    a = (a.merge(lojas, on=["indice", "cnpj"], how="left")
          .merge(linhas_loja, on=["indice", "cnpj", "loja_chave"], how="left")
          .merge(fat_mes, on=["indice", "cnpj"], how="left"))
    a["fat_cnpj"] = a["fat_cnpj"].fillna(0.0).where(com_cnpj.values, 0.0)
    a["lojas_cnpj"] = a["lojas_cnpj"].fillna(1)
    a["faturamento"] = a["fat_cnpj"] / a["lojas_cnpj"] / a["linhas_loja"]
    a["compartilhado"] = a["lojas_cnpj"] > 1
    return a


def situacao(custo: float, faturamento: float, limite: float, sem_erp: bool = False) -> str:
    """ok (até o limite) | acima (passou do limite) | sem_compras (custo sem nenhuma compra) | sem_custo |
    sem_erp (o faturamento do período ainda não foi importado)."""
    if sem_erp:
        return "sem_erp"
    if custo <= 0:
        return "sem_custo"
    if faturamento <= 0:
        return "sem_compras"
    return "ok" if custo / faturamento * 100 <= limite + 1e-9 else "acima"


def _indicadores(custo: float, faturamento: float, limite: float, sem_erp: bool = False) -> dict:
    custo, faturamento = float(custo), float(faturamento)
    return {"custo_periodo": _dinheiro(custo), "faturamento": _dinheiro(faturamento),
            "percentual_custo": _percentual(custo, faturamento), "sem_erp": sem_erp,
            "situacao": situacao(custo, faturamento, limite, sem_erp)}


def _indicadores_grupo(g: pd.DataFrame, limite: float) -> dict:
    """Indicadores de um grupo de linhas; sem_erp = nenhum mês do grupo tem faturamento do ERP importado."""
    return _indicadores(g["valor"].sum(), g["faturamento"].sum(), limite, not bool(g["tem_erp"].any()))


def calcular(faturamento: pd.DataFrame, atend: pd.DataFrame, filtros: FiltrosAtendimento, regras: dict) -> dict:
    inicio, fim = sorted([indice_mes(filtros.inicio), indice_mes(filtros.fim)])
    meses = list(range(inicio, fim + 1))
    limite = regras.get("limite_percentual") or LIMITE_PADRAO
    fat_mes = faturamento_por_cnpj_mes(faturamento, regras)
    fat_mes = fat_mes[fat_mes["indice"].between(inicio, fim)]

    a = atend.copy()
    a["indice"] = a["ano"].astype(int) * 12 + a["mes"].astype(int) - 1 if not a.empty else pd.Series(dtype=int)
    a = a[a["indice"].between(inicio, fim)] if not a.empty else a
    # A divisão do faturamento do CNPJ usa todas as lojas do mês, antes dos filtros (o filtro só escolhe o que mostrar).
    a = atribuir_faturamento(a, fat_mes) if not a.empty else a.assign(faturamento=0.0, compartilhado=False)
    # Meses do período que têm faturamento do ERP importado (de qualquer cliente). Loja atendida num mês sem ERP
    # não "não comprou": o faturamento daquele mês só ainda não foi importado.
    meses_erp = set(int(m) for m in fat_mes["indice"].unique())
    a = a.assign(tem_erp=a["indice"].isin(meses_erp) if not a.empty else pd.Series(dtype=bool))
    if filtros.agencia:
        a = a[a["agencia_chave"] == filtros.agencia]
    if filtros.promotor:
        a = a[a["promotor_chave"] == filtros.promotor]
    if filtros.uf:
        a = a[a["uf"] == filtros.uf]
    if filtros.cidade:
        a = a[a["cidade"] == filtros.cidade]
    if filtros.loja:
        a = a[a["loja"] == filtros.loja]
    if filtros.tipo:
        a = a[a["tipo"] == filtros.tipo]
    if filtros.supervisor:
        a = a[a["supervisor"] == filtros.supervisor]

    meses_com_atendimento = sorted(a["indice"].unique().tolist()) if not a.empty else []
    custo_total, fat_total = float(a["valor"].sum()) if not a.empty else 0.0, float(a["faturamento"].sum()) if not a.empty else 0.0
    # Agências sem custo no período (ex.: promotores CLT/MEI informados com R$ 0): contadas à parte, para não inflar
    # os números de agências, promotores e lojas.
    if not a.empty:
        custo_agencia = a.groupby("agencia_chave")["valor"].sum()
        sem_custo = set(custo_agencia[custo_agencia <= 0].index)
    else:
        sem_custo = set()
    com_custo = a[~a["agencia_chave"].isin(sem_custo)] if not a.empty else a
    zerada = a[a["agencia_chave"].isin(sem_custo)] if not a.empty else a

    def _contar(df):
        if df.empty:
            return 0, 0, 0
        return (int(df["agencia_chave"].nunique()), int(df["promotor_chave"].nunique()),
                int(df[["cnpj", "loja_chave"]].drop_duplicates().shape[0]))
    agencias, promotores, lojas = _contar(com_custo)
    agencias_zero, promotores_zero, lojas_zero = _contar(zerada)
    resumo = {**_indicadores(custo_total, fat_total, limite, not meses_erp),
              "custo": _dinheiro(custo_total), "meses": len(meses),
              "meses_com_arquivo": len(meses_com_atendimento),
              "promotores": promotores, "lojas": lojas, "agencias": agencias,
              "agencias_sem_custo": agencias_zero, "promotores_sem_custo": promotores_zero,
              "lojas_sem_custo": lojas_zero,
              "visitas": int(a["visitas"].fillna(0).sum()) if not a.empty else 0,
              "cnpjs_compartilhados": int(a.loc[a["compartilhado"], "cnpj"].nunique()) if not a.empty else 0,
              "avisos": _avisos(a, meses, meses_com_atendimento, meses_erp)}

    return {
        "resumo": resumo,
        "regras": {"limite_percentual": limite, "valor_faturamento": regras.get("valor_faturamento")},
        "promotores": _por_promotor(a, limite),
        "lojas": _por_loja(a, limite),
        "agencias": _por_agencia(a, limite),
        "por_uf": _arvore(a, limite),
        "mes_a_mes": _mes_a_mes(a, meses, limite, meses_erp),
        "grade": _grade(a, meses),
    }


def _avisos(a: pd.DataFrame, meses: list, com_atendimento: list, meses_erp: set) -> list[str]:
    avisos = []
    sem_erp = [m for m in com_atendimento if m not in meses_erp]
    if sem_erp:
        avisos.append("Sem faturamento do ERP importado em " + ", ".join(_rotulo(m) for m in sem_erp)
                      + ": nesses meses as lojas aparecem com compras R$ 0,00 e o resultado fica negativo. "
                      "Importe o faturamento desses meses na aba Faturamento.")
    sem_arquivo = [m for m in meses if m not in com_atendimento]
    if a.empty:
        avisos.append("Nenhum atendimento de agência no período. Importe os arquivos das agências na aba Agências.")
    elif sem_arquivo:
        avisos.append("Meses do período sem nenhum arquivo de agência (custo zero nesses meses): "
                      + ", ".join(_rotulo(m) for m in sem_arquivo))
    if not a.empty:
        sem_cnpj = a.loc[a["cnpj"] == "", "loja"].unique()
        if len(sem_cnpj):
            avisos.append(f"{len(sem_cnpj)} loja(s) sem CNPJ válido no arquivo da agência: aparecem sem faturamento ("
                          + ", ".join(sem_cnpj[:6]) + (" …" if len(sem_cnpj) > 6 else "") + ").")
    return avisos


def _por_promotor(a: pd.DataFrame, limite) -> list[dict]:
    if a.empty:
        return []
    linhas = []
    for chave, g in a.groupby("promotor_chave", sort=False):
        ultimo = g[g["indice"] == g["indice"].max()]
        linhas.append({
            "chave": chave, "nome": ultimo["promotor"].iloc[-1], "codigo": _juntar(g["promotor_codigo"]),
            "agencia": _juntar(g["agencia"]), "agencia_chave": g["agencia_chave"].iloc[-1],
            "tipo": _juntar(g["tipo"]), "supervisor": _juntar(ultimo["supervisor"]), "ufs": _juntar(g["uf"]), "cidades": _juntar(g["cidade"]),
            "lojas": int(g[["cnpj", "loja_chave"]].drop_duplicates().shape[0]),
            "lojas_ultimo_mes": int(ultimo[["cnpj", "loja_chave"]].drop_duplicates().shape[0]),
            "visitas": int(g["visitas"].fillna(0).sum()),
            "primeiro_mes": _rotulo(int(g["indice"].min())), "ultimo_mes": _rotulo(int(g["indice"].max())),
            "meses_com_atendimento": int(g["indice"].nunique()),
            **_indicadores_grupo(g, limite),
        })
    return sorted(linhas, key=lambda l: l["nome"])


def _por_loja(a: pd.DataFrame, limite) -> list[dict]:
    if a.empty:
        return []
    linhas = []
    for (cnpj, loja_chave), g in a.groupby(["cnpj", "loja_chave"], sort=False):
        ultimo = g[g["indice"] == g["indice"].max()]
        linhas.append({
            "chave": f"{cnpj}|{loja_chave}", "loja": ultimo["loja"].iloc[-1], "cnpj": cnpj,
            "cidade": ultimo["cidade"].iloc[-1], "uf": ultimo["uf"].iloc[-1],
            "agencia": _juntar(g["agencia"]), "agencia_chaves": sorted(set(g["agencia_chave"])), "tipo": _juntar(g["tipo"]),
            "promotor": _juntar(ultimo["promotor"]), "supervisor": _juntar(ultimo["supervisor"]),
            "promotor_chaves": sorted(set(g["promotor_chave"])), "dias": _juntar(ultimo["dias"]),
            "visitas": int(g["visitas"].fillna(0).sum()), "compartilhado": bool(g["compartilhado"].any()),
            "status": ultimo["status"].iloc[-1], "meses_com_atendimento": int(g["indice"].nunique()),
            **_indicadores_grupo(g, limite),
        })
    return sorted(linhas, key=lambda l: (l["uf"], l["cidade"], l["loja"]))


def _por_agencia(a: pd.DataFrame, limite) -> list[dict]:
    if a.empty:
        return []
    linhas = []
    for chave, g in a.groupby("agencia_chave", sort=False):
        linhas.append({
            "chave": chave, "nome": g["agencia"].iloc[-1], "tipo": _juntar(g["tipo"]), "ufs": _juntar(g["uf"]),
            "lojas": int(g[["cnpj", "loja_chave"]].drop_duplicates().shape[0]),
            "promotores": int(g["promotor_chave"].nunique()), "visitas": int(g["visitas"].fillna(0).sum()),
            "meses": sorted(_rotulo(int(m)) for m in g["indice"].unique()),
            **_indicadores_grupo(g, limite),
        })
    return sorted(linhas, key=lambda l: l["nome"])


def _arvore(a: pd.DataFrame, limite) -> list[dict]:
    """Linhas na ordem UF → agência → promotor (a tabela do Resumo abre em níveis)."""
    if a.empty:
        return []
    linhas = []

    def linha(nivel, nome, g, **extra):
        return {"nivel": nivel, "nome": nome, "promotores": int(g["promotor_chave"].nunique()),
                "lojas": int(g[["cnpj", "loja_chave"]].drop_duplicates().shape[0]),
                "visitas": int(g["visitas"].fillna(0).sum()),
                **_indicadores_grupo(g, limite), **extra}

    a = a.assign(uf=a["uf"].replace("", "—"))
    for uf, gu in sorted(a.groupby("uf"), key=lambda x: (x[0] == "—", x[0])):
        linhas.append(linha("uf", uf, gu, uf=uf))
        for agencia_chave, ga in sorted(gu.groupby("agencia_chave"), key=lambda x: x[1]["agencia"].iloc[-1]):
            linhas.append(linha("agencia", ga["agencia"].iloc[-1], ga, uf=uf, agencia_chave=agencia_chave))
            for chave, gp in sorted(ga.groupby("promotor_chave"), key=lambda x: x[1]["promotor"].iloc[-1]):
                linhas.append(linha("promotor", gp["promotor"].iloc[-1], gp, uf=uf, chave=chave,
                                    agencia_chave=agencia_chave))
    return linhas


def _mes_a_mes(a: pd.DataFrame, meses: list, limite, meses_erp: set) -> list[dict]:
    linhas = []
    for indice in meses:
        g = a[a["indice"] == indice] if not a.empty else a
        vazio = g.empty
        linhas.append({"mes": _rotulo(indice), "com_atendimento": not vazio,
                       "lojas": 0 if vazio else int(g[["cnpj", "loja_chave"]].drop_duplicates().shape[0]),
                       "visitas": 0 if vazio else int(g["visitas"].fillna(0).sum()),
                       **_indicadores(0 if vazio else g["valor"].sum(), 0 if vazio else g["faturamento"].sum(),
                                      limite, indice not in meses_erp)})
    return linhas


def _grade(a: pd.DataFrame, meses: list) -> dict:
    """Faturamento mês a mês de cada loja (clicável para ver as notas)."""
    rotulos = [_rotulo(m) for m in meses]
    linhas = []
    if not a.empty:
        por_loja = a.groupby(["cnpj", "loja_chave", "indice"])["faturamento"].sum()
        for numero, ((cnpj, loja_chave), g) in enumerate(a.groupby(["cnpj", "loja_chave"], sort=False)):
            ultimo = g[g["indice"] == g["indice"].max()]
            valores = {_rotulo(m): _dinheiro(por_loja.get((cnpj, loja_chave, m), 0.0)) for m in meses}
            linhas.append({"linha": numero, "agencia": _juntar(g["agencia"]), "promotor": _juntar(ultimo["promotor"]),
                           "cnpj": cnpj, "loja": ultimo["loja"].iloc[-1], "cidade": ultimo["cidade"].iloc[-1],
                           "uf": ultimo["uf"].iloc[-1], "meses": valores, "total": _dinheiro(sum(valores.values())),
                           "compartilhado": bool(g["compartilhado"].any()),
                           "detalhe": {"cnpj": cnpj, "cod_cli": ""}})
        linhas.sort(key=lambda l: (l["uf"], l["agencia"], l["promotor"], l["loja"]))
    totais = {r: _dinheiro(sum(l["meses"][r] for l in linhas)) for r in rotulos}
    return {"meses": rotulos, "linhas": linhas, "totais": {**totais, "total": _dinheiro(sum(totais.values()))}}


def opcoes(faturamento: pd.DataFrame, atend: pd.DataFrame) -> dict:
    meses = {f"{int(y)}-{int(m):02d}" for y, m in zip(faturamento["ano"], faturamento["mes"])}
    meses |= {f"{int(y)}-{int(m):02d}" for y, m in zip(atend["ano"], atend["mes"])}
    locais = atend[["uf", "cidade"]].replace("", pd.NA).dropna().drop_duplicates().sort_values(["uf", "cidade"])
    ultimas = atend.sort_values(["ano", "mes"])
    promotores = ultimas.drop_duplicates("promotor_chave", keep="last").sort_values("promotor")
    agencias = ultimas.drop_duplicates("agencia_chave", keep="last").sort_values("agencia")
    lojas = ultimas.drop_duplicates(["cnpj", "loja_chave"], keep="last").drop_duplicates("loja").sort_values("loja")
    return {
        "meses": sorted(meses),
        "agencias": [{"chave": l.agencia_chave, "nome": l.agencia} for l in agencias.itertuples()],
        "promotores": [{"chave": l.promotor_chave, "nome": l.promotor, "agencia_chave": l.agencia_chave,
                        "agencia": l.agencia} for l in promotores.itertuples()],
        "lojas": [{"nome": l.loja, "cidade": l.cidade, "uf": l.uf} for l in lojas.itertuples()],
        "ufs": sorted(u for u in atend["uf"].unique() if u),
        "cidades": [{"uf": l.uf, "cidade": l.cidade} for l in locais.itertuples()],
        "tipos": [t for t in ("Agência", "CLT", "MEI", "Freelancer") if t in set(atend["tipo"])],
        "supervisores": sorted({s for s in atend["supervisor"] if s}, key=str.casefold),
    }
