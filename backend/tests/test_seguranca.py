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
