"""Leitura das planilhas (Excel ou CSV) e conversão para as tabelas do sistema.

Os nomes de coluna são procurados por apelidos, sem diferenciar acento, maiúscula
ou pontuação. Se o layout real mudar, basta acrescentar o novo nome na lista.
"""
import io
import re
import unicodedata

import pandas as pd

SEM_TIPO = "Sem tipo"


class ErroImportacao(Exception):
    pass


# ---------------------------------------------------------------------------
# Normalização
# ---------------------------------------------------------------------------

def normalizar_texto(valor) -> str:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    texto = unicodedata.normalize("NFKD", str(valor)).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]+", " ", texto.upper()).strip()


def normalizar_cnpj(valor) -> str:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    digitos = re.sub(r"\D", "", str(valor))
    # Excel costuma comer o zero da frente quando o CNPJ vira número.
    if len(digitos) in (12, 13):
        digitos = digitos.zfill(14)
    return digitos


def normalizar_codigo(valor) -> str:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return str(valor).strip()


def converter_numero(valor) -> float:
    """Aceita número do Excel ou texto no formato brasileiro (R$ 1.234,56)."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = re.sub(r"[^\d,.\-]", "", str(valor))
    if not texto or texto in "-.,":
        return 0.0
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# Localizar cabeçalho e colunas
# ---------------------------------------------------------------------------

def _ler_abas(conteudo: bytes, nome_arquivo: str):
    """Devolve (nome_da_aba, função que lê a aba com header=None)."""
    if nome_arquivo.lower().endswith(".csv"):
        texto = conteudo.decode("utf-8-sig", errors="replace")
        separador = ";" if texto.split("\n", 1)[0].count(";") > texto.split("\n", 1)[0].count(",") else ","

        def ler_csv(**kwargs):
            return pd.read_csv(io.StringIO(texto), sep=separador, header=None, dtype=object, **kwargs)
        return [("CSV", ler_csv)]

    try:
        excel = pd.ExcelFile(io.BytesIO(conteudo))
    except Exception as erro:
        raise ErroImportacao(f"Não consegui abrir o arquivo como Excel: {erro}") from erro

    def leitor(aba):
        def ler(**kwargs):
            return excel.parse(aba, header=None, dtype=object, **kwargs)
        return ler
    return [(aba, leitor(aba)) for aba in excel.sheet_names]


def _mapear_colunas(linha, apelidos: dict) -> dict:
    """Para cada campo, a posição da primeira coluna cujo nome bate com um apelido."""
    nomes = {}
    for posicao, celula in enumerate(linha):
        nomes.setdefault(normalizar_texto(celula), posicao)
    mapa = {}
    for campo, opcoes in apelidos.items():
        for opcao in opcoes:
            if normalizar_texto(opcao) in nomes:
                mapa[campo] = nomes[normalizar_texto(opcao)]
                break
    return mapa


def ler_tabelas(conteudo: bytes, nome_arquivo: str, apelidos: dict, valida) -> list:
    """Procura, em todas as abas, a linha de cabeçalho que satisfaz `valida(mapa)`.

    Retorna uma lista de (aba, DataFrame com as colunas renomeadas para os campos).
    """
    encontradas = []
    for aba, ler in _ler_abas(conteudo, nome_arquivo):
        previa = ler(nrows=30)
        melhor = None
        for indice, linha in previa.iterrows():
            mapa = _mapear_colunas(linha.tolist(), apelidos)
            if valida(mapa) and (melhor is None or len(mapa) > len(melhor[1])):
                melhor = (indice, mapa)
        if melhor is None:
            continue
        linha_cabecalho, mapa = melhor
        dados = ler(skiprows=linha_cabecalho + 1)
        tabela = pd.DataFrame({campo: dados.iloc[:, posicao] for campo, posicao in mapa.items()
                               if posicao < dados.shape[1]})
        encontradas.append((aba, tabela))
    return encontradas


def _descrever(apelidos: dict, campos) -> str:
    return "; ".join(f"{c} ({' / '.join(apelidos[c][:3])})" for c in campos)


# ---------------------------------------------------------------------------
# Faturamento (exportação do ERP, uma linha por item de nota)
# ---------------------------------------------------------------------------

# Campo do sistema -> nomes de coluna aceitos (a ordem define a preferência).
APELIDOS_FATURAMENTO = {
    "data_emissao": ["DT EMIS", "DT EMISSAO", "DATA EMISSAO", "DATA"],
    "ano": ["ANO"],
    "mes": ["MES"],
    "cod_emp": ["COD EMP", "COD EMPRESA"],
    "num_nf": ["NUM NF", "NUM", "NUMERO NF", "NUMERO", "NF", "NOTA"],
    "cod_segmento": ["COD SEGMENTO", "COD SEGM"],
    "descricao_segmento": ["DESCRICAO SEGMENTO"],
    "cod_cli": ["COD CLI", "COD CLIENTE", "CODIGO CLIENTE"],
    "cod_est": ["COD EST", "COD ESTABELECIMENTO"],
    "tp_pes": ["TP PES", "TIPO PESSOA"],
    "cnpj_cpf": ["CNPJ CPF", "CNPJ", "CPF CNPJ", "CPFCNPJ"],
    "razao_social": ["RAZAO SOCIAL", "NOME CLIENTE", "CLIENTE", "NOME", "1"],
    "cidade": ["CIDADE", "MUNICIPIO"],
    "uf": ["UF", "ESTADO"],
    "cod_rep": ["COD REP", "COD REPRESENTANTE"],
    "representante": ["REPRESENTANTE"],
    "familia_2": ["FAMILIA 2"],
    "familia_4": ["FAMILIA 4"],
    "marca": ["MARCA"],
    "embalagem": ["EMBALAGEM"],
    "volume": ["VOLUME"],
    "um": ["UM"],
    "cod_item": ["COD ITEM"],
    "descricao_item": ["DESCRICAO ITEM"],
    "qtde": ["QTDE", "QTD"],
    "ump": ["UMP"],
    "preco_unit": ["PRECO UNIT", "PRECO UN"],
    "vlr_mercadoria": ["VLR MERCADORIA"],
    "vlr_total": ["VLR TOTAL", "VLR TOT", "VALOR TOTAL"],
    "cod_tp_nf": ["COD TP NF"],
    "tipo_nf": ["TIPO NF", "TIPO NOTA"],
    "cfop": ["CFOP"],
    "receita": ["RECEITA"],
    "cond_pgto": ["COND PGTO"],
    "qtde_caixa": ["QTDE CAIXA"],
    "bonificacao": ["BONIFICACAO"],
    "total_venda": ["TOTAL VENDA", "TOTAL VENDAS"],
    "grupo": ["GRUPO"],
}
CAMPOS_NUMERICOS = ("qtde", "preco_unit", "vlr_mercadoria", "vlr_total", "qtde_caixa", "bonificacao", "total_venda")
CAMPOS_TEXTO = [c for c in APELIDOS_FATURAMENTO
                if c not in CAMPOS_NUMERICOS + ("data_emissao", "ano", "mes", "cnpj_cpf", "tipo_nf")]
TAMANHOS = {"cod_emp": 20, "num_nf": 30, "cod_segmento": 20, "descricao_segmento": 120, "cod_cli": 30, "cod_est": 20,
            "tp_pes": 2, "razao_social": 200, "cidade": 120, "uf": 2, "cod_rep": 20, "representante": 150,
            "familia_2": 120, "familia_4": 150, "marca": 150, "embalagem": 40, "volume": 20, "um": 10,
            "cod_item": 30, "descricao_item": 255, "ump": 20, "cod_tp_nf": 20, "cfop": 10, "receita": 10,
            "cond_pgto": 60, "grupo": 60}


def _valida_faturamento(mapa):
    tem_periodo = "data_emissao" in mapa or ("ano" in mapa and "mes" in mapa)
    tem_valor = "total_venda" in mapa or "vlr_total" in mapa
    return tem_periodo and tem_valor and all(c in mapa for c in ("cnpj_cpf", "num_nf"))


def numero_ou_nada(valor):
    """Número do Excel ou texto brasileiro; vazio/"-" = 0; texto que não é número = None (erro)."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip()
    if texto in ("", "-", "R$ -", "R$-"):
        return 0.0
    limpo = re.sub(r"[^\d,.\-]", "", texto)
    if not limpo or not re.search(r"\d", limpo):
        return None
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    try:
        return float(limpo)
    except ValueError:
        return None


