// Faturamento mês a mês por loja (substitui as abas SC, SP, PR, MG, RS da planilha).
import { useEffect, useState } from 'react'
import { http } from '../api.js'
import { formatarCnpj, formatarData, formatarMes, formatarMoeda } from '../formato.js'
import { Modal, Tabela } from './ui.jsx'

const NOMES_ACAO = { soma: 'soma', subtrai: 'desconta', ignora: 'fora' }

function DetalheNotas({ linha, mes, aoFechar }) {
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
            {linha.detalhe.rede ? 'Notas de toda a rede (mesma raiz de CNPJ). ' : `CNPJ ${formatarCnpj(linha.cnpj)}. `}
            {linha.detalhe.cod_cli && `Só o COD CLI ${linha.detalhe.cod_cli} (faturamento separado por loja). `}
            {linha.compartilhado && 'O CNPJ é compartilhado com outra loja: estas notas valem para todas. '}
            {linha.detalhe.dividido_por > 1 && `Na grade, o valor está dividido por ${linha.detalhe.dividido_por} lojas da rede. `}
            Total considerado pelas regras: <b>{formatarMoeda(dados.total_considerado)}</b>.
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
              { campo: 'total_venda', titulo: 'TOTAL VENDA', num: true, mostrar: (i) => formatarMoeda(i.total_venda) },
              { campo: 'acao', titulo: 'No faturamento', mostrar: (i) => NOMES_ACAO[i.acao] },
              { campo: 'valor_considerado', titulo: 'Considerado', num: true, mostrar: (i) => formatarMoeda(i.valor_considerado) },
            ]}
          />
        </>
      )}
    </Modal>
  )
}

export default function GradeMensal({ grade }) {
  const [busca, setBusca] = useState('')
  const [detalhe, setDetalhe] = useState(null)
  const termo = busca.trim().toLowerCase()
  const linhas = grade.linhas.filter((l) => !termo || `${l.loja} ${l.promotor} ${l.cidade} ${l.supervisor}`.toLowerCase().includes(termo))
  const repetido = grade.soma_das_linhas.total - grade.totais.total

  const colunasMeses = grade.meses.map((m) => ({
    campo: m, titulo: formatarMes(m).replace('/', ' '), num: true,
    ordenar: (l) => l.meses?.[m] ?? 0,
    exportar: (l) => (l.meses ? l.meses[m] : l[m]),
    mostrar: (l) => {
      if (!l.meses) return <b>{formatarMoeda(l[m])}</b>
      const valor = l.meses[m]
      if (!valor || !l.cnpj) return <span className="texto-suave">{valor ? formatarMoeda(valor) : '—'}</span>
      return (
        <button className="valor-clicavel" title="Ver as notas deste mês" onClick={() => setDetalhe({ linha: l, mes: m })}>
          {formatarMoeda(valor)}
        </button>
      )
    },
  }))

  return (
    <section className="bloco">
      <div className="bloco-cabecalho">
        <h2>Faturamento mês a mês ({linhas.length} lojas)</h2>
        <input className="nao-imprimir" placeholder="Buscar loja, promotor, cidade" value={busca} onChange={(e) => setBusca(e.target.value)} />
      </div>
      <p className="dica">
        Uma linha por loja × promotor, como as abas SC, SP, PR… da planilha. Clique num valor para ver as notas. A linha
        <b> Total</b> conta cada CNPJ uma vez por mês.
        {repetido > 0.005 && (
          <> A planilha somaria {formatarMoeda(grade.soma_das_linhas.total)} (linha "Soma das linhas"), porque repete o valor
            de lojas que dividem o mesmo CNPJ: {formatarMoeda(repetido)} a mais.</>
        )}
      </p>
      <div className="grade-mensal">
      <Tabela
        chave="linha"
        linhas={linhas}
        porPagina={100}
        arquivo="faturamento-mes-a-mes"
        vazio="Nenhuma loja com esses filtros."
        rodape={[
          { loja: 'Total (sem repetir CNPJ)', supervisor: 'Total (sem repetir CNPJ)', ...grade.totais },
          ...(repetido > 0.005 ? [{ loja: 'Soma das linhas (como a planilha)', supervisor: 'Soma das linhas (como a planilha)',
            ...grade.soma_das_linhas }] : []),
        ]}
        colunas={[
          { campo: 'loja', titulo: 'PDV', quebra: true, fixa: true,
            mostrar: (l) => (l.meses
              ? <>{l.loja}{l.compartilhado && <span className="etiqueta" title="CNPJ compartilhado com outra loja: o valor é do CNPJ inteiro">compartilhado</span>}</>
              : <b>{l.supervisor}</b>),
            exportar: (l) => l.loja ?? l.supervisor },
          { campo: 'promotor', titulo: 'Promotor', quebra: true },
          { campo: 'supervisor', titulo: 'Supervisor', quebra: true, mostrar: (l) => (l.meses ? l.supervisor : '') },
          { campo: 'cnpj', titulo: 'CNPJ', mostrar: (l) => (l.meses ? formatarCnpj(l.cnpj) : ''), exportar: (l) => (l.cnpj ? formatarCnpj(l.cnpj) : '') },
          { campo: 'cidade', titulo: 'Cidade', quebra: true, mostrar: (l) => (l.meses ? `${l.cidade}${l.uf ? ` - ${l.uf}` : ''}` : '') },
          ...colunasMeses,
          { campo: 'total', titulo: 'TOTAL', num: true, mostrar: (l) => <b>{formatarMoeda(l.total)}</b> },
        ]}
      />
      </div>
      {detalhe && <DetalheNotas linha={detalhe.linha} mes={detalhe.mes} aoFechar={() => setDetalhe(null)} />}
    </section>
  )
}
