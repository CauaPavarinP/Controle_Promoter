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
      <button className="secundario limpar" onClick={limpar}>Limpar filtros</button>
    </section>
  )
}
