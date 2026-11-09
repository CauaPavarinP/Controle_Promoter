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
@pytest.mark.parametrize("rota", ["promotores", "roteiro", "faturamento/previa"])
def test_arquivo_ruim_vira_mensagem(cliente, rota, nome):
    entrar(cliente)
    resposta = cliente.post(f"/api/importacoes/{rota}", files={"arquivo": (nome, ARQUIVOS[nome])})
    resposta = _esperar_leitura(cliente, resposta)
    assert resposta.status_code in (400, 413), (rota, nome, resposta.status_code, resposta.text[:300])
    assert resposta.json()["detail"]
    assert cliente.get("/api/opcoes").status_code == 200   # o servidor continua de pé
