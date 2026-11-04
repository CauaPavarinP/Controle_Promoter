"""Exportação das tabelas da tela para Excel (.xlsx) formatado.

A tela manda as colunas (título e formato) e as linhas já na ordem em que aparecem; aqui só se monta a
planilha: título, cabeçalho colorido, R$ e %, coluna e linha de total em destaque (com barras na coluna
TOTAL), filtro e cabeçalho fixo.
"""
import io
import re
import unicodedata
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.formatting.rule import DataBarRule
from openpyxl.utils import get_column_letter
from pydantic import BaseModel, Field

from .autenticacao import usuario_logado

rotas = APIRouter(prefix="/api")

# Zero aparece como "-", como na tela. R$ sem centavos quando os valores são grandes (mais fácil de ler).
MOEDA_SEM_CENTAVOS = '"R$" #,##0;-"R$" #,##0;"-"'
MOEDA_COM_CENTAVOS = '"R$" #,##0.00;-"R$" #,##0.00;"-"'
FORMATOS = {"percentual": '0.0%;-0.0%;"-"', "inteiro": "#,##0", "texto": "@"}
LARGURA_MINIMA = {"moeda": 14, "percentual": 10, "numero": 9}
MAX_LINHAS = 200_000

AZUL = "1F4E8C"
AZUL_CLARO = "E7EEF8"
CINZA_TEXTO = "667085"
FUNDO_ZEBRA = "F7F9FC"
FUNDO_COLUNA_TOTAL = "EEF3FA"
COR_BARRA = "A9C1E6"
LINHA = Side(style="thin", color="DDE3EA")
LINHA_TOTAL = Side(style="medium", color=AZUL)

class Coluna(BaseModel):
    titulo: str = Field(max_length=120)
    formato: str = "texto"


class Exportacao(BaseModel):
    titulo: str = Field(max_length=120)
    subtitulo: str = Field(default="", max_length=500)
    colunas: list[Coluna] = Field(min_length=1, max_length=100)
    linhas: list[list] = Field(default_factory=list)
    totais: list[list] = Field(default_factory=list)
    destaques: list[int] = Field(default_factory=list)  # linhas (a partir de 0) em negrito, ex.: as UFs do Resumo


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


