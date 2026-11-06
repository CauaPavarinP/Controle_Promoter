"""Correções da auditoria de 11/2026 (versão simplificada). Cada teste corresponde a um item da auditoria."""
import io
import time
from datetime import date

import pandas as pd

from app.calculos import Filtros, calcular_painel, indice_mes
from app.importacao import ler_numero
from conftest import entrar, importar_cadastros, importar_faturamento

ANO = date.today().year
HOJE = ANO * 12 + date.today().month - 1


def _enviar(cliente, tipo, abas: dict, startrow=0):
    conteudo = io.BytesIO()
    with pd.ExcelWriter(conteudo) as escritor:
        for aba, tabela in abas.items():
            tabela.to_excel(escritor, sheet_name=aba, index=False, startrow=startrow)
    resposta = cliente.post(f"/api/importacoes/{tipo}", files={"arquivo": (f"{tipo}.xlsx", conteudo.getvalue())})
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _promotor(cliente, nome):
    resumo = next(p for p in cliente.get("/api/promotores").json() if p["nome"] == nome)
    return cliente.get(f"/api/promotores/{resumo['id']}").json()


def _linha_promotor(codigo, nome, municipio, supervisor="Sup Um", salario=2000, ajuda=600, vt=400, total=None,
                    admissao="2024-01-10"):
    return {"Admissão": pd.Timestamp(admissao), "código": codigo, "Colaborador": nome, "Salário": salario,
            "Ajud. Custo": ajuda, "V. transp.": vt, "Municipio": municipio, "SUPERVISOR": supervisor,
            "TOTAL": total if total is not None else salario + (ajuda if isinstance(ajuda, (int, float)) else 0) + vt}


# 1. Ajuda de custo "600 + 120m" virava 600120 -------------------------------------------------------------

def test_numero_em_texto_so_aceita_um_numero():
    assert ler_numero("600 + 120m") is None       # soma é tratada à parte (ler_soma_mensal)
    assert ler_numero("600 120") is None
    assert ler_numero("R$ 1.234,56") == 1234.56
    assert ler_numero("1.200") == 1200.0          # milhar brasileiro (antes virava 1,2)
    assert ler_numero("1234.56") == 1234.56
    assert ler_numero(" - ") == 0.0 and ler_numero(None) == 0.0


def test_soma_mensal_em_texto():
    from app.importacao import ler_soma_mensal
    assert ler_soma_mensal("600 + 120m") == 720.0     # 600 + 120 mensais (resposta do Maurício)
    assert ler_soma_mensal("600 +120m") == 720.0
    assert ler_soma_mensal("R$ 600 + R$ 120 mensais") == 720.0
    assert ler_soma_mensal("1.200,50 + 120m") == 1320.5
    for texto in ("600 120", "600 a 700", "600", "abc", 600):
        assert ler_soma_mensal(texto) is None


def test_ajuda_de_custo_600_mais_120m_vale_720_por_mes(cliente, banco):
    entrar(cliente)
    # Na planilha, o TOTAL dessas linhas não soma a ajuda (o Excel trata o texto como 0): 2000 + 400 = 2400.
    linhas = [_linha_promotor(30001, "Ana Sara", "TIJUCAS - SC", ajuda="600 + 120m", total=2400),
              _linha_promotor(30002, "Bia Sara", "TIJUCAS - SC", ajuda=600120),
              _linha_promotor(30003, "Cida Sara", "TIJUCAS - SC", ajuda="seiscentos", total=2400)]
    resposta = _enviar(cliente, "promotores", {"PROMOTORES BRASIL": pd.DataFrame(linhas)}, startrow=4)
    assert any("Ana Sara ('600 + 120m' = R$ 720,00)" in a for a in resposta["avisos"])
    assert any("600120" in a and "fora do normal" in a for a in resposta["avisos"])
    assert any("seiscentos" in a and "não é número" in a for a in resposta["avisos"])
    ana = _promotor(cliente, "Ana Sara")["custos"][0]
    assert ana["ajuda_custo"] == 720 and ana["total"] == 2000 + 720 + 400
    for nome in ("Bia Sara", "Cida Sara"):
        custo = _promotor(cliente, nome)["custos"][0]
        assert custo["ajuda_custo"] == 0 and custo["total"] == 2400


