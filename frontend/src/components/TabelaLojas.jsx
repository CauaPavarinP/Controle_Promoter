import { useState } from 'react'
import { classePercentual, formatarMoeda, formatarPercentual } from '../formato.js'
import { Tabela } from './ui.jsx'

// Detalhe por loja: o ponto principal do pedido (achar as lojas que não compensam).
export default function TabelaLojas({ lojas, regras }) {
  const [busca, setBusca] = useState('')
  const [soSemCompra, setSoSemCompra] = useState(false)

  const termo = busca.trim().toLowerCase()
  const visiveis = lojas.filter(
    (l) =>
      (!soSemCompra || l.faturamento <= 0) &&
      (!termo || `${l.loja} ${l.cidade} ${l.promotor}`.toLowerCase().includes(termo)),
  )

  const etiquetas = (l) => (
    <>
      {l.separado_por_cod_cli && (
        <span className="etiqueta etiqueta-ok" title="Outras lojas usam o mesmo CNPJ; o faturamento foi separado pelo COD CLI de cada uma">
          separado pelo COD CLI
        </span>
      )}
      {l.compartilhado && (
        <span className="etiqueta" title="O ERP fatura por CNPJ: o valor é do CNPJ inteiro e conta uma vez só nos totais">
          faturamento compartilhado com outra loja
        </span>
      )}
    </>
  )

  return (
    <section className="bloco">
      <div className="bloco-cabecalho">
        <h2>Lojas ({visiveis.length})</h2>
        <div className="bloco-ferramentas nao-imprimir">
          <input placeholder="Buscar loja, cidade ou promotor" value={busca} onChange={(e) => setBusca(e.target.value)} />
          <label className="marcar">
            <input type="checkbox" checked={soSemCompra} onChange={(e) => setSoSemCompra(e.target.checked)} />
            Só lojas sem compra
          </label>
        </div>
      </div>
      <div className="legenda">
        <span><i className="cor-sem-compra" /> Sem faturamento no período e com visitas</span>
        {regras.limite_percentual != null && <span><i className="cor-critico" /> Custo acima de {regras.limite_percentual}% do faturamento</span>}
      </div>
      <p className="dica">
        Custo da loja = parte do custo do promotor
        ({regras.rateio_custo === 'visitas' ? 'proporcional às visitas por semana' : 'em partes iguais por loja'}).
      </p>
      <Tabela
        chave="chave"
        linhas={visiveis.map((l) => ({ ...l, chave: `${l.codigo_promotor}-${l.cnpj}-${l.loja}` }))}
        arquivo="lojas-custo-x-faturamento"
        classeLinha={(l) => (l.faturamento <= 0 && l.visitas_semana > 0 ? 'linha-sem-compra' : '')}
        vazio="Nenhuma loja com esses filtros."
        colunas={[
          { campo: 'loja', titulo: 'Loja', quebra: true, mostrar: (l) => <>{l.loja}{etiquetas(l)}</> },
          { campo: 'cidade', titulo: 'Cidade', quebra: true, mostrar: (l) => `${l.cidade}${l.uf ? ` - ${l.uf}` : ''}`,
            exportar: (l) => `${l.cidade}${l.uf ? ` - ${l.uf}` : ''}` },
          { campo: 'promotor', titulo: 'Promotor', quebra: true },
          { campo: 'visitas_semana', titulo: 'Visitas/ semana', num: true, mostrar: (l) => l.visitas_semana ?? '—' },
          { campo: 'faturamento', titulo: 'Faturamento', num: true, mostrar: (l) => formatarMoeda(l.faturamento) },
          { campo: 'custo_periodo', titulo: 'Custo do promotor atribuído', num: true, mostrar: (l) => formatarMoeda(l.custo_periodo) },
          { campo: 'percentual_custo', titulo: '% custo', num: true, ordenar: (l) => l.percentual_custo ?? -1,
            mostrar: (l) => (
              <span className={classePercentual(l.percentual_custo, regras)}
                title={l.compartilhado ? 'Não calculado: o faturamento mostrado é do CNPJ inteiro' : undefined}>
                {formatarPercentual(l.percentual_custo)}
              </span>
            ) },
          { campo: 'faturamento_por_visita', titulo: 'Faturamento por visita', num: true, ordenar: (l) => l.faturamento_por_visita ?? -1,
            mostrar: (l) => formatarMoeda(l.faturamento_por_visita) },
        ]}
      />
    </section>
  )
}
