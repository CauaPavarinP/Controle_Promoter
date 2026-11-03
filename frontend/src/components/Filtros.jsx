import { useEffect, useState } from 'react'
import { formatarMes } from '../formato.js'

function Seletor({ rotulo, valor, aoMudar, opcoes, todos = 'Todos' }) {
  return (
    <label className="filtro">
      {rotulo}
      <select value={valor} onChange={(e) => aoMudar(e.target.value)}>
        {todos !== null && <option value="">{todos}</option>}
        {opcoes.map((o) => (
          <option key={o.valor} value={o.valor}>{o.texto}</option>
        ))}
      </select>
    </label>
  )
}

/** Campo de PDV com sugestões: só filtra quando o nome bate com um PDV da lista (ou fica vazio). */
function FiltroPdv({ pdvs, valor, aoMudar }) {
  const [texto, setTexto] = useState(valor)
  useEffect(() => setTexto(valor), [valor])
  function mudar(novo) {
    setTexto(novo)
    if (!novo || pdvs.some((p) => p.nome === novo)) aoMudar(novo)
  }
  return (
    <label className="filtro filtro-pdv">
      PDV
      <input list="lista-pdvs" value={texto} placeholder="Todos" onChange={(e) => mudar(e.target.value)} />
      <datalist id="lista-pdvs">
        {pdvs.map((p) => <option key={p.nome} value={p.nome}>{`${p.cidade}${p.uf ? ` - ${p.uf}` : ''}`}</option>)}
      </datalist>
    </label>
  )
}

const indice = (anoMes) => Number(anoMes.slice(0, 4)) * 12 + Number(anoMes.slice(5, 7)) - 1
const rotulo = (i) => `${Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, '0')}`

export default function Filtros({ opcoes, filtros, alterar, limpar }) {
  const meses = opcoes.meses.map((m) => ({ valor: m, texto: formatarMes(m) }))

  // Listas dependentes: promotores do supervisor escolhido, cidades da UF escolhida.
  const promotores = opcoes.promotores
    .filter((p) => !filtros.supervisor || p.supervisor === filtros.supervisor)
    .map((p) => ({ valor: p.codigo, texto: p.nome }))
  const cidades = opcoes.cidades
    .filter((c) => !filtros.uf || c.uf === filtros.uf)
    .map((c) => ({ valor: c.cidade, texto: filtros.uf ? c.cidade : `${c.cidade} - ${c.uf}` }))

  function mudarSupervisor(valor) {
    alterar('supervisor', valor)
    const promotor = opcoes.promotores.find((p) => p.codigo === filtros.promotor)
    if (valor && promotor && promotor.supervisor !== valor) alterar('promotor', '')
  }

  function mudarUf(valor) {
    alterar('uf', valor)
    alterar('cidade', '')
  }

  // Atalhos de período, contados a partir do último mês com faturamento.
  const ultimo = opcoes.meses[opcoes.meses.length - 1]
  function aplicarPeriodo(inicioDesejado) {
    const inicio = opcoes.meses.find((m) => indice(m) >= indice(inicioDesejado)) || opcoes.meses[0]
    alterar('modo', 'acumulado')
    alterar('inicio', inicio)
    alterar('fim', ultimo)
  }
  const atalhos = [
    { texto: 'Ano até hoje', inicio: `${ultimo.slice(0, 4)}-01` },
    { texto: 'Últimos 3 meses', inicio: rotulo(indice(ultimo) - 2) },
    { texto: 'Últimos 6 meses', inicio: rotulo(indice(ultimo) - 5) },
    { texto: 'Últimos 12 meses', inicio: rotulo(indice(ultimo) - 11) },
  ]

  // Filtros escolhidos, mostrados como etiquetas com "x" para tirar.
  const nomePromotor = opcoes.promotores.find((p) => p.codigo === filtros.promotor)?.nome
  const ativos = [
    filtros.supervisor && { campo: 'supervisor', texto: `Supervisor: ${filtros.supervisor}` },
    filtros.promotor && { campo: 'promotor', texto: `Promotor: ${nomePromotor || filtros.promotor}` },
    filtros.uf && { campo: 'uf', texto: `UF: ${filtros.uf}` },
    filtros.cidade && { campo: 'cidade', texto: `Cidade: ${filtros.cidade}` },
    filtros.pdv && { campo: 'pdv', texto: `PDV: ${filtros.pdv}` },
  ].filter(Boolean)
  const [maisFiltros, setMaisFiltros] = useState(false)
  const escondidosAtivos = ['promotor', 'cidade', 'pdv'].filter((c) => filtros[c]).length

  return (
    <section className="filtros">
      <div className="filtros-linha">
        <div className="filtro">
          Período
          <div className="alternar">
            <button className={filtros.modo === 'acumulado' ? 'ativo' : ''} onClick={() => alterar('modo', 'acumulado')}>
              Acumulado
            </button>
            <button className={filtros.modo === 'mes' ? 'ativo' : ''} onClick={() => alterar('modo', 'mes')}>
              Um mês
            </button>
          </div>
        </div>
        <Seletor
          rotulo={filtros.modo === 'mes' ? 'Mês' : 'De'}
          valor={filtros.inicio}
          aoMudar={(v) => alterar('inicio', v)}
          opcoes={meses}
          todos={null}
        />
        {filtros.modo === 'acumulado' && (
          <Seletor rotulo="Até" valor={filtros.fim} aoMudar={(v) => alterar('fim', v)} opcoes={meses} todos={null} />
        )}
        <Seletor
          rotulo="Supervisor"
          valor={filtros.supervisor}
          aoMudar={mudarSupervisor}
          opcoes={opcoes.supervisores.map((s) => ({ valor: s, texto: s }))}
        />
        <Seletor rotulo="UF" valor={filtros.uf} aoMudar={mudarUf} opcoes={opcoes.ufs.map((u) => ({ valor: u, texto: u }))} />
        <button className="secundario mais-filtros" onClick={() => setMaisFiltros((v) => !v)} aria-expanded={maisFiltros}>
          {maisFiltros ? 'Menos filtros ▴' : `Mais filtros${escondidosAtivos ? ` (${escondidosAtivos})` : ''} ▾`}
        </button>
      </div>

      {maisFiltros && (
        <div className="filtros-linha">
          <Seletor rotulo="Promotor" valor={filtros.promotor} aoMudar={(v) => alterar('promotor', v)} opcoes={promotores} />
          <Seletor rotulo="Cidade" valor={filtros.cidade} aoMudar={(v) => alterar('cidade', v)} opcoes={cidades} todos="Todas" />
          <FiltroPdv pdvs={opcoes.pdvs || []} valor={filtros.pdv} aoMudar={(v) => alterar('pdv', v)} />
          <div className="atalhos">
            <span className="dica">Período rápido:</span>
            {atalhos.map((a) => (
              <button key={a.texto} className="secundario" onClick={() => aplicarPeriodo(a.inicio)}>{a.texto}</button>
            ))}
          </div>
        </div>
      )}

      {ativos.length > 0 && (
        <div className="filtros-ativos">
          {ativos.map((a) => (
            <button key={a.campo} className="chip" onClick={() => (a.campo === 'uf' ? mudarUf('') : alterar(a.campo, ''))}
              title="Tirar este filtro">
              {a.texto} <span aria-hidden="true">✕</span>
            </button>
          ))}
          <button className="link" onClick={limpar}>Limpar tudo</button>
        </div>
      )}
    </section>
  )
}
