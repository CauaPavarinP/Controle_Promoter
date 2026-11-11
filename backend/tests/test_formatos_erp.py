"""Faturamento nos formatos que o gerador de relatórios do ERP (Focco3i) exporta: .xls (HTML), .txt e .csv."""
from html import escape

from openpyxl import load_workbook

from conftest import EXEMPLOS, entrar, importar_atendimento

PERIODO = {"inicio": "2026-01", "fim": "2026-09"}


def _linhas_exemplo():
    return [["" if v is None else v for v in linha]
            for linha in load_workbook(EXEMPLOS / "faturamento_exemplo.xlsx", read_only=True).active.iter_rows(values_only=True)]


def _br(valor):
    """Número como o ERP escreve em texto: 1.234,50."""
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return str(valor)


def _html_focco(linhas) -> bytes:
    """Imita o "Gera Excel" do Focco3i: página HTML em Windows-1252, título e linhas vazias antes do cabeçalho."""
    corpo = ["<HTML>", "<HEAD>", "<TITLE>Gerador de Relatórios Focco3i</TITLE>",
             "<style>td { border: 1px solid; }</style>", "</HEAD>", "<BODY>", "<TABLE border=1>",
             '<TR><TD colspan="16"><B>Relatorio Faturamento - Mauricio</B></TD></TR>', "<TR></TR>", "<TR><TD></TD></TR>"]
    for numero, linha in enumerate(linhas):
        tag = "TH" if numero == 0 else "TD"
        corpo.append("<TR>" + "".join(f"<{tag} style='mso-number-format:\"\\@\"'>{escape(_br(v))}</{tag}>" for v in linha)
                     + "</TR>")
    corpo += ["</TABLE>", "</BODY>", "</HTML>"]
    return "\r\n".join(corpo).encode("cp1252")


def _importar(cliente, nome, conteudo):
    previa = cliente.post("/api/importacoes/faturamento/previa", files={"arquivo": (nome, conteudo)})
    assert previa.status_code == 200, previa.text
    dados = previa.json()
    assert "token" in dados, dados
    return dados, cliente.post(f"/api/importacoes/faturamento/{dados['token']}/confirmar", json={})


def _total_xlsx(cliente):
    entrar(cliente)
    with open(EXEMPLOS / "faturamento_exemplo.xlsx", "rb") as arquivo:
        dados, resposta = _importar(cliente, "faturamento_exemplo.xlsx", arquivo.read())
    assert resposta.status_code == 200
    total = cliente.get("/api/faturamento", params=PERIODO).json()["totais"]["total"]
    return dados["linhas_validas"], total


def test_xls_do_focco_em_html(cliente):
    linhas = _linhas_exemplo()
    entrar(cliente)
    dados, resposta = _importar(cliente, "relatorio.xls", _html_focco(linhas))
    assert resposta.status_code == 200, resposta.text
    assert dados["linhas_validas"] == len(linhas) - 1 and not dados["linhas_com_erro"]
    erp = cliente.get("/api/faturamento", params=PERIODO).json()
    clientes = {c["cnpj"]: c for c in erp["clientes"]}
    assert clientes["00000001000101"]["razao_social"] == "REDE ALFA LTDA"
    assert erp["totais"]["total"] > 0


def test_xls_html_da_o_mesmo_total_que_o_xlsx(cliente, banco):
    linhas = _linhas_exemplo()
    entrar(cliente)
    _importar(cliente, "relatorio.xls", _html_focco(linhas))
    html = cliente.get("/api/faturamento", params=PERIODO).json()["totais"]["total"]
    with open(EXEMPLOS / "faturamento_exemplo.xlsx", "rb") as arquivo:
        _, resposta = _importar(cliente, "faturamento_exemplo.xlsx", arquivo.read())
    # O mesmo período: pede para substituir.
    assert resposta.status_code == 400
    previa = cliente.post("/api/importacoes/faturamento/previa",
                          files={"arquivo": ("f.xlsx", (EXEMPLOS / "faturamento_exemplo.xlsx").read_bytes())}).json()
    cliente.post(f"/api/importacoes/faturamento/{previa['token']}/confirmar", json={"substituir": True})
    assert cliente.get("/api/faturamento", params=PERIODO).json()["totais"]["total"] == html


def test_txt_separado_por_ponto_e_virgula_tabulacao_ou_barra(cliente):
    linhas = _linhas_exemplo()
    entrar(cliente)
    totais = []
    for separador in (";", "\t", "|"):
        texto = "Relatorio Faturamento - Mauricio\r\n\r\n" + "\r\n".join(separador.join(_br(v) for v in l) for l in linhas)
        previa = cliente.post("/api/importacoes/faturamento/previa",
                              files={"arquivo": ("relatorio.txt", texto.encode("cp1252"))}).json()
        assert previa["linhas_validas"] == len(linhas) - 1, (separador, previa)
        resultado = cliente.post(f"/api/importacoes/faturamento/{previa['token']}/confirmar",
                                 json={"substituir": True})
        assert resultado.status_code == 200
        totais.append(cliente.get("/api/faturamento", params=PERIODO).json()["totais"]["total"])
    assert len(set(totais)) == 1 and totais[0] > 0


