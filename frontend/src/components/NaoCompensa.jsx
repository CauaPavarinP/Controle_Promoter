// "Onde o custo não compensa": a pergunta do Maurício no áudio — loja que compra pouco e recebe
// o promotor várias vezes por semana, e promotor que custa muito para o que as lojas dele compram.
import { useState } from 'react'
import { classePercentual, formatarMoeda, formatarPercentual } from '../formato.js'
import { Tabela } from './ui.jsx'

const QUANTIDADE = 10

export default function NaoCompensa({ lojas, promotores, regras, aoAbrirPromotor }) {
  const [verTodasLojas, setVerTodasLojas] = useState(false)
  const [verTodosPromotores, setVerTodosPromotores] = useState(false)

  // Loja que divide o CNPJ com outra fica de fora (o faturamento dela é do CNPJ inteiro), e loja sem CNPJ
  // também (não dá para achar o faturamento).
  const candidatas = lojas.filter((l) => l.cnpj && !l.compartilhado)
  const semVisitas = candidatas.filter((l) => !(l.visitas_semana > 0)).length
  // A planilha não tem visitas por semana: sem elas, a lista ordena pelo faturamento.
  const [criterio, setCriterio] = useState(null)
  const porVisita = (criterio ?? (semVisitas <= candidatas.length / 2 ? 'visita' : 'faturamento')) === 'visita'
  const lojasOrdenadas = [...candidatas].sort((a, b) => {
    if (porVisita) {
      const comA = a.visitas_semana > 0
      const comB = b.visitas_semana > 0
      if (comA !== comB) return comA ? -1 : 1
      if (comA) return (a.faturamento_por_visita ?? 0) - (b.faturamento_por_visita ?? 0)
    }
    return a.faturamento - b.faturamento
  })
  // Promotor com custo e sem nenhuma compra nas lojas vem primeiro; depois, do maior % para o menor.
  const peso = (p) => p.percentual_custo ?? Number.MAX_VALUE
  const piorPromotores = promotores.filter((p) => p.custo_periodo > 0).sort((a, b) => peso(b) - peso(a))

  return (
    <section className="bloco nao-compensa">
      <h2>Onde o custo não compensa</h2>
      <div className="duas-colunas">
        <div>
          <h3>{porVisita ? 'Lojas que compram pouco para as visitas que recebem' : 'Lojas que menos compram'}</h3>
          <div className="alternar alternar-pequeno nao-imprimir">
            <button className={porVisita ? 'ativo' : ''} onClick={() => setCriterio('visita')}>Por visita</button>
            <button className={!porVisita ? 'ativo' : ''} onClick={() => setCriterio('faturamento')}>Por faturamento</button>
          </div>
          <p className="dica">
            {porVisita
              ? 'Ordenadas pelo faturamento por visita (o que a loja comprou ÷ visitas do promotor no período).'
              : 'Ordenadas pelo que a loja comprou no período, da que menos comprou para a que mais comprou.'}
            {semVisitas > 0 && (
              <> {semVisitas} loja(s) sem visitas por semana informadas: preencha em Lojas por UF → Alterar… → Visitas por semana.</>
            )}
          </p>
          <Tabela
            chave="chave"
            linhas={(verTodasLojas ? lojasOrdenadas : lojasOrdenadas.slice(0, QUANTIDADE))
              .map((l) => ({ ...l, chave: `${l.codigo_promotor}-${l.cnpj}-${l.loja}` }))}
            porPagina={verTodasLojas ? 20 : QUANTIDADE}
            arquivo="lojas-que-compram-pouco"
            vazio="Nenhuma loja com esses filtros."
            classeLinha={(l) => (l.faturamento <= 0 ? 'linha-sem-compra' : '')}
            colunas={[
              { campo: 'loja', titulo: 'Loja', quebra: true,
                mostrar: (l) => <>{l.loja}<small className="dica sublinha">{l.cidade}{l.uf ? ` - ${l.uf}` : ''} · {l.promotor}</small></> },
              { campo: 'visitas_semana', titulo: 'Visitas/sem.', num: true, mostrar: (l) => l.visitas_semana ?? '—' },
              { campo: 'faturamento', titulo: 'Comprou', num: true, mostrar: (l) => formatarMoeda(l.faturamento) },
              { campo: 'faturamento_por_visita', titulo: 'Por visita', num: true, ordenar: (l) => l.faturamento_por_visita ?? Infinity,
                mostrar: (l) => (l.faturamento_por_visita == null ? '—' : <b>{formatarMoeda(l.faturamento_por_visita)}</b>) },
            ]}
          />
          {lojasOrdenadas.length > QUANTIDADE && (
            <button className="secundario" onClick={() => setVerTodasLojas((v) => !v)}>
              {verTodasLojas ? 'Mostrar só as 10 primeiras' : `Ver todas (${lojasOrdenadas.length})`}
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
