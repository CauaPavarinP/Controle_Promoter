import { useState } from 'react'
import { http } from '../../api.js'
import { mascararDocumento, UFS } from '../../formato.js'
import { Campo, Modal } from '../ui.jsx'

export const PDV_VAZIO = { cnpj_cpf: '', nome_fantasia: '', razao_social: '', cod_cli_erp: '', cidade: '', uf: '' }

export function FormularioPdv({ inicial, aoFechar, aoSalvar }) {
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
