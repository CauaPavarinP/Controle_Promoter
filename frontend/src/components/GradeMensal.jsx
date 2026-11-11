// Faturamento mês a mês por loja atendida (clicável para ver as notas do ERP).
import { useEffect, useState } from 'react'
import { http } from '../api.js'
import { formatarCnpj, formatarData, formatarMes, formatarMoeda } from '../formato.js'
import { Modal, Tabela } from './ui.jsx'

const NOMES_ACAO = { soma: 'soma', subtrai: 'desconta', ignora: 'fora' }

// Detalhe das NFs/itens daquele PDV naquele mês.
export function DetalheNotas({ linha, mes, aoFechar }) {
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState('')
  useEffect(() => {
    http.get(`/api/faturamento/itens?${new URLSearchParams({ ...linha.detalhe, mes })}`).then(setDados).catch((e) => setErro(e.message))
  }, [linha, mes])
  return (
    <Modal titulo={`${linha.loja} — ${formatarMes(mes)}`} aoFechar={aoFechar} largo>
      {erro && <div className="erro-caixa">{erro}</div>}
      {!dados && !erro && <p>Carregando…</p>}
      {dados && (
        <>
          <p className="dica">
            CNPJ {formatarCnpj(linha.cnpj)}{linha.detalhe.cod_cli && ` · COD CLI ${linha.detalhe.cod_cli}`}. Total
            considerado: <b>{formatarMoeda(dados.total_considerado)}</b>.
          </p>
          {dados.limitado && <p className="aviso-texto">Mostrando os primeiros 5.000 itens.</p>}
          <Tabela
            chave="chave"
            linhas={dados.itens.map((i, n) => ({ ...i, chave: n }))}
            porPagina={50}
            arquivo={`notas-${linha.loja}-${mes}`}
            vazio="Nenhuma nota neste mês."
            classeLinha={(i) => (i.acao === 'ignora' ? 'linha-fora' : '')}
            colunas={[
              { campo: 'data', titulo: 'Data', mostrar: (i) => formatarData(i.data), exportar: (i) => formatarData(i.data) },
              { campo: 'num_nf', titulo: 'NF' },
              { campo: 'cod_cli', titulo: 'COD CLI' },
              { campo: 'tipo_nf', titulo: 'Tipo' },
              { campo: 'descricao_item', titulo: 'Item', quebra: true },
              { campo: 'qtde', titulo: 'Qtde', num: true },
              { campo: 'vlr_total', titulo: 'VLR TOTAL', num: true, mostrar: (i) => formatarMoeda(i.vlr_total) },
              { campo: 'acao', titulo: 'No faturamento', mostrar: (i) => NOMES_ACAO[i.acao] },
              { campo: 'valor_considerado', titulo: 'Considerado', num: true, mostrar: (i) => formatarMoeda(i.valor_considerado) },
            ]}
          />
        </>
      )}
    </Modal>
  )
}

export default function GradeMensal({ grade, acoes }) {
  const [detalhe, setDetalhe] = useState(null)

  const colunasMeses = grade.meses.map((m) => ({
    campo: m, titulo: formatarMes(m).replace('/', ' '), num: true,
    ordenar: (l) => l.meses?.[m] ?? 0,
    exportar: (l) => (l.meses ? l.meses[m] : l[m]),
    mostrar: (l) => {
      if (!l.meses) return <b>{formatarMoeda(l[m])}</b>
      const valor = l.meses[m]
      if (!valor || !l.cnpj) return valor ? formatarMoeda(valor) : '—'
      return (
        <button className="valor-clicavel" title="Ver as notas deste mês" onClick={() => setDetalhe({ linha: l, mes: m })}>
          {formatarMoeda(valor)}
        </button>
      )
    },
  }))

  return (
    <section className="bloco">
      <h2>Compras mês a mês ({grade.linhas.length})</h2>
      <p className="dica nao-imprimir">Clique num valor para ver as notas daquele mês.</p>
      <div className="grade-mensal">
        <Tabela
          chave="linha"
          linhas={grade.linhas}
          porPagina={100}
          arquivo="faturamento-pdv"
          vazio="Nenhuma loja com esses filtros."
          rodape={[{ agencia: 'Total', ...grade.totais }]}
          colunas={[
            { campo: 'agencia', titulo: 'Agência', quebra: true },
            { campo: 'promotor', titulo: 'Promotor', quebra: true },
            { campo: 'cnpj', titulo: 'CNPJ', mostrar: (l) => (l.meses ? formatarCnpj(l.cnpj) : ''), exportar: (l) => (l.cnpj ? formatarCnpj(l.cnpj) : '') },
            { campo: 'loja', titulo: 'PDV', quebra: true,
              mostrar: (l) => <>{l.loja}{l.compartilhado && <span className="etiqueta" title="Faturamento compartilhado com outra loja do mesmo CNPJ">compartilhado</span>}</> },
            { campo: 'cidade', titulo: 'Cidade', quebra: true },
            { campo: 'uf', titulo: 'UF' },
            ...colunasMeses,
            { campo: 'total', titulo: 'TOTAL', num: true, mostrar: (l) => <b>{formatarMoeda(l.total)}</b> },
            ...(acoes ? [{ campo: 'acoes', titulo: '', semOrdem: true, semExportar: true, mostrar: (l) => (l.meses ? acoes(l) : null) }] : []),
          ]}
        />
      </div>
      {detalhe && <DetalheNotas linha={detalhe.linha} mes={detalhe.mes} aoFechar={() => setDetalhe(null)} />}
    </section>
  )
}
