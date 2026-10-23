import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import Filtros from './Filtros.jsx'
import CardsResumo from './CardsResumo.jsx'
import TabelaPromotores from './TabelaPromotores.jsx'
import TabelaLojas from './TabelaLojas.jsx'
import Importar from './Importar.jsx'

const FILTROS_VAZIOS = { modo: 'acumulado', inicio: '', fim: '', supervisor: '', promotor: '', uf: '', cidade: '' }

// Período padrão: janeiro do último ano com dados até o último mês importado.
function periodoPadrao(meses) {
  if (!meses.length) return { inicio: '', fim: '' }
  const ultimo = meses[meses.length - 1]
  const inicioDoAno = meses.find((m) => m.startsWith(ultimo.slice(0, 4)))
  return { inicio: inicioDoAno, fim: ultimo }
}

export default function Painel({ usuario, aoSair }) {
  const [opcoes, setOpcoes] = useState(null)
  const [filtros, setFiltros] = useState(FILTROS_VAZIOS)
  const [dados, setDados] = useState(null)
  const [carregando, setCarregando] = useState(false)
  const [erro, setErro] = useState('')
  const [mostrarImportar, setMostrarImportar] = useState(false)

  const carregarOpcoes = useCallback(async () => {
    try {
      const novas = await api.opcoes()
      setOpcoes(novas)
      setFiltros((atual) =>
        atual.inicio && novas.meses.includes(atual.inicio) ? atual : { ...atual, ...periodoPadrao(novas.meses) },
      )
      if (!novas.meses.length) setMostrarImportar(true)
    } catch (e) {
      setErro(e.message)
    }
  }, [])

  useEffect(() => {
    carregarOpcoes()
  }, [carregarOpcoes])

  // Recalcula o painel sempre que um filtro muda.
  useEffect(() => {
    if (!filtros.inicio) return
    const { modo, ...resto } = filtros
    const parametros = { ...resto, fim: modo === 'mes' ? filtros.inicio : filtros.fim }
    let cancelado = false
    setCarregando(true)
    setErro('')
    api.painel(parametros)
      .then((resposta) => !cancelado && setDados(resposta))
      .catch((e) => !cancelado && setErro(e.message))
      .finally(() => !cancelado && setCarregando(false))
    return () => {
      cancelado = true
    }
  }, [filtros])

  const alterarFiltro = (campo, valor) => setFiltros((atual) => ({ ...atual, [campo]: valor }))

  return (
    <div className="pagina">
      <header className="topo">
        <div>
          <h1>Controle de Promotores</h1>
          <p className="subtitulo">Custo dos promotores × faturamento das lojas</p>
        </div>
        <div className="topo-acoes">
          <button className="secundario" onClick={() => setMostrarImportar((v) => !v)}>
            {mostrarImportar ? 'Fechar importação' : 'Atualizar dados'}
          </button>
          <span className="usuario">{usuario}</span>
          <button className="secundario" onClick={aoSair}>Sair</button>
        </div>
      </header>

      {mostrarImportar && (
        <Importar importacoes={opcoes?.importacoes || {}} aoImportar={carregarOpcoes} />
      )}

      {opcoes?.roteiro_sem_vinculo?.length > 0 && (
        <div className="aviso">
          Colaboradores do roteiro que não estão na lista de promotores (ficam fora do painel):{' '}
          {opcoes.roteiro_sem_vinculo.join(', ')}
        </div>
      )}

      {opcoes && opcoes.meses.length > 0 && (
        <>
          <Filtros
            opcoes={opcoes}
            filtros={filtros}
            alterar={alterarFiltro}
            limpar={() => setFiltros({ ...FILTROS_VAZIOS, ...periodoPadrao(opcoes.meses) })}
          />
          {erro && <div className="erro-caixa">{erro}</div>}
          {dados && (
            <div className={carregando ? 'atualizando' : ''}>
              <CardsResumo resumo={dados.resumo} />
              <TabelaPromotores
                promotores={dados.promotores}
                selecionado={filtros.promotor}
                aoSelecionar={(codigo) => alterarFiltro('promotor', filtros.promotor === codigo ? '' : codigo)}
              />
              <TabelaLojas lojas={dados.lojas} />
            </div>
          )}
        </>
      )}
    </div>
  )
}
