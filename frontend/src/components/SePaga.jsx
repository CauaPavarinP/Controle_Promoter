// "Vale a pena?": o lucro que a 101 tem com as lojas (faturamento do ERP × margem) cobre o que ela paga à agência
// por elas? Usado nas abas Promotores, Agências e Lojas por UF.
import { useEffect, useState } from 'react'
import { http } from '../api.js'
import { formatarMes, formatarMoeda, formatarPercentual } from '../formato.js'
import { Tabela } from './ui.jsx'

// Faixas de EXEMPLO (a definir com o Maurício): quanto do lucro das lojas vai para pagar o atendimento.
export const FAIXAS = { bom: 50, limite: 100 }

/** 'ok' | 'limite' | 'prejuizo' | 'sem-faturamento' | 'sem-erp' | null (sem margem). */
export function situacao(linha) {
  if (linha?.sem_erp) return 'sem-erp'
  if (!linha || linha.resultado == null) return null
  if (!linha.lucro_estimado) return linha.custo_periodo > 0 ? 'sem-faturamento' : null
  if (linha.percentual_do_lucro <= FAIXAS.bom) return 'ok'
  if (linha.percentual_do_lucro <= FAIXAS.limite) return 'limite'
  return 'prejuizo'
}

const TEXTOS = {
  ok: '🟢 Vale a pena', limite: '🟡 No limite', prejuizo: '🔴 Não vale a pena', 'sem-faturamento': '🔴 Sem compras',
  'sem-erp': '⚪ Falta o faturamento do ERP',
}

export function EtiquetaSituacao({ linha }) {
  const s = situacao(linha)
  if (!s) return <span className="dica">—</span>
  return <span className={`se-paga se-paga-${s}`}>{TEXTOS[s]}</span>
}

export const textoSituacao = (linha) => TEXTOS[situacao(linha)] || ''

// Colunas de dinheiro e do veredito, iguais nas tabelas de promotores, agências e lojas.
export const COLUNAS_SE_PAGA = [
  { campo: 'custo_periodo', titulo: 'Custo', num: true, formato: 'moeda', mostrar: (l) => formatarMoeda(l.custo_periodo) },
  { campo: 'faturamento', titulo: 'Compraram', num: true, formato: 'moeda',
    mostrar: (l) => (l.sem_erp ? '—' : formatarMoeda(l.faturamento)) },
  { campo: 'resultado', titulo: 'Sobra p/ 101', num: true, formato: 'moeda', ordenar: (l) => (l.sem_erp ? null : l.resultado) ?? -1e12,
    mostrar: (l) => (l.resultado == null || l.sem_erp ? '—'
      : <b className={l.resultado >= 0 ? 'texto-ok' : 'texto-critico'}>{formatarMoeda(l.resultado)}</b>) },
  { campo: 'se_paga', titulo: 'Vale a pena?', ordenar: (l) => l.percentual_do_lucro ?? 9999,
    exportar: textoSituacao, mostrar: (l) => <EtiquetaSituacao linha={l} /> },
]

function periodoPadrao(meses) {
  if (!meses.length) return { inicio: '', fim: '' }
  const ultimo = meses[meses.length - 1]
  return { inicio: meses.find((m) => m.startsWith(ultimo.slice(0, 4))), fim: ultimo }
}

/** Busca o painel do período (e filtros extras, ex.: { promotor }) e devolve { dados, periodo, setPeriodo, recarregar }. */
export function useSePaga(meses, extras = {}, periodoInicial = null) {
  const [periodo, setPeriodo] = useState(() => periodoInicial || periodoPadrao(meses))
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState('')
  const [versao, setVersao] = useState(0)
  const chaveExtras = JSON.stringify(extras)
  useEffect(() => {
    if (!periodo.inicio && meses.length) setPeriodo(periodoPadrao(meses))
  }, [meses, periodo.inicio])
  useEffect(() => {
    if (!periodo.inicio) return
    let cancelado = false
    setErro('')
    http.get(`/api/painel?${new URLSearchParams({ ...periodo, ...JSON.parse(chaveExtras) })}`)
      .then((d) => !cancelado && setDados(d))
      .catch((e) => !cancelado && setErro(e.message))
    return () => { cancelado = true }
  }, [periodo, versao, chaveExtras])
  return { dados, erro, periodo, setPeriodo, recarregar: () => setVersao((v) => v + 1) }
}

