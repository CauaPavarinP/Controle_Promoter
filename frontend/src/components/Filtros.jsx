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

  return (
    <section className="filtros">
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
      <Seletor rotulo="Promotor" valor={filtros.promotor} aoMudar={(v) => alterar('promotor', v)} opcoes={promotores} />
      <Seletor rotulo="UF" valor={filtros.uf} aoMudar={mudarUf} opcoes={opcoes.ufs.map((u) => ({ valor: u, texto: u }))} />
      <Seletor rotulo="Cidade" valor={filtros.cidade} aoMudar={(v) => alterar('cidade', v)} opcoes={cidades} todos="Todas" />
      <FiltroPdv pdvs={opcoes.pdvs || []} valor={filtros.pdv} aoMudar={(v) => alterar('pdv', v)} />
      <button className="secundario limpar" onClick={limpar}>Limpar filtros</button>
      <div className="atalhos">
        {atalhos.map((a) => (
          <button key={a.texto} className="secundario" onClick={() => aplicarPeriodo(a.inicio)}>{a.texto}</button>
        ))}
      </div>
    </section>
  )
}
