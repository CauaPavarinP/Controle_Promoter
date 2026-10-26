const NOMES = { faturamento: 'Faturamento', promotores: 'Promotores', roteiro: 'Roteiro' }

export default function Avisos({ opcoes }) {
  const semVinculo = opcoes.roteiro_sem_vinculo || []
  const importacoes = Object.entries(opcoes.importacoes || {})
  const nenhum = !semVinculo.length && importacoes.every(([, i]) => !i.avisos?.length)

  return (
    <>
      {nenhum && <div className="bloco vazio">Nenhum aviso. Os dados importados não têm problemas conhecidos.</div>}

      {semVinculo.length > 0 && (
        <section className="bloco">
          <h2>Colaboradores do roteiro sem cadastro de promotor ({semVinculo.length})</h2>
          <p className="dica">
            As lojas destes colaboradores ficaram fora dos roteiros na importação. Normalmente o nome está escrito diferente
            entre as abas do roteiro e a aba PROMOTORES BRASIL, ou a pessoa não está cadastrada. Cadastre o promotor (ou
            corrija o nome) e importe o roteiro de novo, ou vincule os PDVs em Roteiros.
          </p>
          <ul className="lista-avisos">
            {semVinculo.map((nome) => <li key={nome}>{nome}</li>)}
          </ul>
        </section>
      )}

      {importacoes.map(([tipo, info]) =>
        info.avisos?.length ? (
          <section className="bloco" key={tipo}>
            <h2>{NOMES[tipo] || tipo}</h2>
            <p className="dica">
              Última importação: <b>{info.arquivo}</b> em {new Date(info.data_hora).toLocaleString('pt-BR')}
            </p>
            <ul className="lista-avisos">
              {info.avisos.map((aviso) => <li key={aviso}>⚠ {aviso}</li>)}
            </ul>
          </section>
        ) : null,
      )}
    </>
  )
}
