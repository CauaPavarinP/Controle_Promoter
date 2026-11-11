// Aba Agências: importa o arquivo que cada agência (ou MEI, ou a própria 101 com promotores CLT) manda no modelo
// único, e mostra o resultado de cada agência: lojas, promotores, quanto custou e quanto as lojas compraram.
import { useEffect, useState } from 'react'
import { http } from '../api.js'
import { formatarDataHora, formatarMes, formatarMoeda } from '../formato.js'
import { Envio, Historico } from './Importar.jsx'
import { COLUNAS_SE_PAGA, OpcaoOcultarSemCusto, QuadroSePaga, useOcultarSemCusto, useSePaga } from './SePaga.jsx'
import { Tabela } from './ui.jsx'

function RepetidasOutraAgencia({ repetidas, escolha, setEscolha }) {
  const existentes = [...new Set(repetidas.map((r) => r.agencia_existente))]
  return (
    <div className="caixa-alerta repetidas">
      <p>
        <b>⚠ {repetidas.length} loja(s) deste arquivo já estão no sistema, no mesmo mês, por outra agência</b>{' '}
        ({existentes.join(', ')}). Se for o mesmo atendimento com outro nome de agência, gravar as duas conta o custo
        duas vezes.
      </p>
      <Tabela
        chave="chave"
        linhas={repetidas.map((r, i) => ({ ...r, chave: i }))}
        porPagina={10}
        arquivo="lojas-repetidas"
        colunas={[
          { campo: 'mes', titulo: 'Mês', mostrar: (r) => formatarMes(r.mes) },
          { campo: 'loja', titulo: 'Loja (neste arquivo)', quebra: true },
          { campo: 'cnpj', titulo: 'CNPJ', mostrar: (r) => r.cnpj || <span className="texto-alerta">sem CNPJ (pelo nome)</span> },
          { campo: 'agencia_nova', titulo: 'Agência neste arquivo', quebra: true },
          { campo: 'agencia_existente', titulo: 'Já está no sistema por', quebra: true },
        ]}
      />
      <fieldset className="escolha">
        <legend>O que fazer com essas lojas?</legend>
        <label className="marcar">
          <input type="radio" name="repetidas" checked={escolha === 'ignorar'} onChange={() => setEscolha('ignorar')} />
          <span><b>Ignorar as repetidas</b>: grava só as lojas novas do arquivo; as que já estão ficam como estão.</span>
        </label>
        <label className="marcar">
          <input type="radio" name="repetidas" checked={escolha === 'substituir'} onChange={() => setEscolha('substituir')} />
          <span>
            <b>Substituir</b>: tira essas lojas da outra agência nesses meses e grava as deste arquivo. Desfazer esta
            importação depois <b>não</b> devolve as lojas à outra agência: para voltar atrás, importe de novo o arquivo
            dela.
          </span>
        </label>
        <p className="dica">Ou clique em <b>Cancelar</b> para não gravar nada.</p>
      </fieldset>
    </div>
  )
}

