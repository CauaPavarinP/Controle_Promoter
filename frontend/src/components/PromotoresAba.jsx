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
    </>
  )
}
