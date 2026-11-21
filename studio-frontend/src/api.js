export async function request(path, options={}) {
  const res = await fetch('/api' + path, {
    headers: {'Content-Type':'application/json'},
    ...options,
  })
  let data = null
  try { data = await res.json() } catch { throw new Error('Invalid response from the TraceMind API') }
  if (!res.ok) throw new Error(typeof data.detail==='string' ? data.detail : `Request failed (${res.status})`)
  return data
}
export function withQuery(path, params) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([k,v])=>{ if (v !== undefined && v !== null && v !== '') search.set(k, String(v)) })
  return `${path}?${search.toString()}`
}
export const fmtDate = (value) => {
  if (!value) return '—'
  const d = new Date(value.length===10 ? `${value}T12:00:00Z` : value)
  return Number.isNaN(d.getTime()) ? value : new Intl.DateTimeFormat('en-GB',{day:'numeric',month:'short',timeZone:'UTC'}).format(d)
}
export const fmtTime = (value) => {
  if (!value) return '—'
  const d=new Date(value)
  return Number.isNaN(d.getTime()) ? value : new Intl.DateTimeFormat('en-GB',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',timeZone:'UTC'}).format(d)+' UTC'
}
