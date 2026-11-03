"""Exportação das tabelas da tela para Excel (.xlsx) formatado.

A tela manda as colunas (título e formato) e as linhas já na ordem em que aparecem; aqui só se monta a
planilha: título, cabeçalho colorido, R$ e %, linhas de total em negrito, filtro e cabeçalho fixo.
"""
import io
import re
import unicodedata
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from pydantic import BaseModel, Field

from .autenticacao import usuario_logado

rotas = APIRouter(prefix="/api")

# Zero aparece como "-", como na tela.
FORMATOS = {"moeda": '"R$" #,##0.00;-"R$" #,##0.00;"-"', "percentual": '0.0%;-0.0%;"-"', "inteiro": "#,##0",
            "numero": "#,##0.##", "texto": "@"}
LARGURA_MINIMA = {"moeda": 15, "percentual": 9}
MAX_LINHAS = 200_000

AZUL = "1F4E8C"
FUNDO_TOTAL = "E7EEF8"
FUNDO_ZEBRA = "F6F8FB"
BORDA = Side(style="thin", color="C9D2DE")


class Coluna(BaseModel):
    titulo: str = Field(max_length=120)
    formato: str = "texto"


class Exportacao(BaseModel):
    titulo: str = Field(max_length=120)
    subtitulo: str = Field(default="", max_length=500)
    colunas: list[Coluna] = Field(min_length=1, max_length=100)
    linhas: list[list] = Field(default_factory=list)
    totais: list[list] = Field(default_factory=list)


def _nome_arquivo(titulo: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", titulo).encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9\- ]+", "", sem_acento).strip().replace(" ", "-").lower() or "exportacao"
    return f"{base[:60]}-{datetime.now():%Y-%m-%d}.xlsx"


def _valor(valor, formato: str):
    """Número fica número (o Excel soma e formata); % vem da tela como 8.1 e vira 0.081."""
    if isinstance(valor, bool) or valor is None:
        return "" if valor is None else ("Sim" if valor else "Não")
    if isinstance(valor, (int, float)):
        return valor / 100 if formato == "percentual" else valor
    return str(valor)


def montar_planilha(dados: Exportacao) -> bytes:
    if len(dados.linhas) + len(dados.totais) > MAX_LINHAS:
        raise HTTPException(status_code=400, detail="Tabela grande demais para exportar. Use os filtros.")
    livro = Workbook()
    aba = livro.active
    aba.title = re.sub(r"[\[\]:*?/\\]", "", dados.titulo)[:31] or "Dados"
    total_colunas = len(dados.colunas)

    aba["A1"] = dados.titulo
    aba["A1"].font = Font(bold=True, size=14, color=AZUL)
    aba["A2"] = (f"{dados.subtitulo} · " if dados.subtitulo else "") + \
        f"Controle de Promotores — 101 do Brasil · gerado em {datetime.now():%d/%m/%Y %H:%M}"
    aba["A2"].font = Font(italic=True, size=9, color="667085")

    linha_cabecalho = 4
    for i, coluna in enumerate(dados.colunas, start=1):
        celula = aba.cell(row=linha_cabecalho, column=i, value=coluna.titulo)
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = PatternFill("solid", fgColor=AZUL)
        celula.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        celula.border = Border(top=BORDA, bottom=BORDA, left=BORDA, right=BORDA)
    aba.row_dimensions[linha_cabecalho].height = 30

    larguras = [len(c.titulo) for c in dados.colunas]
    numero_linha = linha_cabecalho
    for indice, valores in enumerate(dados.linhas + dados.totais):
        numero_linha += 1
        e_total = indice >= len(dados.linhas)
        for i, coluna in enumerate(dados.colunas, start=1):
            bruto = valores[i - 1] if i - 1 < len(valores) else None
            valor = _valor(bruto, coluna.formato)
            celula = aba.cell(row=numero_linha, column=i)
            celula.value = valor
            if isinstance(valor, str):
                celula.data_type = "s"  # texto que começa com "=" não vira fórmula
            elif coluna.formato in FORMATOS:
                celula.number_format = FORMATOS[coluna.formato]
            celula.border = Border(bottom=BORDA)
            if e_total:
                celula.font = Font(bold=True)
                celula.fill = PatternFill("solid", fgColor=FUNDO_TOTAL)
                celula.border = Border(top=Side(style="medium", color=AZUL), bottom=BORDA)
            elif indice % 2:
                celula.fill = PatternFill("solid", fgColor=FUNDO_ZEBRA)
            texto = f"{valor:,.2f}" if isinstance(valor, (int, float)) and coluna.formato == "moeda" else str(valor)
            # R$, negrito do total e a seta do filtro ocupam espaço além dos dígitos.
            extra = 6 if coluna.formato == "moeda" else 2
            larguras[i - 1] = max(larguras[i - 1], len(texto) + extra, LARGURA_MINIMA.get(coluna.formato, 0))

    for i, largura in enumerate(larguras, start=1):
        aba.column_dimensions[get_column_letter(i)].width = min(max(largura + 1, 9), 50)
    aba.freeze_panes = aba.cell(row=linha_cabecalho + 1, column=1)
    if dados.linhas:
        ultima = linha_cabecalho + len(dados.linhas)
        aba.auto_filter.ref = f"A{linha_cabecalho}:{get_column_letter(total_colunas)}{ultima}"
    aba.page_setup.orientation = "landscape"
    aba.page_setup.fitToWidth = 1
    aba.page_setup.fitToHeight = 0
    aba.sheet_properties.pageSetUpPr.fitToPage = True
    aba.print_title_rows = f"{linha_cabecalho}:{linha_cabecalho}"

    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()


@rotas.post("/exportar")
def exportar(dados: Exportacao, _=Depends(usuario_logado)):
    conteudo = montar_planilha(dados)
    nome = _nome_arquivo(dados.titulo)
    return StreamingResponse(
        io.BytesIO(conteudo),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'})
