"""Sistema alimentado só pelo arquivo do ERP (faturamento) e pelos arquivos das agências (atendimento)."""
import io

from openpyxl import load_workbook

from conftest import EXEMPLOS, entrar, importar_atendimento, importar_faturamento

PERIODO = {"inicio": "2026-01", "fim": "2026-09"}
COLUNAS_MODELO = ["Mês de referência", "Agência ou MEI", "CNPJ da loja", "Loja", "Cidade", "UF", "Promotor",
                  "Código do promotor", "Dias de visita", "Visitas no mês", "Valor do mês (R$)", "Status", "Observação"]


def _arquivo(linhas: list[list]) -> bytes:
    """Arquivo no modelo das agências com as linhas dadas (sem a linha de exemplo)."""
    livro = load_workbook(EXEMPLOS / "modelo_atendimento_agencias.xlsx")
    aba = livro["Atendimentos"]
    for coluna in range(1, 14):
        aba.cell(2, coluna).value = None
    for numero, valores in enumerate(linhas, start=2):
        for coluna, valor in enumerate(valores, start=1):
            aba.cell(numero, coluna, valor)
    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()


def _linha(mes="10/2026", agencia="Agência Beta", cnpj="11.222.333/0001-81", loja="Loja Um", promotor="Paula",
           codigo="", valor=100, visitas=4, cidade="Curitiba", uf="PR", status="Ativa", observacao=""):
    return [mes, agencia, cnpj, loja, cidade, uf, promotor, codigo, "Ter", visitas, valor, status, observacao]


def _previa(cliente, conteudo):
    return cliente.post("/api/importacoes/atendimento/previa", files={"arquivo": ("a.xlsx", conteudo)})


# --- Leitura do arquivo da agência ------------------------------------------------------------------------------

def test_modelo_para_download_tem_as_colunas_certas(cliente):
    entrar(cliente)
    resposta = cliente.get("/api/modelo-atendimento")
    assert resposta.status_code == 200
    livro = load_workbook(io.BytesIO(resposta.content))
    assert livro.sheetnames[:3] == ["Instruções", "Atendimentos", "Resumo"]
    assert [c.value for c in livro["Atendimentos"][1]][:13] == COLUNAS_MODELO
    # A linha de exemplo do modelo é ignorada: o modelo vazio não tem nada para importar.
    assert _previa(cliente, resposta.content).status_code == 400


def test_cnpj_com_zero_a_mais_e_corrigido_e_invalido_entra_sem_cnpj(cliente):
    entrar(cliente)
    previa = _previa(cliente, _arquivo([
        _linha(cnpj="009.477.652/0042-64", loja="Fort Coronel"),        # 15 dígitos com zero na frente: corrige
        _linha(cnpj="9477652004183", loja="Fort Guanandi"),              # 13 dígitos (o Excel comeu o zero)
        _linha(cnpj="009.477.652/01096-06", loja="Fort Cafezais"),       # 16 dígitos: inválido
        _linha(cnpj="77.752.293/0107-46 - LAR SANTA HELENA", loja="Lar Santa Helena"),  # CNPJ junto com o nome
        _linha(cnpj="09.447.652/0020-59", loja="COMPER CD"),             # 14 dígitos, verificador errado
    ])).json()
    assert previa["linhas_validas"] == 5
    assert any("corrigidos" in a and "Fort Coronel" in a and "Fort Guanandi" in a for a in previa["avisos"])
    assert any("2 loja(s) sem CNPJ válido" in a for a in previa["avisos"])
    invalidos = {c["loja"]: c for c in previa["cnpjs_invalidos"]}
    assert set(invalidos) == {"Fort Cafezais", "COMPER CD"}
    assert invalidos["COMPER CD"] == {"linha": 6, "aba": "Atendimentos", "loja": "COMPER CD",
                                      "cnpj": "09.447.652/0020-59", "motivo": "dígito verificador não confere"}
    assert invalidos["Fort Cafezais"]["motivo"] == "16 dígitos"
    importar = cliente.post(f"/api/importacoes/atendimento/{previa['token']}/confirmar", json={})
    assert importar.status_code == 200
    lojas = {l["loja"]: l["cnpj"] for l in cliente.get("/api/painel", params={"inicio": "2026-10", "fim": "2026-10"}).json()["lojas"]}
    assert lojas == {"Fort Coronel": "09477652004264", "Fort Guanandi": "09477652004183", "Fort Cafezais": "",
                     "Lar Santa Helena": "77752293010746", "COMPER CD": ""}


