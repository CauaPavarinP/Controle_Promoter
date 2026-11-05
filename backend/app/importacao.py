"""Leitura das planilhas (Excel ou CSV) e conversão para as tabelas do sistema.

Os nomes de coluna são procurados por apelidos, sem diferenciar acento, maiúscula
ou pontuação. Se o layout real mudar, basta acrescentar o novo nome na lista.
"""
import io
import re
import unicodedata

import numpy as np
import pandas as pd

from .leitor_xlsx import ArquivoNaoSuportado, LivroXlsx

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


# Número escrito como texto. Formato brasileiro (1.234,56 / 1234,56 / 1.200) ou com ponto decimal (1234.56).
# Qualquer outra coisa ("600 + 120m", "R$ 600 a 700", "1,2,3") NÃO é número: antes os dígitos eram colados
# ("600 + 120m" virava 600120).
_NUMERO_BR = re.compile(r"-?(\d{1,3}(\.\d{3})+|\d+)(,\d+)?")
_NUMERO_PONTO = re.compile(r"-?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?")


def ler_numero(valor):
    """Número do Excel ou texto com UM número (aceita R$, espaços nas pontas e "-" = zero).

    Vazio = 0. Texto que não é exatamente um número = None (quem chama decide se é erro).
    """
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return 0.0
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).replace("\xa0", " ").strip()
    texto = re.sub(r"^R\$\s*", "", texto, flags=re.IGNORECASE).strip()
    if texto in ("", "-"):
        return 0.0
    if _NUMERO_BR.fullmatch(texto):
        return float(texto.replace(".", "").replace(",", "."))
    if _NUMERO_PONTO.fullmatch(texto):
        return float(texto.replace(",", ""))
    return None


def converter_numero(valor) -> float:
    """Como ler_numero, mas texto que não é número vale 0."""
    numero = ler_numero(valor)
    return 0.0 if numero is None else numero


# ---------------------------------------------------------------------------
# Localizar cabeçalho e colunas
# ---------------------------------------------------------------------------

def _ler_abas(conteudo: bytes, nome_arquivo: str):
    """Devolve (nome_da_aba, função que lê a aba com header=None)."""
    if nome_arquivo.lower().endswith(".csv"):
        texto = conteudo.decode("utf-8-sig", errors="replace")
        separador = ";" if texto.split("\n", 1)[0].count(";") > texto.split("\n", 1)[0].count(",") else ","

        def ler_csv(**kwargs):
            try:
                return pd.read_csv(io.StringIO(texto), sep=separador, header=None, dtype=object, **kwargs)
            except (pd.errors.EmptyDataError, pd.errors.ParserError) as erro:
                raise ErroImportacao(f"Não consegui ler o CSV (vazio ou mal formado): {erro}") from erro
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
    return ler_numero(valor)


def _texto_celula(valor):
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    return normalizar_codigo(valor) or None


# Lido aos poucos: a aba FATURAMENTO real tem ~317 mil linhas e 40 colunas. Lida de uma vez passava de 1 GB de
# memória (o Render grátis tem 512 MB). Em partes, com os textos repetidos guardados como "category", fica em
# ~1/5 disso.
LINHAS_POR_PARTE = 5_000
CAMPOS_REPETIDOS = CAMPOS_TEXTO + ["cnpj_cpf", "tipo_nf", "tipo_nf_chave"]


def _cabecalho(linhas: list, apelidos: dict, valida):
    """(índice da linha de cabeçalho, mapa campo -> coluna) entre as primeiras linhas, ou None."""
    melhor = None
    for indice, linha in enumerate(linhas):
        mapa = _mapear_colunas(list(linha), apelidos)
        if valida(mapa) and (melhor is None or len(mapa) > len(melhor[1])):
            melhor = (indice, mapa)
    return melhor


