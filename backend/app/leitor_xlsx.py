"""Leitor rápido de .xlsx/.xlsm, linha a linha, com pouca memória.

O openpyxl lê a aba FATURAMENTO (~317 mil linhas x 40 colunas) em ~1 min num computador comum e ~7x isso no
servidor gratuito do Render (0,15 de processador). Aqui o XML de dentro do arquivo é lido aos poucos e as células
são achadas com expressões regulares (rodam em C): ~3x mais rápido e ~8x menos memória.

Por dentro, um .xlsx é um zip com:
- xl/workbook.xml + xl/_rels/workbook.xml.rels: nome de cada aba e o arquivo XML dela;
- xl/sharedStrings.xml: os textos (cada célula de texto guarda só o número do texto nesta lista);
- xl/worksheets/sheetN.xml: as linhas (<row>) e células (<c r="B7" t="s"><v>12</v></c>).

Devolve os valores como o openpyxl com data_only=True: o valor calculado das fórmulas, número inteiro sem ".0",
data como número de série do Excel (quem lê converte; ver serial_para_data na importação).
"""
import html
import io
import re
import zipfile

_NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_ABA = re.compile(r'<sheet\b[^>]*?\bname="([^"]*)"[^>]*?\br:id="([^"]*)"', re.S)
_ABA_ID_ANTES = re.compile(r'<sheet\b[^>]*?\br:id="([^"]*)"[^>]*?\bname="([^"]*)"', re.S)
_RELACAO = re.compile(r'<Relationship\b[^>]*?\bId="([^"]*)"[^>]*?\bTarget="([^"]*)"', re.S)
_RELACAO_ALVO_ANTES = re.compile(r'<Relationship\b[^>]*?\bTarget="([^"]*)"[^>]*?\bId="([^"]*)"', re.S)
_TEXTO_COMPARTILHADO = re.compile(r"<si>(.*?)</si>", re.S)
_PEDACO_TEXTO = re.compile(r"<t(?:\s[^>]*)?>([^<]*)</t>")
_FONETICO = re.compile(r"<rPh\b.*?</rPh>", re.S)
_LINHA_NUM = re.compile(rb'<row\b[^>]*?\br="(\d+)"')
# Uma busca só por linha devolve, para cada célula: (coluna "AB", tipo "s", valor de <v>, texto de <is>).
# <c r="AB12" s="3" t="s"> <f>…</f> <v>…</v> </c>   ou   <c …><is><t>texto</t></is></c>   ou   <c … />
# Os atributos podem vir em qualquer ordem (por isso r= e t= são procurados "à frente", sem consumir).
_CELULAS = re.compile(
    rb'<c\b(?:(?=[^>]*?\br="([A-Z]+)\d))?(?:(?=[^>]*?\bt="(\w+)"))?[^>]*?'
    rb'(?:/>|>(?:<f\b[^>]*?(?:/>|>[^<]*</f>))?(?:<v>([^<]*)</v>)?(?:<is>(.*?)</is>)?</c>)', re.S)
_INLINE = re.compile(rb"<t(?:\s[^>]*)?>([^<]*)</t>")
_FIM_LINHA = b"</row>"


class ArquivoNaoSuportado(Exception):
    """O arquivo não tem a estrutura esperada; quem chama usa o leitor antigo (openpyxl)."""


def _indice_coluna(letras: bytes) -> int:
    numero = 0
    for letra in letras:
        numero = numero * 26 + letra - 64
    return numero - 1


def _caminho_da_aba(alvo: str) -> str:
    alvo = alvo.lstrip("/")
    return alvo if alvo.startswith("xl/") else "xl/" + alvo