def test_linhas_com_erro_exemplo_e_total_sao_tratadas(cliente):
    entrar(cliente)
    previa = _previa(cliente, _arquivo([
        _linha(),
        _linha(mes="13/2026", loja="Mês errado"),
        _linha(agencia="", loja="Sem agência"),
        _linha(valor="cem reais", loja="Valor errado"),
        _linha(valor=None, loja="Sem valor"),
        _linha(promotor="", loja="Sem promotor"),
        _linha(observacao="EXEMPLO - apague esta linha antes de enviar", loja="Exemplo"),
        [None, None, None, None, None, None, None, None, None, None, 1700, None, None],   # linha de total
        _linha(mes="2026-11", loja="Mês no outro formato"),
    ])).json()
    assert previa["linhas_validas"] == 4
    assert sorted(e["motivo"].split(" (")[0].split(":")[0] for e in previa["erros"]) == [
        "Agência ou MEI vazio", "Mês de referência vazio ou inválido", "Valor do mês não é número"]
    assert any("sem valor" in a and "Sem valor" in a for a in previa["avisos"])
    assert any("Sem promotor informado" in a for a in previa["avisos"])
    assert [g["mes"] for g in previa["grupos"]] == ["2026-10", "2026-11"]


def test_arquivo_fora_do_modelo_e_recusado_com_mensagem(cliente):
    entrar(cliente)
    with open(EXEMPLOS / "faturamento_exemplo.xlsx", "rb") as arquivo:
        resposta = _previa(cliente, arquivo.read())
    assert resposta.status_code == 400 and "Agência ou MEI" in resposta.json()["detail"]


def test_nomes_parecidos_e_codigo_do_promotor(cliente):
    entrar(cliente)
    previa = _previa(cliente, _arquivo([
        _linha(promotor="Marceli", loja="Loja Um"),
        _linha(promotor="Marcely", loja="Loja Dois"),
        _linha(promotor="João", codigo="77", loja="Loja Três"),
        _linha(mes="11/2026", promotor="Joao Silva", codigo="77", loja="Loja Três"),   # mesmo código, nome diferente
    ])).json()
    assert any("parecidos" in a and "Marceli / Marcely" in a for a in previa["avisos"])
    assert previa["promotores"] == 3       # Marceli, Marcely e o código 77
    cliente.post(f"/api/importacoes/atendimento/{previa['token']}/confirmar", json={})
    promotores = cliente.get("/api/painel", params={"inicio": "2026-10", "fim": "2026-11"}).json()["promotores"]
    codigo_77 = next(p for p in promotores if p["codigo"] == "77")
    assert codigo_77["nome"] == "Joao Silva" and codigo_77["meses_com_atendimento"] == 2


def test_reimportar_pede_confirmacao_substitui_e_desfaz(cliente):
    entrar(cliente)
    importar_atendimento(cliente)
    previa = _previa(cliente, (EXEMPLOS / "atendimento_exemplo.xlsx").read_bytes()).json()
    assert len(previa["substituir"]) == 18 and all(g["ja_existe"] for g in previa["grupos"])
    sem_confirmar = cliente.post(f"/api/importacoes/atendimento/{previa['token']}/confirmar", json={})
    assert sem_confirmar.status_code == 400 and "substituição" in sem_confirmar.json()["detail"]
    resultado = cliente.post(f"/api/importacoes/atendimento/{previa['token']}/confirmar", json={"substituir": True}).json()
    assert len(resultado["substituidos"]) == 18
    assert cliente.get("/api/painel", params=PERIODO).json()["resumo"]["custo"] == 44200   # não duplicou
    historico = cliente.get("/api/importacoes").json()
    assert [i["situacao"] for i in historico if i["tipo"] == "atendimento"] == ["ativa", "substituida"]
    assert cliente.post(f"/api/importacoes/{resultado['importacao_id']}/desfazer").status_code == 200
    assert cliente.get("/api/painel", params=PERIODO).json()["resumo"]["custo"] == 0


