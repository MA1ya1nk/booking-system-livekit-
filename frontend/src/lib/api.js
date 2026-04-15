const configuredBase = import.meta.env.VITE_API_BASE_URL
const trimmed = typeof configuredBase === 'string' ? configuredBase.trim() : ''

if (import.meta.env.PROD && !trimmed) {
  throw new Error(
    'VITE_API_BASE_URL is not set. Set it to your API base (e.g. https://api.example.com/api/v1) before building for production.',
  )
}

const API_BASE_URL = trimmed || 'http://localhost:8000/api/v1'

export async function apiRequest(path, { method = 'GET', token, body } = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })

  const isJson = response.headers.get('content-type')?.includes('application/json')
  const data = isJson ? await response.json() : null

  if (!response.ok) {
    const detail = data?.detail
    let message = 'Request failed'
    if (typeof detail === 'string') message = detail
    else if (Array.isArray(detail))
      message = detail.map((d) => (typeof d === 'object' ? d.msg || JSON.stringify(d) : String(d))).join('; ')
    throw new Error(message)
  }
  return data
}

export { API_BASE_URL }
