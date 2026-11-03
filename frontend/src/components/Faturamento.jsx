// Aba Faturamento: o que veio do ERP (aba FATURAMENTO da planilha), por UF e por cliente, mês a mês.
import { useEffect, useState } from 'react'
import { http } from '../api.js'
import { formatarCnpj, formatarMes, formatarMoeda } from '../formato.js'
import { DetalheNotas } from './GradeMensal.jsx'
import { Envio, Historico, PreviaFaturamento } from './Importar.jsx'
import { definirSubtituloExportacao, Tabela } from './ui.jsx'

function Importacao({ aoImportar }) {
  const [previa, setPrevia] = useState(null)
  const [concluido, setConcluido] = useState(null)
  const [versao, setVersao] = useState(0)

  async function enviar(arquivo) {
    setConcluido(null)
    setPrevia(await http.enviarArquivo('/api/importacoes/faturamento/previa', arquivo))
  }

  return (
    <>
      <section className="importar">
        <div className="importar-cartao destaque">
          <Envio
            titulo="Importar faturamento do ERP"
            descricao={'Arquivo exportado do ERP no layout da aba FATURAMENTO (uma linha por item de nota), ou a própria ' +
              'planilha "ROTEIROS X FATURAMENTOS". Você confere o resumo antes de gravar; mês que já existe só é ' +
              'substituído se você confirmar.'}
            rotulo="Ler arquivo"
            aoEnviar={enviar}
          />
        </div>
      </section>
      {previa && (
        <section className="bloco">
          <PreviaFaturamento
            previa={previa}
            aoCancelar={() => setPrevia(null)}
            aoConcluir={(resultado) => { setPrevia(null); setConcluido(resultado); setVersao((v) => v + 1); aoImportar() }}
          />
        </section>
      )}
      {concluido && (
        <div className="sucesso">
          Faturamento gravado: {concluido.linhas_importadas} linhas de {concluido.meses.map(formatarMes).join(', ')}.
          {concluido.meses_substituidos.length > 0 && <> Meses substituídos: {concluido.meses_substituidos.map(formatarMes).join(', ')}.</>}
          {concluido.aviso && <p className="aviso-texto">⚠ {concluido.aviso}</p>}
        </div>
      )}
      <details className="bloco">
        <summary>Histórico de importações do faturamento</summary>
        <Historico versao={versao} aoDesfazer={() => { setVersao((v) => v + 1); aoImportar() }} tipos={['faturamento']} />
      </details>
    </>
  )
}

function colunasDosMeses(meses, aoClicar) {
  return meses.map((m) => ({
    campo: m, titulo: formatarMes(m).replace('/', ' '), num: true,
    ordenar: (l) => l.meses?.[m] ?? 0,
    exportar: (l) => (l.meses ? l.meses[m] : l[m]),
    mostrar: (l) => {
      const valor = l.meses ? l.meses[m] : l[m]
      if (!l.meses) return <b>{formatarMoeda(valor)}</b>
      if (!valor) return '—'
      if (!aoClicar) return formatarMoeda(valor)
      return (
        <button className="valor-clicavel" title="Ver as notas deste mês" onClick={() => aoClicar(l, m)}>
          {formatarMoeda(valor)}
        </button>
      )
    },
  }))
}

