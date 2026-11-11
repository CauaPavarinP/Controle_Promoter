from conftest import entrar, importar_atendimento, importar_faturamento


def test_rotas_exigem_login(cliente):
    assert cliente.get("/health").status_code == 200
    assert cliente.get("/api/opcoes").status_code == 401
    assert cliente.get("/api/painel", params={"inicio": "2026-01", "fim": "2026-09"}).status_code == 401
    assert cliente.post("/api/login", json={"usuario": "mauricio", "senha": "errada"}).status_code == 401


def test_importar_e_consultar_painel(cliente):
    entrar(cliente)
    importar_atendimento(cliente)
    _, resposta = importar_faturamento(cliente)
    assert resposta.status_code == 200, resposta.text

    opcoes = cliente.get("/api/opcoes").json()
    assert opcoes["meses"][0] == "2026-01"
    assert [a["nome"] for a in opcoes["agencias"]] == ["101 do Brasil", "Agência Alfa"]
    assert len(opcoes["promotores"]) == 4 and opcoes["ufs"] == ["PR", "SC"]

    painel = cliente.get("/api/painel", params={"inicio": "2026-01", "fim": "2026-09"}).json()
    assert painel["resumo"]["promotores"] == 4
    assert painel["resumo"]["lojas"] == 11
    assert painel["resumo"]["faturamento"] > 0

    cliente.post("/api/logout")
    assert cliente.get("/api/opcoes").status_code == 401


def test_importacao_com_arquivo_errado(cliente):
    entrar(cliente)
    from conftest import EXEMPLOS
    with open(EXEMPLOS / "atendimento_exemplo.xlsx", "rb") as arquivo:
        resposta = cliente.post("/api/importacoes/faturamento/previa", files={"arquivo": ("p.xlsx", arquivo)})
    assert resposta.status_code == 400
    assert "faturamento" in resposta.json()["detail"]


def test_regras_salvas_mudam_o_painel(cliente):
    entrar(cliente)
    importar_atendimento(cliente)
    importar_faturamento(cliente)

    dados = cliente.get("/api/regras").json()
    # Padrão: todos os tipos de nota somam (o valor é o VLR TOTAL do ERP).
    assert {t["tipo"]: t["acao"] for t in dados["tipos_nf"]} == {
        "1-Venda": "soma", "5-Bonificacao": "soma", "2-Devolucao": "soma"}
    parametros = {"inicio": "2026-01", "fim": "2026-09"}
    antes = cliente.get("/api/painel", params=parametros).json()["resumo"]["faturamento"]

    regras = dados["regras"]
    regras["tipos_nf"]["2 DEVOLUCAO"] = "ignora"       # a devolução de -500 deixa de contar
    assert cliente.put("/api/regras", json=regras).status_code == 200
    assert cliente.get("/api/painel", params=parametros).json()["resumo"]["faturamento"] == antes + 500

    regras["somente_receita"] = True                    # a bonificação (RECEITA = NAO) de 300 sai
    assert cliente.put("/api/regras", json=regras).status_code == 200
    assert cliente.get("/api/painel", params=parametros).json()["resumo"]["faturamento"] == antes + 500 - 300

    regras["limite_percentual"] = "abc"
    assert cliente.put("/api/regras", json=regras).status_code == 400