def test_reimportar_corrige_600_mais_120m_gravado_como_zero(cliente, banco):
    """A versão anterior gravou ajuda 0: reimportar corrige no lugar (desde a admissão), não vira reajuste."""
    entrar(cliente)
    linhas = pd.DataFrame([_linha_promotor(30001, "Ana Sara", "TIJUCAS - SC", ajuda="600 + 120m", total=2400)])
    _enviar(cliente, "promotores", {"PROMOTORES BRASIL": linhas}, startrow=4)
    from app.modelos import CustoPromotor
    with banco.db.SessaoLocal() as sessao:   # como a versão anterior gravava
        sessao.query(CustoPromotor).update({"ajuda_custo": 0, "outros": 0})
        sessao.commit()
    resposta = _enviar(cliente, "promotores", {"PROMOTORES BRASIL": linhas}, startrow=4)
    assert resposta["cadastros"]["custos_corrigidos"] == 1 and resposta["cadastros"]["reajustes"] == 0
    custos = _promotor(cliente, "Ana Sara")["custos"]
    assert len(custos) == 1 and custos[0]["ajuda_custo"] == 720 and custos[0]["total"] == 3120


def test_reimportar_corrige_custo_gravado_errado(cliente, banco):
    entrar(cliente)
    linhas = pd.DataFrame([_linha_promotor(30001, "Ana Sara", "TIJUCAS - SC", ajuda=600)])
    _enviar(cliente, "promotores", {"PROMOTORES BRASIL": linhas}, startrow=4)
    from app.modelos import CustoPromotor
    with banco.db.SessaoLocal() as sessao:   # como a versão anterior gravava
        sessao.query(CustoPromotor).update({"ajuda_custo": 600120})
        sessao.commit()
    resposta = _enviar(cliente, "promotores", {"PROMOTORES BRASIL": linhas}, startrow=4)
    assert resposta["cadastros"]["custos_corrigidos"] == 1 and resposta["cadastros"]["reajustes"] == 0
    custos = _promotor(cliente, "Ana Sara")["custos"]
    assert len(custos) == 1 and custos[0]["ajuda_custo"] == 600 and custos[0]["total"] == 3000


# 2. Promotor ligado à loja pela chave errada --------------------------------------------------------------

def _promotores_basicos(cliente):
    linhas = [_linha_promotor(11, "Carlos PR", "CURITIBA - PR"),
              _linha_promotor(30011, "Debora MG", "BELO HORIZONTE - MG"),
              _linha_promotor(30020, "Maria Silva", "LONDRINA - PR"),
              _linha_promotor(30021, "Maria Silva", "UBERABA - MG")]
    _enviar(cliente, "promotores", {"PROMOTORES BRASIL": pd.DataFrame(linhas)}, startrow=4)


def test_codigo_que_nao_confere_com_o_nome_nao_liga_a_loja(cliente):
    entrar(cliente)
    _promotores_basicos(cliente)
    roteiro = pd.DataFrame([
        # Código 11 é do Carlos (PR), mas a linha é da Débora (MG): vale o nome.
        {"COD COLABORADOR": 11, "Colaborador": "DEBORA MG", "CPF/CNPJ": "11.111.111/0001-11",
         "Razão Social": "LOJA BH", "Cidade": "BELO HORIZONTE", "UF": "MG"},
        # Código de alguém e nome que não existe: fica pendente em vez de ir para o dono do código.
        {"COD COLABORADOR": 11, "Colaborador": "FULANO SEM CADASTRO", "CPF/CNPJ": "22.222.222/0001-22",
         "Razão Social": "LOJA CONTAGEM", "Cidade": "CONTAGEM", "UF": "MG"},
    ])
    resposta = _enviar(cliente, "roteiro", {"MG": roteiro})
    assert resposta["cadastros"]["criados"] == 1 and resposta["cadastros"]["pendentes"] == 1
    assert [r["pdv"] for r in _promotor(cliente, "Debora MG")["roteiros"]] == ["LOJA BH"]
    assert _promotor(cliente, "Carlos PR")["roteiros"] == []