function PreviaAtendimento({ previa, aoConcluir, aoCancelar }) {
  const [substituir, setSubstituir] = useState(false)
  const [escolha, setEscolha] = useState(null)
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState('')
  const existentes = previa.substituir.length > 0
  const repetidas = previa.repetidas_outra_agencia || []
  const invalidos = previa.cnpjs_invalidos || []
  const descartadas = previa.descartadas || []

  async function confirmar() {
    setEnviando(true)
    setErro('')
    try {
      aoConcluir(await http.post(`/api/importacoes/atendimento/${previa.token}/confirmar`,
        { substituir, repetidas: repetidas.length ? escolha : null }))
    } catch (e) {
      setErro(e.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="previa">
      <h3>Confira antes de gravar — {previa.arquivo}</h3>
      <div className="previa-numeros">
        <div><span>Linhas</span><b>{previa.linhas_validas} válidas{previa.linhas_com_erro > 0 && <span className="texto-critico"> · {previa.linhas_com_erro} com erro</span>}</b></div>
        <div><span>Lojas</span><b>{previa.lojas}</b></div>
        <div><span>Promotores</span><b>{previa.promotores}</b></div>
        <div><span>Valor total</span><b>{formatarMoeda(previa.valor_total)}</b></div>
      </div>
      <Tabela
        chave="chave"
        linhas={previa.grupos.map((g) => ({ ...g, chave: `${g.agencia}-${g.mes}` }))}
        porPagina={24}
        colunas={[
          { campo: 'agencia', titulo: 'Agência', quebra: true },
          { campo: 'mes', titulo: 'Mês', mostrar: (g) => formatarMes(g.mes) },
          { campo: 'lojas', titulo: 'Lojas', num: true },
          { campo: 'promotores', titulo: 'Promotores', num: true },
          { campo: 'visitas', titulo: 'Visitas', num: true },
          { campo: 'valor', titulo: 'Valor', num: true, mostrar: (g) => formatarMoeda(g.valor) },
          { campo: 'ja_existe', titulo: '', semOrdem: true,
            mostrar: (g) => (g.ja_existe ? <span className="etiqueta">já importado: será substituído</span> : '') },
        ]}
      />
      {repetidas.length > 0 && <RepetidasOutraAgencia repetidas={repetidas} escolha={escolha} setEscolha={setEscolha} />}
      {previa.avisos.map((a) => <p key={a} className="aviso-texto">⚠ {a}</p>)}
      {invalidos.length > 0 && (
        <details open className="caixa-alerta">
          <summary><b>CNPJ inválido ({invalidos.length})</b>: essas lojas entram sem CNPJ e sem faturamento. Peça a correção à agência.</summary>
          <Tabela chave="chave" linhas={invalidos.map((c, i) => ({ ...c, chave: i }))} porPagina={10} arquivo="cnpj-invalido"
            colunas={[{ campo: 'linha', titulo: 'Linha', num: true }, { campo: 'aba', titulo: 'Aba' },
              { campo: 'loja', titulo: 'Loja', quebra: true },
              { campo: 'cnpj', titulo: 'CNPJ informado', mostrar: (c) => <b className="texto-critico">{c.cnpj || '(vazio)'}</b> },
              { campo: 'motivo', titulo: 'Motivo' }]} />
        </details>
      )}
      {descartadas.length > 0 && (
        <details>
          <summary>Linhas descartadas ({descartadas.length}): cabeçalho repetido ou título no meio do arquivo</summary>
          <Tabela chave="chave" linhas={descartadas.map((d, i) => ({ ...d, chave: i }))} porPagina={10} arquivo="linhas-descartadas"
            colunas={[{ campo: 'linha', titulo: 'Linha', num: true }, { campo: 'aba', titulo: 'Aba' },
              { campo: 'motivo', titulo: 'Motivo' }, { campo: 'conteudo', titulo: 'Conteúdo da linha', quebra: true }]} />
        </details>
      )}
      {previa.linhas_com_erro > 0 && (
        <details>
          <summary>Ver linhas com erro (ficam de fora)</summary>
          <Tabela chave="linha" linhas={previa.erros} porPagina={20} arquivo="linhas-com-erro"
            colunas={[{ campo: 'aba', titulo: 'Aba' }, { campo: 'linha', titulo: 'Linha no Excel', num: true },
              { campo: 'motivo', titulo: 'Motivo' }]} />
        </details>
      )}
      {existentes && (
        <label className="marcar caixa-alerta">
          <input type="checkbox" checked={substituir} onChange={(e) => setSubstituir(e.target.checked)} />
          Já existe atendimento importado de {previa.substituir.join(', ')}. Substituir (apaga o que está no sistema
          dessas agências nesses meses e grava o arquivo novo).
        </label>
      )}
      {erro && <p className="erro">{erro}</p>}
      <div className="acoes">
        <button onClick={confirmar} disabled={enviando || (existentes && !substituir) || (repetidas.length > 0 && !escolha)}>
          {enviando ? 'Gravando…' : 'Gravar atendimento'}
        </button>
        <button className="secundario" onClick={aoCancelar} disabled={enviando}>Cancelar</button>
      </div>
    </div>
  )
}

function Importacao({ aoImportar }) {
  const [previa, setPrevia] = useState(null)
  const [concluido, setConcluido] = useState(null)
  const [versao, setVersao] = useState(0)
  return (
    <>
      <section className="importar">
        <div className="importar-cartao destaque">
          <Envio
            titulo="Importar o arquivo de uma agência"
            descricao={'Arquivo no modelo "Atendimento das agências" (uma linha por loja: mês, agência, CNPJ, loja, ' +
              'promotor, dias, visitas e valor do mês). Pode ter uma ou várias agências e meses. Você confere o resumo ' +
              'antes de gravar; agência e mês que já existem só são substituídos se você confirmar.'}
            rotulo="Ler arquivo"
            aoEnviar={async (arquivo) => {
              setConcluido(null)
              setPrevia(await http.enviarArquivo('/api/importacoes/atendimento/previa', arquivo))
            }}
          />
          <p className="dica">
            <a href="/api/modelo-atendimento">Baixar o modelo em Excel</a> para mandar às agências (com instruções e
            conferência do CNPJ).
          </p>
        </div>
      </section>
      {previa && (
        <section className="bloco">
          <PreviaAtendimento previa={previa} aoCancelar={() => setPrevia(null)}
            aoConcluir={(r) => { setPrevia(null); setConcluido(r); setVersao((v) => v + 1); aoImportar() }} />
        </section>
      )}
      {concluido && (
        <div className="sucesso">
          Atendimento gravado: {concluido.linhas_importadas} linha(s) de {concluido.meses.map(formatarMes).join(', ')}.
          {concluido.substituidos.length > 0 && <> Substituídos: {concluido.substituidos.join(', ')}.</>}
          {concluido.repetidas_ignoradas > 0 && <> {concluido.repetidas_ignoradas} loja(s) repetida(s) ignorada(s).</>}
          {concluido.repetidas_substituidas > 0 && <> {concluido.repetidas_substituidas} loja(s) tirada(s) da outra agência.</>}
        </div>
      )}
      <details className="bloco">
        <summary>Histórico de importações das agências</summary>
        <Historico versao={versao} aoDesfazer={() => { setVersao((v) => v + 1); aoImportar() }} tipos={['atendimento', 'limpeza']} />
      </details>
    </>
  )
}

function Backups({ versao }) {
  const [lista, setLista] = useState(null)
  useEffect(() => {
    http.get('/api/backups').then(setLista).catch(() => setLista([]))
  }, [versao])
  if (!lista?.length) return <p className="dica">Nenhum backup guardado ainda.</p>
  return (
    <ul className="lista-backups">
      {lista.map((b) => (
        <li key={b.id}>
          <a href={`/api/backups/${b.id}`} download>{b.arquivo}</a>{' '}
          <span className="dica">· {b.linhas} linha(s) · {b.motivo} · {b.usuario} · {formatarDataHora(b.criado_em)}</span>
        </li>
      ))}
    </ul>
  )
}

function ApagarDados({ aoApagar }) {
  const [texto, setTexto] = useState('')
  const [mensagem, setMensagem] = useState(null)
  const [versao, setVersao] = useState(0)
  async function apagar() {
    try {
      const r = await http.post('/api/cadastros/apagar', { confirmacao: texto })
      setTexto('')
      setMensagem({ erro: false, texto: `Apagados ${r.atendimentos} atendimento(s).` +
        (r.backup_arquivo ? ` Backup guardado: ${r.backup_arquivo} (lista abaixo; dá para importar de novo).` : '') })
      setVersao((v) => v + 1)
      aoApagar()
    } catch (e) {
      setMensagem({ erro: true, texto: e.message })
    }
  }
  return (
    <details className="bloco nao-imprimir">
      <summary>Apagar os dados das agências e começar do zero</summary>
      <p className="dica">
        Apaga todos os atendimentos importados das agências (e o que sobrou dos cadastros da planilha antiga).
        Antes de apagar, o sistema guarda um <b>backup</b> no banco: um Excel no modelo das agências, que dá para
        importar de novo. O faturamento do ERP, os usuários, as regras e o histórico de importações ficam.
      </p>
      <div className="acoes">
        <input value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Digite APAGAR"
          aria-label="Para confirmar, digite APAGAR" />
        <button className="secundario perigo" disabled={texto.trim().toUpperCase() !== 'APAGAR'} onClick={apagar}>Apagar dados</button>
      </div>
      {mensagem && <p className={mensagem.erro ? 'erro' : 'texto-ok'}>{mensagem.texto}</p>}
      <h3>Backups guardados</h3>
      <p className="dica">
        Os 10 mais recentes. <a href="/api/atendimentos/exportar" download>Baixar agora uma cópia de tudo o que está no
        sistema</a>.
      </p>
      <Backups versao={versao} />
    </details>
  )
}

export default function Agencias({ admin, meses, aoImportar }) {
  const sePaga = useSePaga(meses)
  const recarregar = () => { sePaga.recarregar(); aoImportar() }
  const ocultacao = useOcultarSemCusto(sePaga.dados?.agencias)
  const agencias = (sePaga.dados?.agencias || []).filter((a) => ocultacao.visivel([a.chave]))
  return (
    <>
      {admin && <Importacao aoImportar={recarregar} />}
      {meses.length > 0 && (
        <>
          <QuadroSePaga titulo="As agências valem o que custam?" meses={meses} periodo={sePaga.periodo} contar="agencias"
            linhas={sePaga.dados ? agencias : undefined}
            setPeriodo={sePaga.setPeriodo} dados={sePaga.dados} podeEditar={admin} aoMudarLimite={sePaga.recarregar} />
          {sePaga.erro && <div className="erro-caixa">{sePaga.erro}</div>}
          <section className="bloco">
            <div className="bloco-cabecalho">
              <h2>Agências ({sePaga.dados ? agencias.length : '…'})</h2>
              <div className="bloco-ferramentas"><OpcaoOcultarSemCusto {...ocultacao} /></div>
            </div>
            {!sePaga.dados ? <p className="carregando">Calculando…</p> : (
              <Tabela
                chave="chave"
                linhas={agencias}
                arquivo="agencias"
                vazio="Nenhuma agência neste período. Importe os arquivos das agências."
                colunas={[
                  { campo: 'nome', titulo: 'Agência ou MEI', quebra: true },
                  { campo: 'tipo', titulo: 'Tipo' },
                  { campo: 'ufs', titulo: 'UF' },
                  { campo: 'lojas', titulo: 'Lojas', num: true, formato: 'inteiro' },
                  { campo: 'promotores', titulo: 'Promotores', num: true, formato: 'inteiro' },
                  { campo: 'visitas', titulo: 'Visitas', num: true, formato: 'inteiro' },
                  { campo: 'meses', titulo: 'Meses com arquivo', semOrdem: true,
                    mostrar: (a) => (a.meses.length > 1
                      ? `${formatarMes(a.meses[0])} a ${formatarMes(a.meses[a.meses.length - 1])} (${a.meses.length})`
                      : formatarMes(a.meses[0])),
                    exportar: (a) => a.meses.join(', ') },
                  ...COLUNAS_SE_PAGA,
                ]}
              />
            )}
          </section>
        </>
      )}
      {admin && <ApagarDados aoApagar={recarregar} />}
    </>
  )
}
