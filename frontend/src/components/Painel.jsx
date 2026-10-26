import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import Filtros from './Filtros.jsx'
import CardsResumo from './CardsResumo.jsx'
import TabelaPromotores from './TabelaPromotores.jsx'
import TabelaLojas from './TabelaLojas.jsx'
import Importar from './Importar.jsx'
import Avisos from './Avisos.jsx'
import Regras from './Regras.jsx'
import Promotores from './cadastros/Promotores.jsx'
import Supervisores from './cadastros/Supervisores.jsx'
import Pdvs from './cadastros/Pdvs.jsx'
import Roteiros from './cadastros/Roteiros.jsx'
import Usuarios from './cadastros/Usuarios.jsx'
import MeuPerfil from './cadastros/MeuPerfil.jsx'

const FILTROS_VAZIOS = { modo: 'acumulado', inicio: '', fim: '', supervisor: '', promotor: '', uf: '', cidade: '' }

// grupo: título no menu | admin: só administrador vê
const ABAS = [
  { id: 'visao-geral', grupo: 'Análise', titulo: 'Visão geral', subtitulo: 'Custo dos promotores × faturamento das lojas' },
  { id: 'lojas', grupo: 'Análise', titulo: 'Lojas', subtitulo: 'Faturamento de cada loja atendida no período' },
  { id: 'avisos', grupo: 'Análise', titulo: 'Avisos dos dados', subtitulo: 'Problemas encontrados nos dados' },
  { id: 'promotores', grupo: 'Cadastros', titulo: 'Promotores', subtitulo: 'Promotores, custos por competência e roteiro de cada um' },
  { id: 'supervisores', grupo: 'Cadastros', titulo: 'Supervisores', subtitulo: 'Supervisores e suas equipes' },
  { id: 'pdvs', grupo: 'Cadastros', titulo: 'PDVs', subtitulo: 'Pontos de venda atendidos pelos promotores' },
  { id: 'roteiros', grupo: 'Cadastros', titulo: 'Roteiros', subtitulo: 'Qual promotor atende qual PDV, desde quando e quantas vezes por semana' },
  { id: 'importar', grupo: 'Configuração', titulo: 'Atualizar dados', subtitulo: 'Importe as planilhas para atualizar o sistema', admin: true },
  { id: 'regras', grupo: 'Configuração', titulo: 'Regras do cálculo', subtitulo: 'Defina como o sistema calcula custo e faturamento' },
  { id: 'usuarios', grupo: 'Configuração', titulo: 'Usuários', subtitulo: 'Quem acessa o sistema e com qual perfil', admin: true },
  { id: 'perfil', grupo: null, titulo: 'Meu perfil', subtitulo: 'Seus dados de acesso' },
]
const ABAS_DE_ANALISE = ['visao-geral', 'lojas', 'avisos']

// Período padrão: janeiro do último ano com dados até o último mês importado.
function periodoPadrao(meses) {
  if (!meses.length) return { inicio: '', fim: '' }
  const ultimo = meses[meses.length - 1]
  const inicioDoAno = meses.find((m) => m.startsWith(ultimo.slice(0, 4)))
  return { inicio: inicioDoAno, fim: ultimo }
}