def test_homonimos_usam_a_uf_da_loja_e_avisam_uf_diferente(cliente):
    entrar(cliente)
    _promotores_basicos(cliente)
    roteiro = pd.DataFrame([
        {"Colaborador": "MARIA SILVA", "CPF/CNPJ": "33.333.333/0001-33", "Razão Social": "LOJA UBERABA",
         "Cidade": "UBERABA", "UF": "MG"},
        {"Colaborador": "MARIA SILVA", "CPF/CNPJ": "44.444.444/0001-44", "Razão Social": "LOJA SP",
         "Cidade": "SAO PAULO", "UF": "SP"},       # nenhuma Maria em SP: não dá para decidir
        {"Colaborador": "CARLOS PR", "CPF/CNPJ": "55.555.555/0001-55", "Razão Social": "LOJA JOINVILLE",
         "Cidade": "JOINVILLE", "UF": "SC"},
    ])
    resposta = _enviar(cliente, "roteiro", {"LOJAS": roteiro})
    assert resposta["cadastros"]["pendentes"] == 1 and resposta["cadastros"]["uf_diferente"] == 1
    assert any("UF diferente" in a and "LOJA JOINVILLE" in a for a in resposta["avisos"])
    mg = next(p for p in cliente.get("/api/promotores").json() if p["nome"] == "Maria Silva" and p["uf"] == "MG")
    assert [r["pdv"] for r in cliente.get(f"/api/promotores/{mg['id']}").json()["roteiros"]] == ["LOJA UBERABA"]


# 3, 4, 5 e 9. Cálculo do painel ------------------------------------------------------------------------------

def _venda(mes, cnpj, valor, ano=2026):
    return {"ano": ano, "mes": mes, "cnpj": cnpj, "chave_tipo": "1 VENDA", "tipo_nf": "1-Venda", "cod_cliente": "",
            "total_venda": valor, "vlr_total": valor, "notas": 1, "receita": "SIM"}


def _cenario():
    promotores = pd.DataFrame([
        {"codigo": "1", "nome": "Ana", "admissao": "2025-01-10", "desligamento": "", "municipio": "X", "uf": "SC",
         "supervisor": "Sup", "funcao": "Promotor", "custo_mensal": 1000.0},
        {"codigo": "2", "nome": "Bruno", "admissao": "2025-01-10", "desligamento": "", "municipio": "X", "uf": "SC",
         "supervisor": "Sup", "funcao": "Promotor", "custo_mensal": 1000.0},
        # Admitido em junho de 2026: não conta antes disso.
        {"codigo": "3", "nome": "Caio", "admissao": "2026-06-01", "desligamento": "", "municipio": "X", "uf": "SC",
         "supervisor": "", "funcao": "Promotor", "custo_mensal": 1000.0},
        {"codigo": "9", "nome": "Sup. Vera", "admissao": "2020-01-01", "desligamento": "", "municipio": "X",
         "uf": "SC", "supervisor": "Sup", "funcao": "Supervisor", "custo_mensal": 9000.0},
    ])
    custos = pd.DataFrame([{"codigo": c, "ano": 2020, "mes": 1, "total": t, "salario": t, "ajuda_custo": 0,
                            "vale_transporte": 0, "outros": 0} for c, t in (("1", 1000.0), ("2", 1000.0),
                                                                            ("3", 1000.0), ("9", 9000.0))])

    def rot(codigo, loja, cnpj, inicio="2026-01-01"):
        return {"codigo_promotor": codigo, "colaborador": "", "cnpj": cnpj, "loja": loja, "cidade": "C", "uf": "SC",
                "cod_cli": "", "visitas_semana": None, "data_inicio": inicio, "data_fim": ""}
    roteiro = pd.DataFrame([
        rot("1", "REDE - A", "111"), rot("2", "REDE - B", "111"), rot("2", "REDE - C", "111"),  # 3 lojas, 1 CNPJ
        rot("1", "MERCADO", "222"), rot("2", "MERCADO", "222"),                               # 2 promotores na loja
        rot("3", "LOJA DO CAIO", "333"), rot("9", "LOJA DA VERA", "444"), rot("1", "SEM CNPJ", ""),
    ])
    faturamento = pd.DataFrame([_venda(m, c, v) for m in range(1, 10) for c, v in
                                (("111", 3000.0), ("222", 1000.0), ("333", 500.0), ("444", 700.0))])
    return faturamento, promotores, roteiro, custos


