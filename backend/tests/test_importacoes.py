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


def test_grade_mes_a_mes_e_detalhe_das_notas(cliente):
    entrar(cliente)
    importar_cadastros(cliente)
    importar_faturamento(cliente)
    painel = cliente.get("/api/painel", params={**PERIODO, "uf": "PR"}).json()
    grade = painel["grade"]
    assert grade["meses"][0] == "2026-01" and len(grade["meses"]) == 9
    assert {l["uf"] for l in grade["linhas"]} == {"PR"}
    # A linha de totais conta cada CNPJ uma vez: bate com o faturamento do resumo.
    assert grade["totais"]["total"] == painel["resumo"]["faturamento"]

    linha = next(l for l in grade["linhas"] if l["loja"] == "ATACADO SIGMA")
    mes = next(m for m, v in linha["meses"].items() if v)
    detalhe = cliente.get("/api/faturamento/itens", params={**linha["detalhe"], "mes": mes}).json()
    assert detalhe["itens"] and detalhe["total_considerado"] == linha["meses"][mes]

    # Filtro por PDV e bloco de custos (como a aba PROMOTORES BRASIL).
    so_pdv = cliente.get("/api/painel", params={**PERIODO, "pdv": "ATACADO SIGMA"}).json()
    assert [l["loja"] for l in so_pdv["lojas"]] == ["ATACADO SIGMA"]
    assert [c["nome"] for c in so_pdv["custos"]] == ["Carla Teste"]
    assert so_pdv["custos"][0]["total"] == 3250.0
    loja = so_pdv["lojas"][0]
    assert loja["faturamento_por_visita"] == round(loja["faturamento"] / (2 * 52 / 12 * 9), 2)
    assert "pdvs" in cliente.get("/api/opcoes").json()


def test_arquivo_lento_e_lido_em_segundo_plano(cliente, banco, monkeypatch):
    """Arquivo que demora: a resposta vem "lendo" e a tela pergunta o andamento até ficar pronto."""
    import time
    entrar(cliente)
    monkeypatch.setattr(banco.main, "ESPERA_PREVIA_SEGUNDOS", 0)
    with open(EXEMPLOS / "faturamento_exemplo.xlsx", "rb") as conteudo:
        resposta = cliente.post("/api/importacoes/faturamento/previa", files={"arquivo": ("f.xlsx", conteudo)}).json()
    assert resposta["situacao"] == "lendo"
    for _ in range(100):
        resposta = cliente.get(f"/api/importacoes/faturamento/leitura/{resposta['leitura']}").json()
        if resposta["situacao"] != "lendo":
            break
        time.sleep(0.1)
    assert resposta["situacao"] == "pronto" and resposta["linhas_validas"] > 0
    # Perguntar de novo depois de pronta devolve a mesma prévia (antes dizia "o servidor pode ter reiniciado").
    de_novo = cliente.get(f"/api/importacoes/faturamento/leitura/{resposta['leitura']}")
    assert de_novo.status_code == 200 and de_novo.json()["token"] == resposta["token"]
    confirmado = cliente.post(f"/api/importacoes/faturamento/{resposta['token']}/confirmar", json={"substituir": False})
    assert confirmado.status_code == 200
    assert cliente.get("/api/importacoes/faturamento/leitura/nao-existe").status_code == 400
    historico = cliente.get("/api/importacoes").json()
    assert historico[0]["data_hora"].endswith("Z")  # UTC marcado: o navegador mostra no horário de Brasília


def test_somas_guardadas_sao_refeitas_quando_o_faturamento_muda(cliente):
    """O Resumo e a aba Faturamento usam a soma guardada na memória, mas nunca uma soma velha."""
    entrar(cliente)
    importar_cadastros(cliente)
    assert _faturamento_total(cliente) == 0
    assert cliente.get("/api/faturamento", params=PERIODO).json()["totais"]["total"] == 0
    _, resposta = importar_faturamento(cliente)
    ident = resposta.json()["importacao_id"]
    total = _faturamento_total(cliente)
    assert total > 0
    assert cliente.get("/api/faturamento", params=PERIODO).json()["totais"]["total"] > 0
    assert cliente.post(f"/api/importacoes/{ident}/desfazer").status_code == 200
    assert _faturamento_total(cliente) == 0
    assert cliente.get("/api/faturamento", params=PERIODO).json()["totais"]["total"] == 0
    assert cliente.get("/api/opcoes").json()["meses"] == []


