from conftest import entrar

CNPJ_A = "11222333000181"   # CNPJs com dígito verificador válido
CNPJ_B = "11444777000161"


# ---------------------------------------------------------------------------
# Usuários e login
# ---------------------------------------------------------------------------

def test_primeiro_admin_e_perfil_consulta_so_le(cliente):
    eu = entrar(cliente)
    assert eu["perfil"] == "admin"
    novo = cliente.post("/api/usuarios", json={"nome": "Rayan", "usuario": "rayan", "perfil": "consulta"}).json()
    cliente.post("/api/logout")

    sessao = entrar(cliente, "rayan", novo["senha_provisoria"])
    # Senha provisória (o administrador sabe qual é): antes de trocar, não vê nada.
    assert sessao["trocar_senha"] is True
    assert cliente.get("/api/opcoes").status_code == 403
    assert cliente.get("/api/sessao").status_code == 200
    assert cliente.put("/api/minha-senha", json={"senha_atual": "errada", "nova_senha": "nova-senha-1"}).status_code == 400
    assert cliente.put("/api/minha-senha", json={"senha_atual": novo["senha_provisoria"],
                                                  "nova_senha": novo["senha_provisoria"]}).status_code == 400
    assert cliente.put("/api/minha-senha", json={"senha_atual": novo["senha_provisoria"],
                                                  "nova_senha": "nova-senha-1"}).status_code == 200
    assert cliente.get("/api/sessao").json()["trocar_senha"] is False
    assert cliente.get("/api/opcoes").status_code == 200
    assert cliente.put("/api/regras", json={"limite_percentual": 10}).status_code == 403
    assert cliente.get("/api/usuarios").status_code == 403
    cliente.post("/api/logout")
    entrar(cliente, "rayan", "nova-senha-1")


def test_bloqueio_apos_tentativas_erradas(cliente):
    for _ in range(5):
        assert cliente.post("/api/login", json={"usuario": "mauricio", "senha": "errada"}).status_code == 401
    resposta = cliente.post("/api/login", json={"usuario": "mauricio", "senha": "senha-teste"})
    assert resposta.status_code == 401 and "Muitas tentativas" in resposta.json()["detail"]


def test_nao_fica_sem_administrador(cliente):
    eu = entrar(cliente)
    assert cliente.post(f"/api/usuarios/{eu['id']}/inativar").status_code == 400
    assert cliente.put(f"/api/usuarios/{eu['id']}", json={"nome": "M", "perfil": "consulta"}).status_code == 400


# ---------------------------------------------------------------------------
# Cadastros
# ---------------------------------------------------------------------------


def test_so_administrador_apaga_cadastros(cliente):
    entrar(cliente)
    novo = cliente.post("/api/usuarios", json={"nome": "Consulta", "usuario": "consulta", "perfil": "consulta"}).json()
    cliente.post("/api/logout")
    entrar(cliente, "consulta", novo["senha_provisoria"])
    cliente.put("/api/minha-senha", json={"senha_atual": novo["senha_provisoria"], "nova_senha": "senha-nova-123"})
    resposta = cliente.post("/api/cadastros/apagar", json={"confirmacao": "APAGAR"})
    assert resposta.status_code == 403 and "administradores" in resposta.json()["detail"]
