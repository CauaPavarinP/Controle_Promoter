import { classePercentual, formatarMoeda, formatarPercentual } from '../formato.js'

// Os 4 números principais do Resumo. Promotores, lojas e visitas ficam como detalhe dos cartões.
export default function CardsResumo({ resumo, regras }) {
  return (
    <>
      <section className="cards cards-4">
        <div className="card">
          <span>Custo dos promotores</span>
          <strong>{formatarMoeda(resumo.custo)}</strong>
          <small>{resumo.promotores} promotor(es) · {resumo.meses} mês(es)</small>
        </div>
        <div className="card">
          <span>Faturamento das lojas</span>
          <strong>{formatarMoeda(resumo.faturamento)}</strong>
          <small>{resumo.lojas} loja(s) atendida(s)</small>
        </div>
        <div className="card">
          <span>Custo ÷ faturamento</span>
          <strong className={classePercentual(resumo.percentual_custo, regras)}>{formatarPercentual(resumo.percentual_custo)}</strong>
          <small>{resumo.visitas_semana ?? '—'} visitas por semana</small>
        </div>
        <div className={`card ${resumo.lojas_sem_compra > 0 ? 'card-alerta' : ''}`}>
          <span>Lojas visitadas sem compra</span>
          <strong>{resumo.lojas_sem_compra}</strong>
          <small>recebem o promotor e não compraram no período</small>
        </div>
      </section>
      {resumo.cnpjs_compartilhados > 0 && (
        <p className="nota">
          ⚠ {resumo.cnpjs_compartilhados} CNPJ(s) com mais de uma loja e sem COD CLI para separar: o faturamento é
          compartilhado entre as lojas e conta uma vez só nos totais.
        </p>
      )}
    </>
  )
}
