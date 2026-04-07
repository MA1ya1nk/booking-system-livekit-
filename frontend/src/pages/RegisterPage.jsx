import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { useAuth } from '../context/AuthContext'
import { apiRequest } from '../lib/api'

function RegisterPage() {
  const navigate = useNavigate()
  const { setAuthToken } = useAuth()
  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [error, setError] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    try {
      const data = await apiRequest('/auth/register', { method: 'POST', body: form })
      setAuthToken(data.access_token)
      navigate('/dashboard')
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <AppShell title="Register">
      <form className="form" onSubmit={handleSubmit}>
        <input
          placeholder="Full name"
          value={form.name}
          onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
        />
        <input
          placeholder="Email"
          type="email"
          value={form.email}
          onChange={(e) => setForm((prev) => ({ ...prev, email: e.target.value }))}
        />
        <input
          placeholder="Password"
          type="password"
          value={form.password}
          onChange={(e) => setForm((prev) => ({ ...prev, password: e.target.value }))}
        />
        <button className="btn primary" type="submit">
          Register
        </button>
        {error ? <p className="error">{error}</p> : null}
      </form>
      <p className="footnote">
        Already registered? <Link to="/login">Go to login</Link>
      </p>
    </AppShell>
  )
}

export default RegisterPage
