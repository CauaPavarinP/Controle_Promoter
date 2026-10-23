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
    descricao: 'Lista com código, colaborador, supervisor e custo (aba PROMOTORES BRASIL). Substitui a lista atual.',
  },
  {
    tipo: 'roteiro',
    titulo: 'Roteiro',
    descricao: 'Qual promotor atende qual loja (abas SC, SP… com Colaborador e Razão Social). Substitui o roteiro atual.',
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
          {resultado.promotores != null && <> {resultado.promotores} promotor(es).</>}
          {resultado.lojas != null && <> {resultado.lojas} loja(s).</>}
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