def _texto_celula(valor):
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    return normalizar_codigo(valor) or None


def ler_faturamento(conteudo: bytes, nome_arquivo: str):
    """Lê a exportação do ERP. Devolve (itens válidos, erros [{linha, motivo}], avisos, aba)."""
    tabelas = ler_tabelas(conteudo, nome_arquivo, APELIDOS_FATURAMENTO, _valida_faturamento)
    if not tabelas:
        raise ErroImportacao(
            "Não encontrei a base de faturamento. Colunas obrigatórias: CNPJ CPF, NUM NF, TOTAL VENDA (ou VLR TOTAL) "
            "e a data de emissão (ou ANO e MÊS).")
    aba, df = tabelas[0]
    avisos = []
    if len(tabelas) > 1:
        avisos.append(f"Mais de uma aba parece base de faturamento; usei só a aba '{aba}'.")
    for campo in APELIDOS_FATURAMENTO:
        if campo not in df:
            df[campo] = None
    if df["total_venda"].isna().all():
        avisos.append("O arquivo não tem a coluna TOTAL VENDA; usei VLR TOTAL no lugar.")
        df["total_venda"] = df["vlr_total"]

    # Número da linha no Excel, para o relatório de erros (cabeçalho + 1).
    df["linha"] = range(2, len(df) + 2)
    df = df[~df[["cnpj_cpf", "num_nf", "total_venda", "vlr_total"]].isna().all(axis=1)]  # linhas vazias

    df["cnpj_cpf"] = df["cnpj_cpf"].map(normalizar_cnpj)
    datas = pd.to_datetime(df["data_emissao"], errors="coerce", dayfirst=True)
    ano = pd.to_numeric(df["ano"], errors="coerce").fillna(datas.dt.year)
    mes = pd.to_numeric(df["mes"], errors="coerce").fillna(datas.dt.month)
    df["ano"], df["mes"] = ano, mes
    df["data_emissao"] = datas.dt.date
    for campo in CAMPOS_NUMERICOS:
        df[campo] = df[campo].map(numero_ou_nada)

    erros = []
    motivos = pd.Series("", index=df.index)
    motivos[df["cnpj_cpf"] == ""] = "CNPJ/CPF vazio"
    motivos[(motivos == "") & (df["ano"].isna() | df["mes"].isna() | ~df["mes"].between(1, 12))] = "data inválida"
    motivos[(motivos == "") & df["total_venda"].isna()] = "TOTAL VENDA não é número"
    for linha, motivo in zip(df.loc[motivos != "", "linha"], motivos[motivos != ""]):
        erros.append({"linha": int(linha), "motivo": motivo})
    df = df[motivos == ""].copy()

    df["ano"] = df["ano"].astype(int)
    df["mes"] = df["mes"].astype(int)
    for campo in CAMPOS_TEXTO:
        df[campo] = df[campo].map(_texto_celula).map(
            lambda v, t=TAMANHOS[campo]: v[:t] if isinstance(v, str) else v)
    df["cod_cli"] = df["cod_cli"].fillna("")
    df["tipo_nf"] = df["tipo_nf"].fillna("").astype(str).str.strip().replace("", SEM_TIPO).str[:60]
    df["tipo_nf_chave"] = df["tipo_nf"].map(normalizar_texto)
    df["data_emissao"] = df["data_emissao"].where(df["data_emissao"].notna(), None)
    return df.drop(columns=["linha"]), erros, avisos, aba