def _partes_do_arquivo(fonte, nome_arquivo: str, apelidos: dict, valida):
    """Acha a aba e o cabeçalho e devolve (aba, mapa, nº da 1ª linha de dados no Excel, avisos, gerador de partes).

    `fonte` é o conteúdo (bytes) ou o caminho do arquivo no disco; do disco ele é lido aos poucos, sem carregar
    o arquivo inteiro na memória. Cada parte é um DataFrame só com as colunas reconhecidas, com no máximo
    LINHAS_POR_PARTE linhas.
    """
    from itertools import chain, islice

    def em_partes(linhas, mapa):
        posicoes = list(mapa.items())
        while True:
            bloco = list(islice(linhas, LINHAS_POR_PARTE))
            if not bloco:
                return
            yield pd.DataFrame({campo: [linha[pos] if pos < len(linha) else None for linha in bloco]
                                for campo, pos in posicoes})

    if nome_arquivo.lower().endswith(".csv"):
        import csv
        if isinstance(fonte, (bytes, bytearray)):
            arquivo_texto = io.StringIO(fonte.decode("utf-8-sig", errors="replace"))
        else:
            arquivo_texto = open(fonte, encoding="utf-8-sig", errors="replace", newline="")  # noqa: SIM115
        primeira = arquivo_texto.readline()
        arquivo_texto.seek(0)
        separador = ";" if primeira.count(";") > primeira.count(",") else ","
        try:
            linhas = (tuple(c if c != "" else None for c in linha)
                      for linha in csv.reader(arquivo_texto, delimiter=separador))
            primeiras = list(islice(linhas, 30))
        except Exception as erro:  # noqa: BLE001 - CSV mal formado vira mensagem para o usuário
            raise ErroImportacao(f"Não consegui ler o CSV: {erro}") from erro
        achado = _cabecalho(primeiras, apelidos, valida)
        if achado is None:
            return None
        indice, mapa = achado
        return "CSV", mapa, indice + 2, [], em_partes(chain(primeiras[indice + 1:], linhas), mapa)

    candidatas = []
    try:
        # Leitor rápido (app/leitor_xlsx.py): ~3x mais rápido e ~8x menos memória que o openpyxl.
        livro = LivroXlsx(fonte)
        abas = [(nome, livro.linhas(caminho)) for nome, caminho in livro.abas]
    except ArquivoNaoSuportado:
        from openpyxl import load_workbook
        try:
            livro = load_workbook(io.BytesIO(fonte) if isinstance(fonte, (bytes, bytearray)) else fonte,
                                  read_only=True, data_only=True)
        except Exception as erro:  # noqa: BLE001 - arquivo que não é Excel vira mensagem para o usuário
            raise ErroImportacao(f"Não consegui abrir o arquivo como Excel: {erro}") from erro
        abas = [(aba.title, aba.iter_rows(values_only=True)) for aba in livro.worksheets]
    for nome_aba, linhas in abas:
        primeiras = list(islice(linhas, 30))
        achado = _cabecalho(primeiras, apelidos, valida)
        if achado is not None:
            candidatas.append((nome_aba, achado, primeiras, linhas))
    if not candidatas:
        return None
    nome_aba, (indice, mapa), primeiras, linhas = candidatas[0]
    avisos = [f"Mais de uma aba parece base de faturamento; usei só a aba '{nome_aba}'."] if len(candidatas) > 1 else []
    return nome_aba, mapa, indice + 2, avisos, em_partes(chain(primeiras[indice + 1:], linhas), mapa)


def _datas(valores: pd.Series) -> pd.Series:
    """Datas de texto (05/01/2026), de data do Excel ou de número de série do Excel (46027 = 05/01/2026)."""
    numeros = pd.to_numeric(valores, errors="coerce")
    serial = numeros.between(20_000, 80_000)  # de 1954 a 2119: número de série, não um ano ou código
    datas = pd.to_datetime(valores.where(~serial), errors="coerce", dayfirst=True)
    if serial.any():
        datas[serial] = pd.to_datetime(numeros[serial], unit="D", origin="1899-12-30")
    return datas


def _por_valor_distinto(serie: pd.Series, funcao) -> pd.Series:
    """Aplica `funcao` uma vez por valor diferente (não por célula): a coluna repete muito ("JOINVILLE" em
    milhares de linhas), então isso corta a maior parte do trabalho da conferência."""
    codigos, distintos = pd.factorize(serie, use_na_sentinel=True)
    convertidos = np.empty(len(distintos) + 1, dtype=object)
    convertidos[:-1] = [funcao(valor) for valor in distintos]
    convertidos[-1] = funcao(None)  # código -1 = célula vazia
    return pd.Series(convertidos[codigos], index=serie.index)


