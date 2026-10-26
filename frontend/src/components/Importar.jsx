import { useState } from 'react'
import { api } from '../api.js'

const TIPOS = [
  {
    tipo: 'faturamento',
    titulo: 'Faturamento',
    descricao: 'Exportação do ERP (uma linha por item de nota). Os meses do arquivo substituem os já importados.',
  },
  {
    tipo: 'promotores',
    titulo: 'Promotores',
    descricao: 'Aba PROMOTORES BRASIL. Cria ou atualiza promotores, supervisores e custos pelo código. Não apaga nada; custo diferente vira reajuste a partir deste mês.',
  },
  {
    tipo: 'roteiro',
    titulo: 'Roteiro',
    descricao: 'Abas SC, SP, PR… (Colaborador + Razão Social). Cria os PDVs e os vínculos que ainda não existem. Não apaga nada; colaborador não encontrado vira pendência.',
  },
]

function CartaoImportacao({ tipo, titulo, descricao, ultima, aoImportar }) {
  const [arquivo, setArquivo] = useState(null)
  const [enviando, setEnviando] = useState(false)
  const [resultado, setResultado] = useState(null)
  const [erro, setErro] = useState('')

  async function enviar() {
    setEnviando(true)
    setErro('')
    setResultado(null)
    try {
      setResultado(await api.importar(tipo, arquivo))
      setArquivo(null)
      aoImportar()
    } catch (e) {
      setErro(e.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="importar-cartao">
      <h3>{titulo}</h3>
      <p className="dica">{descricao}</p>
      {ultima && (
        <p className="dica">
          Última: <b>{ultima.arquivo}</b> em {new Date(ultima.data_hora).toLocaleString('pt-BR')}
        </p>
      )}
      <input type="file" accept=".xlsx,.xlsm,.csv" onChange={(e) => setArquivo(e.target.files[0] || null)} />
      <button disabled={!arquivo || enviando} onClick={enviar}>
        {enviando ? 'Importando… (arquivos grandes demoram)' : 'Importar'}
      </button>
      {erro && <p className="erro">{erro}</p>}
      {resultado && (
        <div className="sucesso">
          Importado.
          {resultado.meses && <> Meses: {resultado.meses.join(', ')}.</>}
          {resultado.cadastros && (
            <>
              {' '}Novos: {resultado.cadastros.criados}.
              {resultado.cadastros.atualizados != null && <> Atualizados: {resultado.cadastros.atualizados}.</>}
              {resultado.cadastros.reajustes != null && <> Reajustes: {resultado.cadastros.reajustes}.</>}
              {resultado.cadastros.mantidos != null && <> Já existiam: {resultado.cadastros.mantidos}.</>}
              {resultado.cadastros.pendentes != null && <> Pendências: {resultado.cadastros.pendentes}.</>}
            </>
          )}
          {resultado.avisos?.map((aviso) => <p key={aviso} className="aviso-texto">⚠ {aviso}</p>)}
        </div>
      )}
    </div>
  )
}

export default function Importar({ importacoes, aoImportar }) {
  return (
    <section className="importar">
      {TIPOS.map((t) => (
        <CartaoImportacao key={t.tipo} {...t} ultima={importacoes[t.tipo]} aoImportar={aoImportar} />
      ))}
    </section>
  )
}
