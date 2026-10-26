import { classePercentual, formatarMoeda, formatarPercentual } from '../formato.js'

export default function CardsResumo({ resumo, regras }) {
  return (
    <>
      <section className="cards">
        <div className="card">
          <span>Custo dos promotores</span>
          <strong>{formatarMoeda(resumo.custo)}</strong>
          <small>{resumo.promotores} promotor(es) • {resumo.meses} mês(es)</small>
        </div>
        <div className="card">
          <span>Faturamento das lojas</span>
          <strong>{formatarMoeda(resumo.faturamento)}</strong>
          <small>{resumo.lojas} loja(s) atendida(s)</small>
        </div>
        <div className={`card ${classePercentual(resumo.percentual_custo, regras)}`}>
          <span>Custo sobre faturamento</span>
          <strong>{formatarPercentual(resumo.percentual_custo)}</strong>
          <small>quanto do faturamento vai para o promotor</small>
        </div>
        <div className={`card ${resumo.lojas_sem_compra ? 'pct-critico' : ''}`}>
          <span>Lojas sem compra no período</span>
          <strong>{resumo.lojas_sem_compra}</strong>
          <small>de {resumo.lojas} loja(s)</small>
        </div>
      </section>
      {resumo.cnpjs_compartilhados > 0 && (
        <p className="nota">
          ⚠ {resumo.cnpjs_compartilhados} CNPJ(s) atendem mais de uma loja (rede que compra pela matriz). Nessas lojas o
          valor mostrado é o do CNPJ inteiro; nos totais ele é contado uma vez só.
        </p>
      )}
    </>
  )
}
