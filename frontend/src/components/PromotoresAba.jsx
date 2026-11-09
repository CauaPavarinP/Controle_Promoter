// Aba Promotores: cadastro dos promotores (como a aba PROMOTORES BRASIL), com importação da planilha.
import { useState } from 'react'
import { http } from '../api.js'
import { Envio, ResultadoCadastro } from './Importar.jsx'
import Promotores from './cadastros/Promotores.jsx'
import Supervisores from './cadastros/Supervisores.jsx'

export default function PromotoresAba({ admin }) {
  const [resultado, setResultado] = useState(null)
  // Muda depois de importar, para a lista de promotores recarregar.
  const [versao, setVersao] = useState(0)

  return (
    <>
      {admin && (
        <details className="bloco nao-imprimir">
          <summary>Importar a aba PROMOTORES BRASIL da planilha</summary>
          <div className="importar-cartao">
            <Envio
              titulo="Promotores e custos"
              descricao={'Envie a planilha "ROTEIROS X FATURAMENTOS". O sistema lê a aba PROMOTORES BRASIL (código, ' +
                'colaborador, admissão, salário, ajuda de custo, vale-transporte, município, UF e supervisor). Cria ou ' +
                'atualiza pelo código; custo diferente vira reajuste a partir deste mês. Não apaga nada.'}
              aoEnviar={async (arquivo) => {
                setResultado(await http.enviarArquivo('/api/importacoes/promotores', arquivo))
                setVersao((v) => v + 1)
              }}
            />
            <ResultadoCadastro titulo="Promotores" resultado={resultado} />
          </div>
        </details>
      )}
      <Promotores key={versao} podeEditar={admin} />
      <details className="bloco">
        <summary>Supervisores</summary>
        <Supervisores key={versao} podeEditar={admin} />
      </details>
      {admin && <ApagarCadastros />}
    </>
  )
}

/** Apaga promotores, custos, lojas e roteiros para importar a planilha do zero. Não tem volta. */
function ApagarCadastros() {
  const [apagando, setApagando] = useState(false)

  async function apagar() {
    const resposta = window.prompt(
      'Isto apaga TODOS os promotores, custos, lojas (PDVs), roteiros, colaboradores não encontrados e ligações ' +
      'lembradas. Não tem volta.\n\nFica: faturamento do ERP, usuários, regras e o histórico de importações.\n\n' +
      'Para confirmar, digite APAGAR:')
    if (resposta === null) return
    setApagando(true)
    try {
      const apagados = await http.post('/api/cadastros/apagar', { confirmacao: resposta })
      window.alert(`Cadastros apagados: ${apagados.promotores} promotores, ${apagados.custos} custos, ` +
        `${apagados.lojas} lojas, ${apagados.roteiros} roteiros e ${apagados.supervisores} supervisores.\n\n` +
        'Agora importe a aba PROMOTORES BRASIL e depois as abas SC, SP, PR, MG e RS.')
      window.location.reload()
    } catch (e) {
      window.alert(e.message)
    } finally {
      setApagando(false)
    }
  }

  return (
    <details className="bloco nao-imprimir">
      <summary>Apagar cadastros e começar do zero</summary>
      <p className="dica">
        Apaga todos os promotores, custos, lojas (PDVs), roteiros, colaboradores não encontrados e ligações lembradas,
        para importar a planilha de novo do zero. <b>Não tem volta.</b> O faturamento do ERP, os usuários, as regras
        do cálculo e o histórico de importações ficam. Supervisor ligado a um usuário também fica.
      </p>
      <button className="secundario perigo" disabled={apagando} onClick={apagar}>
        {apagando ? 'Apagando…' : 'Apagar cadastros…'}
      </button>
    </details>
  )
}
