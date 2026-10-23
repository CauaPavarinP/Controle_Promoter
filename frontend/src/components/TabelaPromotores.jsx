import { classePercentual, formatarMoeda, formatarPercentual } from '../formato.js'

export default function TabelaPromotores({ promotores, selecionado, aoSelecionar }) {
  return (
    <section className="bloco">
      <h2>Promotores</h2>
      <p className="dica">Clique em um promotor para ver só as lojas dele. Ordenado do maior % de custo para o menor.</p>
      <div className="tabela-rolagem">
        <table>
          <thead>
            <tr>
              <th>Promotor</th>
              <th>Supervisor</th>
              <th>Município</th>
              <th className="num">Lojas</th>
              <th className="num">Sem compra</th>
              <th className="num">Visitas/sem.</th>
              <th className="num">Custo mensal</th>
              <th className="num">Custo no período</th>
              <th className="num">Faturamento</th>
              <th className="num">% custo</th>
            </tr>
          </thead>
          <tbody>
            {promotores.map((p) => (
              <tr
                key={p.codigo}
                className={`clicavel ${selecionado === p.codigo ? 'selecionada' : ''}`}
                onClick={() => aoSelecionar(p.codigo)}
              >
                <td>{p.nome}</td>
                <td>{p.supervisor}</td>
                <td>{p.municipio}</td>
                <td className="num">{p.lojas}</td>
                <td className={`num ${p.lojas_sem_compra ? 'texto-critico' : ''}`}>{p.lojas_sem_compra}</td>
                <td className="num">{p.visitas_semana ?? '—'}</td>
                <td className="num">{formatarMoeda(p.custo_mensal)}</td>
                <td className="num">{formatarMoeda(p.custo_periodo)}</td>
                <td className="num">{formatarMoeda(p.faturamento)}</td>
                <td className={`num ${classePercentual(p.percentual_custo)}`}>
                  {formatarPercentual(p.percentual_custo)}
                </td>
              </tr>
            ))}
            {!promotores.length && (
              <tr><td colSpan={10} className="vazio">Nenhum promotor com esses filtros.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}