def test_so_administrador_importa(cliente):
    entrar(cliente)
    novo = cliente.post("/api/usuarios", json={"nome": "Consulta", "usuario": "consulta", "perfil": "consulta"}).json()
    cliente.post("/api/logout")
    entrar(cliente, "consulta", novo["senha_provisoria"])
    cliente.put("/api/minha-senha", json={"senha_atual": novo["senha_provisoria"], "nova_senha": "senha-nova-123"})
    assert _previa(cliente, _arquivo([_linha()])).status_code == 403
    assert cliente.get("/api/painel", params=PERIODO).status_code == 200


# --- Cálculo: custo das agências × faturamento do ERP -----------------------------------------------------------

def test_totais_batem_em_todas_as_visoes(cliente):
    entrar(cliente)
    importar_faturamento(cliente)
    importar_atendimento(cliente)
    painel = cliente.get("/api/painel", params=PERIODO).json()
    resumo = painel["resumo"]
    assert resumo["custo"] == 44200 and resumo["agencias"] == 2 and resumo["promotores"] == 4 and resumo["lojas"] == 11
    erp = cliente.get("/api/faturamento", params=PERIODO).json()
    for visao in ("promotores", "lojas", "agencias"):
        assert round(sum(l["faturamento"] for l in painel[visao]), 2) == resumo["faturamento"], visao
        assert round(sum(l["custo_periodo"] for l in painel[visao]), 2) == resumo["custo"], visao
    ufs = [l for l in painel["por_uf"] if l["nivel"] == "uf"]
    assert round(sum(l["faturamento"] for l in ufs), 2) == resumo["faturamento"]
    assert painel["grade"]["totais"]["total"] == resumo["faturamento"]
    assert round(sum(m["faturamento"] for m in painel["mes_a_mes"]), 2) == resumo["faturamento"]
    # Toda loja do ERP de exemplo está no arquivo das agências: nenhum cliente "fora do roteiro".
    assert all(c["no_roteiro"] for c in erp["clientes"])
    assert resumo["faturamento"] <= erp["totais"]["total"]
    # Árvore UF → agência → promotor.
    assert [l["nivel"] for l in painel["por_uf"]][:4] == ["uf", "agencia", "promotor", "promotor"]


def test_faturamento_so_conta_nos_meses_com_atendimento(cliente):
    """Bruno começa em fevereiro: as compras de janeiro das lojas dele não contam para ele."""
    entrar(cliente)
    importar_faturamento(cliente)
    importar_atendimento(cliente)
    bruno = lambda p: next(x for x in p["promotores"] if x["nome"] == "Bruno Teste")
    jan = cliente.get("/api/painel", params={"inicio": "2026-01", "fim": "2026-01"}).json()
    assert not any(p["nome"] == "Bruno Teste" for p in jan["promotores"])
    ano = bruno(cliente.get("/api/painel", params=PERIODO).json())
    assert ano["primeiro_mes"] == "2026-02" and ano["meses_com_atendimento"] == 8


def test_cnpj_de_varias_lojas_divide_o_faturamento(cliente):
    entrar(cliente)
    importar_faturamento(cliente)
    importar_atendimento(cliente)
    lojas = {l["loja"]: l for l in cliente.get("/api/painel", params=PERIODO).json()["lojas"]}
    centro, praia = lojas["REDE ALFA - CENTRO"], lojas["REDE ALFA - PRAIA"]
    assert centro["compartilhado"] and praia["compartilhado"] and centro["faturamento"] == praia["faturamento"]
    erp = {c["cnpj"]: c["total"] for c in cliente.get("/api/faturamento", params=PERIODO).json()["clientes"]}
    assert round(centro["faturamento"] + praia["faturamento"], 2) == erp["00000001000136"]


