import { useState } from 'react'
import { http } from '../../api.js'
import { formatarCnpj, mascararDocumento, UFS } from '../../formato.js'
import { Campo, Modal, Situacao, Tabela, useLista } from '../ui.jsx'

const PDV_VAZIO = { cnpj_cpf: '', nome_fantasia: '', razao_social: '', cod_cli_erp: '', cidade: '', uf: '' }

function FormularioPdv({ inicial, aoFechar, aoSalvar }) {
  const [dados, setDados] = useState({ ...inicial, cnpj_cpf: mascararDocumento(inicial.cnpj_cpf || '') })
  const [sugestao, setSugestao] = useState(null)
  const [erro, setErro] = useState('')
  const alterar = (campo, valor) => setDados((d) => ({ ...d, [campo]: valor }))

  // Ao sair do campo CNPJ, procura o cliente no faturamento importado e completa o que estiver vazio.
  async function buscarNoFaturamento() {
    const digitos = dados.cnpj_cpf.replace(/\D/g, '')
    if (digitos.length !== 11 && digitos.length !== 14) return
    try {
      const resposta = await http.get(`/api/pdvs/sugestao?cnpj=${digitos}`)
      setSugestao(resposta)
      if (resposta.encontrado) {
        setDados((d) => ({
          ...d,
          razao_social: d.razao_social || resposta.razao_social,
          cidade: d.cidade || resposta.cidade,
          uf: d.uf || resposta.uf,
          cod_cli_erp: d.cod_cli_erp || (resposta.cod_cli_erp.length === 1 ? resposta.cod_cli_erp[0] : ''),
        }))
      }
    } catch {
      setSugestao(null)
    }
  }

  async function salvar() {
    setErro('')
    try {
      if (inicial.id) await http.put(`/api/pdvs/${inicial.id}`, dados)
      else await http.post('/api/pdvs', dados)
      aoSalvar()
    } catch (e) {
      setErro(e.message)
    }
  }

  return (
    <Modal titulo={inicial.id ? 'Editar PDV' : 'Novo PDV'} aoFechar={aoFechar} largo
      rodape={<button onClick={salvar} disabled={!dados.nome_fantasia.trim()}>Salvar</button>}>
      <div className="campos-linha">
        <Campo rotulo="CNPJ ou CPF" dica="Deixe vazio se não souber: o PDV fica sem faturamento até ter o CNPJ.">
          <input value={dados.cnpj_cpf} onChange={(e) => alterar('cnpj_cpf', mascararDocumento(e.target.value))}
            onBlur={buscarNoFaturamento} placeholder="00.000.000/0000-00" />
        </Campo>
        <Campo rotulo="Código do cliente no ERP (COD CLI)" dica="Serve para separar o faturamento de lojas com o mesmo CNPJ.">
          <input value={dados.cod_cli_erp} onChange={(e) => alterar('cod_cli_erp', e.target.value)} />
        </Campo>
      </div>
      {sugestao && (
        <p className={sugestao.encontrado ? 'texto-ok' : 'dica'}>
          {sugestao.encontrado
            ? `Encontrado no faturamento: ${sugestao.razao_social} (${sugestao.cidade}/${sugestao.uf}). Códigos de cliente: ${sugestao.cod_cli_erp.join(', ') || '—'}.`
            : 'Este CNPJ ainda não aparece no faturamento importado.'}
        </p>
      )}
      <Campo rotulo="Nome do PDV" dica='O nome usado no dia a dia, ex.: "GIASSI - AREIAS".'>
        <input value={dados.nome_fantasia} onChange={(e) => alterar('nome_fantasia', e.target.value)} />
      </Campo>
      <Campo rotulo="Razão social (do ERP)">
        <input value={dados.razao_social} onChange={(e) => alterar('razao_social', e.target.value)} />
      </Campo>
      <div className="campos-linha">
        <Campo rotulo="Cidade"><input value={dados.cidade} onChange={(e) => alterar('cidade', e.target.value)} /></Campo>
        <Campo rotulo="UF" largura="100px">
          <select value={dados.uf} onChange={(e) => alterar('uf', e.target.value)}>
            <option value="">—</option>
            {UFS.map((u) => <option key={u}>{u}</option>)}
          </select>
        </Campo>
      </div>
      {erro && <p className="erro">{erro}</p>}
    </Modal>
  )
}

