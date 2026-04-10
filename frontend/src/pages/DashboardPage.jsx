import { useCallback, useEffect, useState } from 'react'
import AppShell from '../components/AppShell'
import { useAuth } from '../context/AuthContext'
import { apiRequest } from '../lib/api'
import { bookableSlotOptions, cancellableAppointmentOptions } from '../lib/dashboardDropdowns'

function toIsoLocal(date) {
  const pad = (num) => String(num).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}:00`
}

function generateSlots(service, selectedDate) {
  if (!service || !selectedDate) return []
  const [year, month, day] = selectedDate.split('-').map(Number)
  const [sh, sm] = service.slot_start_time.split(':').map(Number)
  const [eh, em] = service.slot_end_time.split(':').map(Number)
  const start = new Date(year, month - 1, day, sh, sm, 0)
  const end = new Date(year, month - 1, day, eh, em, 0)
  const slots = []
  let cursor = new Date(start)
  while (cursor < end) {
    slots.push(new Date(cursor))
    cursor = new Date(cursor.getTime() + service.slot_duration_minutes * 60000)
  }
  return slots
}

function DashboardPage() {
  const { token } = useAuth()
  const [services, setServices] = useState([])
  const [appointments, setAppointments] = useState([])
  const [bookedSlots, setBookedSlots] = useState([])
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().slice(0, 10))
  const [error, setError] = useState('')
  const [form, setForm] = useState({ service_id: '', appointment_time: '', note: '' })
  const [cancelAppointmentId, setCancelAppointmentId] = useState('')

  const loadData = useCallback(async () => {
    if (!token) return
    try {
      const [servicesData, appointmentsData] = await Promise.all([
        apiRequest('/services'),
        apiRequest('/appointments/me', { token }),
      ])
      setServices(servicesData)
      setAppointments(appointmentsData)
    } catch (err) {
      setError(err.message)
    }
  }, [token])

  useEffect(() => {
    loadData()
  }, [loadData])

  useEffect(() => {
    if (!cancelAppointmentId) return
    const stillExists = appointments.some(
      (a) => a.status === 'booked' && String(a.id) === cancelAppointmentId,
    )
    if (!stillExists) setCancelAppointmentId('')
  }, [appointments, cancelAppointmentId])

  useEffect(() => {
    const loadBookedSlots = async () => {
      if (!form.service_id || !selectedDate) {
        setBookedSlots([])
        return
      }
      try {
        const data = await apiRequest(
          `/appointments/booked-slots?service_id=${form.service_id}&day=${selectedDate}`,
          { token },
        )
        setBookedSlots(data.slots || [])
      } catch (err) {
        setError(err.message)
      }
    }
    loadBookedSlots()
  }, [form.service_id, selectedDate, token])

  const handleBook = async (e) => {
    e.preventDefault()
    setError('')
    try {
      await apiRequest('/appointments', {
        method: 'POST',
        token,
        body: {
          service_id: Number(form.service_id),
          appointment_time: form.appointment_time,
          note: form.note,
        },
      })
      setForm({ service_id: '', appointment_time: '', note: '' })
      await loadData()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleCancel = async () => {
    const id = Number(cancelAppointmentId)
    if (!id) return
    setError('')
    try {
      await apiRequest(`/appointments/${id}/cancel`, { method: 'PATCH', token })
      setCancelAppointmentId('')
      await loadData()
    } catch (err) {
      setError(err.message)
    }
  }

  const selectedService = services.find((item) => item.id === Number(form.service_id))
  const generatedSlots = generateSlots(selectedService, selectedDate)
  const bookedSet = new Set(bookedSlots)
  const now = new Date()
  const bookableSlots = generatedSlots.filter((slot) => {
    const value = toIsoLocal(slot)
    return slot > now && !bookedSet.has(value)
  })

  const slotOptions = bookableSlotOptions(bookableSlots, toIsoLocal)
  const cancelOptions = cancellableAppointmentOptions(appointments)

  return (
    <AppShell title="User Dashboard">
      <div className="grid">
        <div className="card">
          <h3>Book Appointment</h3>
          <form className="form" onSubmit={handleBook}>
            <select
              value={form.service_id}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, service_id: e.target.value, appointment_time: '' }))
              }
              required
            >
              <option value="">Select service</option>
              {services.map((service) => (
                <option value={service.id} key={service.id}>
                  {service.name} ({service.slot_duration_minutes}m) - Rs {service.price}
                </option>
              ))}
            </select>
            <input
              type="date"
              value={selectedDate}
              min={new Date().toISOString().slice(0, 10)}
              onChange={(e) => {
                setSelectedDate(e.target.value)
                setForm((prev) => ({ ...prev, appointment_time: '' }))
              }}
              required
            />
            {selectedService ? (
              <select
                value={form.appointment_time}
                onChange={(e) =>
                  setForm((prev) => ({ ...prev, appointment_time: e.target.value }))
                }
                required
                disabled={slotOptions.length === 0}
              >
                <option value="">
                  {slotOptions.length === 0 ? 'No available slots for this date' : 'Select a time slot'}
                </option>
                {slotOptions.map(({ value, label }) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            ) : null}
            <input
              placeholder="Note (optional)"
              value={form.note}
              onChange={(e) => setForm((prev) => ({ ...prev, note: e.target.value }))}
            />
            <button className="btn primary" type="submit">
              Book
            </button>
          </form>
          {error ? <p className="error">{error}</p> : null}
        </div>

        <div className="card">
          <h3>My Appointments</h3>
          {cancelOptions.length > 0 ? (
            <div className="form cancel-row">
              <select
                value={cancelAppointmentId}
                onChange={(e) => setCancelAppointmentId(e.target.value)}
                aria-label="Select appointment to cancel"
              >
                <option value="">Cancel: choose an appointment…</option>
                {cancelOptions.map(({ value, label }) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="btn"
                disabled={!cancelAppointmentId}
                onClick={handleCancel}
              >
                Cancel appointment
              </button>
            </div>
          ) : null}
          <div className="list">
            {appointments.length === 0 ? <p className="small-text">No appointments yet.</p> : null}
            {appointments.map((item) => (
              <div className="list-item" key={item.id}>
                <div>
                  <strong>{item.service.name}</strong>
                  <p className="small-text">{new Date(item.appointment_time).toLocaleString()}</p>
                  <p className="small-text">Status: {item.status}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </AppShell>
  )
}

export default DashboardPage