def test_varios_pedidos_ao_mesmo_tempo_fazem_uma_soma_so(banco, monkeypatch):
    """Telas abertas juntas esperam a mesma soma, em vez de cada uma ocupar uma conexão com o banco."""
    import threading
    import time

    import pandas as pd

    chamadas = []

    def soma_lenta():
        chamadas.append(1)
        time.sleep(0.3)
        return pd.DataFrame({"ano": [2026], "mes": [1]})

    monkeypatch.setattr(banco.faturamento, "_somar_faturamento_mensal", soma_lenta)
    resultados = []
    tarefas = [threading.Thread(target=lambda: resultados.append(banco.faturamento.faturamento_mensal()))
               for _ in range(5)]
    for tarefa in tarefas:
        tarefa.start()
    for tarefa in tarefas:
        tarefa.join()
    assert len(chamadas) == 1 and len(resultados) == 5
    resultados[0].loc[0, "ano"] = 1999          # cada um recebe a sua cópia
    assert banco.faturamento.faturamento_mensal().loc[0, "ano"] == 2026
    banco.faturamento.limpar_cache()            # faturamento mudou: a próxima tela soma de novo
    banco.faturamento.faturamento_mensal()
    assert len(chamadas) == 2


def test_cnpj_com_mais_de_14_digitos_nao_derruba_o_roteiro(cliente):
    """Célula com dois CNPJs (28 dígitos) dava erro 500 (VARCHAR(14)); agora a loja entra sem CNPJ, com aviso."""
    import io

    import pandas as pd
    entrar(cliente)
    importar_cadastros(cliente, "promotores")
    nome = cliente.get("/api/promotores").json()[0]["nome"]
    sc = pd.DataFrame({"Colaborador": [nome, nome], "CPF/CNPJ": ["12.345.678/0001-90 / 98.765.432/0001-10",
                                                               "11.222.333/0001-81"],
                       "RAZÃO SOCIAL": ["Loja Dupla", "Loja Certa"], "Cidade": ["ITAJAI", "ITAJAI"], "UF": ["SC", "SC"]})
    arquivo = io.BytesIO()
    with pd.ExcelWriter(arquivo) as planilha:
        sc.to_excel(planilha, sheet_name="SC", index=False)
    resposta = cliente.post("/api/importacoes/roteiro", files={"arquivo": ("sc.xlsx", arquivo.getvalue())})
    assert resposta.status_code == 200, resposta.text
    assert any("CNPJ inválido" in aviso and "Loja Dupla" in aviso for aviso in resposta.json()["avisos"])
    pdvs = {p["nome_fantasia"]: p["cnpj_cpf"] for p in cliente.get("/api/pdvs").json()}
    assert pdvs["Loja Dupla"] == "" and pdvs["Loja Certa"] == "11222333000181"


def test_erro_inesperado_vira_mensagem_para_a_tela(banco, monkeypatch):
    """Falha não prevista: resposta em JSON com `detail` (a tela mostrava só "Erro ao falar com o servidor")."""
    from fastapi.testclient import TestClient

    def quebra(*_args, **_kwargs):
        raise RuntimeError("falha de teste")

    monkeypatch.setattr(banco.main, "calcular_painel", quebra)
    with TestClient(banco.main.app, raise_server_exceptions=False) as cliente:
        entrar(cliente)
        resposta = cliente.get("/api/painel", params=PERIODO)
    assert resposta.status_code == 500
    assert resposta.json()["detail"].startswith("Erro inesperado no servidor. (ref. ")