def _tratar_parte(df: pd.DataFrame, primeira_linha: int, usar_vlr_total: bool):
    """Valida e converte uma parte do faturamento. Devolve (itens válidos, erros [{linha, motivo}])."""
    for campo in APELIDOS_FATURAMENTO:
        if campo not in df:
            df[campo] = None
    if usar_vlr_total:
        df["total_venda"] = df["vlr_total"]
    # Número da linha no Excel, para o relatório de erros.
    df["linha"] = range(primeira_linha, primeira_linha + len(df))
    df = df[~df[["cnpj_cpf", "num_nf", "total_venda", "vlr_total"]].isna().all(axis=1)]  # linhas vazias

    df["cnpj_cpf"] = _por_valor_distinto(df["cnpj_cpf"], normalizar_cnpj)
    datas = _datas(df["data_emissao"])
    ano = pd.to_numeric(df["ano"], errors="coerce").fillna(datas.dt.year)
    mes = pd.to_numeric(df["mes"], errors="coerce").fillna(datas.dt.month)
    df["ano"], df["mes"] = ano, mes
    # Fica como data compacta (datetime64) até a gravação: 317 mil objetos "date" do Python pesavam na memória.
    df["data_emissao"] = datas.dt.normalize()
    for campo in CAMPOS_NUMERICOS:
        df[campo] = _por_valor_distinto(df[campo], numero_ou_nada)

    erros = []
    motivos = pd.Series("", index=df.index)
    motivos[df["cnpj_cpf"] == ""] = "CNPJ/CPF vazio"
    motivos[df["cnpj_cpf"].str.len() > 14] = "CNPJ/CPF com mais de 14 dígitos"
    motivos[(motivos == "") & (df["ano"].isna() | df["mes"].isna() | ~df["mes"].between(1, 12)
                               | ~df["ano"].between(2000, 2100))] = "data inválida"
    motivos[(motivos == "") & df["total_venda"].isna()] = "TOTAL VENDA não é número"
    for linha, motivo in zip(df.loc[motivos != "", "linha"], motivos[motivos != ""]):
        erros.append({"linha": int(linha), "motivo": motivo})
    df = df[motivos == ""].copy()

    df["ano"] = df["ano"].astype("int16")
    df["mes"] = df["mes"].astype("int8")
    for campo in CAMPOS_TEXTO:
        df[campo] = _por_valor_distinto(
            df[campo], lambda v, t=TAMANHOS[campo]: (lambda x: x[:t] if isinstance(x, str) else x)(_texto_celula(v)))
    df["cod_cli"] = df["cod_cli"].fillna("")
    df["tipo_nf"] = df["tipo_nf"].fillna("").astype(str).str.strip().replace("", SEM_TIPO).str[:60]
    df["tipo_nf_chave"] = _por_valor_distinto(df["tipo_nf"], normalizar_texto)
    for campo in CAMPOS_NUMERICOS:
        df[campo] = df[campo].astype("float64")
    return df.drop(columns=["linha"]), erros


def devolver_memoria() -> None:
    """Devolve ao sistema a memória que o Python já liberou mas ainda segura (no Linux, malloc_trim).

    Sem isso a memória "usada" do servidor só sobe durante a importação, mesmo com os dados já descartados.
    """
    import ctypes
    import gc
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):  # fora do Linux (ex.: Windows no PC) não existe; não faz falta
        pass


def _codificar(serie: pd.Series, dicionario: dict) -> np.ndarray:
    """Troca cada texto por um número de um dicionário único para o arquivo todo (-1 = vazio).

    Assim cada texto diferente (cliente, item, nota…) fica guardado uma vez só, e cada linha guarda só o número.
    """
    locais, distintos = pd.factorize(serie, use_na_sentinel=True)
    globais = np.array([dicionario.setdefault(v, len(dicionario)) for v in distintos], dtype=np.int32)
    return np.where(locais < 0, -1, globais[locais] if len(globais) else -1).astype(np.int32)


def _juntar_partes(partes: list, dicionarios: dict) -> pd.DataFrame:
    """Junta as partes; as colunas de texto viram "category" com o dicionário do arquivo todo."""
    if not partes:
        return pd.DataFrame(columns=list(APELIDOS_FATURAMENTO) + ["tipo_nf_chave"])
    colunas = {}
    for campo in list(partes[0].columns):
        # pop: cada coluna sai das partes assim que é juntada, para não ficar tudo duplicado na memória.
        pedacos = [p.pop(campo) for p in partes]
        if campo in dicionarios:
            categorias = pd.Index(list(dicionarios[campo]), dtype=object)
            colunas[campo] = pd.Categorical.from_codes(np.concatenate([x.to_numpy() for x in pedacos]),
                                                       categories=categorias)
        else:
            colunas[campo] = pd.concat(pedacos, ignore_index=True)
        del pedacos
    partes.clear()
    devolver_memoria()
    return pd.DataFrame(colunas)


