const moeda = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })
const NOMES_MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']

export const formatarMoeda = (valor) => (valor == null ? '—' : moeda.format(valor))

export const formatarPercentual = (valor) =>
  valor == null ? '—' : `${valor.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`

// "2026-04" -> "abr/2026"
export const formatarMes = (anoMes) => {
  const [ano, mes] = anoMes.split('-')
  return `${NOMES_MESES[Number(mes) - 1]}/${ano}`
}

export const formatarCnpj = (cnpj) =>
  cnpj && cnpj.length === 14
    ? cnpj.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5')
    : cnpj || 'sem CNPJ'

// Cor do "% custo sobre faturamento". As faixas vêm das regras salvas na aba "Regras do cálculo".
export function classePercentual(valor, regras) {
  if (valor == null) return 'pct-sem'
  if (valor >= regras.faixa_critico) return 'pct-critico'
  if (valor >= regras.faixa_alerta) return 'pct-alerta'
  return 'pct-ok'
}