export default function Painel({ usuario, aoSair }) {
  const admin = usuario.perfil === 'admin'
  const abasPermitidas = ABAS.filter((a) => !a.admin || admin)

  // A aba fica no endereço (#lojas, #promotores…) para o F5 e o "voltar" do navegador funcionarem.
  const abaDoEndereco = useCallback(() => {
    const id = window.location.hash.replace('#', '')
    return abasPermitidas.some((a) => a.id === id) ? id : 'visao-geral'
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [admin])

  const [aba, setAba] = useState(abaDoEndereco)
  const [opcoes, setOpcoes] = useState(null)
  const [filtros, setFiltros] = useState(FILTROS_VAZIOS)
  const [dados, setDados] = useState(null)
  const [carregando, setCarregando] = useState(false)
  const [erro, setErro] = useState('')
  // Muda quando regras ou cadastros mudam, para o painel recalcular.
  const [versaoDados, setVersaoDados] = useState(0)

  useEffect(() => {
    const aoMudarEndereco = () => setAba(abaDoEndereco())
    window.addEventListener('hashchange', aoMudarEndereco)
    return () => window.removeEventListener('hashchange', aoMudarEndereco)
  }, [abaDoEndereco])

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
    } catch (e) {
      setErro(e.message)
    }
  }, [])

  // Ao voltar para as abas de análise, recarrega: os cadastros podem ter mudado.
  useEffect(() => {
    if (ABAS_DE_ANALISE.includes(aba)) {
      carregarOpcoes()
      setVersaoDados((v) => v + 1)
    }
  }, [aba, carregarOpcoes])

  useEffect(() => {
    if (opcoes && !opcoes.meses.length && admin && aba === 'visao-geral') irPara('importar')
  }, [opcoes, admin, aba])

  // Recalcula o painel sempre que um filtro muda.
  useEffect(() => {
    if (!filtros.inicio || !ABAS_DE_ANALISE.includes(aba)) return
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtros, versaoDados])

  const alterarFiltro = (campo, valor) => setFiltros((atual) => ({ ...atual, [campo]: valor }))

  // Clicar num promotor na visão geral abre as lojas dele.
  function verLojasDoPromotor(codigo) {
    alterarFiltro('promotor', codigo)
    irPara('lojas')
  }

  const temDados = opcoes && opcoes.meses.length > 0
  const totalAvisos = opcoes ? contarAvisos(opcoes) : 0
  const abaAtual = ABAS.find((a) => a.id === aba)
  const grupos = [...new Set(abasPermitidas.map((a) => a.grupo).filter(Boolean))]

  return (
    <div className="layout">
      <aside className="menu-lateral">
        <div className="menu-marca">
          <strong>Controle de Promotores</strong>
          <span>Comercial • 101 do Brasil</span>
        </div>
        <nav className="menu-itens">
          {grupos.map((grupo) => (
            <div key={grupo} className="menu-grupo">
              <span className="menu-grupo-titulo">{grupo}</span>
              {abasPermitidas.filter((a) => a.grupo === grupo).map((a) => (
                <button key={a.id} className={aba === a.id ? 'ativo' : ''} onClick={() => irPara(a.id)}>
                  {a.titulo}
                  {a.id === 'avisos' && totalAvisos > 0 && <span className="contador">{totalAvisos}</span>}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="menu-usuario">
          <strong>{usuario.nome}</strong>
          <span className="dica">{admin ? 'Administrador' : usuario.perfil === 'supervisor' ? 'Supervisor' : 'Consulta'}</span>
          <div className="acoes">
            <button className={`secundario ${aba === 'perfil' ? 'ativo' : ''}`} onClick={() => irPara('perfil')}>Meu perfil</button>
            <button className="secundario" onClick={aoSair}>Sair</button>
          </div>
        </div>
      </aside>

      <main className="conteudo">
        <header className="conteudo-topo">
          <h1>{abaAtual.titulo}</h1>
          <p className="subtitulo">{abaAtual.subtitulo}</p>
        </header>

        {erro && ABAS_DE_ANALISE.includes(aba) && <div className="erro-caixa">{erro}</div>}

        {(aba === 'visao-geral' || aba === 'lojas') && !temDados && opcoes && (
          <div className="aviso">
            Ainda não há faturamento importado.{' '}
            {admin ? <a href="#importar">Importe as planilhas em Atualizar dados.</a> : 'Peça a um administrador para importar.'}
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
            <CardsResumo resumo={dados.resumo} regras={dados.regras} />
            <TabelaPromotores
              promotores={dados.promotores}
              regras={dados.regras}
              selecionado={filtros.promotor}
              aoSelecionar={verLojasDoPromotor}
            />
          </div>
        )}

        {aba === 'lojas' && temDados && dados && (
          <div className={carregando ? 'atualizando' : ''}>
            <TabelaLojas lojas={dados.lojas} regras={dados.regras} />
          </div>
        )}

        {aba === 'avisos' && opcoes && <Avisos opcoes={opcoes} />}
        {aba === 'promotores' && <Promotores podeEditar={admin} />}
        {aba === 'supervisores' && <Supervisores podeEditar={admin} />}
        {aba === 'pdvs' && <Pdvs podeEditar={admin} />}
        {aba === 'roteiros' && <Roteiros podeEditar={admin} />}
        {aba === 'importar' && admin && (
          <Importar importacoes={opcoes?.importacoes || {}} aoImportar={carregarOpcoes} />
        )}
        {aba === 'regras' && <Regras podeEditar={admin} aoSalvar={() => setVersaoDados((v) => v + 1)} />}
        {aba === 'usuarios' && admin && <Usuarios eu={usuario} />}
        {aba === 'perfil' && <MeuPerfil usuario={usuario} />}
      </main>
    </div>
  )
}

function contarAvisos(opcoes) {
  const daImportacao = Object.values(opcoes.importacoes || {}).reduce((soma, i) => soma + (i.avisos?.length || 0), 0)
  return daImportacao + (opcoes.roteiro_sem_vinculo?.length ? 1 : 0)
}
