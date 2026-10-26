from conftest import EXEMPLOS, entrar, importar_cadastros, importar_faturamento

PERIODO = {"inicio": "2026-01", "fim": "2026-09"}


def _faturamento_total(cliente):
    return cliente.get("/api/painel", params=PERIODO).json()["resumo"]["faturamento"]


def test_previa_mostra_resumo_antes_de_gravar(cliente):
    entrar(cliente)
    importar_cadastros(cliente, "promotores")         # sem roteiro: todos os CNPJs ficam "sem roteiro"
    with open(EXEMPLOS / "faturamento_exemplo.xlsx", "rb") as arquivo:
        previa = cliente.post("/api/importacoes/faturamento/previa", files={"arquivo": ("f.xlsx", arquivo)}).json()
    assert previa["meses"][0] == "2026-01" and previa["meses_existentes"] == []
    assert previa["linhas_com_erro"] == 0 and previa["clientes"] == 7
    assert previa["cnpjs_sem_roteiro"]["quantidade"] == 7
    assert {t["tipo"] for t in previa["tipos_nf"]} == {"1-Venda", "2-Devolucao", "5-Bonificacao"}
    assert cliente.get("/api/opcoes").json()["meses"] == []   # nada gravado ainda


def test_linhas_com_erro_sao_listadas(cliente, tmp_path):
    entrar(cliente)
    arquivo = tmp_path / "erros.csv"
    arquivo.write_text("DT EMIS;NUM NF;CNPJ CPF;TOTAL VENDA;TIPO NF\n"
                       "05/01/2026;1;11.222.333/0001-81;1.000,50;1-Venda\n"
                       "data ruim;2;11.222.333/0001-81;10;1-Venda\n"
                       "05/01/2026;3;;10;1-Venda\n"
                       "05/01/2026;4;11.222.333/0001-81;abc;1-Venda\n", encoding="utf-8")
    with open(arquivo, "rb") as conteudo:
        previa = cliente.post("/api/importacoes/faturamento/previa", files={"arquivo": ("erros.csv", conteudo)}).json()
    assert previa["linhas_validas"] == 1 and previa["total_venda"] == 1000.5
    assert [(e["linha"], e["motivo"]) for e in previa["erros"]] == [
        (3, "data inválida"), (4, "CNPJ/CPF vazio"), (5, "TOTAL VENDA não é número")]


def test_reimportar_pede_confirmacao_e_nao_duplica(cliente):
    entrar(cliente)
    importar_cadastros(cliente)
    _, primeira = importar_faturamento(cliente)
    assert primeira.status_code == 200
    total = _faturamento_total(cliente)

    _, sem_confirmar = importar_faturamento(cliente)
    assert sem_confirmar.status_code == 400 and "Confirme a substituição" in sem_confirmar.json()["detail"]
    _, segunda = importar_faturamento(cliente, substituir=True)
    assert segunda.status_code == 200 and len(segunda.json()["meses_substituidos"]) == 9
    assert _faturamento_total(cliente) == total

    historico = cliente.get("/api/importacoes").json()
    assert [(h["tipo"], h["situacao"]) for h in historico[:2]] == [("faturamento", "ativa"), ("faturamento", "substituida")]


def test_desfazer_importacao(cliente):
    entrar(cliente)
    importar_cadastros(cliente)
    _, resposta = importar_faturamento(cliente)
    ident = resposta.json()["importacao_id"]
    assert cliente.post(f"/api/importacoes/{ident}/desfazer").json()["itens_apagados"] > 0
    assert cliente.get("/api/opcoes").json()["meses"] == []
    assert cliente.post(f"/api/importacoes/{ident}/desfazer").status_code == 400