def test_faturamento_por_promotor_soma_o_total():
    fat, prom, rot, custos = _cenario()
    painel = calcular_painel(fat, prom, rot, Filtros("2026-01", "2026-03"), custos=custos, ultimo_mes=HOJE)
    soma = sum(p["faturamento"] for p in painel["promotores"])
    assert painel["resumo"]["faturamento"] == round(soma, 2) == 3 * 4000.0
    por_nome = {p["nome"]: p["faturamento"] for p in painel["promotores"]}
    # CNPJ 111: 1/3 para a loja da Ana, 2/3 para as do Bruno; MERCADO: metade para cada.
    assert por_nome == {"Ana": 3 * (1000 + 500), "Bruno": 3 * (2000 + 500)}
    assert round(sum(l["total"] for l in painel["grade"]["linhas"]), 2) == painel["grade"]["totais"]["total"]
    assert round(sum(l["faturamento"] for l in painel["por_uf"] if l["nivel"] == "uf"), 2) == 12000.0


def test_meses_futuros_nao_tem_custo():
    fat, prom, rot, custos = _cenario()
    junho = 2026 * 12 + 5
    futuro = calcular_painel(fat, prom, rot, Filtros("2026-01", "2030-12"), custos=custos, ultimo_mes=junho)
    ate_hoje = calcular_painel(fat, prom, rot, Filtros("2026-01", "2026-06"), custos=custos, ultimo_mes=junho)
    assert futuro["resumo"]["custo"] == ate_hoje["resumo"]["custo"] == 6 * 2000 + 1000
    assert futuro["resumo"]["meses"] == 6 and futuro["grade"]["meses"][-1] == "2026-06"
    assert any("ainda não aconteceram" in a for a in futuro["resumo"]["avisos"])
    so_futuro = calcular_painel(fat, prom, rot, Filtros("2029-01", "2029-12"), custos=custos, ultimo_mes=junho)
    assert so_futuro["resumo"]["custo"] == 0 and so_futuro["resumo"]["promotores"] == 0


def test_promotor_nao_admitido_nao_conta():
    fat, prom, rot, custos = _cenario()
    antes = calcular_painel(fat, prom, rot, Filtros("2026-01", "2026-05"), custos=custos, ultimo_mes=HOJE)
    assert "Caio" not in {p["nome"] for p in antes["promotores"]}
    assert antes["resumo"]["promotores"] == 2
    assert "LOJA DO CAIO" not in {l["loja"] for l in antes["lojas"]}
    assert antes["resumo"]["faturamento"] == 5 * 4000.0      # sem os 500/mês da loja do Caio
    depois = calcular_painel(fat, prom, rot, Filtros("2026-01", "2026-09"), custos=custos, ultimo_mes=HOJE)
    caio = next(p for p in depois["promotores"] if p["nome"] == "Caio")
    assert caio["faturamento"] == 4 * 500.0 and caio["custo_periodo"] == 4 * 1000.0   # junho a setembro


def test_supervisor_fora_e_avisos_dos_dados():
    fat, prom, rot, custos = _cenario()
    painel = calcular_painel(fat, prom, rot, Filtros("2026-07", "2026-07"), custos=custos, ultimo_mes=HOJE)
    assert "Sup. Vera" not in {p["nome"] for p in painel["promotores"]}
    assert painel["resumo"]["custo"] == 3000.0
    avisos = " | ".join(painel["resumo"]["avisos"])
    assert "supervisor(es) cadastrado(s) como promotor" in avisos
    assert "1 loja(s) sem CNPJ" in avisos
    assert "1 promotor(es) sem supervisor" in avisos
    assert "Nenhuma loja tem visitas por semana" in avisos


# 6. Início do roteiro --------------------------------------------------------------------------------------

def test_roteiro_comeca_na_admissao(cliente):
    entrar(cliente)
    admissao = date(ANO, 3, 15)
    linhas = [_linha_promotor(30001, "Ana Nova", "TIJUCAS - SC", admissao=admissao.isoformat()),
              _linha_promotor(30002, "Bia Antiga", "TIJUCAS - SC", admissao="2020-05-01")]
    _enviar(cliente, "promotores", {"PROMOTORES BRASIL": pd.DataFrame(linhas)}, startrow=4)
    roteiro = pd.DataFrame([{"Colaborador": n, "CPF/CNPJ": c, "Razão Social": l, "Cidade": "TIJUCAS", "UF": "SC"}
                            for n, c, l in (("ANA NOVA", "11.111.111/0001-11", "LOJA 1"),
                                            ("BIA ANTIGA", "22.222.222/0001-22", "LOJA 2"))])
    _enviar(cliente, "roteiro", {"SC": roteiro})
    assert _promotor(cliente, "Ana Nova")["roteiros"][0]["data_inicio"] == admissao.isoformat()
    assert _promotor(cliente, "Bia Antiga")["roteiros"][0]["data_inicio"] == f"{ANO}-01-01"


