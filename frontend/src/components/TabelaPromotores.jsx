import { classePercentual, formatarMoeda, formatarPercentual } from '../formato.js'
import { Tabela } from './ui.jsx'

// Ranking por promotor: faturamento das lojas dele × custo dele no período.
export default function TabelaPromotores({ promotores, regras, aoSelecionar }) {
  const pct = (p) => <span className={classePercentual(p.percentual_custo, regras)}>{formatarPercentual(p.percentual_custo)}</span>
  return (
    <section className="bloco">
      <h2>Promotores</h2>
      <p className="dica nao-imprimir">Clique em um promotor para abrir as lojas dele.</p>
      <Tabela
        chave="codigo"
        linhas={promotores}
        arquivo="promotores-custo-x-faturamento"
        aoClicar={(p) => aoSelecionar(p.codigo)}
        vazio="Nenhum promotor com esses filtros."
        colunas={[
          { campo: 'nome', titulo: 'Promotor', quebra: true },
          { campo: 'supervisor', titulo: 'Supervisor' },
          { campo: 'municipio', titulo: 'Município' },
          { campo: 'lojas', titulo: 'Lojas', num: true },
          { campo: 'visitas_semana', titulo: 'Visitas/sem.', num: true, mostrar: (p) => p.visitas_semana ?? '—' },
          { campo: 'custo_periodo', titulo: 'Custo no período', num: true, mostrar: (p) => formatarMoeda(p.custo_periodo) },
          { campo: 'faturamento', titulo: 'Faturamento', num: true, mostrar: (p) => formatarMoeda(p.faturamento) },
          { campo: 'percentual_custo', titulo: '% custo', num: true, mostrar: pct, ordenar: (p) => p.percentual_custo ?? -1 },
        ]}
      />
    </section>
  )
}
