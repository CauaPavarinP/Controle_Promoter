"""Proteções contra invasão: sessão que cai ao sair/trocar senha, pedido de outro site, cabeçalhos, caminhos."""
from fastapi.testclient import TestClient

from conftest import entrar


def test_cabecalhos_de_seguranca(cliente):
    resposta = cliente.get("/health")
    assert resposta.headers["x-frame-options"] == "DENY"
    assert resposta.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in resposta.headers["content-security-policy"]


def test_cookie_copiado_para_de_valer_ao_sair(banco, cliente):
    entrar(cliente)
    cookie = cliente.cookies.get("session")
    with TestClient(banco.main.app) as ladrao:
        ladrao.cookies.set("session", cookie)
        assert ladrao.get("/api/sessao").status_code == 200
        cliente.post("/api/logout")
        assert ladrao.get("/api/sessao").status_code == 401


def test_trocar_senha_derruba_as_outras_sessoes(banco, cliente):
    entrar(cliente)
    with TestClient(banco.main.app) as ladrao:
        ladrao.cookies.set("session", cliente.cookies.get("session"))
        resposta = cliente.put("/api/minha-senha", json={"senha_atual": "senha-teste", "nova_senha": "senha-nova-123"})
        assert resposta.status_code == 200
        assert ladrao.get("/api/sessao").status_code == 401
        assert cliente.get("/api/sessao").status_code == 200  # quem trocou continua logado


def test_pedido_vindo_de_outro_site_e_recusado(cliente):
    entrar(cliente)
    fora = cliente.post("/api/supervisores", json={"nome": "X"}, headers={"Origin": "https://site-malicioso.com"})
    assert fora.status_code == 403
    dentro = cliente.post("/api/supervisores", json={"nome": "Y"}, headers={"Origin": "http://testserver"})
    assert dentro.status_code == 200


def test_caminhos_fora_do_front_nao_vazam(cliente):
    for caminho in ("/../backend/.env", "/..%2f..%2fbackend%2fapp%2fconfig.py", "/assets/..%2f..%2fapp%2fconfig.py"):
        resposta = cliente.get(caminho)
        assert "SECRET_KEY" not in resposta.text and "import" not in resposta.text


def test_login_limita_tamanho(cliente):
    assert cliente.post("/api/login", json={"usuario": "x" * 500, "senha": "y"}).status_code == 422


def test_envio_grande_demais_e_recusado_antes_de_receber(cliente):
    """400 MB numa rota comum levavam o servidor a 1,37 GB de memória (o do Render tem 512 MB)."""
    entrar(cliente)
    from app.limites import LIMITE_EXPORTACAO, LIMITE_PADRAO
    corpo = b'{"titulo":"x","colunas":[{"titulo":"a"}],"linhas":[["' + b"A" * (LIMITE_EXPORTACAO + 10) + b'"]]}'
    resposta = cliente.post("/api/exportar", content=corpo, headers={"Content-Type": "application/json"})
    assert resposta.status_code == 413 and "grande demais" in resposta.json()["detail"]
    # Sem Content-Length (envio em partes): conta os bytes e para no limite.
    def em_partes():
        for _ in range(3):
            yield b"x" * LIMITE_PADRAO
    resposta = cliente.put("/api/regras", content=em_partes(), headers={"Content-Type": "application/json"})
    assert resposta.status_code == 413
    # Tamanho normal continua passando.
    ok = cliente.post("/api/exportar", json={"titulo": "x", "colunas": [{"titulo": "a"}], "linhas": [["b"]]})
    assert ok.status_code == 200


def test_bloqueio_nao_entrega_quais_usuarios_existem(cliente):
    """Antes, só usuário que existe aparecia como "bloqueado": dava para descobrir os logins válidos."""
    respostas = {}
    for nome in ("mauricio", "nao-existe"):
        for _ in range(5):
            assert cliente.post("/api/login", json={"usuario": nome, "senha": "errada"}).status_code == 401
        respostas[nome] = cliente.post("/api/login", json={"usuario": nome, "senha": "errada"}).json()["detail"]
    assert respostas["mauricio"] == respostas["nao-existe"]
    assert "Muitas tentativas" in respostas["nao-existe"]
    # Bloqueado mesmo com a senha certa, até passar o tempo.
    assert cliente.post("/api/login", json={"usuario": "mauricio", "senha": "senha-teste"}).status_code == 401
