// PROTÓTIPO — "O promotor está se pagando?"
// Lucro da 101 com as lojas do promotor (faturamento × margem) comparado com o custo dele no período.
// Enquanto não houver o custo de cada produto, o lucro é estimado por uma margem única, editável.
import { useEffect, useState } from 'react'
import { http } from '../../api.js'
import { formatarMes, formatarMoeda, formatarPercentual } from '../../formato.js'
import { Tabela } from '../ui.jsx'

// Faixas de EXEMPLO (a definir com o Maurício): quanto do lucro das lojas vai para pagar o promotor.
export const FAIXAS = { bom: 50, limite: 100 }

/** 'ok' | 'limite' | 'prejuizo' | 'sem-faturamento' | null (sem margem). */
export function situacao(linha) {
  if (!linha || linha.resultado == null) return null
  if (!linha.lucro_estimado) return linha.custo_periodo > 0 ? 'sem-faturamento' : null
  if (linha.percentual_do_lucro <= FAIXAS.bom) return 'ok'
  if (linha.percentual_do_lucro <= FAIXAS.limite) return 'limite'
  return 'prejuizo'
}

const TEXTOS = {
  ok: '🟢 Se paga', limite: '🟡 No limite', prejuizo: '🔴 Não se paga', 'sem-faturamento': '🔴 Sem faturamento',
}

export function EtiquetaSituacao({ linha }) {
  const s = situacao(linha)
  if (!s) return <span className="dica">—</span>
  return <span className={`se-paga se-paga-${s}`}>{TEXTOS[s]}</span>
}

export const textoSituacao = (linha) => TEXTOS[situacao(linha)] || ''

function periodoPadrao(meses) {
  if (!meses.length) return { inicio: '', fim: '' }
  const ultimo = meses[meses.length - 1]
  return { inicio: meses.find((m) => m.startsWith(ultimo.slice(0, 4))), fim: ultimo }
}

/** Busca o painel do período e devolve { dados, periodo, setPeriodo, recarregar }. */
export function useSePaga(meses) {
  const [periodo, setPeriodo] = useState(() => periodoPadrao(meses))
  const [dados, setDados] = useState(null)
  const [versao, setVersao] = useState(0)
  useEffect(() => {
    if (!periodo.inicio && meses.length) setPeriodo(periodoPadrao(meses))
  }, [meses, periodo.inicio])
  useEffect(() => {
    if (!periodo.inicio) return
    let cancelado = false
    http.get(`/api/painel?${new URLSearchParams(periodo)}`).then((d) => !cancelado && setDados(d))
    return () => { cancelado = true }
  }, [periodo, versao])
  return { dados, periodo, setPeriodo, recarregar: () => setVersao((v) => v + 1) }
}

/** Quadro do topo: período, margem da 101 e o resultado geral. */
export function QuadroSePaga({ meses, periodo, setPeriodo, dados, podeEditar, aoMudarMargem }) {
  const margem = dados?.regras?.margem_percentual
  const [editando, setEditando] = useState(null)
  const [erro, setErro] = useState('')
  const resumo = dados?.resumo
  const contagem = { ok: 0, limite: 0, prejuizo: 0, 'sem-faturamento': 0 }
  for (const p of dados?.promotores || []) {
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
        <h2>O promotor está se pagando? <span className="etiqueta">protótipo</span></h2>
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
            <input className="margem-campo" inputMode="decimal" value={editando} autoFocus
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
          Lucro estimado = o que as lojas do promotor compraram da 101 × margem. Quando houver o custo de cada produto
          (pergunta 2 para o Maurício), o lucro passa a ser calculado produto por produto e este campo deixa de ser
          necessário.
        </p>
      </div>

      {margem == null && (
        <div className="aviso">Informe a margem para ver quem se paga. Sem ela, só dá para comparar o custo com o faturamento.</div>
      )}

      {resumo && margem != null && (
        <div className="cards cards-4">
          <div className="card"><span>Lojas compraram</span><strong>{formatarMoeda(resumo.faturamento)}</strong></div>
          <div className="card"><span>Lucro estimado da 101</span><strong>{formatarMoeda(resumo.lucro_estimado)}</strong></div>
          <div className="card"><span>Custo dos promotores</span><strong>{formatarMoeda(resumo.custo)}</strong></div>
          <div className={`card ${resumo.resultado >= 0 ? 'pct-ok' : 'pct-critico'}`}>
            <span>Sobra para a 101</span><strong>{formatarMoeda(resumo.resultado)}</strong>
            <small>{formatarPercentual(resumo.percentual_do_lucro)} do lucro vai para os promotores</small>
          </div>
        </div>
      )}
      {resumo && margem != null && (
        <p className="se-paga-legenda">
          <span className="se-paga se-paga-ok">🟢 Se paga: {contagem.ok}</span>{' '}
          <span className="se-paga se-paga-limite">🟡 No limite: {contagem.limite}</span>{' '}
          <span className="se-paga se-paga-prejuizo">🔴 Não se paga: {contagem.prejuizo + contagem['sem-faturamento']}</span>
          <span className="dica">
            {' '}· Faixas de exemplo (a definir): até {FAIXAS.bom}% do lucro = se paga; de {FAIXAS.bom}% a {FAIXAS.limite}% = no
            limite; acima de {FAIXAS.limite}% = a 101 paga mais do que lucra com as lojas dele.
          </span>
        </p>
      )}
    </section>
  )
}

