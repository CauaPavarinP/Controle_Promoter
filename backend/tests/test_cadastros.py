import pandas as pd

from conftest import EXEMPLOS, entrar, gravar_itens

CNPJ_A = "11222333000181"   # CNPJs com dígito verificador válido
CNPJ_B = "11444777000161"


def _supervisor(cliente, nome="Vanessa"):
    resposta = cliente.post("/api/supervisores", json={"nome": nome})
    assert resposta.status_code == 200, resposta.text
    return resposta.json()["id"]


def _promotor(cliente, supervisor_id, codigo="100", nome="Ana", salario=1000.0, inicio=(2026, 1), admissao=None):
    resposta = cliente.post("/api/promotores", json={
        "codigo": codigo, "nome": nome, "supervisor_id": supervisor_id, "municipio": "TIJUCAS", "uf": "SC",
        "data_admissao": admissao,
        "custo": {"ano": inicio[0], "mes": inicio[1], "salario": salario}})
    assert resposta.status_code == 200, resposta.text
    return resposta.json()["id"]


def _pdv(cliente, nome, cnpj=CNPJ_A):
    resposta = cliente.post("/api/pdvs", json={"cnpj_cpf": cnpj, "nome_fantasia": nome, "cidade": "Tijucas", "uf": "sc"})
    assert resposta.status_code == 200, resposta.text
    return resposta.json()["id"]


def _vincular(cliente, promotor_id, pdv_id, inicio="2026-01-01", visitas=None):
    return cliente.post("/api/roteiros", json={"promotor_id": promotor_id, "pdv_id": pdv_id,
                                               "data_inicio": inicio, "visitas_por_semana": visitas})


def _faturamento(banco, linhas):
    gravar_itens(banco, linhas)


def _painel(cliente, inicio, fim, **filtros):
    resposta = cliente.get("/api/painel", params={"inicio": inicio, "fim": fim, **filtros})
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


# ---------------------------------------------------------------------------
# Usuários e login
# ---------------------------------------------------------------------------

def test_primeiro_admin_e_perfil_consulta_so_le(cliente):
    eu = entrar(cliente)
    assert eu["perfil"] == "admin"
    novo = cliente.post("/api/usuarios", json={"nome": "Rayan", "usuario": "rayan", "perfil": "consulta"}).json()
    cliente.post("/api/logout")

    entrar(cliente, "rayan", novo["senha_provisoria"])
    assert cliente.get("/api/promotores").status_code == 200
    assert cliente.post("/api/supervisores", json={"nome": "X"}).status_code == 403
    assert cliente.get("/api/usuarios").status_code == 403
    assert cliente.put("/api/minha-senha", json={"senha_atual": "errada", "nova_senha": "nova-senha-1"}).status_code == 400
    assert cliente.put("/api/minha-senha", json={"senha_atual": novo["senha_provisoria"],
                                                  "nova_senha": "nova-senha-1"}).status_code == 200
    cliente.post("/api/logout")
    entrar(cliente, "rayan", "nova-senha-1")


def test_bloqueio_apos_tentativas_erradas(cliente):
    for _ in range(5):
        assert cliente.post("/api/login", json={"usuario": "mauricio", "senha": "errada"}).status_code == 401
    resposta = cliente.post("/api/login", json={"usuario": "mauricio", "senha": "senha-teste"})
    assert resposta.status_code == 401 and "bloqueado" in resposta.json()["detail"]


def test_nao_fica_sem_administrador(cliente):
    eu = entrar(cliente)
    assert cliente.post(f"/api/usuarios/{eu['id']}/inativar").status_code == 400
    assert cliente.put(f"/api/usuarios/{eu['id']}", json={"nome": "M", "perfil": "consulta"}).status_code == 400


# ---------------------------------------------------------------------------
# Cadastros
# ---------------------------------------------------------------------------

