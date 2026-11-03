// Aba Lojas por UF: substitui as abas SC, SP, PR, MG e RS da planilha. Lojas e promotores vêm da planilha
// (ou são cadastrados aqui); o faturamento de cada mês é calculado com o arquivo do ERP.
import { useState } from 'react'
import { http } from '../api.js'
import { mascararDocumento, UFS } from '../formato.js'
import GradeMensal from './GradeMensal.jsx'
import { Envio, ResultadoCadastro } from './Importar.jsx'
import { FormularioPdv } from './cadastros/Pdvs.jsx'
import { EditarRoteiroModal, EncerrarModal, TrocarModal } from './cadastros/RoteiroModais.jsx'
import { Campo, EscolhaComBusca, Modal, useLista } from './ui.jsx'

export const UFS_DA_PLANILHA = ['SC', 'SP', 'PR', 'MG', 'RS']
// Padrão: início do ano, para a loja já aparecer nos meses do faturamento importado.
const inicioDoAno = () => `${new Date().getFullYear()}-01-01`

function NovaLojaModal({ promotores, ufInicial, aoFechar, aoSalvar }) {
  const [dados, setDados] = useState({
    pdv: { cnpj_cpf: '', nome_fantasia: '', razao_social: '', cod_cli_erp: '', cidade: '', uf: ufInicial || '' },
    promotor_id: null, data_inicio: inicioDoAno(), visitas_por_semana: null,
  })
  const [sugestao, setSugestao] = useState(null)
  const [erro, setErro] = useState('')
  const [enviando, setEnviando] = useState(false)
  const alterarPdv = (campo, valor) => setDados((d) => ({ ...d, pdv: { ...d.pdv, [campo]: valor } }))
  const alterar = (campo, valor) => setDados((d) => ({ ...d, [campo]: valor }))

  // Ao sair do campo CNPJ, completa razão social, cidade e UF com o que veio do ERP.
  async function buscarNoFaturamento() {
    const digitos = dados.pdv.cnpj_cpf.replace(/\D/g, '')
    if (digitos.length !== 11 && digitos.length !== 14) return
    try {
      const resposta = await http.get(`/api/pdvs/sugestao?cnpj=${digitos}`)
      setSugestao(resposta)
      if (resposta.encontrado) {
        setDados((d) => ({
          ...d,
          pdv: {
            ...d.pdv,
            nome_fantasia: d.pdv.nome_fantasia || resposta.razao_social,
            razao_social: d.pdv.razao_social || resposta.razao_social,
            cidade: d.pdv.cidade || resposta.cidade,
            uf: d.pdv.uf || resposta.uf,
            cod_cli_erp: d.pdv.cod_cli_erp || (resposta.cod_cli_erp.length === 1 ? resposta.cod_cli_erp[0] : ''),
          },
        }))
      }
    } catch {
      setSugestao(null)
    }
  }

  async function salvar() {
    setErro('')
    setEnviando(true)
    try {
      await http.post('/api/lojas', dados)
      aoSalvar()
    } catch (e) {
      setErro(e.message)
    } finally {
      setEnviando(false)
    }
  }

  const opcoesPromotor = promotores.filter((p) => p.ativo)
    .map((p) => ({ valor: p.id, texto: `${p.nome} (${p.codigo})${p.supervisor ? ` — ${p.supervisor}` : ''}` }))

  return (
    <Modal titulo="Cadastrar loja" aoFechar={aoFechar} largo
      rodape={
        <button onClick={salvar} disabled={enviando || !dados.pdv.nome_fantasia.trim() || !dados.promotor_id || !dados.data_inicio}>
          Salvar
        </button>
      }>
      <Campo rotulo="Promotor que atende">
        <EscolhaComBusca opcoes={opcoesPromotor} valor={dados.promotor_id} aoMudar={(v) => alterar('promotor_id', v)} />
      </Campo>
      <div className="campos-linha">
        <Campo rotulo="CNPJ ou CPF" dica="É por ele que o sistema acha o faturamento no ERP.">
          <input value={dados.pdv.cnpj_cpf} onChange={(e) => alterarPdv('cnpj_cpf', mascararDocumento(e.target.value))}
            onBlur={buscarNoFaturamento} placeholder="00.000.000/0000-00" />
        </Campo>
        <Campo rotulo="Código do cliente no ERP (COD CLI)" dica="Opcional. Separa o faturamento de lojas com o mesmo CNPJ.">
          <input value={dados.pdv.cod_cli_erp} onChange={(e) => alterarPdv('cod_cli_erp', e.target.value)} />
        </Campo>
      </div>
      {sugestao && (
        <p className={sugestao.encontrado ? 'texto-ok' : 'dica'}>
          {sugestao.encontrado
            ? `Encontrado no faturamento: ${sugestao.razao_social} (${sugestao.cidade}/${sugestao.uf}).`
            : 'Este CNPJ ainda não aparece no faturamento importado.'}
        </p>
      )}
      <Campo rotulo="Nome da loja (Razão Social na planilha)">
        <input value={dados.pdv.nome_fantasia} onChange={(e) => alterarPdv('nome_fantasia', e.target.value)} />
      </Campo>
      <div className="campos-linha">
        <Campo rotulo="Cidade"><input value={dados.pdv.cidade} onChange={(e) => alterarPdv('cidade', e.target.value)} /></Campo>
        <Campo rotulo="UF" largura="100px">
          <select value={dados.pdv.uf} onChange={(e) => alterarPdv('uf', e.target.value)}>
            <option value="">—</option>
            {UFS.map((u) => <option key={u}>{u}</option>)}
          </select>
        </Campo>
      </div>
      <div className="campos-linha">
        <Campo rotulo="Atende desde" dica="O faturamento da loja conta para o promotor a partir desta data.">
          <input type="date" value={dados.data_inicio} onChange={(e) => alterar('data_inicio', e.target.value)} />
        </Campo>
        <Campo rotulo="Visitas por semana">
          <select value={dados.visitas_por_semana ?? ''}
            onChange={(e) => alterar('visitas_por_semana', e.target.value ? Number(e.target.value) : null)}>
            <option value="">Não informado</option>
            {[1, 2, 3, 4, 5, 6, 7].map((n) => <option key={n} value={n}>{n}x por semana</option>)}
          </select>
        </Campo>
      </div>
      {erro && <p className="erro">{erro}</p>}
    </Modal>
  )
}

