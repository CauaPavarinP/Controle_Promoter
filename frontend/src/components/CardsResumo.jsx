import { classePercentual, formatarMoeda, formatarPercentual } from '../formato.js'

// Os 4 números principais do Resumo: custo das agências, compras das lojas, custo ÷ compras, promotores e lojas.
export default function CardsResumo({ resumo, regras }) {
  return (
    <>
      <section className="cards cards-4">
        <div className="card">
          <span>Pago às agências</span>
          <strong>{formatarMoeda(resumo.custo)}</strong>
          <small>
            {resumo.meses_com_arquivo === resumo.meses
              ? `atendimento das lojas em ${resumo.meses} mês(es)`
              : `arquivo de agência em ${resumo.meses_com_arquivo} de ${resumo.meses} meses do período`}
          </small>
        </div>
        <div className="card">
          <span>Lojas compraram</span>
          <strong>{formatarMoeda(resumo.faturamento)}</strong>
          <small>faturamento do ERP das lojas atendidas</small>
        </div>
        <div className="card">
          <span>% do faturamento</span>
          <strong className={resumo.sem_erp ? '' : classePercentual(resumo.percentual_custo, regras) || 'pct-ok'}>
            {resumo.sem_erp ? '—' : formatarPercentual(resumo.percentual_custo)}
          </strong>
          <small>custo ÷ compras das lojas · máximo {formatarPercentual(regras?.limite_percentual)}</small>
        </div>
        <div className="card">
          <span>Agências · promotores · lojas</span>
          <strong>{resumo.agencias} · {resumo.promotores} · {resumo.lojas}</strong>
          <small>
            {resumo.visitas} visita(s) no período
            {resumo.agencias_sem_custo > 0 && (
              <span title="Agências que informaram todas as lojas com R$ 0 no período (ex.: CLT, MEI, freelancer pagos por fora). Não entram nos números acima.">
                <br />+ {resumo.agencias_sem_custo} agência(s) sem custo: {resumo.promotores_sem_custo} promotor(es), {resumo.lojas_sem_custo} loja(s)
              </span>
            )}
          </small>
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