/** Quadro do topo: período, margem da 101 e o resultado geral. */
export function QuadroSePaga({ titulo, meses, periodo, setPeriodo, dados, podeEditar, aoMudarMargem, contar = 'promotores' }) {
  const margem = dados?.regras?.margem_percentual
  const [editando, setEditando] = useState(null)
  const [erro, setErro] = useState('')
  const resumo = dados?.resumo
  const contagem = { ok: 0, limite: 0, prejuizo: 0, 'sem-faturamento': 0, 'sem-erp': 0 }
  for (const p of dados?.[contar] || []) {
    const s = situacao(p)
    if (s) contagem[s] += 1
  }

  async function salvarMargem() {
    setErro('')
    try {
      const { regras } = await http.get('/api/regras')
      await http.put('/api/regras', { ...regras, margem_percentual: editando === '' ? null : editando })
      setEditando(null)
      aoMudarMargem()
    } catch (e) {
      setErro(e.message)
    }
  }

  return (
    <section className="bloco se-paga-quadro">
      <div className="bloco-cabecalho">
        <h2>{titulo}</h2>
        <div className="bloco-ferramentas">
          <label className="filtro">De
            <select value={periodo.inicio} onChange={(e) => setPeriodo({ ...periodo, inicio: e.target.value })}>
              {meses.map((m) => <option key={m} value={m}>{formatarMes(m)}</option>)}
            </select>
          </label>
          <label className="filtro">Até
            <select value={periodo.fim} onChange={(e) => setPeriodo({ ...periodo, fim: e.target.value })}>
              {meses.map((m) => <option key={m} value={m}>{formatarMes(m)}</option>)}
            </select>
          </label>
        </div>
      </div>

      <div className="se-paga-margem">
        <b>Margem da 101 sobre as vendas:</b>{' '}
        {editando !== null ? (
          <>
            <input className="margem-campo" inputMode="decimal" value={editando} autoFocus aria-label="Margem da 101 (%)"
              onChange={(e) => setEditando(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && salvarMargem()} /> %
            <button onClick={salvarMargem}>Salvar</button>
            <button className="secundario" onClick={() => setEditando(null)}>Cancelar</button>
          </>
        ) : (
          <>
            {margem != null ? <b className="margem-valor">{formatarPercentual(margem)}</b> : <span className="texto-alerta">não informada</span>}
            {podeEditar && <button className="secundario" onClick={() => setEditando(margem != null ? String(margem).replace('.', ',') : '')}>Alterar</button>}
          </>
        )}
        {erro && <p className="erro">{erro}</p>}
        <p className="dica">
          Lucro estimado = o que as lojas compraram da 101 (ERP) × margem. Vale a pena quando esse lucro cobre o que a
          101 paga pelo atendimento (arquivos das agências). Quando houver o custo de cada produto, o lucro passa a ser
          calculado produto por produto.
        </p>
      </div>

      {(resumo?.avisos || []).map((aviso) => <p key={aviso} className="nota">⚠ {aviso}</p>)}
      {margem == null && (
        <div className="aviso">Informe a margem para ver quem vale a pena. Sem ela, só dá para comparar o custo com as compras.</div>
      )}

      {resumo && (
        <div className="cards cards-4">
          <div className="card"><span>Lojas compraram</span><strong>{formatarMoeda(resumo.faturamento)}</strong></div>
          <div className="card"><span>Lucro estimado da 101</span><strong>{margem != null ? formatarMoeda(resumo.lucro_estimado) : '—'}</strong></div>
          <div className="card"><span>Pago às agências</span><strong>{formatarMoeda(resumo.custo)}</strong>
            <small>{formatarPercentual(resumo.percentual_custo)} do que as lojas compraram</small></div>
          <div className={`card ${margem == null ? '' : resumo.resultado >= 0 ? 'pct-ok' : 'pct-critico'}`}>
            <span>Sobra para a 101</span><strong>{margem != null ? formatarMoeda(resumo.resultado) : '—'}</strong>
            {margem != null && resumo.percentual_do_lucro != null && (
              <small>{formatarPercentual(resumo.percentual_do_lucro)} do lucro vai para o atendimento</small>
            )}
          </div>
        </div>
      )}
      {resumo && margem != null && (
        <p className="se-paga-legenda">
          <span className="se-paga se-paga-ok">🟢 Vale a pena: {contagem.ok}</span>{' '}
          <span className="se-paga se-paga-limite">🟡 No limite: {contagem.limite}</span>{' '}
          <span className="se-paga se-paga-prejuizo">🔴 Não vale a pena: {contagem.prejuizo + contagem['sem-faturamento']}</span>
          <span className="dica">
            {' '}· Faixas de exemplo (a definir): até {FAIXAS.bom}% do lucro = vale a pena; de {FAIXAS.bom}% a {FAIXAS.limite}% =
            no limite; acima de {FAIXAS.limite}% = a 101 paga mais do que lucra com essas lojas.
          </span>
        </p>
      )}
    </section>
  )
}

/** Cartões do resultado de um promotor (ou agência) e a tabela das lojas dele. */
export function FichaSePaga({ linha, lojas, periodo, carregado, temFaturamento, quem = 'ele' }) {
  if (!temFaturamento) {
    return (
      <div className="aviso">
        Ainda não há faturamento importado. Importe o arquivo do ERP na aba <b>Faturamento</b> para ver quanto as lojas
        compraram e se vale a pena.
      </div>
    )
  }
  if (!carregado) return <p className="dica">Calculando…</p>
  if (!linha) {
    return (
      <div className="aviso">
        Sem atendimento de {formatarMes(periodo.inicio)} a {formatarMes(periodo.fim)} nos arquivos das agências.
      </div>
    )
  }
  const temMargem = linha.resultado != null
  return (
    <>
      <p className="dica">Período: {formatarMes(periodo.inicio)} a {formatarMes(periodo.fim)}</p>
      <div className="cards cards-4">
        <div className="card"><span>Lojas compraram</span><strong>{formatarMoeda(linha.faturamento)}</strong></div>
        <div className="card"><span>Lucro estimado da 101</span><strong>{temMargem ? formatarMoeda(linha.lucro_estimado) : '—'}</strong></div>
        <div className="card"><span>Custo no período</span><strong>{formatarMoeda(linha.custo_periodo)}</strong>
          <small>{formatarPercentual(linha.percentual_custo)} do que as lojas compraram</small></div>
        <div className={`card ${!temMargem ? '' : linha.resultado >= 0 ? 'pct-ok' : 'pct-critico'}`}>
          <span>Sobra para a 101</span><strong>{temMargem ? formatarMoeda(linha.resultado) : '—'}</strong>
          {!temMargem && <small>Informe a margem da 101 no topo da aba.</small>}
          {temMargem && (
            <small>
              <EtiquetaSituacao linha={linha} />
              {linha.percentual_do_lucro != null && ` · ${formatarPercentual(linha.percentual_do_lucro)} do lucro vai para ${quem}`}
            </small>
          )}
        </div>
      </div>
      <Tabela
        chave="chave"
        linhas={lojas}
        porPagina={10}
        arquivo={`lojas-${linha.nome || linha.chave}`}
        vazio="Nenhuma loja no período."
        colunas={[
          { campo: 'loja', titulo: 'Loja', quebra: true,
            mostrar: (l) => <>{l.loja}{l.compartilhado && <span className="etiqueta" title="O CNPJ é de mais de uma loja: o faturamento foi dividido entre elas">CNPJ compartilhado</span>}</> },
          { campo: 'cidade', titulo: 'Cidade', mostrar: (l) => `${l.cidade}${l.uf ? ` - ${l.uf}` : ''}` },
          { campo: 'dias', titulo: 'Dias', quebra: true },
          { campo: 'visitas', titulo: 'Visitas', num: true, formato: 'inteiro' },
          ...COLUNAS_SE_PAGA,
        ]}
      />
    </>
  )
}