def _formato_numerico(coluna: Coluna, valores: list) -> str | None:
    numeros = [v for v in valores if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if coluna.formato == "moeda":
        grandes = any(abs(v) >= 1000 for v in numeros)
        return MOEDA_SEM_CENTAVOS if grandes else MOEDA_COM_CENTAVOS
    if coluna.formato == "numero":
        return "#,##0" if all(float(v).is_integer() for v in numeros) else "#,##0.0#"
    return FORMATOS.get(coluna.formato)


def montar_planilha(dados: Exportacao) -> bytes:
    if len(dados.linhas) + len(dados.totais) > MAX_LINHAS:
        raise HTTPException(status_code=400, detail="Tabela grande demais para exportar. Use os filtros.")
    livro = Workbook()
    aba = livro.active
    aba.title = re.sub(r"[\[\]:*?/\\]", "", dados.titulo)[:31] or "Dados"
    aba.sheet_view.showGridLines = False  # só as divisórias leves das linhas
    total_colunas = len(dados.colunas)
    ultima_letra = get_column_letter(total_colunas)

    # Título e, embaixo, filtros em uso e data.
    aba["A1"] = dados.titulo
    aba["A1"].font = Font(bold=True, size=16, color=AZUL)
    aba.row_dimensions[1].height = 26
    aba["A2"] = (f"{dados.subtitulo}   ·   " if dados.subtitulo else "") + \
        f"Controle de Promotores — 101 do Brasil   ·   gerado em {datetime.now():%d/%m/%Y %H:%M}"
    aba["A2"].font = Font(size=10, color=CINZA_TEXTO)

    linha_cabecalho = 4
    e_coluna_total = [c.titulo.strip().upper() == "TOTAL" for c in dados.colunas]
    for i, coluna in enumerate(dados.colunas, start=1):
        celula = aba.cell(row=linha_cabecalho, column=i, value=coluna.titulo)
        celula.font = Font(bold=True, color="FFFFFF", size=11)
        celula.fill = PatternFill("solid", fgColor=AZUL)
        celula.alignment = Alignment(horizontal="left" if coluna.formato == "texto" else "right",
                                     vertical="center", wrap_text=True, indent=1)
    aba.row_dimensions[linha_cabecalho].height = 34

    formatos = [_formato_numerico(c, [linha[i] for linha in dados.linhas + dados.totais if i < len(linha)])
                for i, c in enumerate(dados.colunas)]
    larguras = [len(c.titulo) + 3 for c in dados.colunas]
    destaques = set(dados.destaques)
    numero_linha = linha_cabecalho
    for indice, valores in enumerate(dados.linhas + dados.totais):
        numero_linha += 1
        e_total = indice >= len(dados.linhas)
        aba.row_dimensions[numero_linha].height = 20 if e_total else 18
        for i, coluna in enumerate(dados.colunas, start=1):
            bruto = valores[i - 1] if i - 1 < len(valores) else None
            valor = _valor(bruto, coluna.formato)
            celula = aba.cell(row=numero_linha, column=i)
            celula.value = valor
            if isinstance(valor, str):
                celula.data_type = "s"  # texto que começa com "=" não vira fórmula
            elif formatos[i - 1]:
                celula.number_format = formatos[i - 1]
            celula.alignment = Alignment(horizontal="left" if coluna.formato == "texto" else "right",
                                         vertical="center", indent=1)
            if e_total:
                celula.font = Font(bold=True, size=11, color=AZUL)
                celula.fill = PatternFill("solid", fgColor=AZUL_CLARO)
                celula.border = Border(top=LINHA_TOTAL, bottom=LINHA_TOTAL)
            else:
                celula.border = Border(bottom=LINHA)
                if indice in destaques:
                    celula.font = Font(bold=True, color=AZUL)
                    celula.fill = PatternFill("solid", fgColor=AZUL_CLARO)
                elif e_coluna_total[i - 1]:
                    celula.font = Font(bold=True)
                    celula.fill = PatternFill("solid", fgColor=FUNDO_COLUNA_TOTAL)
                elif indice % 2:
                    celula.fill = PatternFill("solid", fgColor=FUNDO_ZEBRA)
            if isinstance(valor, (int, float)) and coluna.formato == "moeda":
                texto = f"R$ {valor:,.0f}" if formatos[i - 1] == MOEDA_SEM_CENTAVOS else f"R$ {valor:,.2f}"
            else:
                texto = str(valor)
            larguras[i - 1] = max(larguras[i - 1], len(texto) + 3, LARGURA_MINIMA.get(coluna.formato, 0))

    for i, largura in enumerate(larguras, start=1):
        aba.column_dimensions[get_column_letter(i)].width = min(max(largura, 9), 45)

    if dados.linhas:
        primeira, ultima = linha_cabecalho + 1, linha_cabecalho + len(dados.linhas)
        aba.auto_filter.ref = f"A{linha_cabecalho}:{ultima_letra}{ultima}"
        # Barras na coluna TOTAL: mostra de relance quem tem mais.
        for i, total in enumerate(e_coluna_total, start=1):
            if total and len(dados.linhas) >= 3:
                letra = get_column_letter(i)
                aba.conditional_formatting.add(
                    f"{letra}{primeira}:{letra}{ultima}",
                    DataBarRule(start_type="num", start_value=0, end_type="max", color=COR_BARRA))
    # Cabeçalho sempre visível; em tabela larga, a primeira coluna (nome) também.
    fixar_coluna = total_colunas > 6 and dados.colunas[0].formato == "texto"
    aba.freeze_panes = aba.cell(row=linha_cabecalho + 1, column=2 if fixar_coluna else 1)

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
