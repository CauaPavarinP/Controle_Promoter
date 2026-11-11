"""Rotas que sobraram dos cadastros antigos.

Os cadastros de promotores, supervisores, lojas e roteiros eram alimentados pela planilha "ROTEIROS X
FATURAMENTOS", que não é mais usada: agora tudo vem dos arquivos das agências (app/atendimento.py).
Ficam só a lista de supervisores (perfil "supervisor" dos usuários) e a limpeza dos dados para recomeçar.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import atendimento, db
from .autenticacao import exigir_admin, usuario_logado
from .carga import trava_cadastros
from .modelos import (ApelidoColaborador, CustoPromotor, Importacao, Pdv, Promotor, Roteiro, RoteiroPendente,
                      Supervisor, Usuario)

rotas = APIRouter(prefix="/api")


def _erro(mensagem: str, status: int = 400):
    raise HTTPException(status_code=status, detail=mensagem)


@rotas.get("/supervisores")
def listar_supervisores(sessao: Session = Depends(db.sessao_db), _=Depends(usuario_logado)):
    return [{"id": s.id, "nome": s.nome, "ativo": s.ativo}
            for s in sessao.scalars(select(Supervisor).order_by(Supervisor.nome))]


PALAVRA_DE_CONFIRMACAO = "APAGAR"


class ConfirmacaoApagar(BaseModel):
    confirmacao: str = Field(max_length=20)


@rotas.post("/cadastros/apagar")
def apagar_cadastros(dados: ConfirmacaoApagar, sessao: Session = Depends(db.sessao_db), usuario=Depends(exigir_admin)):
    """Apaga todos os atendimentos importados das agências (e o que sobrou dos cadastros da planilha antiga).

    Fica: faturamento do ERP, usuários, regras do cálculo e o histórico de importações. Não tem volta.
    """
    if dados.confirmacao.strip().upper() != PALAVRA_DE_CONFIRMACAO:
        _erro(f"Para apagar, digite {PALAVRA_DE_CONFIRMACAO} na confirmação.")
    if not trava_cadastros.acquire(blocking=False):
        _erro("Tem uma importação em andamento. Espere ela terminar para apagar.")
    try:
        from .faturamento import registrar
        supervisores_de_usuarios = select(Usuario.supervisor_id).where(Usuario.supervisor_id.is_not(None))
        # Cadastros da planilha antiga (não são mais usados).
        for modelo in (ApelidoColaborador, Roteiro, RoteiroPendente, CustoPromotor, Promotor, Pdv):
            sessao.query(modelo).delete()
        sessao.query(Supervisor).filter(Supervisor.id.not_in(supervisores_de_usuarios)).delete(
            synchronize_session=False)
        sessao.query(Importacao).filter(Importacao.tipo.in_(["promotores", "roteiro"]),
                                        Importacao.situacao == "ativa").update({"situacao": "apagada"})
        sessao.commit()
        apagados = atendimento.apagar_tudo(sessao)
        registrar(sessao, "limpeza", "Apagar dados das agências", usuario.usuario, apagados,
                  [f"atendimentos apagados: {apagados}"])
        return {"atendimentos": apagados}
    finally:
        trava_cadastros.release()
