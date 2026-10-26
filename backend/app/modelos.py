"""Tabelas dos cadastros (SQLAlchemy). A estrutura do banco é criada pelas migrations
em backend/migrations; este arquivo só descreve as tabelas para o Python."""
from datetime import date, datetime

from sqlalchemy import (Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
                        UniqueConstraint, func)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

PERFIS = ("admin", "consulta", "supervisor")


class Base(DeclarativeBase):
    pass


class Carimbo:
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


def _dinheiro():
    return mapped_column(Numeric(12, 2, asdecimal=False), default=0, nullable=False)


class Supervisor(Carimbo, Base):
    __tablename__ = "supervisores"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), unique=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)

    promotores: Mapped[list["Promotor"]] = relationship(back_populates="supervisor")


class Promotor(Carimbo, Base):
    __tablename__ = "promotores"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nome: Mapped[str] = mapped_column(String(150))
    data_admissao: Mapped[date | None] = mapped_column(Date)
    data_desligamento: Mapped[date | None] = mapped_column(Date)
    municipio: Mapped[str] = mapped_column(String(120), default="")
    uf: Mapped[str] = mapped_column(String(2), default="")
    supervisor_id: Mapped[int | None] = mapped_column(ForeignKey("supervisores.id"))
    funcao: Mapped[str] = mapped_column(String(30), default="Promotor")
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    observacao: Mapped[str] = mapped_column(Text, default="")

    supervisor: Mapped[Supervisor | None] = relationship(back_populates="promotores")
    custos: Mapped[list["CustoPromotor"]] = relationship(
        back_populates="promotor", cascade="all, delete-orphan",
        order_by="(CustoPromotor.ano, CustoPromotor.mes)")
    roteiros: Mapped[list["Roteiro"]] = relationship(back_populates="promotor")