def ler_faturamento(fonte, nome_arquivo: str, ao_progredir=None):
    """Lê a exportação do ERP (bytes ou caminho do arquivo). Devolve (itens válidos, erros, avisos, aba).

    `ao_progredir(linhas_lidas)` é chamado a cada parte, para a tela mostrar o andamento.
    """
    achado = _partes_do_arquivo(fonte, nome_arquivo, APELIDOS_FATURAMENTO, _valida_faturamento)
    if achado is None:
        raise ErroImportacao(
            "Não encontrei a base de faturamento. Colunas obrigatórias: CNPJ CPF, NUM NF, TOTAL VENDA (ou VLR TOTAL) "
            "e a data de emissão (ou ANO e MÊS).")
    aba, mapa, primeira_linha, avisos, partes_brutas = achado
    usar_vlr_total = "total_venda" not in mapa
    if usar_vlr_total:
        avisos.append("O arquivo não tem a coluna TOTAL VENDA; usei VLR TOTAL no lugar.")
    partes, erros = [], []
    dicionarios = {campo: {} for campo in CAMPOS_REPETIDOS}
    linhas_lidas = 0
    for bruta in partes_brutas:
        parte, erros_parte = _tratar_parte(bruta, primeira_linha, usar_vlr_total)
        primeira_linha += len(bruta)
        linhas_lidas += len(bruta)
        erros += erros_parte
        if not parte.empty:
            for campo in CAMPOS_REPETIDOS:
                parte[campo] = _codificar(parte[campo], dicionarios[campo])
            partes.append(parte)
        if ao_progredir:
            ao_progredir(linhas_lidas)
        if len(partes) % 10 == 0:
            devolver_memoria()
    return _juntar_partes(partes, dicionarios), erros, avisos, aba


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
    "uf": ["UF", "ESTADO"],
    "supervisor": ["SUPERVISOR"],
    "salario": ["SALARIO"],
    "ajuda_custo": ["AJUD CUSTO", "AJUDA CUSTO", "AJUDA DE CUSTO"],
    "transporte": ["V TRANSP", "VALE TRANSPORTE", "TRANSPORTE"],
    "total": ["TOTAL", "CUSTO TOTAL"],
}


# Acima disso, um item do custo mensal de um promotor (salário, ajuda, vale ou total) é erro de digitação/leitura.
LIMITE_CUSTO_MENSAL = 50_000.0
_PALAVRAS_SUPERVISOR = re.compile(r"\b(SUP|SUPERVISOR|SUPERVISORA|SUPERV)\b")


