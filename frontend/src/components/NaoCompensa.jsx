// "Onde o custo não compensa": a pergunta do Maurício no áudio — loja que compra pouco e recebe
// o promotor várias vezes por semana, e promotor que custa muito para o que as lojas dele compram.
import { useState } from 'react'
import { classePercentual, formatarMoeda, formatarPercentual } from '../formato.js'
import { Tabela } from './ui.jsx'

const QUANTIDADE = 10

export default function NaoCompensa({ lojas, promotores, regras, aoAbrirPromotor }) {
  const [verTodasLojas, setVerTodasLojas] = useState(false)
  const [verTodosPromotores, setVerTodosPromotores] = useState(false)

  // Lojas com visita, da que menos compra por visita para a que mais compra. Loja que divide o CNPJ
  // com outra fica de fora: o faturamento dela é do CNPJ inteiro.
  const lojasVisitadas = lojas
    .filter((l) => l.visitas_semana > 0 && !l.compartilhado)
    .sort((a, b) => (a.faturamento_por_visita ?? 0) - (b.faturamento_por_visita ?? 0))
  // Promotor com custo e sem nenhuma compra nas lojas vem primeiro; depois, do maior % para o menor.
  const peso = (p) => p.percentual_custo ?? Number.MAX_VALUE
  const piorPromotores = promotores.filter((p) => p.custo_periodo > 0).sort((a, b) => peso(b) - peso(a))

  return (
    <section className="bloco nao-compensa">
      <h2>Onde o custo não compensa</h2>
      <div className="duas-colunas">
        <div>
          <h3>Lojas que compram pouco para as visitas que recebem</h3>
          <p className="dica">Ordenadas pelo faturamento por visita (o que a loja comprou ÷ visitas do promotor no período).</p>
          <Tabela
            chave="chave"
            linhas={(verTodasLojas ? lojasVisitadas : lojasVisitadas.slice(0, QUANTIDADE))
              .map((l) => ({ ...l, chave: `${l.codigo_promotor}-${l.cnpj}-${l.loja}` }))}
            porPagina={verTodasLojas ? 20 : QUANTIDADE}
            arquivo="lojas-que-compram-pouco"
            vazio="Nenhuma loja com visitas por semana informadas."
            classeLinha={(l) => (l.faturamento <= 0 ? 'linha-sem-compra' : '')}
            colunas={[
              { campo: 'loja', titulo: 'Loja', quebra: true,
                mostrar: (l) => <>{l.loja}<small className="dica sublinha">{l.cidade}{l.uf ? ` - ${l.uf}` : ''} · {l.promotor}</small></> },
              { campo: 'visitas_semana', titulo: 'Visitas/sem.', num: true },
              { campo: 'faturamento', titulo: 'Comprou', num: true, mostrar: (l) => formatarMoeda(l.faturamento) },
              { campo: 'faturamento_por_visita', titulo: 'Por visita', num: true, ordenar: (l) => l.faturamento_por_visita ?? 0,
                mostrar: (l) => <b>{formatarMoeda(l.faturamento_por_visita ?? 0)}</b> },
            ]}
          />
          {lojasVisitadas.length > QUANTIDADE && (
            <button className="secundario" onClick={() => setVerTodasLojas((v) => !v)}>
              {verTodasLojas ? 'Mostrar só as 10 primeiras' : `Ver todas (${lojasVisitadas.length})`}
            </button>
          )}
        </div>
        <div>
          <h3>Promotores com o maior custo sobre o faturamento</h3>
          <p className="dica">Custo do promotor no período ÷ o que as lojas dele compraram. Clique para ver as lojas.</p>
          <Tabela
            chave="codigo"
            linhas={verTodosPromotores ? piorPromotores : piorPromotores.slice(0, QUANTIDADE)}
            porPagina={verTodosPromotores ? 20 : QUANTIDADE}
            arquivo="promotores-maior-custo"
            vazio="Nenhum promotor com esses filtros."
            aoClicar={(p) => aoAbrirPromotor(p.codigo)}
            colunas={[
              { campo: 'nome', titulo: 'Promotor', quebra: true,
                mostrar: (p) => <>{p.nome}<small className="dica sublinha">{p.supervisor || 'sem supervisor'} · {p.lojas} loja(s)</small></> },
              { campo: 'custo_periodo', titulo: 'Custo', num: true, mostrar: (p) => formatarMoeda(p.custo_periodo) },
              { campo: 'faturamento', titulo: 'Faturamento', num: true, mostrar: (p) => formatarMoeda(p.faturamento) },
              { campo: 'percentual_custo', titulo: '% custo', num: true, ordenar: peso,
                mostrar: (p) => (
                  <b className={classePercentual(p.percentual_custo, regras)}>
                    {p.percentual_custo == null ? 'sem compra' : formatarPercentual(p.percentual_custo)}
                  </b>
                ) },
            ]}
          />
          {piorPromotores.length > QUANTIDADE && (
            <button className="secundario" onClick={() => setVerTodosPromotores((v) => !v)}>
              {verTodosPromotores ? 'Mostrar só os 10 primeiros' : `Ver todos (${piorPromotores.length})`}
            </button>
          )}
        </div>
      </div>
    </section>
  )
}