# ---------------------------------------------------------------------------
# Totais das abas por UF (para conferir com o sistema)
# ---------------------------------------------------------------------------

MESES_ABREVIADOS = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]
APELIDOS_TOTAIS_UF = {
    "cnpj": ["CPF CNPJ", "CNPJ CPF", "CPFCNPJ", "CNPJ"],
    "loja": ["RAZAO SOCIAL", "LOJA"],
    "uf": ["UF", "ESTADO"],
    **{f"m{i + 1}": [m] for i, m in enumerate(MESES_ABREVIADOS)},
}


def ler_totais_abas_uf(conteudo: bytes, nome_arquivo: str) -> pd.DataFrame:
    """Faturamento mês a mês de cada linha das abas SC, SP, PR… (como a planilha calculou)."""
    def valida(mapa):
        return "loja" in mapa and "cnpj" in mapa and sum(1 for c in mapa if c.startswith("m")) >= 6

    linhas = []
    for aba, df in ler_tabelas(conteudo, nome_arquivo, APELIDOS_TOTAIS_UF, valida):
        df = df[df["loja"].notna()]
        for mes in range(1, 13):
            coluna = f"m{mes}"
            if coluna not in df:
                continue
            valores = df[coluna].map(numero_ou_nada).fillna(0)
            linhas += [{"aba": aba, "cnpj": normalizar_cnpj(c), "loja": str(l).strip(), "mes": mes, "valor": float(v)}
                       for c, l, v in zip(df["cnpj"], df["loja"], valores)]
    return pd.DataFrame(linhas, columns=["aba", "cnpj", "loja", "mes", "valor"])