def test_filtros_por_agencia_promotor_uf_e_loja(cliente):
    entrar(cliente)
    importar_faturamento(cliente)
    importar_atendimento(cliente)
    opcoes = cliente.get("/api/opcoes").json()
    alfa = next(a["chave"] for a in opcoes["agencias"] if a["nome"] == "Agência Alfa")
    so_alfa = cliente.get("/api/painel", params={**PERIODO, "agencia": alfa}).json()
    assert {p["nome"] for p in so_alfa["promotores"]} == {"Ana Teste", "Bruno Teste"}
    carla = next(p["chave"] for p in opcoes["promotores"] if p["nome"] == "Carla Teste")
    so_carla = cliente.get("/api/painel", params={**PERIODO, "promotor": carla}).json()
    assert {l["loja"] for l in so_carla["lojas"]} == {"REDE OMEGA - BATEL", "REDE OMEGA - PORTAO", "ATACADO SIGMA"}
    assert len(so_carla["mes_a_mes"]) == 9 and all(m["com_atendimento"] for m in so_carla["mes_a_mes"])
    assert {l["uf"] for l in cliente.get("/api/painel", params={**PERIODO, "uf": "SC"}).json()["lojas"]} == {"SC"}
    assert cliente.get("/api/painel", params={**PERIODO, "loja": "SUPER GAMA"}).json()["resumo"]["lojas"] == 1


def test_mes_sem_arquivo_de_agencia_e_avisado(cliente):
    entrar(cliente)
    importar_faturamento(cliente)
    importar_atendimento(cliente, _arquivo([_linha(mes="03/2026", cnpj="00.000.006/0001-69", loja="ATACADO SIGMA")]))
    painel = cliente.get("/api/painel", params={"inicio": "2026-02", "fim": "2026-03"}).json()
    assert any("sem nenhum arquivo de agência" in a and "2026-02" in a for a in painel["resumo"]["avisos"])
    vazio = cliente.get("/api/painel", params={"inicio": "2026-05", "fim": "2026-05"}).json()
    assert vazio["resumo"]["custo"] == 0 and vazio["promotores"] == []


def test_vale_a_pena_com_a_margem(cliente):
    """Resultado = compras das lojas × margem da 101 − custo do atendimento."""
    entrar(cliente)
    importar_faturamento(cliente)
    importar_atendimento(cliente)
    painel = cliente.get("/api/painel", params=PERIODO).json()
    assert all(p["resultado"] is None for p in painel["promotores"])   # sem margem: só o %
    regras = cliente.get("/api/regras").json()["regras"]
    assert regras["valor_faturamento"] == "vlr_total"
    assert cliente.put("/api/regras", json={**regras, "margem_percentual": "abc"}).status_code == 400
    assert cliente.put("/api/regras", json={**regras, "margem_percentual": 150}).status_code == 400
    assert cliente.put("/api/regras", json={**regras, "margem_percentual": "10,5"}).json()["regras"]["margem_percentual"] == 10.5
    painel = cliente.get("/api/painel", params=PERIODO).json()   # a resposta guardada foi descartada
    for visao in ("promotores", "lojas", "agencias", "mes_a_mes"):
        for linha in painel[visao]:
            lucro = linha["faturamento"] * 0.105
            assert abs(linha["lucro_estimado"] - lucro) < 0.02
            assert abs(linha["resultado"] - (lucro - linha["custo_periodo"])) < 0.02
            if lucro > 0:
                assert abs(linha["percentual_do_lucro"] - linha["custo_periodo"] / lucro * 100) < 0.1
    resumo = painel["resumo"]
    assert abs(sum(p["resultado"] for p in painel["promotores"]) - resumo["resultado"]) < 1
    assert painel["regras"]["margem_percentual"] == 10.5