def test_importacao_inicial_da_planilha_e_conferencia(cliente):
    entrar(cliente)
    with open(EXEMPLOS / "planilha_completa_exemplo.xlsx", "rb") as arquivo:
        resultado = cliente.post("/api/importacoes/planilha", files={"arquivo": ("ROTEIROS.xlsx", arquivo)}).json()
    assert resultado["promotores"]["cadastros"]["criados"] == 4
    assert resultado["roteiro"]["cadastros"]["criados"] == 11
    assert resultado["conferencia"] == {"abas": ["PR", "SC"], "ano": 2026}
    token = resultado["faturamento"]["token"]
    assert cliente.post(f"/api/importacoes/faturamento/{token}/confirmar", json={}).status_code == 200

    conferencia = cliente.get("/api/conferencia").json()
    assert conferencia["disponivel"] and conferencia["ano"] == 2026
    for aba in conferencia["abas"]:
        # Com as regras padrão (TOTAL VENDA, todos os tipos), o sistema bate com a planilha.
        assert aba["total"]["diferenca"] == 0, aba
    pr = next(a for a in conferencia["abas"] if a["aba"] == "PR")
    assert pr["total"]["sem_repetir_cnpj"] < pr["total"]["planilha"]   # REDE OMEGA e LAMBDA repetem CNPJ

    # Rodar a importação inicial de novo não duplica os cadastros.
    with open(EXEMPLOS / "planilha_completa_exemplo.xlsx", "rb") as arquivo:
        de_novo = cliente.post("/api/importacoes/planilha", files={"arquivo": ("ROTEIROS.xlsx", arquivo)}).json()
    assert de_novo["roteiro"]["cadastros"]["criados"] == 0
    assert len(cliente.get("/api/pdvs").json()) == 11


def test_pendencias_e_lojas_com_mesmo_cnpj(cliente):
    entrar(cliente)
    importar_cadastros(cliente)
    importar_faturamento(cliente)
    pendencias = cliente.get("/api/pendencias").json()
    mesmo = {g["cnpj"]: g for g in pendencias["lojas_mesmo_cnpj"]}
    assert set(mesmo) == {"00000001000101", "00000005000105", "00000008000108"}
    lambda_ = mesmo["00000008000108"]
    assert lambda_["cod_cli_no_faturamento"] == ["2001", "2002"] and not lambda_["separado_por_cod_cli"]
    assert "MERCADO DELTA" in {p["pdv"] for p in pendencias["pdvs_sem_faturamento"]}
    assert pendencias["roteiros_sem_visitas"] == 0 and pendencias["total"] > 0

    # Preenchendo o COD CLI de cada loja da LAMBDA, o faturamento passa a ser separado.
    for loja in lambda_["lojas"]:
        codigo = "2001" if "CENTRO" in loja["nome"] else "2002"
        pdv = next(p for p in cliente.get("/api/pdvs").json() if p["id"] == loja["id"])
        assert cliente.put(f"/api/pdvs/{loja['id']}", json={**pdv, "cod_cli_erp": codigo}).status_code == 200
    pendencias = cliente.get("/api/pendencias").json()
    assert next(g for g in pendencias["lojas_mesmo_cnpj"] if g["cnpj"] == "00000008000108")["separado_por_cod_cli"]
    lojas = cliente.get("/api/painel", params=PERIODO).json()["lojas"]
    lambda_lojas = [l for l in lojas if l["loja"].startswith("LAMBDA")]
    assert all(l["separado_por_cod_cli"] and not l["compartilhado"] for l in lambda_lojas)
    assert lambda_lojas[0]["faturamento"] != lambda_lojas[1]["faturamento"]


def test_resolver_colaborador_pendente(cliente, tmp_path):
    entrar(cliente)
    importar_cadastros(cliente, "promotores")
    arquivo = tmp_path / "roteiro.csv"
    arquivo.write_text("Colaborador;CPF/CNPJ;Razão Social;Cidade;UF\n"
                       "FULANO DE TAL;11.222.333/0001-81;LOJA X;TIJUCAS;SC\n"
                       "FULANO DE TAL;11.444.777/0001-61;LOJA Y;TIJUCAS;SC\n", encoding="utf-8")
    with open(arquivo, "rb") as conteudo:
        cliente.post("/api/importacoes/roteiro", files={"arquivo": ("roteiro.csv", conteudo)})
    pendencias = cliente.get("/api/pendencias").json()
    assert pendencias["colaboradores_sem_promotor"][0]["quantidade"] == 2
    ana = next(p for p in cliente.get("/api/promotores").json() if p["nome"] == "Ana Teste")
    resposta = cliente.post("/api/pendencias/colaborador", json={
        "colaborador": "FULANO DE TAL", "promotor_id": ana["id"], "data_inicio": "2026-01-01"})
    assert resposta.json() == {"vinculos_criados": 2}
    assert cliente.get("/api/pendencias").json()["colaboradores_sem_promotor"] == []
