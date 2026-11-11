"""Leitura, linha a linha, dos arquivos de texto que o ERP gera: CSV, TXT e o ".xls" do Focco.

O botão "Gera Excel" do gerador de relatórios do Focco3i salva uma PÁGINA HTML com extensão .xls (o Excel abre,
mas não é uma pasta de trabalho). Aqui ela é lida tabela por tabela, linha <tr> por linha, aos poucos: o arquivo
não é carregado inteiro na memória. TXT e CSV são texto separado por ";", tabulação, "|" ou ",".

Cada linha sai como uma tupla de textos (célula vazia = None), igual às linhas do leitor de .xlsx.
"""
import codecs
import csv
import io
from html.parser import HTMLParser

PEDACO = 1024 * 1024                 # bytes lidos por vez do disco
LIMITE_CELULA = 10_000               # caracteres de uma célula (o resto é descartado)
LIMITE_COLUNAS = 500                 # células por linha
LIMITE_PENDENTE = 16 * 1024 * 1024   # tag HTML sem fim acumulando na memória: arquivo inválido
ASSINATURA_XLS_ANTIGO = b"\xd0\xcf\x11\xe0"   # .xls de verdade (formato binário do Excel 97-2003)
SEPARADORES = (";", "\t", "|", ",")


class ArquivoTextoInvalido(Exception):
    """Mensagem pronta para o usuário."""


EXTENSOES_TEXTO = (".csv", ".txt", ".xls")


def eh_texto(nome_arquivo: str) -> bool:
    return nome_arquivo.lower().endswith(EXTENSOES_TEXTO)


def _abrir_binario(fonte):
    if isinstance(fonte, (bytes, bytearray)):
        return io.BytesIO(fonte)
    return open(fonte, "rb")  # noqa: SIM115 - fechado por quem chama


def _codificacao(inicio: bytes) -> str:
    """UTF-8 quando o começo do arquivo é UTF-8 válido; senão Windows-1252 (o padrão do Focco no Windows)."""
    if inicio.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if inicio.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return "utf-16"
    amostra = inicio
    # Um caractere de vários bytes pode ter sido cortado no fim da amostra: ignora os últimos 3 bytes.
    for corte in range(4):
        try:
            (amostra[:-corte] if corte else amostra).decode("utf-8")
            return "utf-8"
        except UnicodeDecodeError:
            continue
    return "cp1252"


def _pedacos_de_texto(arquivo, codificacao: str):
    decodificador = codecs.getincrementaldecoder(codificacao)(errors="replace")
    while True:
        bloco = arquivo.read(PEDACO)
        if not bloco:
            final = decodificador.decode(b"", final=True)
            if final:
                yield final
            return
        yield decodificador.decode(bloco)


class _TabelaHtml(HTMLParser):
    """Junta as células <td>/<th> de cada <tr> e guarda as linhas prontas em self.prontas."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.prontas = []
        self._linha = None
        self._celula = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._fechar_linha()
            self._linha = []
        elif tag in ("td", "th"):
            self._fechar_celula()
            if self._linha is None:
                self._linha = []
            self._celula = []
        elif tag == "br" and self._celula is not None:
            self._celula.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self._fechar_celula()
        elif tag in ("tr", "table"):
            self._fechar_linha()

    def handle_data(self, data):
        if self._celula is not None and sum(map(len, self._celula)) < LIMITE_CELULA:
            self._celula.append(data)

    def _fechar_celula(self):
        if self._celula is None:
            return
        texto = " ".join("".join(self._celula).replace("\xa0", " ").split())[:LIMITE_CELULA]
        if self._linha is not None and len(self._linha) < LIMITE_COLUNAS:
            self._linha.append(texto or None)
        self._celula = None

    def _fechar_linha(self):
        self._fechar_celula()
        if self._linha is not None:
            if any(c is not None for c in self._linha):
                self.prontas.append(tuple(self._linha))
            self._linha = None


def _linhas_html(arquivo, codificacao: str):
    leitor = _TabelaHtml()
    for texto in _pedacos_de_texto(arquivo, codificacao):
        leitor.feed(texto)
        if len(leitor.rawdata) > LIMITE_PENDENTE:
            raise ArquivoTextoInvalido("O arquivo HTML está mal formado (uma marcação não termina). Gere o relatório "
                                       "de novo no ERP ou salve como .xlsx no Excel.")
        if leitor.prontas:
            yield from leitor.prontas
            leitor.prontas = []
    leitor.close()
    leitor._fechar_linha()
    yield from leitor.prontas


def _separador(linhas_inicio: list[str]) -> str:
    """O separador que mais aparece numa mesma linha (o cabeçalho é a linha com mais colunas)."""
    melhor, contagem = ";", 0
    for separador in SEPARADORES:
        maior = max((linha.count(separador) for linha in linhas_inicio), default=0)
        if maior > contagem:
            melhor, contagem = separador, maior
    return melhor


def _linhas_separadas(arquivo, codificacao: str):
    texto = io.TextIOWrapper(arquivo, encoding=codificacao, errors="replace", newline="")
    inicio = [texto.readline() for _ in range(30)]
    separador = _separador(inicio)
    from itertools import chain
    leitor = csv.reader(chain(inicio, texto), delimiter=separador)
    try:
        for linha in leitor:
            celulas = tuple((c.strip() or None) for c in linha[:LIMITE_COLUNAS])
            if any(c is not None for c in celulas):
                yield celulas
    except csv.Error as erro:
        raise ArquivoTextoInvalido(f"Não consegui ler o arquivo de texto: {erro}") from erro


def linhas_do_texto(fonte, nome_arquivo: str):
    """Gera as linhas (tuplas de texto) de um CSV, TXT ou .xls do Focco. Levanta ArquivoTextoInvalido."""
    arquivo = _abrir_binario(fonte)
    try:
        inicio = arquivo.read(64 * 1024)
        arquivo.seek(0)
        if inicio.startswith(ASSINATURA_XLS_ANTIGO):
            raise ArquivoTextoInvalido("Este .xls está no formato antigo do Excel (97-2003), que o sistema não lê. "
                                       "Abra no Excel, salve como Pasta de Trabalho do Excel (.xlsx) e envie de novo.")
        if inicio.startswith(b"PK"):
            raise ArquivoTextoInvalido("Este arquivo é um .xlsx com a extensão trocada. Renomeie para .xlsx e envie "
                                       "de novo.")
        codificacao = _codificacao(inicio)
        amostra = inicio.decode(codificacao, errors="replace").lstrip("﻿ \r\n\t").lower()
        eh_html = amostra.startswith("<") and ("<table" in amostra or "<html" in amostra or "<tr" in amostra)
        yield from (_linhas_html(arquivo, codificacao) if eh_html else _linhas_separadas(arquivo, codificacao))
    finally:
        arquivo.close()