def test_supervisor_so_inativa_sem_equipe_e_transfere(cliente):
    entrar(cliente)
    vanessa, lionis = _supervisor(cliente, "Vanessa"), _supervisor(cliente, "Lionis")
    assert cliente.post("/api/supervisores", json={"nome": "vanessa"}).status_code == 400
    _promotor(cliente, vanessa)
    assert cliente.post(f"/api/supervisores/{vanessa}/inativar").status_code == 400
    assert cliente.post(f"/api/supervisores/{vanessa}/transferir", json={"para_id": lionis}).json() == {"transferidos": 1}
    assert cliente.post(f"/api/supervisores/{vanessa}/inativar").status_code == 200


def test_pdv_valida_cnpj_e_aceita_mesmo_cnpj_com_outro_nome(cliente):
    entrar(cliente)
    assert cliente.post("/api/pdvs", json={"cnpj_cpf": "11.222.333/0001-80", "nome_fantasia": "X"}).status_code == 400
    _pdv(cliente, "DE PIERI - OFICINAS")
    _pdv(cliente, "DE PIERI - TUBARAO")
    assert cliente.post("/api/pdvs", json={"cnpj_cpf": CNPJ_A, "nome_fantasia": "de pieri - oficinas"}).status_code == 400
    pdvs = cliente.get("/api/pdvs").json()
    assert [p["lojas_mesmo_cnpj"] for p in pdvs] == [2, 2]


def test_reajuste_nao_muda_meses_anteriores(cliente, banco):
    entrar(cliente)
    promotor = _promotor(cliente, _supervisor(cliente), salario=1000.0)
    assert cliente.post(f"/api/promotores/{promotor}/custos",
                        json={"ano": 2026, "mes": 7, "salario": 2000.0}).status_code == 200
    _faturamento(banco, [(1, CNPJ_A, 100.0)])
    assert _painel(cliente, "2026-01", "2026-06")["resumo"]["custo"] == 6000.0
    assert _painel(cliente, "2026-01", "2026-09")["resumo"]["custo"] == 6000.0 + 3 * 2000.0
    detalhe = cliente.get(f"/api/promotores/{promotor}").json()
    assert [c["mes"] for c in detalhe["custos"]] == [7, 1]


def test_troca_de_promotor_nao_muda_o_passado(cliente, banco):
    entrar(cliente)
    supervisor = _supervisor(cliente)
    ana = _promotor(cliente, supervisor, "100", "Ana")
    bruno = _promotor(cliente, supervisor, "200", "Bruno")
    loja = _pdv(cliente, "MERCADO A")
    vinculo = _vincular(cliente, ana, loja, visitas=3).json()["id"]
    assert _vincular(cliente, ana, loja, "2026-03-01").status_code == 400   # sobreposição
    _faturamento(banco, [(m, CNPJ_A, 1000.0) for m in range(1, 10)])

    assert cliente.post(f"/api/roteiros/{vinculo}/trocar",
                        json={"promotor_id": bruno, "data": "2026-07-01"}).status_code == 200
    painel = _painel(cliente, "2026-01", "2026-09")
    por_nome = {p["nome"]: p for p in painel["promotores"]}
    assert por_nome["Ana"]["faturamento"] == 6000.0
    assert por_nome["Bruno"]["faturamento"] == 3000.0
    assert painel["resumo"]["faturamento"] == 9000.0
    assert _painel(cliente, "2026-01", "2026-06")["promotores"][0]["faturamento"] == 6000.0

    roteiros = cliente.get("/api/roteiros").json()
    assert [(r["promotor"], r["situacao"], r["visitas_por_semana"]) for r in roteiros] == [
        ("Ana", "encerrado", 3), ("Bruno", "vigente", 3)]

    # Troca marcada para o futuro: o vínculo novo fica "agendado", não "encerrado".
    bruno_vinculo = next(r["id"] for r in roteiros if r["promotor"] == "Bruno")
    cliente.post(f"/api/roteiros/{bruno_vinculo}/trocar", json={"promotor_id": ana, "data": "2099-01-01"})
    situacoes = sorted(r["situacao"] for r in cliente.get("/api/roteiros").json())
    assert situacoes == ["agendado", "encerrado", "vigente"]