class CustoPromotor(Carimbo, Base):
    """Custo por competência: vale a partir de ano/mês até o próximo reajuste."""
    __tablename__ = "custos_promotor"
    __table_args__ = (UniqueConstraint("promotor_id", "ano", "mes"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    promotor_id: Mapped[int] = mapped_column(ForeignKey("promotores.id", ondelete="CASCADE"))
    ano: Mapped[int] = mapped_column(Integer)
    mes: Mapped[int] = mapped_column(Integer)
    salario: Mapped[float] = _dinheiro()
    ajuda_custo: Mapped[float] = _dinheiro()
    vale_transporte: Mapped[float] = _dinheiro()
    outros: Mapped[float] = _dinheiro()

    promotor: Mapped[Promotor] = relationship(back_populates="custos")

    @property
    def total(self) -> float:
        return round((self.salario or 0) + (self.ajuda_custo or 0) + (self.vale_transporte or 0)
                     + (self.outros or 0), 2)


class Pdv(Carimbo, Base):
    """Ponto de venda. Identificado por CNPJ + nome, porque há lojas diferentes com o mesmo CNPJ."""
    __tablename__ = "pdvs"
    __table_args__ = (UniqueConstraint("cnpj_cpf", "nome_chave"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    cnpj_cpf: Mapped[str] = mapped_column(String(14), default="")
    nome_fantasia: Mapped[str] = mapped_column(String(200))
    nome_chave: Mapped[str] = mapped_column(String(200))   # nome sem acento/maiúsculo, para não duplicar
    cod_cli_erp: Mapped[str] = mapped_column(String(30), default="")
    razao_social: Mapped[str] = mapped_column(String(200), default="")
    cidade: Mapped[str] = mapped_column(String(120), default="")
    uf: Mapped[str] = mapped_column(String(2), default="")
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)

    roteiros: Mapped[list["Roteiro"]] = relationship(back_populates="pdv")


class Roteiro(Carimbo, Base):
    """Vínculo promotor ↔ PDV com vigência (data_fim vazia = vigente)."""
    __tablename__ = "roteiros"
    id: Mapped[int] = mapped_column(primary_key=True)
    promotor_id: Mapped[int] = mapped_column(ForeignKey("promotores.id"))
    pdv_id: Mapped[int] = mapped_column(ForeignKey("pdvs.id"))
    data_inicio: Mapped[date] = mapped_column(Date)
    data_fim: Mapped[date | None] = mapped_column(Date)
    visitas_por_semana: Mapped[int | None] = mapped_column(Integer)
    dias_semana: Mapped[str] = mapped_column(String(40), default="")
    observacao: Mapped[str] = mapped_column(Text, default="")

    promotor: Mapped[Promotor] = relationship(back_populates="roteiros")
    pdv: Mapped[Pdv] = relationship(back_populates="roteiros")


class RoteiroPendente(Carimbo, Base):
    """Linha de roteiro importada que não achou o promotor (vira pendência, sem vínculo inventado)."""
    __tablename__ = "roteiro_pendencias"
    id: Mapped[int] = mapped_column(primary_key=True)
    colaborador: Mapped[str] = mapped_column(String(150), default="")
    cnpj_cpf: Mapped[str] = mapped_column(String(14), default="")
    loja: Mapped[str] = mapped_column(String(200), default="")
    cidade: Mapped[str] = mapped_column(String(120), default="")
    uf: Mapped[str] = mapped_column(String(2), default="")
    visitas_por_semana: Mapped[int | None] = mapped_column(Integer)
    origem: Mapped[str] = mapped_column(String(60), default="")


class Usuario(Carimbo, Base):
    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(150))
    usuario: Mapped[str] = mapped_column(String(60), unique=True)
    senha_hash: Mapped[str] = mapped_column(String(255))
    perfil: Mapped[str] = mapped_column(String(20), default="consulta")
    supervisor_id: Mapped[int | None] = mapped_column(ForeignKey("supervisores.id"))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    tentativas_falhas: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_ate: Mapped[datetime | None] = mapped_column(DateTime)


class Importacao(Base):
    """Histórico de importações. As de faturamento podem ser desfeitas (apaga os itens dela)."""
    __tablename__ = "importacoes"
    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(20))          # faturamento | promotores | roteiro | planilha
    arquivo_nome: Mapped[str] = mapped_column(String(255), default="")
    usuario: Mapped[str] = mapped_column(String(60), default="")
    periodos: Mapped[str] = mapped_column(Text, default="")  # "2026-01,2026-02…"
    linhas_lidas: Mapped[int] = mapped_column(Integer, default=0)
    linhas_importadas: Mapped[int] = mapped_column(Integer, default=0)
    linhas_com_erro: Mapped[int] = mapped_column(Integer, default=0)
    total_venda: Mapped[float] = mapped_column(Numeric(16, 2, asdecimal=False), default=0)
    avisos: Mapped[str] = mapped_column(Text, default="")    # JSON: lista de textos
    log_erros: Mapped[str] = mapped_column(Text, default="")  # JSON: [{linha, motivo}]
    situacao: Mapped[str] = mapped_column(String(20), default="ativa")  # ativa | desfeita
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def _texto(tamanho=None):
    return mapped_column(String(tamanho) if tamanho else Text, nullable=True)


def _valor():
    return mapped_column(Numeric(14, 2, asdecimal=False), nullable=True)


class FaturamentoItem(Base):
    """Uma linha por item de nota fiscal, como na aba FATURAMENTO (exportação do ERP)."""
    __tablename__ = "faturamento_itens"
    id: Mapped[int] = mapped_column(primary_key=True)
    importacao_id: Mapped[int] = mapped_column(ForeignKey("importacoes.id", ondelete="CASCADE"))
    ano: Mapped[int] = mapped_column(Integer)
    mes: Mapped[int] = mapped_column(Integer)
    data_emissao: Mapped[date | None] = mapped_column(Date)
    cod_emp: Mapped[str | None] = _texto(20)
    num_nf: Mapped[str | None] = _texto(30)
    cod_segmento: Mapped[str | None] = _texto(20)
    descricao_segmento: Mapped[str | None] = _texto(120)
    cod_cli: Mapped[str] = mapped_column(String(30), default="")
    cod_est: Mapped[str | None] = _texto(20)
    tp_pes: Mapped[str | None] = _texto(2)
    cnpj_cpf: Mapped[str] = mapped_column(String(14))
    razao_social: Mapped[str | None] = _texto(200)
    cidade: Mapped[str | None] = _texto(120)
    uf: Mapped[str | None] = _texto(2)
    cod_rep: Mapped[str | None] = _texto(20)
    representante: Mapped[str | None] = _texto(150)
    familia_2: Mapped[str | None] = _texto(120)
    familia_4: Mapped[str | None] = _texto(150)
    marca: Mapped[str | None] = _texto(150)
    embalagem: Mapped[str | None] = _texto(40)
    volume: Mapped[str | None] = _texto(20)
    um: Mapped[str | None] = _texto(10)
    cod_item: Mapped[str | None] = _texto(30)
    descricao_item: Mapped[str | None] = _texto(255)
    qtde: Mapped[float | None] = _valor()
    ump: Mapped[str | None] = _texto(20)
    preco_unit: Mapped[float | None] = _valor()
    vlr_mercadoria: Mapped[float | None] = _valor()
    vlr_total: Mapped[float | None] = _valor()
    cod_tp_nf: Mapped[str | None] = _texto(20)
    tipo_nf: Mapped[str] = mapped_column(String(60), default="")
    tipo_nf_chave: Mapped[str] = mapped_column(String(60), default="")  # sem acento/maiúsculo, para as regras
    cfop: Mapped[str | None] = _texto(10)
    receita: Mapped[str | None] = _texto(10)
    cond_pgto: Mapped[str | None] = _texto(60)
    qtde_caixa: Mapped[float | None] = _valor()
    bonificacao: Mapped[float | None] = _valor()
    total_venda: Mapped[float | None] = _valor()
    grupo: Mapped[str | None] = _texto(60)
