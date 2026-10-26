import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { formatarMes } from '../formato.js'
import Filtros from './Filtros.jsx'
import CardsResumo from './CardsResumo.jsx'
import TabelaPromotores from './TabelaPromotores.jsx'
import TabelaLojas from './TabelaLojas.jsx'
import GradeMensal from './GradeMensal.jsx'
import BlocoCustos from './BlocoCustos.jsx'
import Importar from './Importar.jsx'
import Pendencias from './Pendencias.jsx'
import Conferencia from './Conferencia.jsx'
import Regras from './Regras.jsx'
import Promotores from './cadastros/Promotores.jsx'
import Supervisores from './cadastros/Supervisores.jsx'
import Pdvs from './cadastros/Pdvs.jsx'
import Roteiros from './cadastros/Roteiros.jsx'
import Usuarios from './cadastros/Usuarios.jsx'
import MeuPerfil from './cadastros/MeuPerfil.jsx'

const FILTROS_VAZIOS = { modo: 'acumulado', inicio: '', fim: '', supervisor: '', promotor: '', uf: '', cidade: '', pdv: '' }

// grupo: título no menu | admin: só administrador vê
const ABAS = [
  { id: 'visao-geral', grupo: 'Análise', titulo: 'Visão geral', subtitulo: 'Custo dos promotores × faturamento das lojas' },
  { id: 'lojas', grupo: 'Análise', titulo: 'Lojas', subtitulo: 'Faturamento de cada loja atendida no período' },
  { id: 'mensal', grupo: 'Análise', titulo: 'Faturamento mês a mês', subtitulo: 'Cada loja mês a mês, como as abas SC, SP, PR… da planilha' },
  { id: 'pendencias', grupo: 'Análise', titulo: 'Pendências', subtitulo: 'O que falta corrigir para os números ficarem confiáveis' },
  { id: 'promotores', grupo: 'Cadastros', titulo: 'Promotores', subtitulo: 'Promotores, custos por competência e roteiro de cada um' },
  { id: 'supervisores', grupo: 'Cadastros', titulo: 'Supervisores', subtitulo: 'Supervisores e suas equipes' },
  { id: 'pdvs', grupo: 'Cadastros', titulo: 'PDVs', subtitulo: 'Pontos de venda atendidos pelos promotores' },
  { id: 'roteiros', grupo: 'Cadastros', titulo: 'Roteiros', subtitulo: 'Qual promotor atende qual PDV, desde quando e quantas vezes por semana' },
  { id: 'importar', grupo: 'Configuração', titulo: 'Atualizar dados', subtitulo: 'Importe as planilhas para atualizar o sistema', admin: true },
  { id: 'regras', grupo: 'Configuração', titulo: 'Regras do cálculo', subtitulo: 'Defina como o sistema calcula custo e faturamento' },
  { id: 'conferencia', grupo: 'Configuração', titulo: 'Conferência', subtitulo: 'Totais do sistema comparados com as abas da planilha' },
  { id: 'usuarios', grupo: 'Configuração', titulo: 'Usuários', subtitulo: 'Quem acessa o sistema e com qual perfil', admin: true },
  { id: 'perfil', grupo: null, titulo: 'Meu perfil', subtitulo: 'Seus dados de acesso' },
]
const ABAS_DE_ANALISE = ['visao-geral', 'lojas', 'mensal', 'pendencias']
const ABAS_COM_FILTRO = ['visao-geral', 'lojas', 'mensal']

