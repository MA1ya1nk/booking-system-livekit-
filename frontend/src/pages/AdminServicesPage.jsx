import { useCallback, useEffect, useState } from 'react'
import AppShell from '../components/AppShell'
import { useAuth } from '../context/AuthContext'
import { apiRequest } from '../lib/api'

function AdminServicesPage() {
  const { token } = useAuth()
  const [services, setServices] = useState([])
  const [error, setError] = useState('')
  const [form, setForm] = useState({
    name: '',
    slot_duration_minutes: '15',
    slot_start_time: '09:00:00',
    slot_end_time: '17:00:00',
    price: '',
  })

  const loadServices = useCallback(async () => {
    if (!token) return
    try {
      const data = await apiRequest('/services', { token })
      setServices(data)
    } catch (err) {
      setError(err.message)
    }
  }, [token])

  useEffect(() => {
    loadServices()
  }, [loadServices])

  const createService = async (e) => {
    e.preventDefault()
    setError('')
    try {
      await apiRequest('/services', {
        method: 'POST',
        token,
        body: {
          ...form,
          slot_duration_minutes: Number(form.slot_duration_minutes),
          price: Number(form.price),
        },
      })
      setForm({
        name: '',
        slot_duration_minutes: '15',
        slot_start_time: '09:00:00',
        slot_end_time: '17:00:00',
        price: '',
      })
      await loadServices()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <AppShell title="Admin - Manage Services">
      <div className="grid">
        <div className="card">
          <h3>Create Service</h3>
          <form className="form" onSubmit={createService}>
            <input
              placeholder="Service name"
              value={form.name}
              onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
              required
            />
            <select
              value={form.slot_duration_minutes}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, slot_duration_minutes: e.target.value }))
              }
            >
              <option value="15">15 minutes</option>
              <option value="30">30 minutes</option>
              <option value="60">60 minutes</option>
            </select>
            <input
              type="time"
              step="1"
              value={form.slot_start_time}
              onChange={(e) => setForm((prev) => ({ ...prev, slot_start_time: e.target.value }))}
            />
            <input
              type="time"
              step="1"
              value={form.slot_end_time}
              onChange={(e) => setForm((prev) => ({ ...prev, slot_end_time: e.target.value }))}
            />
            <input
              type="number"
              min="1"
              placeholder="Price"
              value={form.price}
              onChange={(e) => setForm((prev) => ({ ...prev, price: e.target.value }))}
              required
            />
            <button className="btn primary" type="submit">
              Save Service
            </button>
          </form>
          {error ? <p className="error">{error}</p> : null}
        </div>

        <div className="card">
          <h3>Available Services</h3>
          <div className="list">
            {services.map((service) => (
              <div className="list-item" key={service.id}>
                <div>
                  <strong>{service.name}</strong>
                  <p className="small-text">
                    {service.slot_duration_minutes}m | {service.slot_start_time} -{' '}
                    {service.slot_end_time}
                  </p>
                </div>
                <span>Rs {service.price}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </AppShell>
  )
}

export default AdminServicesPage
