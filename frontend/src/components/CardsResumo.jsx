import { classePercentual, formatarMoeda, formatarPercentual } from '../formato.js'

// Cartões do resumo, como no documento (seção 7.1): custo, faturamento, custo ÷ faturamento,
// nº de promotores, nº de lojas e total de visitas por semana.
export default function CardsResumo({ resumo, regras }) {
  return (
    <>
      <section className="cards">
        <div className="card">
          <span>Custo dos promotores</span>
          <strong>{formatarMoeda(resumo.custo)}</strong>
          <small>{resumo.meses} mês(es)</small>
        </div>
        <div className="card">
          <span>Faturamento das lojas</span>
          <strong>{formatarMoeda(resumo.faturamento)}</strong>
        </div>
        <div className="card">
          <span>Custo ÷ faturamento</span>
          <strong className={classePercentual(resumo.percentual_custo, regras)}>{formatarPercentual(resumo.percentual_custo)}</strong>
        </div>
        <div className="card">
          <span>Promotores</span>
          <strong>{resumo.promotores}</strong>
        </div>
        <div className="card">
          <span>Lojas</span>
          <strong>{resumo.lojas}</strong>
        </div>
        <div className="card">
          <span>Visitas por semana</span>
          <strong>{resumo.visitas_semana ?? '—'}</strong>
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