// Texto dos filtros para o cabeçalho da impressão.
function descreverFiltros(filtros, opcoes) {
  const fim = filtros.modo === 'mes' ? filtros.inicio : filtros.fim
  const promotor = opcoes?.promotores.find((p) => p.codigo === filtros.promotor)
  const partes = [filtros.inicio === fim ? `Mês: ${formatarMes(fim)}` : `Período: ${formatarMes(filtros.inicio)} a ${formatarMes(fim)}`]
  if (filtros.supervisor) partes.push(`Supervisor: ${filtros.supervisor}`)
  if (promotor) partes.push(`Promotor: ${promotor.nome}`)
  if (filtros.uf) partes.push(`UF: ${filtros.uf}`)
  if (filtros.cidade) partes.push(`Cidade: ${filtros.cidade}`)
  if (filtros.pdv) partes.push(`PDV: ${filtros.pdv}`)
  return partes.join(' · ')
}

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

  // Sem faturamento, o administrador cai direto em "Atualizar dados" — só na abertura do sistema,
  // para não puxar a pessoa de volta enquanto os dados recém-importados ainda estão carregando.
  const jaDirecionou = useRef(false)
  useEffect(() => {
    if (!opcoes || jaDirecionou.current) return
    jaDirecionou.current = true
    if (!opcoes.meses.length && admin && aba === 'visao-geral') irPara('importar')
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
                  {a.id === 'pendencias' && opcoes?.pendencias > 0 && <span className="contador">{opcoes.pendencias}</span>}
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
          <div>
            <h1>{abaAtual.titulo}</h1>
            <p className="subtitulo">{abaAtual.subtitulo}</p>
          </div>
          {ABAS_COM_FILTRO.includes(aba) && temDados && (
            <button className="secundario nao-imprimir" onClick={() => window.print()}>Imprimir</button>
          )}
        </header>
        {ABAS_COM_FILTRO.includes(aba) && temDados && filtros.inicio && (
          <p className="so-impressao cabecalho-impressao">
            Controle de Promotores — 101 do Brasil · {descreverFiltros(filtros, opcoes)} · Impresso em{' '}
            {new Date().toLocaleString('pt-BR')}
          </p>
        )}

        {erro && ABAS_DE_ANALISE.includes(aba) && <div className="erro-caixa">{erro}</div>}

        {opcoes?.reimportar_faturamento && ABAS_COM_FILTRO.includes(aba) && (
          <div className="aviso">
            O sistema agora guarda o faturamento item a item. O faturamento importado na versão anterior não é usado:
            {admin ? <> importe o arquivo de novo em <a href="#importar">Atualizar dados</a>.</> : ' peça a um administrador para importar de novo.'}
          </div>
        )}

        {ABAS_COM_FILTRO.includes(aba) && !temDados && opcoes && (
          <div className="aviso">
            Ainda não há faturamento importado.{' '}
            {admin ? <a href="#importar">Importe as planilhas em Atualizar dados.</a> : 'Peça a um administrador para importar.'}
          </div>
        )}

        {ABAS_COM_FILTRO.includes(aba) && temDados && (
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
            <BlocoCustos custos={dados.custos} fim={formatarMes(filtros.modo === 'mes' ? filtros.inicio : filtros.fim)} />
          </div>
        )}

        {aba === 'mensal' && temDados && dados && (
          <div className={carregando ? 'atualizando' : ''}>
            <GradeMensal grade={dados.grade} />
          </div>
        )}

        {aba === 'lojas' && temDados && dados && (
          <div className={carregando ? 'atualizando' : ''}>
            <TabelaLojas lojas={dados.lojas} regras={dados.regras} />
          </div>
        )}

        {aba === 'pendencias' && (
          <Pendencias podeEditar={admin} meses={opcoes?.meses || []} aoAlterar={carregarOpcoes} />
        )}
        {aba === 'conferencia' && <Conferencia />}
        {aba === 'promotores' && <Promotores podeEditar={admin} />}
        {aba === 'supervisores' && <Supervisores podeEditar={admin} />}
        {aba === 'pdvs' && <Pdvs podeEditar={admin} />}
        {aba === 'roteiros' && <Roteiros podeEditar={admin} />}
        {aba === 'importar' && admin && <Importar aoImportar={carregarOpcoes} />}
        {aba === 'regras' && <Regras podeEditar={admin} aoSalvar={() => setVersaoDados((v) => v + 1)} />}
        {aba === 'usuarios' && admin && <Usuarios eu={usuario} />}
        {aba === 'perfil' && <MeuPerfil usuario={usuario} />}
      </main>
    </div>
  )
}
