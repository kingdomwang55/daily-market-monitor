export function formatDateTime(value: string | null, options?: Intl.DateTimeFormatOptions): string {
  if (!value) return '-'
  const normalized = value.endsWith('Z') ? value : `${value}Z`
  return new Intl.DateTimeFormat('zh-CN', options ?? {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(normalized))
}

export function formatMoney(value: number | null): string {
  if (value === null) return '-'
  return new Intl.NumberFormat('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    signDisplay: 'always',
  }).format(value)
}

export function formatPercent(value: number | null): string {
  if (value === null) return '-'
  return new Intl.NumberFormat('zh-CN', {
    style: 'percent',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    signDisplay: 'always',
  }).format(value)
}
