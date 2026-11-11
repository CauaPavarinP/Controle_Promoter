"""Rotas que sobraram dos cadastros antigos.

Os cadastros de promotores, supervisores, lojas e roteiros eram alimentados pela planilha "ROTEIROS X
FATURAMENTOS", que não é mais usada: agora tudo vem dos arquivos das agências (app/atendimento.py).
Ficam só a lista de supervisores (perfil "supervisor" dos usuários) e a limpeza dos dados para recomeçar.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import atendimento, db
from .autenticacao import exigir_admin, usuario_logado
from .carga import trava_cadastros
from .modelos import (ApelidoColaborador, Backup, CustoPromotor, Importacao, Pdv, Promotor, Roteiro,
                      RoteiroPendente, Supervisor, Usuario)

rotas = APIRouter(prefix="/api")


def _erro(mensagem: str, status: int = 400):
    raise HTTPException(status_code=status, detail=mensagem)


@rotas.get("/supervisores")
def listar_supervisores(sessao: Session = Depends(db.sessao_db), _=Depends(usuario_logado)):
    return [{"id": s.id, "nome": s.nome, "ativo": s.ativo}
            for s in sessao.scalars(select(Supervisor).order_by(Supervisor.nome))]


PALAVRA_DE_CONFIRMACAO = "APAGAR"
BACKUPS_GUARDADOS = 10   # os mais antigos que isso são apagados
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def guardar_backup(sessao: Session, usuario: str, motivo: str) -> Backup | None:
    """Salva no banco um Excel (modelo das agências) com todos os atendimentos. None se não houver nada."""
    conteudo, linhas = atendimento.exportar_xlsx(sessao)
    if not linhas:
        return None
    backup = Backup(usuario=usuario, motivo=motivo[:120], linhas=linhas, conteudo=conteudo,
                    arquivo_nome=f"backup-atendimentos-{datetime.now():%Y-%m-%d-%H%M}.xlsx")
    sessao.add(backup)
    sessao.flush()
    antigos = sessao.scalars(select(Backup.id).order_by(Backup.id.desc()).offset(BACKUPS_GUARDADOS)).all()
    if antigos:
        sessao.query(Backup).filter(Backup.id.in_(antigos)).delete(synchronize_session=False)
    sessao.commit()
    return backup


@rotas.get("/backups")
def listar_backups(sessao: Session = Depends(db.sessao_db), _=Depends(exigir_admin)):
    consulta = select(Backup.id, Backup.criado_em, Backup.usuario, Backup.motivo, Backup.arquivo_nome, Backup.linhas)
    return [{"id": i, "criado_em": c, "usuario": u, "motivo": m, "arquivo": a, "linhas": n}
            for i, c, u, m, a, n in sessao.execute(consulta.order_by(Backup.id.desc()))]


@rotas.get("/backups/{backup_id}")
def baixar_backup(backup_id: int, sessao: Session = Depends(db.sessao_db), _=Depends(exigir_admin)):
    backup = sessao.get(Backup, backup_id)
    if backup is None:
        _erro("Backup não encontrado.", 404)
    return Response(backup.conteudo, media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{backup.arquivo_nome}"'})


@rotas.get("/atendimentos/exportar")
def exportar_atendimentos(sessao: Session = Depends(db.sessao_db), _=Depends(exigir_admin)):
    """Todos os atendimentos no modelo das agências (para conferir ou guardar uma cópia)."""
    conteudo, _linhas = atendimento.exportar_xlsx(sessao)
    return Response(conteudo, media_type=XLSX, headers={
        "Content-Disposition": f'attachment; filename="atendimentos-{datetime.now():%Y-%m-%d}.xlsx"'})


class ConfirmacaoApagar(BaseModel):
    confirmacao: str = Field(max_length=20)


@rotas.post("/cadastros/apagar")
def apagar_cadastros(dados: ConfirmacaoApagar, sessao: Session = Depends(db.sessao_db), usuario=Depends(exigir_admin)):
    """Apaga todos os atendimentos importados das agências (e o que sobrou dos cadastros da planilha antiga).

    Fica: faturamento do ERP, usuários, regras do cálculo e o histórico de importações. Antes de apagar, guarda
    no banco um backup (Excel no modelo das agências, dá para importar de novo): lista em /api/backups.
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
        backup = guardar_backup(sessao, usuario.usuario, "Antes de apagar os dados das agências")
        apagados = atendimento.apagar_tudo(sessao)
        registrar(sessao, "limpeza", "Apagar dados das agências", usuario.usuario, apagados,
                  [f"atendimentos apagados: {apagados}"]
                  + ([f"backup guardado: {backup.arquivo_nome}"] if backup else []))
        return {"atendimentos": apagados, "backup": backup.id if backup else None,
                "backup_arquivo": backup.arquivo_nome if backup else None}
    finally:
        trava_cadastros.release()