# 7. Mês inválido -------------------------------------------------------------------------------------------

def test_mes_invalido_da_400(cliente):
    entrar(cliente)
    importar_cadastros(cliente)
    importar_faturamento(cliente)
    for inicio, fim in (("2026-13", "2026-12"), ("2026-00", "2026-05"), ("2026-1", "2026-05"), ("abc", "2026-05"),
                        ("2026-01", "9999-01"), ("2020-01", "2026-01")):
        resposta = cliente.get("/api/painel", params={"inicio": inicio, "fim": fim})
        assert resposta.status_code == 400, (inicio, fim, resposta.text)
    assert cliente.get("/api/pendencias", params={"inicio": "2026-00", "fim": "2026-05"}).status_code == 400
    assert cliente.get("/api/faturamento/itens",
                       params={"cnpj": "00000001000101", "mes": "2026-13"}).status_code == 400
    assert cliente.get("/api/painel", params={"inicio": "2026-01", "fim": "2026-09"}).status_code == 200
    assert indice_mes("2026-12") == 2026 * 12 + 11


# 8. Desempenho ---------------------------------------------------------------------------------------------

def test_cinco_anos_com_mil_lojas_e_rapido():
    promotores = pd.DataFrame([{"codigo": str(i), "nome": f"P{i}", "admissao": "2020-01-01", "desligamento": "",
                                "municipio": "X", "uf": "SC", "supervisor": f"S{i % 15}", "funcao": "Promotor",
                                "custo_mensal": 3000.0} for i in range(300)])
    custos = pd.DataFrame([{"codigo": str(i), "ano": 2020, "mes": 1, "total": 3000.0, "salario": 3000.0,
                            "ajuda_custo": 0, "vale_transporte": 0, "outros": 0} for i in range(300)])
    roteiro = pd.DataFrame([{"codigo_promotor": str(j % 300), "colaborador": "", "cnpj": f"{j % 700:014d}",
                             "loja": f"L{j}", "cidade": "C", "uf": "SC", "cod_cli": "", "visitas_semana": None,
                             "data_inicio": "2021-01-01", "data_fim": ""} for j in range(1002)])
    fat = pd.DataFrame([_venda(m, f"{c:014d}", 1000.0, ano=a) for a in range(2021, 2026) for m in range(1, 13)
                        for c in range(700)])
    comeco = time.perf_counter()
    painel = calcular_painel(fat, promotores, roteiro, Filtros("2021-01", "2025-12"), custos=custos,
                             ultimo_mes=HOJE)
    assert time.perf_counter() - comeco < 3
    assert painel["resumo"]["faturamento"] == 60 * 700 * 1000.0


# Achados ao tentar quebrar o sistema ------------------------------------------------------------------------

def test_entradas_absurdas_sao_recusadas(cliente):
    entrar(cliente)
    r = cliente.get("/api/painel", params={"inicio": "2026-01", "fim": "2026-09"})   # banco vazio
    assert r.status_code == 200 and r.json()["resumo"]["promotores"] == 0
    importar_cadastros(cliente)
    roteiro = pd.DataFrame([{"Colaborador": "ANA TESTE", "CPF/CNPJ": "99.999.999/0001-99", "Razão Social": f"LOJA {v}",
                             "Cidade": "X", "UF": "SC", "Visitas semana": v} for v in (-3, 0, 1e9, "abc", 2.7, 3)])
    resposta = _enviar(cliente, "roteiro", {"SC": roteiro})
    assert any("5 loja(s) com visitas por semana inválidas" in a for a in resposta["avisos"])
    csv = "DT EMIS;NUM NF;CNPJ CPF;TOTAL VENDA;ANO;MES\n05/01/1900;1;11.222.333/0001-81;10;1900;1\n"
    r = cliente.post("/api/importacoes/faturamento/previa", files={"arquivo": ("f.csv", csv.encode())})
    assert r.status_code == 400
    assert cliente.post("/api/importacoes/roteiro", files={"arquivo": ("v.csv", b"")}).status_code == 400
    promotor = cliente.get("/api/promotores").json()[0]
    r = cliente.post(f"/api/promotores/{promotor['id']}/custos", json={"ano": 2026, "mes": 5, "salario": 600120})
    assert r.status_code == 422 and r.json()["detail"] == "Dados inválidos — salario: no máximo 50000"
