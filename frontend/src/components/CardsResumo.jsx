import { classePercentual, formatarMoeda, formatarPercentual } from '../formato.js'

// Os 4 números principais do Resumo: custo, faturamento, custo ÷ faturamento, promotores e lojas.
export default function CardsResumo({ resumo, regras }) {
  return (
    <>
      <section className="cards cards-4">
        <div className="card">
          <span>Custo dos promotores</span>
          <strong>{formatarMoeda(resumo.custo)}</strong>
          <small>soma de {resumo.meses} mês(es)</small>
        </div>
        <div className="card">
          <span>Faturamento das lojas</span>
          <strong>{formatarMoeda(resumo.faturamento)}</strong>
          <small>das lojas atendidas, pelo ERP</small>
        </div>
        <div className="card">
          <span>Custo ÷ faturamento</span>
          <strong className={classePercentual(resumo.percentual_custo, regras)}>{formatarPercentual(resumo.percentual_custo)}</strong>
          <small>quanto o promotor custa sobre o que as lojas compram</small>
        </div>
        <div className="card">
          <span>Promotores e lojas</span>
          <strong>{resumo.promotores} · {resumo.lojas}</strong>
          <small>promotores · lojas atendidas</small>
        </div>
      </section>
      {resumo.cnpjs_compartilhados > 0 && (
        <p className="nota">
          ⚠ {resumo.cnpjs_compartilhados} CNPJ(s) com mais de uma loja e sem COD CLI para separar: o faturamento do CNPJ
          é dividido entre essas lojas (e entre os promotores de cada loja), para a soma por promotor bater com o total.
        </p>
      )}
      {(resumo.avisos || []).map((aviso) => <p key={aviso} className="nota">⚠ {aviso}</p>)}
    </>
  )
}