def test_acentos_em_utf8_e_windows_1252(cliente):
    linhas = _linhas_exemplo()
    for linha in linhas[1:]:
        if linha[12] == "TIJUCAS":
            linha[12] = "SÃO JOSÉ"
    entrar(cliente)
    for codificacao in ("utf-8", "cp1252"):
        texto = "\n".join(";".join(_br(v) for v in l) for l in linhas)
        previa = cliente.post("/api/importacoes/faturamento/previa",
                              files={"arquivo": ("r.txt", texto.encode(codificacao))}).json()
        cliente.post(f"/api/importacoes/faturamento/{previa['token']}/confirmar", json={"substituir": True})
        cidades = {c["cidade"] for c in cliente.get("/api/faturamento", params=PERIODO).json()["clientes"]}
        assert "SÃO JOSÉ" in cidades, codificacao


def test_xls_antigo_xlsx_renomeado_e_lixo_dao_mensagem_clara(cliente):
    entrar(cliente)
    enviar = lambda nome, conteudo: cliente.post("/api/importacoes/faturamento/previa", files={"arquivo": (nome, conteudo)})
    antigo = enviar("r.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 600)
    assert antigo.status_code == 400 and "97-2003" in antigo.json()["detail"]
    renomeado = enviar("r.xls", (EXEMPLOS / "faturamento_exemplo.xlsx").read_bytes())
    assert renomeado.status_code == 400 and "Renomeie para .xlsx" in renomeado.json()["detail"]
    sem_cabecalho = enviar("r.txt", "qualquer coisa\nsem colunas".encode())
    assert sem_cabecalho.status_code == 400 and "CNPJ CPF" in sem_cabecalho.json()["detail"]
    tag_sem_fim = enviar("r.xls", b"<html><table><tr><td " + b"a" * (17 * 1024 * 1024))
    assert tag_sem_fim.status_code in (400, 413)
    assert enviar("r.pdf", b"%PDF").status_code == 400


def test_mes_sem_faturamento_do_erp_nao_aparece_como_sem_compras(cliente):
    """Agência mandou outubro, mas o faturamento de outubro ainda não foi importado."""
    entrar(cliente)
    importar_atendimento(cliente)
    painel = cliente.get("/api/painel", params={"inicio": "2026-09", "fim": "2026-09"}).json()
    assert painel["resumo"]["sem_erp"] is True
    assert any("Sem faturamento do ERP importado em 2026-09" in a for a in painel["resumo"]["avisos"])
    assert all(l["sem_erp"] for l in painel["lojas"]) and all(p["sem_erp"] for p in painel["promotores"])
    assert painel["mes_a_mes"][0]["sem_erp"] is True
    with open(EXEMPLOS / "faturamento_exemplo.xlsx", "rb") as arquivo:
        _importar(cliente, "f.xlsx", arquivo.read())
    painel = cliente.get("/api/painel", params={"inicio": "2026-09", "fim": "2026-09"}).json()
    assert painel["resumo"]["sem_erp"] is False and not any("Sem faturamento do ERP" in a for a in painel["resumo"]["avisos"])
    assert not any(l["sem_erp"] for l in painel["lojas"])


def test_limite_de_tamanho_por_tipo(cliente, monkeypatch, banco):
    """Texto do ERP (.xls HTML, .txt, .csv) vai até 300 MB; .xlsx e as outras importações continuam em 150 MB."""
    from app.limites import FOLGA_ENVIO, LIMITE_FATURAMENTO_TEXTO, LIMITE_IMPORTACAO, limite_para
    assert limite_para("/api/importacoes/faturamento/previa") == LIMITE_FATURAMENTO_TEXTO + FOLGA_ENVIO
    assert limite_para("/api/importacoes/atendimento/previa") == LIMITE_IMPORTACAO + FOLGA_ENVIO
    assert LIMITE_FATURAMENTO_TEXTO == 300 * 1024 * 1024 and LIMITE_IMPORTACAO == 150 * 1024 * 1024
    entrar(cliente)
    # Sem gerar 150 MB de verdade: baixa o limite do .xlsx e confere que o .xls com o mesmo tamanho passa.
    monkeypatch.setattr(banco.main, "TAMANHO_MAXIMO_MB", 0)
    xlsx = cliente.post("/api/importacoes/faturamento/previa",
                        files={"arquivo": ("f.xlsx", (EXEMPLOS / "faturamento_exemplo.xlsx").read_bytes())})
    assert xlsx.status_code == 413 and "máximo 0 MB" in xlsx.json()["detail"]
    html = cliente.post("/api/importacoes/faturamento/previa", files={"arquivo": ("r.xls", _html_focco(_linhas_exemplo()))})
    assert html.status_code == 200 and "token" in html.json()