def test_apagar_dados_das_agencias(cliente):
    entrar(cliente)
    importar_faturamento(cliente)
    importar_atendimento(cliente)
    assert cliente.post("/api/cadastros/apagar", json={"confirmacao": "sim"}).status_code == 400
    resposta = cliente.post("/api/cadastros/apagar", json={"confirmacao": "apagar"})
    assert resposta.status_code == 200 and resposta.json()["atendimentos"] == 97
    painel = cliente.get("/api/painel", params=PERIODO).json()
    assert painel["resumo"]["custo"] == 0 and painel["promotores"] == []
    assert cliente.get("/api/opcoes").json()["meses"]   # o faturamento fica
    importar_atendimento(cliente)                        # dá para importar de novo
    assert cliente.get("/api/painel", params=PERIODO).json()["resumo"]["custo"] == 44200


# --- Respostas guardadas, compressão e exportação -----------------------------------------------------------------

def test_resumo_guardado_nunca_fica_velho(cliente, banco):
    """Resposta guardada sai rápido, mas qualquer alteração (importar, desfazer, regras) faz recalcular."""
    entrar(cliente)
    importar_faturamento(cliente)
    chamadas = []
    original = banco.main.calcular_painel

    def contando(*args, **kwargs):
        chamadas.append(1)
        return original(*args, **kwargs)
    banco.main.calcular_painel = contando
    try:
        assert cliente.get("/api/painel", params=PERIODO).json()["resumo"]["custo"] == 0
        cliente.get("/api/painel", params=PERIODO)
        assert len(chamadas) == 1                       # a 2ª veio guardada
        resultado = importar_atendimento(cliente)
        assert cliente.get("/api/painel", params=PERIODO).json()["resumo"]["custo"] == 44200 and len(chamadas) == 2
        cliente.get("/api/painel", params={**PERIODO, "uf": "SC"})
        assert len(chamadas) == 3                       # filtro diferente é outra resposta
        assert cliente.post(f"/api/importacoes/{resultado['importacao_id']}/desfazer").status_code == 200
        assert cliente.get("/api/painel", params=PERIODO).json()["resumo"]["custo"] == 0
    finally:
        banco.main.calcular_painel = original


def test_respostas_grandes_vao_comprimidas(cliente):
    entrar(cliente)
    importar_faturamento(cliente)
    importar_atendimento(cliente)
    resposta = cliente.get("/api/painel", params=PERIODO, headers={"Accept-Encoding": "gzip"})
    assert resposta.status_code == 200 and resposta.headers.get("content-encoding") == "gzip"
    assert resposta.json()["resumo"]["faturamento"] > 0


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


# --- Lojas repetidas por outra agência, linhas descartadas, contadores ---------------------------------------------

GRUBAL = "GRUBAL COMERCIO DE BEBIDAS AMERICAN LATIN LTDA"


def _grubal(agencia, valor=200, cnpjs=("11.222.333/0001-81", "77.752.293/0107-46"), sem_cnpj=True):
    linhas = [_linha(agencia=agencia, cnpj=c, loja=f"Loja {i}", valor=valor) for i, c in enumerate(cnpjs)]
    if sem_cnpj:
        linhas.append(_linha(agencia=agencia, cnpj="", loja="Atacadão Araçagy", valor=valor))
    return _arquivo(linhas)


def test_mesma_loja_no_mesmo_mes_por_outra_agencia_e_avisada(cliente):
    """O caso real: o arquivo da GRUBAL e depois um consolidado com as mesmas lojas e outro nome de agência."""
    entrar(cliente)
    importar_atendimento(cliente, _grubal(GRUBAL))
    previa = _previa(cliente, _grubal("GRUBAL (Demonstrativo outubro)")).json()
    repetidas = previa["repetidas_outra_agencia"]
    assert len(repetidas) == 3
    assert {r["agencia_existente"] for r in repetidas} == {GRUBAL}
    assert {r["loja"] for r in repetidas} == {"Loja 0", "Loja 1", "Atacadão Araçagy"}   # sem CNPJ: pelo nome
    assert all(r["mes"] == "2026-10" and "_chave" not in r for r in repetidas)
    # Sem escolher, não grava (o custo seria contado duas vezes).
    sem_escolha = cliente.post(f"/api/importacoes/atendimento/{previa['token']}/confirmar", json={})
    assert sem_escolha.status_code == 400 and "outra agência" in sem_escolha.json()["detail"]
    assert cliente.post(f"/api/importacoes/atendimento/{previa['token']}/confirmar",
                        json={"repetidas": "qualquer"}).status_code == 422
    custo = lambda: cliente.get("/api/painel", params={"inicio": "2026-10", "fim": "2026-10"}).json()["resumo"]["custo"]
    assert custo() == 600