export default function Faturamento({ admin, meses, aoImportar }) {
  const ultimo = meses[meses.length - 1] || ''
  const [periodo, setPeriodo] = useState({ inicio: '', fim: '' })
  const [dados, setDados] = useState(null)
  const [carregando, setCarregando] = useState(false)
  const [erro, setErro] = useState('')
  const [busca, setBusca] = useState('')
  const [uf, setUf] = useState('')
  const [soForaDoRoteiro, setSoForaDoRoteiro] = useState(false)
  const [detalhe, setDetalhe] = useState(null)

  // Período padrão: o ano do último mês importado.
  useEffect(() => {
    if (ultimo && !meses.includes(periodo.inicio)) {
      setPeriodo({ inicio: meses.find((m) => m.startsWith(ultimo.slice(0, 4))), fim: ultimo })
    }
  }, [meses, ultimo, periodo.inicio])

  useEffect(() => {
    if (!periodo.inicio) return
    definirSubtituloExportacao(`Período: ${formatarMes(periodo.inicio)} a ${formatarMes(periodo.fim)}`)
    let cancelado = false
    setErro('')
    setCarregando(true)
    http.get(`/api/faturamento?${new URLSearchParams(periodo)}`)
      .then((d) => !cancelado && setDados(d))
      .catch((e) => !cancelado && setErro(e.message))
      .finally(() => !cancelado && setCarregando(false))
    return () => { cancelado = true }
  }, [periodo])

  const termo = busca.trim().toLowerCase()
  const clientes = (dados?.clientes || []).filter((c) =>
    (!uf || c.uf === uf) && (!soForaDoRoteiro || !c.no_roteiro) &&
    (!termo || `${c.razao_social} ${c.cidade} ${c.cnpj}`.toLowerCase().includes(termo)))
  const abrirNotas = (l, m) => setDetalhe({ linha: { loja: l.razao_social, cnpj: l.cnpj, detalhe: { cnpj: l.cnpj, cod_cli: '' } }, mes: m })

  return (
    <>
      {admin && <Importacao aoImportar={aoImportar} />}

      {!meses.length && <div className="aviso">Ainda não há faturamento importado.</div>}
      {erro && <div className="erro-caixa">{erro}</div>}
      {carregando && <p className="carregando">Carregando o faturamento… com a planilha inteira isso pode levar alguns segundos.</p>}

      {meses.length > 0 && (
        <section className="filtros">
          <label className="filtro">
            De
            <select value={periodo.inicio} onChange={(e) => setPeriodo({ ...periodo, inicio: e.target.value })}>
              {meses.map((m) => <option key={m} value={m}>{formatarMes(m)}</option>)}
            </select>
          </label>
          <label className="filtro">
            Até
            <select value={periodo.fim} onChange={(e) => setPeriodo({ ...periodo, fim: e.target.value })}>
              {meses.map((m) => <option key={m} value={m}>{formatarMes(m)}</option>)}
            </select>
          </label>
        </section>
      )}

      {dados && (
        <div className={carregando ? 'atualizando' : ''}>
          <section className="bloco">
            <h2>Faturamento por UF</h2>
            <p className="dica">Tudo o que o ERP faturou no período, inclusive clientes que nenhum promotor atende.</p>
            <Tabela
              chave="uf"
              linhas={dados.por_uf}
              porPagina={50}
              arquivo="faturamento-por-uf"
              vazio="Nenhum faturamento no período."
              rodape={[{ uf: 'Total', ...dados.totais }]}
              aoClicar={(l) => setUf(l.uf === uf ? '' : l.uf)}
              colunas={[
                { campo: 'uf', titulo: 'UF', mostrar: (l) => (l.meses ? l.uf : <b>{l.uf}</b>) },
                { campo: 'clientes', titulo: 'Clientes', num: true },
                ...colunasDosMeses(dados.meses),
                { campo: 'total', titulo: 'TOTAL', num: true, mostrar: (l) => <b>{formatarMoeda(l.total)}</b> },
              ]}
            />
          </section>

          <section className="bloco">
            <div className="bloco-cabecalho">
              <h2>Clientes ({clientes.length})</h2>
              <div className="bloco-ferramentas nao-imprimir">
                <input placeholder="Buscar cliente, cidade ou CNPJ" value={busca} onChange={(e) => setBusca(e.target.value)} />
                <select value={uf} onChange={(e) => setUf(e.target.value)}>
                  <option value="">Todas as UFs</option>
                  {dados.por_uf.map((u) => <option key={u.uf} value={u.uf}>{u.uf}</option>)}
                </select>
                <label className="marcar">
                  <input type="checkbox" checked={soForaDoRoteiro} onChange={(e) => setSoForaDoRoteiro(e.target.checked)} />
                  Só quem não está no roteiro
                </label>
              </div>
            </div>
            <p className="dica nao-imprimir">Clique num valor para ver as notas daquele mês.</p>
            <div className="grade-mensal">
              <Tabela
                chave="cnpj"
                linhas={clientes}
                porPagina={100}
                arquivo="faturamento-por-cliente"
                vazio="Nenhum cliente com esses filtros."
                colunas={[
                  { campo: 'razao_social', titulo: 'Cliente', quebra: true,
                    mostrar: (c) => <>{c.razao_social || '—'}{!c.no_roteiro && <span className="etiqueta" title="Nenhum promotor atende este CNPJ">fora do roteiro</span>}</> },
                  { campo: 'cnpj', titulo: 'CNPJ', mostrar: (c) => formatarCnpj(c.cnpj), exportar: (c) => formatarCnpj(c.cnpj) },
                  { campo: 'cidade', titulo: 'Cidade', quebra: true },
                  { campo: 'uf', titulo: 'UF' },
                  ...colunasDosMeses(dados.meses, abrirNotas),
                  { campo: 'total', titulo: 'TOTAL', num: true, mostrar: (c) => <b>{formatarMoeda(c.total)}</b> },
                ]}
              />
            </div>
          </section>
        </div>
      )}
      {detalhe && <DetalheNotas linha={detalhe.linha} mes={detalhe.mes} aoFechar={() => setDetalhe(null)} />}
    </>
  )
}