/** Ficha do promotor: o resultado dele e o de cada loja dele. */
export function FichaSePaga({ linha, lojas, periodo }) {
  if (!linha) return <p className="dica">Sem lojas ou sem custo no período escolhido.</p>
  const temMargem = linha.resultado != null
  return (
    <>
      <p className="dica">Período: {formatarMes(periodo.inicio)} a {formatarMes(periodo.fim)}</p>
      <div className="cards cards-4">
        <div className="card"><span>Lojas dele compraram</span><strong>{formatarMoeda(linha.faturamento)}</strong></div>
        <div className="card"><span>Lucro estimado da 101</span><strong>{temMargem ? formatarMoeda(linha.lucro_estimado) : '—'}</strong></div>
        <div className="card"><span>Custo dele no período</span><strong>{formatarMoeda(linha.custo_periodo)}</strong></div>
        <div className={`card ${!temMargem ? '' : linha.resultado >= 0 ? 'pct-ok' : 'pct-critico'}`}>
          <span>Sobra para a 101</span><strong>{temMargem ? formatarMoeda(linha.resultado) : "—"}</strong>
          <small><EtiquetaSituacao linha={linha} />{linha.percentual_do_lucro != null && ` · ${formatarPercentual(linha.percentual_do_lucro)} do lucro vai para ele`}</small>
        </div>
      </div>
      <Tabela
        linhas={lojas}
        porPagina={10}
        arquivo={`lojas-${linha.codigo}`}
        vazio="Nenhuma loja no período."
        colunas={[
          { campo: 'loja', titulo: 'Loja', quebra: true },
          { campo: 'cidade', titulo: 'Cidade', mostrar: (l) => `${l.cidade}${l.uf ? ` - ${l.uf}` : ''}` },
          { campo: 'faturamento', titulo: 'Comprou', num: true, mostrar: (l) => formatarMoeda(l.faturamento) },
          { campo: 'lucro_estimado', titulo: 'Lucro da 101', num: true, mostrar: (l) => (l.lucro_estimado == null ? '—' : formatarMoeda(l.lucro_estimado)) },
          { campo: 'custo_periodo', titulo: 'Custo do promotor nesta loja', num: true, mostrar: (l) => formatarMoeda(l.custo_periodo) },
          { campo: 'resultado', titulo: 'Sobra', num: true,
            mostrar: (l) => (l.resultado == null ? '—' : <b className={l.resultado >= 0 ? 'texto-ok' : 'texto-critico'}>{formatarMoeda(l.resultado)}</b>) },
          { campo: 'situacao', titulo: 'Situação', mostrar: (l) => <EtiquetaSituacao linha={l} />, exportar: textoSituacao,
            ordenar: (l) => l.percentual_do_lucro ?? 9999 },
        ]}
      />
      <p className="dica">
        O custo do promotor é dividido em partes iguais entre as lojas dele (a planilha não tem visitas por semana). Loja
        com CNPJ compartilhado entra com a parte dela do faturamento.
      </p>
    </>
  )
}
