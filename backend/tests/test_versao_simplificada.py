"""Abas da versão simplificada: Resumo por UF/supervisor, Faturamento do ERP e lojas cadastradas na tela."""
import io

import pandas as pd

from conftest import entrar, importar_cadastros, importar_faturamento

PERIODO = {"inicio": "2026-01", "fim": "2026-09"}


def test_resumo_por_uf_e_supervisor(cliente):
    entrar(cliente)
    importar_cadastros(cliente)
    importar_faturamento(cliente)
    painel = cliente.get("/api/painel", params=PERIODO).json()
    linhas = painel["por_uf"]
    ufs = [l for l in linhas if l["nivel"] == "uf"]
    assert ufs and any(l["nivel"] == "promotor" for l in linhas)
    # As UFs somam os cartões do Resumo.
    assert round(sum(l["custo_periodo"] for l in ufs), 2) == painel["resumo"]["custo"]
    assert round(sum(l["faturamento"] for l in ufs), 2) == painel["resumo"]["faturamento"]
    # Cada nível soma o de cima: supervisores somam a UF, promotores somam o supervisor.
    for i, linha in enumerate(linhas):
        if linha["nivel"] == "promotor":
            continue
        filho = "supervisor" if linha["nivel"] == "uf" else "promotor"
        abaixo = []
        for outra in linhas[i + 1:]:
            if outra["nivel"] == linha["nivel"] or (linha["nivel"] == "supervisor" and outra["nivel"] == "uf"):
                break
            if outra["nivel"] == filho:
                abaixo.append(outra)
        assert round(sum(x["custo_periodo"] for x in abaixo), 2) == linha["custo_periodo"]


def test_filtro_de_uf_usa_so_o_custo_das_lojas_da_uf(cliente):
    entrar(cliente)
    importar_cadastros(cliente)
    importar_faturamento(cliente)
    for uf in ("SC", "PR"):
        painel = cliente.get("/api/painel", params={**PERIODO, "uf": uf}).json()
        custo_lojas = sum(l["custo_periodo"] for l in painel["lojas"])
        assert abs(painel["resumo"]["custo"] - custo_lojas) < 0.05
        assert {l["uf"] for l in painel["por_uf"]} == {uf}
    # Período invertido na aba Faturamento é desvirado.
    certo = cliente.get("/api/faturamento", params=PERIODO).json()["totais"]["total"]
    invertido = cliente.get("/api/faturamento", params={"inicio": "2026-09", "fim": "2026-01"}).json()["totais"]["total"]
    assert invertido == certo > 0


def test_aba_faturamento_mostra_tudo_do_erp(cliente):
    entrar(cliente)
    importar_cadastros(cliente)
    previa, _ = importar_faturamento(cliente)
    dados = cliente.get("/api/faturamento", params=PERIODO).json()
    assert dados["meses"][0] == "2026-01"
    assert round(sum(u["total"] for u in dados["por_uf"]), 2) == dados["totais"]["total"]
    assert round(sum(c["total"] for c in dados["clientes"]), 2) == dados["totais"]["total"]
    assert dados["totais"]["total"] == round(previa["total_venda"], 2)
    assert any(c["no_roteiro"] for c in dados["clientes"])
    assert cliente.get("/api/faturamento", params={"inicio": "2026-13", "fim": "2026-09"}).status_code == 400


def test_cadastrar_loja_na_tela(cliente):
    entrar(cliente)
    importar_cadastros(cliente, "promotores")
    promotor = cliente.get("/api/promotores").json()[0]
    loja = {"pdv": {"cnpj_cpf": "", "nome_fantasia": "Mercado Novo", "cidade": "Joinville", "uf": "SC"},
            "promotor_id": promotor["id"], "data_inicio": "2026-01-01", "visitas_por_semana": 2}
    resposta = cliente.post("/api/lojas", json=loja)
    assert resposta.status_code == 200, resposta.text
    # A mesma loja com o mesmo promotor e data é recusada; o PDV não é duplicado.
    assert cliente.post("/api/lojas", json=loja).status_code == 400
    pdvs = [p for p in cliente.get("/api/pdvs").json() if p["nome_fantasia"] == "Mercado Novo"]
    assert len(pdvs) == 1 and pdvs[0]["cidade"] == "JOINVILLE"

    painel = cliente.get("/api/painel", params=PERIODO).json()
    linha = next(l for l in painel["grade"]["linhas"] if l["loja"] == "Mercado Novo")
    assert linha["roteiro_id"] == resposta.json()["roteiro_id"]


def test_aba_pr_sem_estado_usa_o_nome_da_aba(cliente):
    entrar(cliente)
    importar_cadastros(cliente, "promotores")
    promotor = cliente.get("/api/promotores").json()[0]
    pr = pd.DataFrame({"Colaborador": [promotor["nome"]], "CPF/CNPJ": [""], "RAZÃO SOCIAL": ["Loja do PR"],
                       "Coluna1": ["CURITIBA"], "Estado": [None], "JAN": [0]})
    arquivo = io.BytesIO()
    with pd.ExcelWriter(arquivo) as planilha:
        pr.to_excel(planilha, sheet_name="PR", index=False)
    resposta = cliente.post("/api/importacoes/roteiro", files={"arquivo": ("pr.xlsx", arquivo.getvalue())})
    assert resposta.status_code == 200, resposta.text
    pdv = next(p for p in cliente.get("/api/pdvs").json() if p["nome_fantasia"] == "Loja do PR")
    assert (pdv["cidade"], pdv["uf"]) == ("CURITIBA", "PR")


