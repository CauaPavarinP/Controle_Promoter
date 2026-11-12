"""Gera o modelo em Excel que as agências preenchem (backend/exemplos/modelo_atendimento_agencias.xlsx).

Uso: python scripts/gerar_modelo_atendimento.py [arquivo de saída]
"""
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import FormulaRule
from openpyxl.comments import Comment
from openpyxl.utils import get_column_letter

import sys
from pathlib import Path
SAIDA = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parent.parent / "exemplos" / "modelo_atendimento_agencias.xlsx")
AZUL, AZUL_CLARO, CINZA = "1F4E8C", "E7EEF8", "667085"
AMARELO = PatternFill("solid", fgColor="FFF8D6")
CABECALHO = PatternFill("solid", fgColor=AZUL)
FUNDO_CINZA = PatternFill("solid", fgColor="F2F4F7")
F = lambda **k: Font(name="Arial", **k)
LINHA = Side(style="thin", color="D0D5DD")
BORDA = Border(left=LINHA, right=LINHA, top=LINHA, bottom=LINHA)
ULTIMA = 1000  # linhas preparadas para preencher

COLUNAS = [  # (título, largura, obrigatória, ajuda)
    ("Mês de referência", 14, True, "Mês e ano do serviço, no formato MM/AAAA. Ex.: 10/2026"),
    ("Agência ou MEI", 26, True, "Nome da agência, ou do MEI, que presta o serviço"),
    ("Tipo", 13, True, "Tipo de contratação do promotor: Agência, CLT, MEI ou Freelancer (escolha na lista)"),
    ("CNPJ da loja", 22, True, "CNPJ da LOJA atendida (não o da agência). Só o CNPJ nesta coluna, sem o nome da loja"),
    ("Loja", 32, True, "Nome da loja (ex.: Max Atacadista 142 - Assis)"),
    ("Cidade", 20, True, "Cidade da loja"),
    ("UF", 7, True, "Escolha na lista"),
    ("Promotor", 22, True, "Nome de quem atende a loja. Escreva sempre do mesmo jeito em todos os meses"),
    ("Código do promotor", 14, False, "Código ou matrícula do promotor na agência, se houver: identifica a pessoa mesmo com o nome escrito diferente"),
    ("Dias de visita", 18, True, "Dias da semana da visita. Ex.: Seg, Qui"),
    ("Visitas no mês", 11, True, "Quantas visitas foram feitas (ou previstas) no mês nesta loja"),
    ("Valor do mês (R$)", 16, True, "Valor cobrado por ESTA loja no mês. Ver a aba Instruções para quem cobra por visita ou por promotor"),
    ("Status", 13, True, "Ativa ou Encerrada (escolha na lista)"),
    ("Observação", 34, False, "Qualquer informação importante (início no meio do mês, troca de promotor…)"),
    ("Supervisor", 20, False, "Supervisor(a) responsável pelo promotor, se houver"),
    ("Conferência do CNPJ", 30, False, "Preenchido automaticamente: não digite nesta coluna"),
]
TIPOS = ["Agência", "CLT", "MEI", "Freelancer"]
POS = {titulo: i for i, (titulo, *_resto) in enumerate(COLUNAS, start=1)}   # título -> número da coluna
LETRA = {titulo: get_column_letter(i) for titulo, i in POS.items()}
CONFERENCIA = POS["Conferência do CNPJ"]
UFS = "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()

wb = Workbook()