# ---------------------------------------------------------------------------
# Promotores (custo)
# ---------------------------------------------------------------------------

APELIDOS_PROMOTORES = {
    "codigo": ["CODIGO", "COD", "MATRICULA"],
    "nome": ["COLABORADOR", "NOME", "PROMOTOR"],
    "admissao": ["ADMISSAO", "DATA ADMISSAO"],
    "municipio": ["MUNICIPIO", "CIDADE"],
    "supervisor": ["SUPERVISOR"],
    "salario": ["SALARIO"],
    "ajuda_custo": ["AJUD CUSTO", "AJUDA CUSTO", "AJUDA DE CUSTO"],
    "transporte": ["V TRANSP", "VALE TRANSPORTE", "TRANSPORTE"],
    "total": ["TOTAL", "CUSTO TOTAL"],
}


def _valida_promotores(mapa):
    return "codigo" in mapa and "nome" in mapa and ("total" in mapa or "salario" in mapa)


def importar_promotores(conteudo: bytes, nome_arquivo: str):
    tabelas = ler_tabelas(conteudo, nome_arquivo, APELIDOS_PROMOTORES, _valida_promotores)
    if not tabelas:
        raise ErroImportacao(
            "Não encontrei a lista de promotores. Colunas obrigatórias: "
            + _descrever(APELIDOS_PROMOTORES, ["codigo", "nome"]) + " e TOTAL (ou Salário).")
    aba, df = tabelas[0]

    df["codigo"] = df["codigo"].map(normalizar_codigo)
    df["nome"] = df["nome"].fillna("").astype(str).str.strip()
    df = df[(df["codigo"] != "") & (df["nome"] != "")]

    for campo in ("salario", "ajuda_custo", "transporte", "total"):
        df[campo] = df[campo].map(converter_numero) if campo in df else 0.0
    soma = df["salario"] + df["ajuda_custo"] + df["transporte"]
    df["custo_mensal"] = df["total"].where(df["total"] > 0, soma)

    if "admissao" in df:
        df["admissao"] = pd.to_datetime(df["admissao"], errors="coerce", dayfirst=True).dt.strftime("%Y-%m-%d")
    for campo in ("admissao", "municipio", "supervisor"):
        if campo not in df:
            df[campo] = ""
        df[campo] = df[campo].fillna("").astype(str).str.strip()

    avisos = []
    repetidos = df[df["codigo"].duplicated(keep=False)]
    if not repetidos.empty:
        avisos.append("Códigos repetidos (mantive a última linha): "
                      + ", ".join(sorted(repetidos["codigo"].unique())))
        df = df.drop_duplicates("codigo", keep="last")
    sem_supervisor = df[df["supervisor"] == ""]
    if not sem_supervisor.empty:
        avisos.append(f"{len(sem_supervisor)} promotor(es) sem supervisor.")

    resumo = {"aba": aba, "promotores": len(df), "avisos": avisos}
    return df, resumo