def test_so_a_previa_mais_recente_fica_guardada(cliente, banco, monkeypatch):
    """Cada prévia segura os itens na memória até confirmar: uma nova descarta a anterior, e ela expira sozinha."""
    entrar(cliente)
    with open(EXEMPLOS / "faturamento_exemplo.xlsx", "rb") as arquivo:
        conteudo = arquivo.read()
    primeira = cliente.post("/api/importacoes/faturamento/previa", files={"arquivo": ("f.xlsx", conteudo)}).json()
    segunda = cliente.post("/api/importacoes/faturamento/previa", files={"arquivo": ("f.xlsx", conteudo)}).json()
    assert list(banco.faturamento._previas) == [segunda["token"]]
    velha = cliente.post(f"/api/importacoes/faturamento/{primeira['token']}/confirmar", json={"substituir": False})
    assert velha.status_code == 400 and "lido depois" in velha.json()["detail"]
    import os
    arquivo_itens = banco.faturamento._previas[segunda["token"]]["caminho_itens"]
    assert os.path.exists(arquivo_itens)          # os itens ficam em disco, não na memória
    banco.faturamento._descartar_previa(segunda["token"])   # o que o relógio de 30 minutos faz
    assert banco.faturamento._previas == {} and not os.path.exists(arquivo_itens)


def test_arquivo_grande_e_lido_e_gravado_em_processo_separado(cliente, banco, monkeypatch):
    """Acima do limite, ler e gravar rodam num processo que termina no fim e devolve toda a memória."""
    entrar(cliente)
    importar_cadastros(cliente)
    monkeypatch.setattr(banco.faturamento, "LIMITE_ARQUIVO_PROCESSO", 0)
    monkeypatch.setattr(banco.faturamento, "LIMITE_LINHAS_PROCESSO", 0)
    monkeypatch.setattr(banco.main, "ESPERA_PREVIA_SEGUNDOS", 0)
    with open(EXEMPLOS / "faturamento_exemplo.xlsx", "rb") as arquivo:
        resposta = cliente.post("/api/importacoes/faturamento/previa", files={"arquivo": ("f.xlsx", arquivo)}).json()
    import time
    for _ in range(300):
        if resposta["situacao"] != "lendo":
            break
        time.sleep(0.1)
        resposta = cliente.get(f"/api/importacoes/faturamento/leitura/{resposta['leitura']}").json()
    assert resposta["situacao"] == "pronto" and resposta["linhas_validas"] > 0, resposta
    confirmado = cliente.post(f"/api/importacoes/faturamento/{resposta['token']}/confirmar", json={"substituir": False})
    assert confirmado.status_code == 200, confirmado.text
    assert confirmado.json()["linhas_importadas"] == resposta["linhas_validas"]
    assert _faturamento_total(cliente) > 0
    # Erro de regra (mês que já existe) também volta do processo separado como mensagem.
    with open(EXEMPLOS / "faturamento_exemplo.xlsx", "rb") as arquivo:
        resposta = cliente.post("/api/importacoes/faturamento/previa", files={"arquivo": ("f.xlsx", arquivo)}).json()
    for _ in range(300):
        if resposta["situacao"] != "lendo":
            break
        time.sleep(0.1)
        resposta = cliente.get(f"/api/importacoes/faturamento/leitura/{resposta['leitura']}").json()
    repetido = cliente.post(f"/api/importacoes/faturamento/{resposta['token']}/confirmar", json={"substituir": False})
    assert repetido.status_code == 400 and "Já existe faturamento" in repetido.json()["detail"]


def test_uma_leitura_pesada_por_vez(cliente, banco):
    """Importar cadastros enquanto outra planilha é lida somaria a memória: o servidor recusa com aviso."""
    entrar(cliente)
    banco.carga.trava_cadastros.acquire()
    try:
        with open(EXEMPLOS / "promotores_exemplo.xlsx", "rb") as arquivo:
            resposta = cliente.post("/api/importacoes/promotores", files={"arquivo": ("p.xlsx", arquivo)})
        assert resposta.status_code == 400 and "outra planilha" in resposta.json()["detail"]
        with open(EXEMPLOS / "faturamento_exemplo.xlsx", "rb") as arquivo:
            resposta = cliente.post("/api/importacoes/faturamento/previa", files={"arquivo": ("f.xlsx", arquivo)})
        assert resposta.status_code == 400
        assert cliente.post("/api/cadastros/apagar", json={"confirmacao": "APAGAR"}).status_code == 400
    finally:
        banco.carga.trava_cadastros.release()
    importar_cadastros(cliente, "promotores")   # liberado, volta a funcionar
