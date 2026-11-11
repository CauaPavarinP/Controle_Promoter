from conftest import EXEMPLOS, entrar, importar_atendimento, importar_faturamento

PERIODO = {"inicio": "2026-01", "fim": "2026-09"}


def _faturamento_total(cliente):
    return cliente.get("/api/painel", params=PERIODO).json()["resumo"]["faturamento"]


def test_previa_mostra_resumo_antes_de_gravar(cliente):
    entrar(cliente)
    # Sem arquivo de agência: todos os CNPJs ficam "sem agência".
    with open(EXEMPLOS / "faturamento_exemplo.xlsx", "rb") as arquivo:
        previa = cliente.post("/api/importacoes/faturamento/previa", files={"arquivo": ("f.xlsx", arquivo)}).json()
    assert previa["meses"][0] == "2026-01" and previa["meses_existentes"] == []
    assert previa["linhas_com_erro"] == 0 and previa["clientes"] == 7
    assert previa["cnpjs_sem_roteiro"]["quantidade"] == 7
    assert cliente.get("/api/faturamento", params=PERIODO).json()["totais"]["total"] == 0   # nada gravado ainda


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
    importar_atendimento(cliente)
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
    importar_atendimento(cliente)
    _, resposta = importar_faturamento(cliente)
    ident = resposta.json()["importacao_id"]
    assert cliente.post(f"/api/importacoes/{ident}/desfazer").json()["itens_apagados"] > 0
    assert cliente.get("/api/faturamento", params=PERIODO).json()["totais"]["total"] == 0
    assert cliente.post(f"/api/importacoes/{ident}/desfazer").status_code == 400


def test_grade_mes_a_mes_e_detalhe_das_notas(cliente):
    entrar(cliente)
    importar_atendimento(cliente)
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

    # Filtro por loja.
    so_loja = cliente.get("/api/painel", params={**PERIODO, "loja": "ATACADO SIGMA"}).json()
    assert [l["loja"] for l in so_loja["lojas"]] == ["ATACADO SIGMA"]
    assert so_loja["lojas"][0]["promotor"] == "Carla Teste" and so_loja["lojas"][0]["custo_periodo"] == 400 * 9
    assert "lojas" in cliente.get("/api/opcoes").json()


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
    importar_atendimento(cliente)
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
    assert cliente.get("/api/faturamento", params=PERIODO).json()["totais"]["total"] == 0


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
    importar_atendimento(cliente)
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
        with open(EXEMPLOS / "atendimento_exemplo.xlsx", "rb") as arquivo:
            resposta = cliente.post("/api/importacoes/atendimento/previa", files={"arquivo": ("a.xlsx", arquivo)})
        assert resposta.status_code == 400 and "outra planilha" in resposta.json()["detail"]
        with open(EXEMPLOS / "faturamento_exemplo.xlsx", "rb") as arquivo:
            resposta = cliente.post("/api/importacoes/faturamento/previa", files={"arquivo": ("f.xlsx", arquivo)})
        assert resposta.status_code == 400
        assert cliente.post("/api/cadastros/apagar", json={"confirmacao": "APAGAR"}).status_code == 400
    finally:
        banco.carga.trava_cadastros.release()
    importar_atendimento(cliente)   # liberado, volta a funcionar