def eh_supervisor(nome: str, municipio: str = "") -> bool:
    return bool(_PALAVRAS_SUPERVISOR.search(normalizar_texto(nome))
                or _PALAVRAS_SUPERVISOR.search(normalizar_texto(municipio)))


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

    avisos = []
    nomes_colunas = {"salario": "Salário", "ajuda_custo": "Ajuda de custo", "transporte": "Vale transporte",
                     "total": "TOTAL"}
    for campo, rotulo in nomes_colunas.items():
        if campo not in df:
            df[campo] = 0.0
            continue
        originais = df[campo]
        valores = originais.map(ler_numero)
        # Texto que não é um número só (ex.: "600 + 120m"): fica 0, como o Excel faz no TOTAL da planilha, e avisa.
        invalidos = valores.isna()
        # Valor fora do normal para um mês de um promotor (ex.: 600120): fica 0 e avisa.
        absurdos = ~invalidos & ((valores < 0) | (valores > LIMITE_CUSTO_MENSAL))
        for (codigo, nome, original), motivo in (
                [(t, "não é número") for t in zip(df.loc[invalidos, "codigo"], df.loc[invalidos, "nome"],
                                                  originais[invalidos])]
                + [(t, "fora do normal") for t in zip(df.loc[absurdos, "codigo"], df.loc[absurdos, "nome"],
                                                      originais[absurdos])]):
            avisos.append(f"{rotulo} de {nome} (código {codigo}) = '{original}' {motivo}: ficou 0. "
                          "Corrija na planilha ou no cadastro.")
        df[campo] = valores.where(~(invalidos | absurdos), 0.0).astype(float)
    soma = df["salario"] + df["ajuda_custo"] + df["transporte"]
    df["custo_mensal"] = df["total"].where(df["total"] > 0, soma)

    if "admissao" in df:
        df["admissao"] = pd.to_datetime(df["admissao"], errors="coerce", dayfirst=True).dt.strftime("%Y-%m-%d")
    for campo in ("admissao", "municipio", "uf", "supervisor"):
        if campo not in df:
            df[campo] = ""
        df[campo] = df[campo].fillna("").astype(str).str.strip()

    repetidos = df[df["codigo"].duplicated(keep=False)]
    if not repetidos.empty:
        avisos.append("Códigos repetidos (mantive a última linha): "
                      + ", ".join(sorted(repetidos["codigo"].unique())))
        df = df.drop_duplicates("codigo", keep="last")
    # Supervisor na lista de promotores ("Sup." / "Supervisor" no nome ou no município, ou o nome de alguém
    # que aparece na coluna SUPERVISOR): entra como função Supervisor e fica fora da contagem e do custo dos
    # promotores (pergunta 3 do docs/perguntas-mauricio.md).
    nomes_supervisores = {normalizar_texto(n) for n in df["supervisor"] if n}
    df["funcao"] = [
        "Supervisor" if eh_supervisor(nome, municipio) or normalizar_texto(nome) in nomes_supervisores else "Promotor"
        for nome, municipio in zip(df["nome"], df["municipio"])]
    supervisores = df[df["funcao"] == "Supervisor"]
    if not supervisores.empty:
        avisos.append(f"{len(supervisores)} supervisor(es) na lista de promotores ficaram como função Supervisor "
                      "(fora do custo e da contagem de promotores): " + ", ".join(supervisores["nome"][:10]))
    sem_supervisor = df[(df["supervisor"] == "") & (df["funcao"] != "Supervisor")]
    if not sem_supervisor.empty:
        avisos.append(f"{len(sem_supervisor)} promotor(es) sem supervisor: " + ", ".join(sem_supervisor["nome"][:10])
                      + (" …" if len(sem_supervisor) > 10 else ""))

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
    # Na aba PR a cidade está numa coluna sem título ("Coluna1").
    "cidade": ["CIDADE", "MUNICIPIO", "COLUNA1"],
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
    bruto = df["cnpj"]
    df["cnpj"] = df["cnpj"].map(normalizar_cnpj)
    # Mais de 14 dígitos não é um CNPJ (ex.: dois CNPJs na mesma célula). A loja entra sem CNPJ, com aviso,
    # em vez de derrubar a importação inteira.
    cnpj_invalido = df["cnpj"].str.len() > 14
    df.loc[cnpj_invalido, "cnpj"] = ""
    for campo in ("colaborador", "loja", "cidade", "uf"):
        df[campo] = df[campo].fillna("").astype(str).str.strip()
    df["uf"] = df["uf"].str.upper()
    # Coluna UF/Estado vazia (aba PR): a UF é o nome da aba (SC, SP, PR, MG, RS).
    uf_da_aba = df["aba"].astype(str).str.strip().str.upper()
    vazia = (df["uf"] == "") & uf_da_aba.str.fullmatch(r"[A-Z]{2}")
    df.loc[vazia, "uf"] = uf_da_aba[vazia]
    df = df[(df["loja"] != "") & ((df["codigo_promotor"] != "") | (df["colaborador"] != ""))]
    df = df.drop_duplicates(["codigo_promotor", "colaborador", "cnpj", "loja"]).copy()

    avisos = []
    cnpj_invalido = cnpj_invalido.reindex(df.index, fill_value=False)
    if cnpj_invalido.any():
        exemplos = [f"{aba} · {loja} ({str(valor).strip()[:40]})" for aba, loja, valor in
                    zip(df.loc[cnpj_invalido, "aba"], df.loc[cnpj_invalido, "loja"], bruto.loc[df.index][cnpj_invalido])]
        avisos.append(f"{len(exemplos)} loja(s) com CNPJ inválido (mais de 14 dígitos) entraram sem CNPJ, sem "
                      "faturamento. Corrija na planilha ou na tela: " + "; ".join(exemplos[:10])
                      + (" …" if len(exemplos) > 10 else ""))
    # Visitas por semana: inteiro de 1 a 7 (como na tela). O resto fica vazio, com aviso.
    visitas = pd.to_numeric(df["visitas_semana"], errors="coerce")
    validas = visitas.between(1, 7) & (visitas == visitas.round())
    invalidas = df["visitas_semana"].notna() & (df["visitas_semana"].astype(str).str.strip() != "") & ~validas
    if invalidas.any():
        avisos.append(f"{int(invalidas.sum())} loja(s) com visitas por semana inválidas (use 1 a 7) ficaram sem "
                      "visitas: " + ", ".join(df.loc[invalidas, "loja"].head(5)))
    df["visitas_semana"] = visitas.where(validas)
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
