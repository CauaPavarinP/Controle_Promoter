// Pendências / qualidade dos dados (documento, seção 7.8).
import { useEffect, useState } from 'react'
import { http } from '../api.js'
import { formatarCnpj, formatarMes, formatarMoeda } from '../formato.js'
import { FormularioPdv, PDV_VAZIO } from './cadastros/Pdvs.jsx'
import { Campo, Modal, Tabela } from './ui.jsx'

function Secao({ titulo, quantidade, explicacao, children }) {
  return (
    <section className="bloco">
      <h2>{titulo} {quantidade != null && <span className={`contador ${quantidade ? '' : 'zerado'}`}>{quantidade}</span>}</h2>
      {explicacao && <p className="dica">{explicacao}</p>}
      {children}
    </section>
  )
}

function ResolverColaborador({ pendencia, aoFechar, aoSalvar }) {
  const [promotores, setPromotores] = useState([])
  const [dados, setDados] = useState({ promotor_id: '', data_inicio: `${new Date().getFullYear()}-01-01` })
  const [erro, setErro] = useState('')
  useEffect(() => { http.get('/api/promotores').then(setPromotores) }, [])

  async function salvar() {
    try {
      await http.post('/api/pendencias/colaborador', {
        colaborador: pendencia.colaborador, promotor_id: Number(dados.promotor_id), data_inicio: dados.data_inicio,
      })
      aoSalvar()
    } catch (e) {
      setErro(e.message)
    }
  }

  return (
    <Modal titulo={`Ligar as lojas de "${pendencia.colaborador}"`} aoFechar={aoFechar}
      rodape={<button onClick={salvar} disabled={!dados.promotor_id}>Ligar {pendencia.quantidade} loja(s)</button>}>
      <p className="dica">
        Escolha o promotor cadastrado que é essa pessoa. As lojas viram PDVs (se ainda não existirem) e entram no roteiro
        dele. Se a pessoa não está cadastrada, cadastre antes em Promotores.
      </p>
      <Campo rotulo="Promotor">
        <select value={dados.promotor_id} onChange={(e) => setDados({ ...dados, promotor_id: e.target.value })}>
          <option value="">Escolha…</option>
          {promotores.filter((p) => p.ativo).map((p) => <option key={p.id} value={p.id}>{p.nome} ({p.codigo})</option>)}
        </select>
      </Campo>
      <Campo rotulo="Início do atendimento">
        <input type="date" value={dados.data_inicio} onChange={(e) => setDados({ ...dados, data_inicio: e.target.value })} />
      </Campo>
      <p className="dica">Lojas: {pendencia.lojas.join(', ')}</p>
      {erro && <p className="erro">{erro}</p>}
    </Modal>
  )
}

