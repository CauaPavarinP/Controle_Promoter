import { classePercentual, formatarMoeda, formatarPercentual } from '../formato.js'

// Os 4 números principais do Resumo: custo das agências, compras das lojas, custo ÷ compras, promotores e lojas.
export default function CardsResumo({ resumo, regras }) {
  return (
    <>
      <section className="cards cards-4">
        <div className="card">
          <span>Pago às agências</span>
          <strong>{formatarMoeda(resumo.custo)}</strong>
          <small>atendimento das lojas em {resumo.meses} mês(es)</small>
        </div>
        <div className="card">
          <span>Lojas compraram</span>
          <strong>{formatarMoeda(resumo.faturamento)}</strong>
          <small>faturamento do ERP das lojas atendidas</small>
        </div>
        <div className="card">
          <span>Custo ÷ compras</span>
          <strong className={classePercentual(resumo.percentual_custo, regras)}>{formatarPercentual(resumo.percentual_custo)}</strong>
          <small>quanto o atendimento custa sobre o que as lojas compram</small>
        </div>
        <div className="card">
          <span>Agências · promotores · lojas</span>
          <strong>{resumo.agencias} · {resumo.promotores} · {resumo.lojas}</strong>
          <small>{resumo.visitas} visita(s) no período</small>
        </div>
      </section>
      {resumo.cnpjs_compartilhados > 0 && (
        <p className="nota">
          ⚠ {resumo.cnpjs_compartilhados} CNPJ(s) usados por mais de uma loja (rede que compra pela matriz ou pelo CD): o
          faturamento do CNPJ é dividido entre essas lojas, para a soma por promotor e agência bater com o total.
        </p>
      )}
      {(resumo.avisos || []).map((aviso) => <p key={aviso} className="nota">⚠ {aviso}</p>)}
    </>
  )
}