def test_repetidas_ignorar_grava_so_as_novas(cliente):
    entrar(cliente)
    importar_atendimento(cliente, _grubal(GRUBAL))
    arquivo = _grubal("GRUBAL (Demonstrativo outubro)", cnpjs=("11.222.333/0001-81", "09.477.652/0042-64"),
                      sem_cnpj=False)
    previa = _previa(cliente, arquivo).json()
    assert [r["loja"] for r in previa["repetidas_outra_agencia"]] == ["Loja 0"]
    resultado = cliente.post(f"/api/importacoes/atendimento/{previa['token']}/confirmar",
                             json={"repetidas": "ignorar"}).json()
    assert resultado["repetidas_ignoradas"] == 1 and resultado["linhas_importadas"] == 1
    painel = cliente.get("/api/painel", params={"inicio": "2026-10", "fim": "2026-10"}).json()
    assert painel["resumo"]["custo"] == 800
    agencias = {a["nome"]: a["lojas"] for a in painel["agencias"]}
    assert agencias == {GRUBAL: 3, "GRUBAL (Demonstrativo outubro)": 1}


def test_repetidas_substituir_tira_da_outra_agencia(cliente):
    entrar(cliente)
    importar_atendimento(cliente, _grubal(GRUBAL))
    previa = _previa(cliente, _grubal("GRUBAL (Demonstrativo outubro)", valor=150)).json()
    resultado = cliente.post(f"/api/importacoes/atendimento/{previa['token']}/confirmar",
                             json={"repetidas": "substituir"}).json()
    assert resultado["repetidas_substituidas"] == 3
    painel = cliente.get("/api/painel", params={"inicio": "2026-10", "fim": "2026-10"}).json()
    assert painel["resumo"]["custo"] == 450 and {a["nome"] for a in painel["agencias"]} == {"GRUBAL (Demonstrativo outubro)"}
    # A importação antiga ficou vazia: aparece como substituída no histórico.
    historico = [i for i in cliente.get("/api/importacoes").json() if i["tipo"] == "atendimento"]
    assert [i["situacao"] for i in historico] == ["ativa", "substituida"]


def test_mesmo_cnpj_em_outro_mes_ou_mesma_agencia_nao_e_repetida(cliente):
    entrar(cliente)
    importar_atendimento(cliente, _grubal(GRUBAL))
    outro_mes = _previa(cliente, _arquivo([_linha(mes="11/2026", agencia="Outra", cnpj="11.222.333/0001-81")])).json()
    assert outro_mes["repetidas_outra_agencia"] == []
    mesma_agencia = _previa(cliente, _grubal(GRUBAL)).json()
    assert mesma_agencia["repetidas_outra_agencia"] == [] and mesma_agencia["substituir"]


def test_mesma_loja_por_duas_agencias_no_proprio_arquivo(cliente):
    entrar(cliente)
    previa = _previa(cliente, _arquivo([_linha(agencia="A"), _linha(agencia="B")])).json()
    assert any("duas agências no mesmo mês" in a and "A e B" in a for a in previa["avisos"])