def test_exportar_excel_formatado(cliente):
    from openpyxl import load_workbook
    entrar(cliente)
    dados = {"titulo": "Lojas por UF", "subtitulo": "Período: jan/2026 a set/2026",
             "colunas": [{"titulo": "Loja", "formato": "texto"}, {"titulo": "Faturamento", "formato": "moeda"},
                         {"titulo": "% custo", "formato": "percentual"}],
             "linhas": [["=HYPERLINK(\"x\")", 1500.5, 8.1], ["Loja B", None, None]],
             "totais": [["Total", 1500.5, 8.1]], "destaques": [1]}
    resposta = cliente.post("/api/exportar", json=dados)
    assert resposta.status_code == 200, resposta.text
    assert resposta.headers["content-type"].startswith("application/vnd.openxmlformats")
    aba = load_workbook(io.BytesIO(resposta.content)).active
    assert aba["A1"].value == "Lojas por UF"
    assert [c.value for c in aba[4]] == ["Loja", "Faturamento", "% custo"]
    assert aba["A5"].data_type == "s" and aba["A5"].value.startswith("=")  # texto, não fórmula
    assert aba["B5"].value == 1500.5 and "R$" in aba["B5"].number_format
    assert abs(aba["C5"].value - 0.081) < 1e-9 and aba["C5"].number_format.startswith("0.0%")
    assert aba["A7"].font.bold and aba.freeze_panes == "A5"
    assert aba["A6"].font.bold and not aba["A5"].font.bold  # linha 1 (a partir de 0) em destaque
    assert not aba.sheet_view.showGridLines
    cliente.post("/api/logout")
    assert cliente.post("/api/exportar", json=dados).status_code == 401


def test_colaboradores_nao_encontrados(cliente, tmp_path):
    entrar(cliente)
    importar_cadastros(cliente, "promotores")
    arquivo = tmp_path / "roteiro.csv"
    arquivo.write_text("Colaborador;CPF/CNPJ;Razão Social;Cidade;UF\n"
                       "ANA TESTES;11.222.333/0001-81;LOJA X;TIJUCAS;SC\n"      # erro de digitação de "Ana Teste"
                       "ANA TESTES;11.444.777/0001-61;LOJA Y;TIJUCAS;SC\n"
                       "JOAO NINGUEM;11.444.777/0001-61;LOJA Z;ITAJAI;SC\n", encoding="utf-8")
    with open(arquivo, "rb") as conteudo:
        cliente.post("/api/importacoes/roteiro", files={"arquivo": ("roteiro.csv", conteudo)})
    dados = cliente.get("/api/colaboradores-pendentes").json()
    por_nome = {c["colaborador"]: c for c in dados["colaboradores"]}
    assert por_nome["ANA TESTES"]["quantidade"] == 2 and por_nome["ANA TESTES"]["ufs"] == ["SC"]
    assert por_nome["ANA TESTES"]["sugestao"]["nome"] == "Ana Teste"
    assert por_nome["JOAO NINGUEM"]["sugestao"] is None
    assert any(p["nome"] == "Ana Teste" for p in dados["promotores_sem_loja"])

    resposta = cliente.post("/api/pendencias/colaborador", json={
        "colaborador": "ANA TESTES", "promotor_id": por_nome["ANA TESTES"]["sugestao"]["id"], "data_inicio": "2026-01-01"})
    assert resposta.json() == {"vinculos_criados": 2}
    assert cliente.delete("/api/colaboradores-pendentes", params={"colaborador": "JOAO NINGUEM"}).json() == {"descartadas": 1}
    dados = cliente.get("/api/colaboradores-pendentes").json()
    assert dados["colaboradores"] == []
    assert not any(p["nome"] == "Ana Teste" for p in dados["promotores_sem_loja"])


def test_ligacao_fica_lembrada_na_proxima_importacao(cliente, tmp_path):
    entrar(cliente)
    importar_cadastros(cliente, "promotores")
    arquivo = tmp_path / "roteiro.csv"
    arquivo.write_text("Colaborador;CPF/CNPJ;Razão Social;Cidade;UF\n"
                       "ANA TESTES;11.222.333/0001-81;LOJA X;TIJUCAS;SC\n", encoding="utf-8")

    def importar():
        with open(arquivo, "rb") as conteudo:
            return cliente.post("/api/importacoes/roteiro", files={"arquivo": ("roteiro.csv", conteudo)}).json()

    assert importar()["cadastros"]["pendentes"] == 1
    ana = next(p for p in cliente.get("/api/promotores").json() if p["nome"] == "Ana Teste")
    cliente.post("/api/pendencias/colaborador", json={"colaborador": "ANA TESTES", "promotor_id": ana["id"],
                                                      "data_inicio": "2026-01-01"})
    lembrados = cliente.get("/api/colaboradores-pendentes").json()["lembrados"]
    assert [(l["nome"], l["promotor"]) for l in lembrados] == [("ANA TESTES", "Ana Teste")]

    # Reimportar: o nome já vai direto para a Ana, sem pendência e sem duplicar a loja.
    resultado = importar()["cadastros"]
    assert (resultado["pendentes"], resultado["criados"], resultado["mantidos"]) == (0, 0, 1)
    # Ao esquecer a ligação, a próxima importação volta a pedir.
    assert cliente.delete(f"/api/colaboradores-pendentes/lembrados/{lembrados[0]['id']}").status_code == 200
    assert importar()["cadastros"]["pendentes"] == 1