def _textos_compartilhados(zip_: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zip_.namelist():
        return []
    xml = zip_.read("xl/sharedStrings.xml").decode("utf-8")
    textos = []
    for item in _TEXTO_COMPARTILHADO.finditer(xml):
        conteudo = _FONETICO.sub("", item.group(1))  # guias fonéticas (japonês) não fazem parte do texto
        textos.append(html.unescape("".join(_PEDACO_TEXTO.findall(conteudo))))
    return textos


class LivroXlsx:
    """Abre o .xlsx (caminho ou bytes) e lê as abas linha a linha."""

    def __init__(self, fonte):
        try:
            self._zip = zipfile.ZipFile(io.BytesIO(fonte) if isinstance(fonte, (bytes, bytearray)) else fonte)
            livro = self._zip.read("xl/workbook.xml").decode("utf-8")
            relacoes = self._zip.read("xl/_rels/workbook.xml.rels").decode("utf-8")
        except (zipfile.BadZipFile, KeyError, OSError) as erro:
            raise ArquivoNaoSuportado(str(erro)) from erro
        alvos = dict(_RELACAO.findall(relacoes)) or {i: a for a, i in _RELACAO_ALVO_ANTES.findall(relacoes)}
        abas = _ABA.findall(livro) or [(n, i) for i, n in _ABA_ID_ANTES.findall(livro)]
        self.abas = []  # (nome, caminho do XML dentro do zip), na ordem do arquivo
        for nome, ident in abas:
            if ident in alvos:
                caminho = _caminho_da_aba(alvos[ident])
                if caminho in self._zip.namelist():
                    self.abas.append((html.unescape(nome), caminho))
        if not self.abas:
            raise ArquivoNaoSuportado("nenhuma aba encontrada")
        self._textos = None

    @property
    def textos(self) -> list[str]:
        if self._textos is None:
            self._textos = _textos_compartilhados(self._zip)
        return self._textos

    def linhas(self, caminho: str):
        """Gera cada linha da aba como tupla de valores (None = célula vazia), na ordem do Excel.

        Linhas que não existem no XML (vazias) também saem, vazias, para a numeração bater com a do Excel.
        """
        textos = self.textos
        colunas_conhecidas = {}
        esperada = 1
        with self._zip.open(caminho) as arquivo:
            resto = b""
            while True:
                bloco = arquivo.read(1 << 20)
                if bloco:
                    resto += bloco
                    corte = resto.rfind(_FIM_LINHA)
                    if corte < 0:
                        continue
                    pedaco, resto = resto[:corte + len(_FIM_LINHA)], resto[corte + len(_FIM_LINHA):]
                else:
                    pedaco, resto = resto, b""
                for xml_linha in pedaco.split(_FIM_LINHA):
                    numeros = _LINHA_NUM.findall(xml_linha)
                    if not numeros:
                        continue
                    numero = int(numeros[-1])
                    # Linhas vazias que o Excel nem gravou (até 10 mil seguidas; depois disso é só formatação).
                    if 0 < numero - esperada <= 10_000:
                        for _ in range(numero - esperada):
                            yield ()
                    esperada = numero + 1
                    inicio_linha = xml_linha.rfind(b"<row")
                    linha = []
                    posicao = 0
                    for letras, tipo, bruto, inline in _CELULAS.findall(xml_linha, inicio_linha):
                        if letras:
                            posicao = colunas_conhecidas.get(letras)
                            if posicao is None:
                                posicao = colunas_conhecidas[letras] = _indice_coluna(letras)
                        if bruto:
                            if tipo == b"s":
                                valor = textos[int(bruto)]
                            elif not tipo or tipo == b"n":
                                valor = float(bruto) if (b"." in bruto or b"E" in bruto or b"e" in bruto) \
                                    else int(bruto)
                            elif tipo in (b"str", b"d"):
                                valor = html.unescape(bruto.decode("utf-8"))
                            elif tipo == b"b":
                                valor = bruto == b"1"
                            else:  # "e": erro de fórmula (#N/A, #DIV/0!…)
                                valor = None
                        elif inline:
                            valor = html.unescape(b"".join(_INLINE.findall(inline)).decode("utf-8")) or None
                        else:
                            valor = None
                        if valor is not None:
                            if posicao >= len(linha):
                                linha.extend([None] * (posicao + 1 - len(linha)))
                            linha[posicao] = valor
                        posicao += 1
                    yield tuple(linha)
                if not bloco:
                    return