export default function Pdvs({ podeEditar }) {
  const [pdvs, recarregar, erroLista] = useLista(() => http.get('/api/pdvs'))
  const [filtros, setFiltros] = useState({ busca: '', uf: '', situacao: 'ativos', especial: '' })
  const [edicao, setEdicao] = useState(null)
  const [erro, setErro] = useState('')

  async function executar(acao) {
    setErro('')
    try {
      await acao()
      recarregar()
    } catch (e) {
      setErro(e.message)
    }
  }

  if (!pdvs) return erroLista ? <div className="erro-caixa">{erroLista}</div> : <p>Carregando…</p>
  const termo = filtros.busca.trim().toLowerCase()
  const termoDigitos = termo.replace(/\D/g, '')
  const visiveis = pdvs.filter((p) =>
    (filtros.situacao === 'todos' || (filtros.situacao === 'ativos') === p.ativo) &&
    (!filtros.uf || p.uf === filtros.uf) &&
    (filtros.especial !== 'compartilhado' || p.lojas_mesmo_cnpj > 1) &&
    (filtros.especial !== 'sem_cnpj' || !p.cnpj_cpf) &&
    (filtros.especial !== 'sem_promotor' || !p.promotores.length) &&
    (!termo || `${p.nome_fantasia} ${p.razao_social} ${p.cidade}`.toLowerCase().includes(termo) ||
      (termoDigitos.length >= 3 && p.cnpj_cpf.includes(termoDigitos))))
  const ufs = [...new Set(pdvs.map((p) => p.uf).filter(Boolean))].sort()

  const colunas = [
    {
      campo: 'nome_fantasia', titulo: 'PDV', quebra: true,
      mostrar: (p) => (
        <>
          {p.nome_fantasia}
          {p.lojas_mesmo_cnpj > 1 && (
            <span className="etiqueta" title="Outras lojas usam o mesmo CNPJ: o faturamento delas é compartilhado">
              CNPJ em {p.lojas_mesmo_cnpj} lojas
            </span>
          )}
        </>
      ),
    },
    { campo: 'cnpj_cpf', titulo: 'CNPJ/CPF', mostrar: (p) => formatarCnpj(p.cnpj_cpf), exportar: (p) => formatarCnpj(p.cnpj_cpf) },
    { campo: 'cod_cli_erp', titulo: 'Cód. cliente' },
    { campo: 'cidade', titulo: 'Cidade', mostrar: (p) => `${p.cidade}${p.uf ? ` - ${p.uf}` : ''}` },
    {
      campo: 'promotores', titulo: 'Promotor atual', quebra: true,
      mostrar: (p) => p.promotores.join(', ') || <span className="texto-alerta">sem promotor</span>,
      exportar: (p) => p.promotores.join(', '), ordenar: (p) => p.promotores.join(', '),
    },
    { campo: 'ativo', titulo: 'Situação', mostrar: (p) => <Situacao ativo={p.ativo} />, exportar: (p) => (p.ativo ? 'Ativo' : 'Inativo') },
  ]
  if (podeEditar) {
    colunas.push({
      campo: 'acoes', titulo: '', semOrdem: true, semExportar: true,
      mostrar: (p) => (
        <div className="acoes">
          <button className="secundario" onClick={() => setEdicao(p)}>Editar</button>
          {p.ativo ? (
            <button className="secundario perigo" onClick={() => executar(() => http.post(`/api/pdvs/${p.id}/inativar`))}>Inativar</button>
          ) : (
            <button className="secundario" onClick={() => executar(() => http.post(`/api/pdvs/${p.id}/reativar`))}>Reativar</button>
          )}
        </div>
      ),
    })
  }

  return (
    <section className="bloco">
      <div className="bloco-cabecalho">
        <div className="bloco-ferramentas">
          <input placeholder="Buscar nome, cidade ou CNPJ" value={filtros.busca} onChange={(e) => setFiltros({ ...filtros, busca: e.target.value })} />
          <select value={filtros.uf} onChange={(e) => setFiltros({ ...filtros, uf: e.target.value })}>
            <option value="">Todas as UFs</option>
            {ufs.map((u) => <option key={u}>{u}</option>)}
          </select>
          <select value={filtros.situacao} onChange={(e) => setFiltros({ ...filtros, situacao: e.target.value })}>
            <option value="ativos">Ativos</option>
            <option value="inativos">Inativos</option>
            <option value="todos">Todos</option>
          </select>
          <select value={filtros.especial} onChange={(e) => setFiltros({ ...filtros, especial: e.target.value })}>
            <option value="">Todos os PDVs</option>
            <option value="compartilhado">CNPJ usado por mais de uma loja</option>
            <option value="sem_cnpj">Sem CNPJ</option>
            <option value="sem_promotor">Sem promotor</option>
          </select>
        </div>
        {podeEditar && <button onClick={() => setEdicao(PDV_VAZIO)}>+ Novo PDV</button>}
      </div>
      {erro && <div className="erro-caixa">{erro}</div>}
      <Tabela linhas={visiveis} colunas={colunas} arquivo="pdvs" />
      {edicao && <FormularioPdv inicial={edicao} aoFechar={() => setEdicao(null)} aoSalvar={() => { setEdicao(null); recarregar() }} />}
    </section>
  )
}
