"""Leitura das planilhas (Excel ou CSV) e conversão para as tabelas do sistema.

Os nomes de coluna são procurados por apelidos, sem diferenciar acento, maiúscula
ou pontuação. Se o layout real mudar, basta acrescentar o novo nome na lista.
"""
import io
import re
import unicodedata

import numpy as np
import pandas as pd

from .leitor_texto import ArquivoTextoInvalido, eh_texto, linhas_do_texto
from .leitor_xlsx import ArquivoNaoSuportado, ArquivoSuspeito, LivroXlsx, conferir_zip

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


# "600 + 120m": R$ 600 mais R$ 120 mensais (resposta do Maurício) = R$ 720 por mês. Aceita "600 +120m",
# "R$ 600 + R$ 120 mensais" etc. Só soma de dois ou mais valores; qualquer outro texto continua não sendo número.
_PARCELA = r"(?:R\$\s*)?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?"
_SOMA_MENSAL = re.compile(rf"\s*{_PARCELA}(?:\s*\+\s*{_PARCELA}\s*(?:m|mes|mensal|mensais)?\.?)+\s*", re.IGNORECASE)


def _reais(valor: float) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def ler_soma_mensal(valor):
    """Texto como "600 + 120m" vira a soma (720.0); qualquer outra coisa devolve None."""
    if not isinstance(valor, str) or not _SOMA_MENSAL.fullmatch(valor.replace("\xa0", " ")):
        return None
    parcelas = re.findall(r"(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?", valor)
    return round(sum(float(p.replace(".", "").replace(",", ".")) for p in parcelas), 2)


def converter_numero(valor) -> float:
    """Como ler_numero, mas texto que não é número vale 0."""
    numero = ler_numero(valor)
    return 0.0 if numero is None else numero


# ---------------------------------------------------------------------------
# Localizar cabeçalho e colunas
# ---------------------------------------------------------------------------

MENSAGEM_SUSPEITO = ("Este arquivo ocupa muito mais espaço aberto do que parece (pode estar corrompido ou ter sido "
                     "feito para travar o sistema) e não foi aberto. Abra no Excel, salve como uma nova pasta de "
                     "trabalho (.xlsx) e envie de novo.")


def _recusar_suspeito(fonte) -> None:
    try:
        conferir_zip(fonte)
    except ArquivoSuspeito as erro:
        raise ErroImportacao(MENSAGEM_SUSPEITO) from erro


def _linhas_protegidas(linhas):
    """Linha gigante no meio da aba (arquivo malicioso) vira a mesma mensagem, não "erro inesperado"."""
    try:
        yield from linhas
    except ArquivoSuspeito as erro:
        raise ErroImportacao(MENSAGEM_SUSPEITO) from erro


def _linhas_de_texto_protegidas(linhas):
    """Erro de leitura do arquivo de texto vira mensagem para o usuário."""
    try:
        yield from linhas
    except ArquivoTextoInvalido as erro:
        raise ErroImportacao(str(erro)) from erro


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

    _recusar_suspeito(conteudo)
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
    "cod_segmento": ["COD SEGMENTO", "COD SEGMER", "COD SEGM"],   # o Focco corta em "COD SEGMER"
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

    if eh_texto(nome_arquivo):
        # CSV, TXT ou o ".xls" do Focco (página HTML): app/leitor_texto.py, lido aos poucos.
        linhas = _linhas_de_texto_protegidas(linhas_do_texto(fonte, nome_arquivo))
        primeiras = list(islice(linhas, 30))
        achado = _cabecalho(primeiras, apelidos, valida)
        if achado is None:
            return None
        indice, mapa = achado
        aba = "HTML" if nome_arquivo.lower().endswith(".xls") else "Texto"
        return aba, mapa, indice + 2, [], em_partes(chain(primeiras[indice + 1:], linhas), mapa)

    candidatas = []
    _recusar_suspeito(fonte)
    try:
        # Leitor rápido (app/leitor_xlsx.py): ~3x mais rápido e ~8x menos memória que o openpyxl.
        livro = LivroXlsx(fonte)
        abas = [(nome, _linhas_protegidas(livro.linhas(caminho))) for nome, caminho in livro.abas]
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


def ler_faturamento_em_partes(fonte, nome_arquivo: str):
    """Lê a exportação do ERP aos poucos. Devolve (aba, avisos, gerador de (linhas lidas, itens válidos, erros)).

    Cada parte tem no máximo LINHAS_POR_PARTE linhas: quem lê guarda as partes no disco e a memória não cresce com o
    tamanho do arquivo (é o que permite arquivo de qualquer tamanho sem derrubar o servidor).
    """
    achado = _partes_do_arquivo(fonte, nome_arquivo, APELIDOS_FATURAMENTO, _valida_faturamento)
    if achado is None:
        raise ErroImportacao(
            "Não encontrei a base de faturamento. Colunas obrigatórias: CNPJ CPF, NUM NF, TOTAL VENDA (ou VLR TOTAL) "
            "e a data de emissão (ou ANO e MÊS).")
    aba, mapa, primeira_linha, avisos, partes_brutas = achado
    # O relatório do Focco não tem TOTAL VENDA (era uma coluna da planilha antiga): o valor é o VLR TOTAL, que é o
    # padrão do sistema. Não é motivo de aviso.
    usar_vlr_total = "total_venda" not in mapa

    def partes():
        linha = primeira_linha
        for bruta in partes_brutas:
            parte, erros_parte = _tratar_parte(bruta, linha, usar_vlr_total)
            linha += len(bruta)
            yield len(bruta), parte, erros_parte
    return aba, avisos, partes()


def ler_faturamento(fonte, nome_arquivo: str, ao_progredir=None):
    """Lê a exportação do ERP inteira. Devolve (itens válidos, erros, avisos, aba).

    A importação usa ler_faturamento_em_partes (memória constante); esta junta tudo, para arquivos pequenos e testes.
    `ao_progredir(linhas_lidas)` é chamado a cada parte, para a tela mostrar o andamento.
    """
    aba, avisos, partes_lidas = ler_faturamento_em_partes(fonte, nome_arquivo)
    partes, erros = [], []
    dicionarios = {campo: {} for campo in CAMPOS_REPETIDOS}
    linhas_lidas = 0
    for brutas, parte, erros_parte in partes_lidas:
        linhas_lidas += brutas
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


# ---------------------------------------------------------------------------
# Promotores (custo)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Roteiro (qual promotor atende qual loja)
# ---------------------------------------------------------------------------


