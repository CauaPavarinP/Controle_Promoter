"""Arquivos estranhos nas importações: sempre uma mensagem (400), nunca erro 500 nem servidor travado."""
import io
import time
import zipfile

import pandas as pd
import pytest

from conftest import EXEMPLOS, entrar


def _xlsx(abas: dict) -> bytes:
    saida = io.BytesIO()
    with pd.ExcelWriter(saida) as planilha:
        for nome, tabela in abas.items():
            tabela.to_excel(planilha, sheet_name=nome, index=False)
    return saida.getvalue()


def _zip_sem_planilha() -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr("leia-me.txt", "não é Excel")
    return saida.getvalue()


ARQUIVOS = {
    "vazio.xlsx": b"",
    "texto.xlsx": b"isto nao e uma planilha",
    "zip.xlsx": _zip_sem_planilha(),
    "cortado.xlsx": (EXEMPLOS / "faturamento_exemplo.xlsx").read_bytes()[:3000],
    "sem_colunas.xlsx": _xlsx({"Plan1": pd.DataFrame({"A": [1, 2], "B": ["x", "y"]})}),
    "so_cabecalho.xlsx": _xlsx({"Plan1": pd.DataFrame(columns=["Colaborador", "Razão Social", "CNPJ", "Código",
                                                                "Salário", "TOTAL", "NUM NF", "TOTAL VENDA"])}),
    "vazio.csv": b"",
    "binario.csv": bytes(range(256)) * 50,
    "uma_coluna.csv": b"a\n1\n2\n",
    "programa.exe": b"MZ\x90\x00",
}


def _esperar_leitura(cliente, resposta):
    for _ in range(100):
        if resposta.status_code != 200 or resposta.json().get("situacao") != "lendo":
            return resposta
        time.sleep(0.1)
        resposta = cliente.get(f"/api/importacoes/faturamento/leitura/{resposta.json()['leitura']}")
    return resposta


@pytest.mark.parametrize("nome", ARQUIVOS)
@pytest.mark.parametrize("rota", ["atendimento/previa", "faturamento/previa"])
def test_arquivo_ruim_vira_mensagem(cliente, rota, nome):
    entrar(cliente)
    resposta = cliente.post(f"/api/importacoes/{rota}", files={"arquivo": (nome, ARQUIVOS[nome])})
    resposta = _esperar_leitura(cliente, resposta)
    assert resposta.status_code in (400, 413), (rota, nome, resposta.status_code, resposta.text[:300])
    assert resposta.json()["detail"]
    assert cliente.get("/api/opcoes").status_code == 200   # o servidor continua de pé


def _bomba(parte: str, conteudo_inicio: bytes, tamanho: int, fim: bytes) -> bytes:
    """Pega o exemplo e troca uma parte por texto repetido: poucos KB no disco, `tamanho` bytes aberto."""
    saida = io.BytesIO()
    with zipfile.ZipFile(EXEMPLOS / "faturamento_exemplo.xlsx") as original, \
            zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as novo:
        for item in original.infolist():
            if item.filename != parte:
                novo.writestr(item, original.read(item))
        with novo.open(parte, "w", force_zip64=True) as destino:
            destino.write(conteudo_inicio)
            bloco = b"A" * (1 << 20)
            for _ in range(tamanho // len(bloco)):
                destino.write(bloco)
            destino.write(fim)
    return saida.getvalue()


@pytest.mark.parametrize("rota", ["atendimento/previa", "faturamento/previa"])
def test_excel_inflado_e_recusado_sem_abrir(cliente, rota):
    """Zip bomb: um arquivo de poucos KB que abriria centenas de MB derrubava o servidor (512 MB)."""
    entrar(cliente)
    textos = _bomba("xl/sharedStrings.xml", b'<sst><si><t>', 120 * 1024 * 1024, b"</t></si></sst>")
    assert len(textos) < 2 * 1024 * 1024
    resposta = _esperar_leitura(cliente, cliente.post(f"/api/importacoes/{rota}", files={"arquivo": ("b.xlsx", textos)}))
    assert resposta.status_code == 400 and "muito mais espaço aberto" in resposta.json()["detail"]


def test_linha_gigante_na_aba_e_recusada():
    """Uma única linha de 70 MB dentro da aba (sem fim de linha) para a leitura em vez de encher a memória."""
    from app.importacao import ErroImportacao, ler_faturamento
    with zipfile.ZipFile(EXEMPLOS / "faturamento_exemplo.xlsx") as z:
        aba = next(n for n in z.namelist() if n.startswith("xl/worksheets/sheet"))
    arquivo = _bomba(aba, b'<worksheet><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>', 70 * 1024 * 1024,
                     b"</t></is></c></row></sheetData></worksheet>")
    with pytest.raises(ErroImportacao, match="muito mais espaço aberto"):
        ler_faturamento(arquivo, "b.xlsx")