def test_cabecalho_repetido_e_titulo_sao_descartados(cliente):
    """Arquivo com blocos por agência: título ("AGENCIA IMPACTO") e cabeçalho de novo no meio."""
    entrar(cliente)
    previa = _previa(cliente, _arquivo([
        _linha(loja="Loja Um"),
        [None, None, None, "AGENCIA IMPACTO", None, None, "AGENCIA IMPACTO", None, None, None, None, None, None],
        ["Mês de referência", "Agência ou MEI", "CNPJ da loja", "Loja", "Cidade", "UF", "Promotor", "Código do promotor",
         "Dias de visita", "Visitas no mês", "Valor do mês (R$)", "Status", "Observação"],
        _linha(loja="Loja Dois", cnpj="77.752.293/0107-46"),
        _linha(loja="Loja Três", cnpj="09.477.652/0042-64", promotor="Agência Beta"),
    ])).json()
    assert previa["linhas_validas"] == 3
    assert [(d["linha"], d["motivo"]) for d in previa["descartadas"]] == [
        (3, "Parece título (sem CNPJ, valor e visitas)"), (4, "Cabeçalho repetido")]
    assert "AGENCIA IMPACTO" in previa["descartadas"][0]["conteudo"]
    assert any("descartadas" in a for a in previa["avisos"])
    assert any("nome de agência" in a and "Agência Beta" in a for a in previa["avisos"])
    cliente.post(f"/api/importacoes/atendimento/{previa['token']}/confirmar", json={})
    nomes = {p["nome"] for p in cliente.get("/api/painel", params={"inicio": "2026-10", "fim": "2026-10"}).json()["promotores"]}
    assert "AGENCIA IMPACTO" not in nomes


def test_card_conta_so_os_meses_com_arquivo(cliente):
    entrar(cliente)
    importar_atendimento(cliente, _arquivo([_linha(mes="10/2026")]))
    resumo = cliente.get("/api/painel", params={"inicio": "2026-08", "fim": "2026-10"}).json()["resumo"]
    assert resumo["meses"] == 3 and resumo["meses_com_arquivo"] == 1


def test_agencias_sem_custo_contam_a_parte(cliente):
    entrar(cliente)
    importar_atendimento(cliente, _arquivo([
        _linha(agencia="Agência Paga", loja="Loja Um", valor=300),
        _linha(agencia="Red Horse PR CLT", loja="Loja Dois", cnpj="77.752.293/0107-46", valor=0, visitas=None),
        _linha(agencia="Red Horse PR CLT", loja="Loja Três", cnpj="09.477.652/0042-64", promotor="Outro", valor=0),
    ]))
    resumo = cliente.get("/api/painel", params={"inicio": "2026-10", "fim": "2026-10"}).json()["resumo"]
    assert (resumo["agencias"], resumo["promotores"], resumo["lojas"]) == (1, 1, 1)
    assert (resumo["agencias_sem_custo"], resumo["promotores_sem_custo"], resumo["lojas_sem_custo"]) == (1, 2, 2)
    lojas = cliente.get("/api/painel", params={"inicio": "2026-10", "fim": "2026-10"}).json()["lojas"]
    assert all(l["agencia_chaves"] for l in lojas)


def test_apagar_guarda_backup_que_da_para_importar_de_novo(cliente):
    entrar(cliente)
    importar_atendimento(cliente)
    resposta = cliente.post("/api/cadastros/apagar", json={"confirmacao": "APAGAR"}).json()
    assert resposta["atendimentos"] == 97 and resposta["backup"]
    backups = cliente.get("/api/backups").json()
    assert len(backups) == 1 and backups[0]["linhas"] == 97 and backups[0]["arquivo"].endswith(".xlsx")
    arquivo = cliente.get(f"/api/backups/{resposta['backup']}")
    assert arquivo.status_code == 200 and "attachment" in arquivo.headers["content-disposition"]
    assert cliente.get("/api/painel", params=PERIODO).json()["resumo"]["custo"] == 0
    # O backup é o modelo das agências: importar devolve tudo.
    previa = _previa(cliente, arquivo.content).json()
    assert previa["linhas_validas"] == 97 and not previa["cnpjs_invalidos"]
    cliente.post(f"/api/importacoes/atendimento/{previa['token']}/confirmar", json={})
    assert cliente.get("/api/painel", params=PERIODO).json()["resumo"]["custo"] == 44200
    # Sem nada para apagar, não cria backup vazio.
    cliente.post("/api/cadastros/apagar", json={"confirmacao": "APAGAR"})
    vazio = cliente.post("/api/cadastros/apagar", json={"confirmacao": "APAGAR"}).json()
    assert vazio == {"atendimentos": 0, "backup": None, "backup_arquivo": None}
    assert len(cliente.get("/api/backups").json()) == 2
    assert cliente.get("/api/backups/999").status_code == 404