# ---------------------------------------------------------------------------
# Roteiro (qual promotor atende qual loja)
# ---------------------------------------------------------------------------

APELIDOS_ROTEIRO = {
    "codigo_promotor": ["COD PROMOTOR", "CODIGO PROMOTOR", "COD COLABORADOR", "CODIGO COLABORADOR"],
    "colaborador": ["COLABORADOR", "PROMOTOR"],
    "cnpj": ["CPF CNPJ", "CNPJ CPF", "CPFCNPJ", "CNPJ"],
    "loja": ["RAZAO SOCIAL", "LOJA"],
    "cidade": ["CIDADE", "MUNICIPIO"],
    "uf": ["UF", "ESTADO"],
    "visitas_semana": ["VISITAS SEMANA", "VISITAS POR SEMANA", "FREQUENCIA", "FREQUENCIA SEMANAL"],
}


def _valida_roteiro(mapa):
    return ("codigo_promotor" in mapa or "colaborador" in mapa) and "loja" in mapa


def importar_roteiro(conteudo: bytes, nome_arquivo: str):
    """Lê todas as abas que tenham promotor + loja (ex.: abas SC, SP… da planilha atual)."""
    tabelas = ler_tabelas(conteudo, nome_arquivo, APELIDOS_ROTEIRO, _valida_roteiro)
    if not tabelas:
        raise ErroImportacao(
            "Não encontrei o roteiro. Colunas obrigatórias: Colaborador (ou código do promotor) "
            "e Razão Social/Loja. CNPJ, Cidade, UF e Visitas por semana são opcionais.")
    partes = []
    for aba, df in tabelas:
        for campo in APELIDOS_ROTEIRO:
            if campo not in df:
                df[campo] = None
        df["aba"] = aba
        partes.append(df)
    df = pd.concat(partes, ignore_index=True)

    df["codigo_promotor"] = df["codigo_promotor"].map(normalizar_codigo)
    df["cnpj"] = df["cnpj"].map(normalizar_cnpj)
    for campo in ("colaborador", "loja", "cidade", "uf"):
        df[campo] = df[campo].fillna("").astype(str).str.strip()
    df["uf"] = df["uf"].str.upper()
    df["visitas_semana"] = pd.to_numeric(df["visitas_semana"], errors="coerce")
    df = df[(df["loja"] != "") & ((df["codigo_promotor"] != "") | (df["colaborador"] != ""))]
    df = df.drop_duplicates(["codigo_promotor", "colaborador", "cnpj", "loja"])

    avisos = []
    sem_cnpj = int((df["cnpj"] == "").sum())
    if sem_cnpj:
        avisos.append(f"{sem_cnpj} loja(s) sem CNPJ: aparecem no roteiro, mas sem faturamento.")
    resumo = {"abas": [aba for aba, _ in tabelas], "lojas": len(df), "avisos": avisos}
    return df, resumo


def vincular_roteiro(roteiro: pd.DataFrame, promotores: pd.DataFrame):
    """Preenche o código do promotor pelo nome quando o roteiro só tem o nome.

    Devolve o roteiro vinculado e a lista de nomes que não bateram com nenhum promotor.
    """
    roteiro = roteiro.copy()
    por_nome = {normalizar_texto(n): c for c, n in zip(promotores["codigo"], promotores["nome"])}
    faltando = roteiro["codigo_promotor"].fillna("") == ""
    roteiro.loc[faltando, "codigo_promotor"] = (
        roteiro.loc[faltando, "colaborador"].map(lambda n: por_nome.get(normalizar_texto(n), "")))
    codigos = set(promotores["codigo"])
    sem_vinculo = roteiro[~roteiro["codigo_promotor"].isin(codigos)]
    nomes = sorted(set(sem_vinculo["colaborador"].replace("", pd.NA).dropna())
                   | set(sem_vinculo["codigo_promotor"].replace("", pd.NA).dropna()))
    return roteiro[roteiro["codigo_promotor"].isin(codigos)], nomes