export default function Pendencias({ podeEditar, meses, aoAlterar }) {
  const [dados, setDados] = useState(null)
  const [periodo, setPeriodo] = useState({ inicio: '', fim: '' })
  const [erro, setErro] = useState('')
  const [janela, setJanela] = useState(null)

  const carregar = (p = periodo) =>
    http.get(`/api/pendencias?${new URLSearchParams(p)}`)
      .then((d) => { setDados(d); setPeriodo(d.periodo) })
      .catch((e) => setErro(e.message))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { carregar({ inicio: '', fim: '' }) }, [])

  const concluir = () => { setJanela(null); carregar(); aoAlterar() }
  if (!dados) return erro ? <div className="erro-caixa">{erro}</div> : <p>Carregando…</p>

  const mudarPeriodo = (campo, valor) => {
    const novo = { ...periodo, [campo]: valor }
    setPeriodo(novo)
    carregar(novo)
  }
  const opcoesMes = meses.length ? meses : [periodo.inicio, periodo.fim]

  return (
    <>
      <section className="filtros">
        <label className="filtro">
          Período (para faturamento)
          <select value={periodo.inicio} onChange={(e) => mudarPeriodo('inicio', e.target.value)}>
            {opcoesMes.map((m) => <option key={m} value={m}>{formatarMes(m)}</option>)}
          </select>
        </label>
        <label className="filtro">
          Até
          <select value={periodo.fim} onChange={(e) => mudarPeriodo('fim', e.target.value)}>
            {opcoesMes.map((m) => <option key={m} value={m}>{formatarMes(m)}</option>)}
          </select>
        </label>
        <p className="dica">Cada lista pode ser exportada para Excel. Resolver as pendências deixa os números do painel mais confiáveis.</p>
      </section>

      <Secao titulo="Colaboradores do roteiro sem promotor cadastrado" quantidade={dados.colaboradores_sem_promotor.length}
        explicacao="Vieram da planilha de roteiro e não bateram com nenhum promotor (nem ignorando acentos e espaços). As lojas deles ficaram fora do painel.">
        <Tabela chave="colaborador" linhas={dados.colaboradores_sem_promotor} arquivo="colaboradores-sem-promotor" porPagina={20}
          vazio="Nenhum. Todos os colaboradores do roteiro foram encontrados."
          colunas={[
            { campo: 'colaborador', titulo: 'Colaborador (como está na planilha)', quebra: true },
            { campo: 'quantidade', titulo: 'Lojas', num: true },
            { campo: 'origens', titulo: 'Abas', mostrar: (p) => p.origens.join(', '), exportar: (p) => p.origens.join(', ') },
            { campo: 'lojas', titulo: 'Lojas', quebra: true, mostrar: (p) => p.lojas.slice(0, 4).join(', ') + (p.lojas.length > 4 ? '…' : ''),
              exportar: (p) => p.lojas.join(', ') },
            ...(podeEditar ? [{ campo: 'acao', titulo: '', semOrdem: true, semExportar: true,
              mostrar: (p) => <button className="secundario" onClick={() => setJanela({ tipo: 'colaborador', pendencia: p })}>Ligar a um promotor</button> }] : []),
          ]} />
      </Secao>

      <Secao titulo="Lojas diferentes com o mesmo CNPJ" quantidade={dados.lojas_mesmo_cnpj.length}
        explicacao={'O ERP fatura por CNPJ. Se cada loja tiver o seu COD CLI (preenchido no cadastro do PDV) e ele for ' +
          'diferente entre elas, o faturamento é separado por loja. Se não, o valor do CNPJ conta uma vez só nos totais e as ' +
          'lojas aparecem com o aviso "faturamento compartilhado". Confirme com o Maurício se é erro de digitação na ' +
          'planilha ou se são lojas diferentes mesmo.'}>
        <Tabela chave="cnpj" linhas={dados.lojas_mesmo_cnpj} arquivo="lojas-mesmo-cnpj" porPagina={20} vazio="Nenhum CNPJ repetido."
          colunas={[
            { campo: 'cnpj', titulo: 'CNPJ', mostrar: (g) => formatarCnpj(g.cnpj), exportar: (g) => formatarCnpj(g.cnpj) },
            { campo: 'lojas', titulo: 'Lojas (COD CLI no cadastro)', quebra: true, ordenar: (g) => g.lojas[0].nome,
              mostrar: (g) => g.lojas.map((l) => `${l.nome} (${l.cod_cli || 'sem COD CLI'})`).join(' · '),
              exportar: (g) => g.lojas.map((l) => `${l.nome} (${l.cod_cli || 'sem COD CLI'})`).join(' | ') },
            { campo: 'cod_cli_no_faturamento', titulo: 'COD CLI no faturamento', mostrar: (g) => g.cod_cli_no_faturamento.join(', ') || '—',
              exportar: (g) => g.cod_cli_no_faturamento.join(', ') },
            { campo: 'valor_periodo', titulo: 'Faturamento do CNPJ', num: true, mostrar: (g) => formatarMoeda(g.valor_periodo) },
            { campo: 'separado_por_cod_cli', titulo: 'Situação',
              mostrar: (g) => (g.separado_por_cod_cli
                ? <span className="situacao ativa">Separado pelo COD CLI</span>
                : <span className="situacao agendada">Compartilhado</span>),
              exportar: (g) => (g.separado_por_cod_cli ? 'Separado pelo COD CLI' : 'Compartilhado') },
          ]} />
        {podeEditar && <p className="dica">Para separar: em PDVs, edite cada loja e preencha o COD CLI (os códigos que aparecem no faturamento estão na terceira coluna).</p>}
      </Secao>

      <Secao titulo="Clientes que compraram e não estão no roteiro" quantidade={dados.cnpjs_sem_roteiro.length}
        explicacao="CNPJs com faturamento no período que não são atendidos por nenhum promotor. Pode ser normal (cliente sem promotor) ou um PDV que faltou no roteiro.">
        <Tabela chave="cnpj" linhas={dados.cnpjs_sem_roteiro} arquivo="clientes-sem-roteiro" porPagina={20} vazio="Nenhum."
          colunas={[
            { campo: 'razao_social', titulo: 'Cliente', quebra: true },
            { campo: 'cnpj', titulo: 'CNPJ', mostrar: (c) => formatarCnpj(c.cnpj), exportar: (c) => formatarCnpj(c.cnpj) },
            { campo: 'cidade', titulo: 'Cidade', mostrar: (c) => `${c.cidade || ''}${c.uf ? ` - ${c.uf}` : ''}` },
            { campo: 'notas', titulo: 'Notas', num: true },
            { campo: 'valor', titulo: 'Faturamento', num: true, mostrar: (c) => formatarMoeda(c.valor) },
            ...(podeEditar ? [{ campo: 'acao', titulo: '', semOrdem: true, semExportar: true,
              mostrar: (c) => (c.pdv_cadastrado
                ? <a href="#roteiros">Vincular em Roteiros</a>
                : <button className="secundario" onClick={() => setJanela({ tipo: 'pdv', cliente: c })}>Cadastrar PDV</button>) }] : []),
          ]} />
      </Secao>

      <Secao titulo="PDVs atendidos sem faturamento no período" quantidade={dados.pdvs_sem_faturamento.length}
        explicacao="O promotor vai, mas não houve compra (ou o PDV está sem CNPJ). São os primeiros candidatos a rever.">
        <Tabela linhas={dados.pdvs_sem_faturamento} arquivo="pdvs-sem-faturamento" porPagina={20} vazio="Nenhum."
          colunas={[
            { campo: 'pdv', titulo: 'PDV', quebra: true },
            { campo: 'cnpj', titulo: 'CNPJ', mostrar: (p) => formatarCnpj(p.cnpj), exportar: (p) => formatarCnpj(p.cnpj) },
            { campo: 'cidade', titulo: 'Cidade', mostrar: (p) => `${p.cidade}${p.uf ? ` - ${p.uf}` : ''}` },
            { campo: 'promotores', titulo: 'Promotor', mostrar: (p) => p.promotores.join(', '), exportar: (p) => p.promotores.join(', ') },
            { campo: 'visitas_semana', titulo: 'Visitas/sem.', num: true, mostrar: (p) => p.visitas_semana ?? '—' },
          ]} />
      </Secao>

      <Secao titulo="Promotores com cadastro incompleto" quantidade={dados.promotores_incompletos.length}>
        <Tabela linhas={dados.promotores_incompletos} arquivo="promotores-incompletos" porPagina={20} vazio="Nenhum."
          colunas={[
            { campo: 'codigo', titulo: 'Código' },
            { campo: 'nome', titulo: 'Promotor' },
            { campo: 'problemas', titulo: 'Falta', mostrar: (p) => p.problemas.join(', '), exportar: (p) => p.problemas.join(', ') },
          ]} />
        {dados.promotores_incompletos.length > 0 && <p className="dica">Corrija em <a href="#promotores">Promotores</a>.</p>}
      </Secao>

      <Secao titulo="Vínculos sem visitas por semana" quantidade={dados.roteiros_sem_visitas}
        explicacao="Sem as visitas por semana não dá para calcular o custo por visita, nem dividir o custo pelas visitas.">
        {dados.roteiros_sem_visitas > 0 && <p><a href="#roteiros">Preencher em Roteiros</a> (filtro "Sem visitas por semana").</p>}
      </Secao>

      <Secao titulo="PDVs sem CNPJ ou com CNPJ inválido" quantidade={dados.documentos.length}
        explicacao="Sem um CNPJ válido o PDV não consegue ser ligado ao faturamento.">
        <Tabela linhas={dados.documentos} arquivo="pdvs-cnpj" porPagina={20} vazio="Nenhum."
          colunas={[
            { campo: 'pdv', titulo: 'PDV', quebra: true },
            { campo: 'cnpj', titulo: 'CNPJ', mostrar: (p) => formatarCnpj(p.cnpj) },
            { campo: 'cidade', titulo: 'Cidade', mostrar: (p) => `${p.cidade}${p.uf ? ` - ${p.uf}` : ''}` },
            { campo: 'problema', titulo: 'Problema' },
          ]} />
      </Secao>


      {janela?.tipo === 'colaborador' && <ResolverColaborador pendencia={janela.pendencia} aoFechar={() => setJanela(null)} aoSalvar={concluir} />}
      {janela?.tipo === 'pdv' && (
        <FormularioPdv
          inicial={{ ...PDV_VAZIO, cnpj_cpf: janela.cliente.cnpj, nome_fantasia: janela.cliente.razao_social || '',
            razao_social: janela.cliente.razao_social || '', cidade: janela.cliente.cidade || '', uf: janela.cliente.uf || '' }}
          aoFechar={() => setJanela(null)} aoSalvar={concluir} />
      )}
    </>
  )
}