/** Botões de cada loja (só administrador): editar dados, visitas, trocar promotor e encerrar. */
function useAcoesDaLoja(aoAlterar) {
  const [roteiros, recarregarRoteiros] = useLista(() => http.get('/api/roteiros'))
  const [pdvs, recarregarPdvs] = useLista(() => http.get('/api/pdvs'))
  const [promotores] = useLista(() => http.get('/api/promotores'))
  const [janela, setJanela] = useState(null)

  const recarregar = () => {
    recarregarRoteiros()
    recarregarPdvs()
    aoAlterar()
  }
  const concluir = () => {
    setJanela(null)
    recarregar()
  }
  const roteiroDaLinha = (linha) => roteiros?.find((r) => r.id === linha.roteiro_id)

  function acoes(linha) {
    const roteiro = roteiroDaLinha(linha)
    if (!roteiro) return null
    const pdv = pdvs?.find((p) => p.id === roteiro.pdv_id)
    // Um menu só, para a linha não ficar alta com quatro botões.
    const opcoes = [
      pdv && ['pdv', 'Editar dados da loja'],
      roteiro.situacao !== 'encerrado' && ['visitas', 'Visitas por semana'],
      roteiro.situacao !== 'encerrado' && ['trocar', 'Trocar promotor'],
      roteiro.situacao !== 'encerrado' && ['encerrar', 'Encerrar atendimento'],
    ].filter(Boolean)
    return (
      <select className="menu-acoes" value="" aria-label="Alterar loja"
        onChange={(e) => setJanela({ tipo: e.target.value, pdv, roteiro })}>
        <option value="">Alterar…</option>
        {opcoes.map(([tipo, texto]) => <option key={tipo} value={tipo}>{texto}</option>)}
      </select>
    )
  }

  const fechar = () => setJanela(null)
  const janelas = (
    <>
      {janela?.tipo === 'pdv' && <FormularioPdv inicial={janela.pdv} aoFechar={fechar} aoSalvar={concluir} />}
      {janela?.tipo === 'visitas' && <EditarRoteiroModal roteiro={janela.roteiro} aoFechar={fechar} aoSalvar={concluir} />}
      {janela?.tipo === 'trocar' && promotores && (
        <TrocarModal roteiro={janela.roteiro} promotores={promotores} aoFechar={fechar} aoSalvar={concluir} />
      )}
      {janela?.tipo === 'encerrar' && <EncerrarModal roteiro={janela.roteiro} aoFechar={fechar} aoSalvar={concluir} />}
    </>
  )
  return { acoes, janelas, promotores, recarregar }
}

function ImportarAbas({ aoImportar }) {
  const [resultado, setResultado] = useState(null)
  return (
    <details className="bloco nao-imprimir">
      <summary>Importar as abas SC, SP, PR, MG e RS da planilha</summary>
      <div className="importar-cartao">
        <Envio
          titulo="Lojas e promotores das abas por UF"
          descricao={'Envie a planilha "ROTEIROS X FATURAMENTOS". O sistema lê as abas SC, SP, PR, MG e RS (Colaborador, ' +
            'CNPJ, Razão Social, Cidade, UF) e cria as lojas e os vínculos que ainda não existem. Não apaga nada. ' +
            'Importe antes os promotores (aba Promotores), para o sistema achar o colaborador de cada loja.'}
          aoEnviar={async (arquivo) => {
            setResultado(await http.enviarArquivo('/api/importacoes/roteiro', arquivo))
            aoImportar()
          }}
        />
        <ResultadoCadastro titulo="Lojas" resultado={resultado} />
      </div>
    </details>
  )
}

export default function LojasUf({ admin, uf, aoMudarUf, ufs, grade, aoAlterar, children }) {
  const [novaLoja, setNovaLoja] = useState(false)
  const { acoes, janelas, promotores, recarregar } = useAcoesDaLoja(aoAlterar)
  const outras = ufs.filter((u) => !UFS_DA_PLANILHA.includes(u))

  return (
    <>
      <nav className="abas-uf nao-imprimir">
        <button className={!uf ? 'ativo' : ''} onClick={() => aoMudarUf('')}>Todas</button>
        {[...UFS_DA_PLANILHA, ...outras].map((u) => (
          <button key={u} className={uf === u ? 'ativo' : ''} onClick={() => aoMudarUf(u)}>{u}</button>
        ))}
        {admin && (
          <button className="nova-loja" onClick={() => setNovaLoja(true)} disabled={!promotores}>+ Cadastrar loja</button>
        )}
      </nav>
      {admin && <ImportarAbas aoImportar={recarregar} />}
      {children}
      {grade && <GradeMensal grade={grade} acoes={admin ? acoes : undefined} />}
      {admin && janelas}
      {novaLoja && promotores && (
        <NovaLojaModal
          promotores={promotores}
          ufInicial={uf}
          aoFechar={() => setNovaLoja(false)}
          aoSalvar={() => { setNovaLoja(false); recarregar() }}
        />
      )}
    </>
  )
}
