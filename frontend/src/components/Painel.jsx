import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import Filtros from './Filtros.jsx'
import CardsResumo from './CardsResumo.jsx'
import TabelaPromotores from './TabelaPromotores.jsx'
import TabelaLojas from './TabelaLojas.jsx'
import Importar from './Importar.jsx'
import Avisos from './Avisos.jsx'

const FILTROS_VAZIOS = { modo: 'acumulado', inicio: '', fim: '', supervisor: '', promotor: '', uf: '', cidade: '' }

const ABAS = [
  { id: 'visao-geral', titulo: 'Visão geral', subtitulo: 'Custo dos promotores × faturamento das lojas' },
  { id: 'lojas', titulo: 'Lojas', subtitulo: 'Faturamento de cada loja atendida no período' },
  { id: 'avisos', titulo: 'Avisos dos dados', subtitulo: 'Problemas encontrados nas planilhas importadas' },
  { id: 'importar', titulo: 'Atualizar dados', subtitulo: 'Importe as planilhas para atualizar o sistema' },
]

// Período padrão: janeiro do último ano com dados até o último mês importado.
function periodoPadrao(meses) {
  if (!meses.length) return { inicio: '', fim: '' }
  const ultimo = meses[meses.length - 1]
  const inicioDoAno = meses.find((m) => m.startsWith(ultimo.slice(0, 4)))
  return { inicio: inicioDoAno, fim: ultimo }
}

// A aba fica no endereço (#lojas, #importar…) para o F5 e o "voltar" do navegador funcionarem.
function abaDoEndereco() {
  const id = window.location.hash.replace('#', '')
  return ABAS.some((a) => a.id === id) ? id : 'visao-geral'
}

export default function Painel({ usuario, aoSair }) {
  const [aba, setAba] = useState(abaDoEndereco)
  const [opcoes, setOpcoes] = useState(null)
  const [filtros, setFiltros] = useState(FILTROS_VAZIOS)
  const [dados, setDados] = useState(null)
  const [carregando, setCarregando] = useState(false)
  const [erro, setErro] = useState('')

  useEffect(() => {
    const aoMudarEndereco = () => setAba(abaDoEndereco())
    window.addEventListener('hashchange', aoMudarEndereco)
    return () => window.removeEventListener('hashchange', aoMudarEndereco)
  }, [])

  const irPara = (id) => {
    window.location.hash = id
  }

  const carregarOpcoes = useCallback(async () => {
    try {
      const novas = await api.opcoes()
      setOpcoes(novas)
      setFiltros((atual) =>
        atual.inicio && novas.meses.includes(atual.inicio) ? atual : { ...atual, ...periodoPadrao(novas.meses) },
      )
      if (!novas.meses.length) irPara('importar')
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

  // Clicar num promotor na visão geral abre as lojas dele.
  function verLojasDoPromotor(codigo) {
    alterarFiltro('promotor', codigo)
    irPara('lojas')
  }

  const temDados = opcoes && opcoes.meses.length > 0
  const totalAvisos = opcoes ? contarAvisos(opcoes) : 0
  const abaAtual = ABAS.find((a) => a.id === aba)

  return (
    <div className="layout">
      <aside className="menu-lateral">
        <div className="menu-marca">
          <strong>Controle de Promotores</strong>
          <span>Comercial • 101 do Brasil</span>
        </div>
        <nav className="menu-itens">
          {ABAS.map((a) => (
            <button key={a.id} className={aba === a.id ? 'ativo' : ''} onClick={() => irPara(a.id)}>
              {a.titulo}
              {a.id === 'avisos' && totalAvisos > 0 && <span className="contador">{totalAvisos}</span>}
            </button>
          ))}
        </nav>
        <div className="menu-usuario">
          <strong>{usuario}</strong>
          <button className="secundario" onClick={aoSair}>Sair</button>
        </div>
      </aside>

      <main className="conteudo">
        <header className="conteudo-topo">
          <h1>{abaAtual.titulo}</h1>
          <p className="subtitulo">{abaAtual.subtitulo}</p>
        </header>

        {erro && <div className="erro-caixa">{erro}</div>}

        {(aba === 'visao-geral' || aba === 'lojas') && !temDados && opcoes && (
          <div className="aviso">
            Ainda não há faturamento importado.{' '}
            <a href="#importar">Importe as planilhas em Atualizar dados.</a>
          </div>
        )}

        {(aba === 'visao-geral' || aba === 'lojas') && temDados && (
          <Filtros
            opcoes={opcoes}
            filtros={filtros}
            alterar={alterarFiltro}
            limpar={() => setFiltros({ ...FILTROS_VAZIOS, ...periodoPadrao(opcoes.meses) })}
          />
        )}

        {aba === 'visao-geral' && temDados && dados && (
          <div className={carregando ? 'atualizando' : ''}>
            <CardsResumo resumo={dados.resumo} />
            <TabelaPromotores
              promotores={dados.promotores}
              selecionado={filtros.promotor}
              aoSelecionar={verLojasDoPromotor}
            />
          </div>
        )}

        {aba === 'lojas' && temDados && dados && (
          <div className={carregando ? 'atualizando' : ''}>
            <TabelaLojas lojas={dados.lojas} />
          </div>
        )}

        {aba === 'avisos' && opcoes && <Avisos opcoes={opcoes} />}

        {aba === 'importar' && (
          <Importar importacoes={opcoes?.importacoes || {}} aoImportar={carregarOpcoes} />
        )}
      </main>
    </div>
  )
}

function contarAvisos(opcoes) {
  const daImportacao = Object.values(opcoes.importacoes || {}).reduce((soma, i) => soma + (i.avisos?.length || 0), 0)
  return daImportacao + (opcoes.roteiro_sem_vinculo?.length ? 1 : 0)
}