# ------------------------------------------------------------------ Instruções
ins = wb.active
ins.title = "Instruções"
ins.sheet_view.showGridLines = False
ins.column_dimensions["A"].width = 3
ins.column_dimensions["B"].width = 34
ins.column_dimensions["C"].width = 86
linhas = [
    ("titulo", "Modelo de atendimento de promotores — 101 do Brasil"),
    ("sub", "Preencha um arquivo por mês e envie ao Comercial (Maurício). Use sempre este modelo, sem mudar os nomes nem a ordem das colunas."),
    ("", ""),
    ("secao", "Como preencher"),
    ("item", ("1. Uma linha por loja", "Cada loja atendida no mês ocupa uma linha da aba Atendimentos. Não junte várias lojas numa linha.")),
    ("item", ("2. Sem títulos nem totais no meio", "Não coloque linhas de título (ex.: \"ATENDIMENTOS FORT\") nem de total. Os totais aparecem sozinhos na aba Resumo.")),
    ("item", ("3. Células amarelas", "São as que você preenche. A última coluna (Conferência do CNPJ) é automática.")),
    ("item", ("Tipo", "Agência (promotor de agência), CLT (funcionário da 101), MEI ou Freelancer. Escolha na lista.")),
    ("item", ("Promotor", "Escreva o nome sempre do mesmo jeito em todos os meses. Se a agência tiver código ou matrícula do promotor, preencha a coluna Código do promotor: ele identifica a pessoa mesmo que o nome venha escrito diferente.")),
    ("item", ("4. CNPJ da loja", "O CNPJ da LOJA atendida, com 14 dígitos (com ou sem pontos). Só o CNPJ na célula, sem o nome. Se a conferência mostrar \"Verificar\", o número está errado.")),
    ("item", ("5. Mês de referência", "No formato MM/AAAA (ex.: 10/2026). Todas as linhas do arquivo devem ser do mesmo mês.")),
    ("item", ("6. Linha de exemplo", "A linha 2 da aba Atendimentos é só um exemplo: apague antes de enviar.")),
    ("", ""),
    ("secao", "Valor do mês: sempre por loja"),
    ("item", ("Cobra um valor fixo por loja", "Coloque o valor da loja no mês. Ex.: R$ 159,54 por loja → 159,54.")),
    ("item", ("Cobra por visita", "Multiplique o valor da visita pelas visitas do mês. Ex.: R$ 30,00 × 8 visitas = 240,00.")),
    ("item", ("Cobra um valor fechado por promotor", "Divida o valor do promotor entre as lojas que ele atende e coloque a parte de cada loja. Ex.: R$ 3.000,00 para 10 lojas → 300,00 em cada linha.")),
    ("item", ("MEI que recebe por dia", "Multiplique o valor do dia pelos dias trabalhados naquela loja no mês.")),
    ("", ""),
    ("secao", "Status"),
    ("item", ("Ativa", "A loja foi atendida no mês.")),
    ("item", ("Encerrada", "O atendimento da loja terminou neste mês (informe a data na Observação).")),
    ("", ""),
    ("secao", "Por que este modelo"),
    ("texto", "Com todas as agências no mesmo formato, o sistema da 101 junta o custo de cada loja ao faturamento dela, pelo CNPJ, e mostra se o atendimento está se pagando. Arquivos fora do modelo precisam ser refeitos à mão."),
]
r = 1
for tipo, conteudo in linhas:
    if tipo == "titulo":
        ins.cell(r, 2, conteudo).font = F(bold=True, size=16, color=AZUL)
        ins.row_dimensions[r].height = 28
    elif tipo == "sub":
        c = ins.cell(r, 2, conteudo); c.font = F(size=10, color=CINZA)
        ins.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
    elif tipo == "secao":
        for col in (2, 3):
            ins.cell(r, col).fill = CABECALHO
        ins.cell(r, 2, conteudo).font = F(bold=True, size=11, color="FFFFFF")
        ins.row_dimensions[r].height = 20
    elif tipo == "item":
        a, b = conteudo
        ins.cell(r, 2, a).font = F(bold=True, size=10)
        c = ins.cell(r, 3, b); c.font = F(size=10)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ins.cell(r, 2).alignment = Alignment(wrap_text=True, vertical="top")
        ins.row_dimensions[r].height = 15 * max(1, -(-len(b) // 95))
    elif tipo == "texto":
        c = ins.cell(r, 2, conteudo); c.font = F(size=10)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ins.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
        ins.row_dimensions[r].height = 30
    r += 1

# ------------------------------------------------------------------ Listas (oculta)
lst = wb.create_sheet("Listas")
lst["A1"], lst["B1"], lst["C1"] = "UF", "Status", "Tipo"
for i, uf in enumerate(UFS, start=2):
    lst.cell(i, 1, uf)
lst["B2"], lst["B3"] = "Ativa", "Encerrada"
for i, tipo in enumerate(TIPOS, start=2):
    lst.cell(i, 3, tipo)
lst.sheet_state = "hidden"

# ------------------------------------------------------------------ Atendimentos
at = wb.create_sheet("Atendimentos", 1)
at.sheet_view.showGridLines = False
for i, (titulo, largura, obrig, ajuda) in enumerate(COLUNAS, start=1):
    c = at.cell(1, i, titulo)
    c.font = F(bold=True, color="FFFFFF", size=10)
    c.fill = CABECALHO if i < CONFERENCIA else PatternFill("solid", fgColor=CINZA)
    c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    c.border = BORDA
    c.comment = Comment(("Obrigatória. " if obrig else "Opcional. ") + ajuda, "101 do Brasil", width=260, height=90)
    at.column_dimensions[c.column_letter].width = largura
at.row_dimensions[1].height = 34
at.freeze_panes = "A2"

for linha in range(2, ULTIMA + 1):
    for col in range(1, CONFERENCIA + 1):
        c = at.cell(linha, col)
        c.font = F(size=10)
        c.border = BORDA
        c.fill = AMARELO if col < CONFERENCIA else FUNDO_CINZA
    at.cell(linha, POS["Mês de referência"]).number_format = "@"   # 10/2026 não vira data
    at.cell(linha, POS["CNPJ da loja"]).number_format = "@"        # CNPJ não perde o zero da frente
    at.cell(linha, POS["Visitas no mês"]).number_format = "0"
    at.cell(linha, POS["Valor do mês (R$)"]).number_format = '#,##0.00'
    # Conferência do CNPJ: 14 dígitos e dígitos verificadores.
    cnpj = f'{LETRA["CNPJ da loja"]}{linha}'
    d = f'SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE({cnpj},".",""),"/",""),"-","")," ","")'
    s1 = f"SUMPRODUCT(VALUE(MID({d},{{1,2,3,4,5,6,7,8,9,10,11,12}},1)),{{5,4,3,2,9,8,7,6,5,4,3,2}})"
    s2 = f"SUMPRODUCT(VALUE(MID({d},{{1,2,3,4,5,6,7,8,9,10,11,12,13}},1)),{{6,5,4,3,2,9,8,7,6,5,4,3,2}})"
    dv1 = f"IF(MOD({s1},11)<2,0,11-MOD({s1},11))"
    dv2 = f"IF(MOD({s2},11)<2,0,11-MOD({s2},11))"
    at.cell(linha, CONFERENCIA).value = (
        f'=IF(TRIM({cnpj})="","",IF(LEN({d})<>14,"Verificar: precisa ter 14 dígitos",'
        f'IFERROR(IF(AND(VALUE(MID({d},13,1))={dv1},VALUE(MID({d},14,1))={dv2}),"OK",'
        f'"Verificar: número errado"),"Verificar: só números")))')
    at.cell(linha, CONFERENCIA).font = F(size=10, color=CINZA)

exemplo = ["10/2026", "Agência Exemplo Ltda", "Agência", "11.222.333/0001-81", "Supermercado Exemplo - Centro", "Curitiba", "PR",
           "Maria Silva", "", "Seg, Qui", 8, 240, "Ativa", "EXEMPLO - apague esta linha antes de enviar"]
for col, valor in enumerate(exemplo, start=1):
    c = at.cell(2, col, valor)
    c.font = F(size=10, italic=True, color="7A5C00")

# Validações
dv_uf = DataValidation(type="list", formula1=f"=Listas!$A$2:$A${len(UFS) + 1}", allow_blank=True,
                       error="Escolha a UF na lista.", errorTitle="UF inválida", showErrorMessage=True)
dv_status = DataValidation(type="list", formula1="=Listas!$B$2:$B$3", allow_blank=True,
                           error="Escolha Ativa ou Encerrada.", errorTitle="Status inválido", showErrorMessage=True)
dv_visitas = DataValidation(type="whole", operator="between", formula1="0", formula2="31", allow_blank=True,
                            error="Número inteiro de 0 a 31.", errorTitle="Visitas no mês", showErrorMessage=True)
dv_valor = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0", allow_blank=True,
                          error="Digite só o número, sem R$ (ex.: 240,00).", errorTitle="Valor do mês", showErrorMessage=True)
dv_tipo = DataValidation(type="list", formula1=f"=Listas!$C$2:$C${len(TIPOS) + 1}", allow_blank=True,
                         error="Escolha Agência, CLT, MEI ou Freelancer.", errorTitle="Tipo inválido", showErrorMessage=True)
dv_mes = DataValidation(type="custom", allow_blank=True,
                        formula1='AND(LEN(A2)=7,MID(A2,3,1)="/",ISNUMBER(VALUE(LEFT(A2,2))),VALUE(LEFT(A2,2))>=1,VALUE(LEFT(A2,2))<=12,ISNUMBER(VALUE(RIGHT(A2,4))))',
                        error="Use o formato MM/AAAA. Ex.: 10/2026", errorTitle="Mês de referência", showErrorMessage=True)
for dv, col in ((dv_uf, LETRA["UF"]), (dv_status, LETRA["Status"]), (dv_visitas, LETRA["Visitas no mês"]),
                (dv_valor, LETRA["Valor do mês (R$)"]), (dv_mes, LETRA["Mês de referência"]), (dv_tipo, LETRA["Tipo"])):
    at.add_data_validation(dv)
    dv.add(f"{col}2:{col}{ULTIMA}")
# CNPJ com problema fica vermelho.
N = LETRA["Conferência do CNPJ"]
at.conditional_formatting.add(f"{N}2:{N}{ULTIMA}", FormulaRule(formula=[f'LEFT({N}2,9)="Verificar"'],
                              font=Font(name="Arial", bold=True, color="B42318"),
                              fill=PatternFill("solid", fgColor="FDECEB")))
at.conditional_formatting.add(f"{N}2:{N}{ULTIMA}", FormulaRule(formula=[f'{N}2="OK"'], font=Font(name="Arial", color="1D7A46")))
at.auto_filter.ref = f"A1:{N}{ULTIMA}"

# ------------------------------------------------------------------ Resumo
rs = wb.create_sheet("Resumo", 2)
rs.sheet_view.showGridLines = False
rs.column_dimensions["A"].width = 3
rs.column_dimensions["B"].width = 34
rs.column_dimensions["C"].width = 20
rs["B1"] = "Resumo do arquivo (automático)"
rs["B1"].font = F(bold=True, size=14, color=AZUL)
rs["B2"] = "Não precisa preencher nada aqui: os números vêm da aba Atendimentos."
rs["B2"].font = F(size=10, color=CINZA)
itens = [
    ("Lojas no arquivo", f"=COUNTA(Atendimentos!{LETRA['Loja']}2:{LETRA['Loja']}1000)", "0"),
    ("Lojas ativas", f'=COUNTIF(Atendimentos!{LETRA["Status"]}2:{LETRA["Status"]}1000,"Ativa")', "0"),
    ("Visitas no mês", f"=SUM(Atendimentos!{LETRA['Visitas no mês']}2:{LETRA['Visitas no mês']}1000)", "0"),
    ("Valor total do mês (R$)", f"=SUM(Atendimentos!{LETRA['Valor do mês (R$)']}2:{LETRA['Valor do mês (R$)']}1000)", '#,##0.00'),
    ("CNPJs para verificar", f'=COUNTIF(Atendimentos!{N}2:{N}1000,"Verificar*")', "0"),
]
for i, (rotulo, formula, formato) in enumerate(itens, start=4):
    a = rs.cell(i, 2, rotulo); a.font = F(size=11); a.border = BORDA; a.fill = PatternFill("solid", fgColor=AZUL_CLARO)
    b = rs.cell(i, 3, formula); b.font = F(size=11, bold=True); b.border = BORDA; b.number_format = formato
rs["B10"] = "Lembrete: apague a linha de exemplo (linha 2 da aba Atendimentos) antes de enviar; ela entra nestes totais."
rs["B10"].font = F(size=9, italic=True, color=CINZA)

wb.active = 0
wb.save(SAIDA)
print("ok")