def test_transferencia_em_lote_e_desligamento(cliente):
    entrar(cliente)
    supervisor = _supervisor(cliente)
    ana = _promotor(cliente, supervisor, "100", "Ana")
    bruno = _promotor(cliente, supervisor, "200", "Bruno")
    for nome in ("A", "B"):
        _vincular(cliente, ana, _pdv(cliente, nome))
    resposta = cliente.post("/api/roteiros/transferir",
                            json={"de_promotor_id": ana, "para_promotor_id": bruno, "data": "2026-05-01"})
    assert resposta.json() == {"transferidos": 2}
    resposta = cliente.post(f"/api/promotores/{bruno}/inativar", json={"data_desligamento": "2026-08-31"})
    assert resposta.json() == {"roteiros_encerrados": 2}
    assert all(not r["vigente"] for r in cliente.get("/api/roteiros").json())


def test_importacao_da_planilha_e_idempotente(cliente):
    entrar(cliente)
    for _ in range(2):
        for tipo in ("promotores", "roteiro"):
            with open(EXEMPLOS / f"{tipo}_exemplo.xlsx", "rb") as arquivo:
                resposta = cliente.post(f"/api/importacoes/{tipo}", files={"arquivo": (f"{tipo}.xlsx", arquivo)})
            assert resposta.status_code == 200, resposta.text
    assert len(cliente.get("/api/promotores").json()) == 4
    assert len(cliente.get("/api/pdvs").json()) == 11
    assert len(cliente.get("/api/roteiros").json()) == 11
    assert len(cliente.get("/api/supervisores").json()) == 2
    assert resposta.json()["cadastros"] == {"criados": 0, "mantidos": 11, "pendentes": 0,
                                                "uf_diferente": 0}


def test_converte_dados_da_versao_anterior(banco):
    # Simula um banco da versão anterior: planilha gravada nas tabelas "promotores" e "roteiro".
    pd.DataFrame([{"codigo": "1", "nome": "Ana Teste", "admissao": "2025-03-10", "municipio": "TIJUCAS - SC",
                   "supervisor": "Vanessa", "salario": 2000.0, "ajuda_custo": 500.0, "transporte": 300.0,
                   "custo_mensal": 2800.0}]).to_sql("promotores", banco.db.engine, index=False)
    pd.DataFrame([{"codigo_promotor": "", "colaborador": "ANA  TESTE", "cnpj": CNPJ_A, "loja": "LOJA 1",
                   "cidade": "TIJUCAS", "uf": "SC", "visitas_semana": 2},
                  {"codigo_promotor": "", "colaborador": "FULANO", "cnpj": CNPJ_B, "loja": "LOJA 2",
                   "cidade": "ITAJAI", "uf": "SC", "visitas_semana": None}]).to_sql("roteiro", banco.db.engine, index=False)

    # Faturamento no formato antigo (somado por mês) e histórico antigo de importações.
    pd.DataFrame([{"ano": 2026, "mes": 1, "cnpj": CNPJ_A, "valor": 10.0}]).to_sql("faturamento", banco.db.engine, index=False)
    pd.DataFrame([{"tipo": "roteiro", "arquivo": "x.xlsx", "data_hora": "2026-10-01", "linhas": 1, "detalhe": ""}]).to_sql(
        "importacoes", banco.db.engine, index=False)

    banco.carga.preparar_banco()
    banco.carga.preparar_banco()   # rodar de novo não duplica
    assert banco.faturamento.tem_faturamento_antigo()   # avisa para importar o faturamento de novo

    with banco.db.SessaoLocal() as sessao:
        from app.modelos import Promotor, Roteiro
        promotor = sessao.query(Promotor).one()
        assert (promotor.municipio, promotor.uf, promotor.supervisor.nome) == ("TIJUCAS", "SC", "Vanessa")
        assert [(c.ano, c.mes, c.total) for c in promotor.custos] == [(2025, 3, 2800.0)]
        assert sessao.query(Roteiro).count() == 1
        assert banco.dados.colaboradores_pendentes(sessao) == ["FULANO"]
