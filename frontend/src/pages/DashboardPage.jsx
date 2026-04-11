import { useCallback, useEffect, useMemo, useState } from 'react'
import AppShell from '../components/AppShell'
import { useAuth } from '../context/AuthContext'
import { apiRequest } from '../lib/api'
import { loadRazorpayScript } from '../lib/razorpay'

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
  const { token, user } = useAuth()
  const [services, setServices] = useState([])
  const [appointments, setAppointments] = useState([])
  const [bookedSlots, setBookedSlots] = useState([])
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().slice(0, 10))
  const [error, setError] = useState('')
  const [linkMessage, setLinkMessage] = useState('')
  const [linkSending, setLinkSending] = useState(false)
  const [form, setForm] = useState({ service_id: '', appointment_time: '', note: '' })
  /** 'bookings' = active; 'cancelled' = history */
  const [appointmentsView, setAppointmentsView] = useState('bookings')

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

  const handleSendPaymentLink = async () => {
    setError('')
    setLinkMessage('')
    if (!form.service_id || !form.appointment_time) {
      setError('Select service, date, and a time slot first.')
      return
    }
    setLinkSending(true)
    try {
      const body = {
        service_id: Number(form.service_id),
        appointment_time: form.appointment_time,
      }
      if (form.note?.trim()) body.note = form.note.trim()
      const res = await apiRequest('/payments/send-payment-link-email', {
        method: 'POST',
        token,
        body,
      })
      if (res.email_sent) {
        setLinkMessage(
          'Payment link sent to your email. After payment, your booking is created when Razorpay calls the webhook (see server docs).',
        )
      } else {
        setLinkMessage(
          `Email not configured on the server — open this link to pay: ${res.short_url || '(no URL)'}`,
        )
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLinkSending(false)
    }
  }

  const handleBook = async (e) => {
    e.preventDefault()
    setError('')
    setLinkMessage('')
    try {
      await loadRazorpayScript()
      const body = {
        service_id: Number(form.service_id),
        appointment_time: form.appointment_time,
      }
      if (form.note?.trim()) body.note = form.note.trim()

      const { order_id: orderId, amount, currency, key_id: keyId } = await apiRequest(
        '/payments/create-order',
        { method: 'POST', token, body },
      )

      const svc = services.find((item) => item.id === Number(form.service_id))
      const options = {
        key: keyId,
        amount,
        currency,
        order_id: orderId,
        name: 'Hospital booking',
        description: svc ? `Booking: ${svc.name}` : 'Appointment',
        handler: async (response) => {
          try {
            await apiRequest('/payments/verify-and-book', {
              method: 'POST',
              token,
              body: {
                razorpay_order_id: response.razorpay_order_id,
                razorpay_payment_id: response.razorpay_payment_id,
                razorpay_signature: response.razorpay_signature,
              },
            })
            setForm({ service_id: '', appointment_time: '', note: '' })
            await loadData()
          } catch (err) {
            setError(err.message || 'Payment verification failed')
          }
        },
        prefill: user?.email ? { email: user.email } : {},
        theme: { color: '#2563eb' },
        modal: {
          ondismiss: () => {},
        },
      }

      const RazorpayCtor = window.Razorpay
      if (!RazorpayCtor) {
        setError('Razorpay failed to load')
        return
      }
      const rzp = new RazorpayCtor(options)
      rzp.open()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleCancel = async (id) => {
    setError('')
    try {
      await apiRequest(`/appointments/${id}/cancel`, { method: 'PATCH', token })
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

  const filteredAppointments = useMemo(() => {
    if (appointmentsView === 'bookings') {
      return appointments.filter((a) => a.status === 'booked')
    }
    return appointments.filter((a) => a.status === 'cancelled')
  }, [appointments, appointmentsView])

  return (
    <AppShell title="User Dashboard">
      <div className="grid">
        <div className="card">
          <h3>Book Appointment</h3>
          <p className="small-text">
            Pay with Razorpay (test mode). Or email yourself a payment link and pay later — configure
            webhooks on the API for the link flow.
          </p>
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
              <div className="slot-grid">
                {bookableSlots.map((slot) => {
                  const value = toIsoLocal(slot)
                  const selected = form.appointment_time === value
                  return (
                    <button
                      key={value}
                      type="button"
                      className={`btn slot-btn ${selected ? 'primary' : ''}`}
                      onClick={() => setForm((prev) => ({ ...prev, appointment_time: value }))}
                    >
                      {slot.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </button>
                  )
                })}
              </div>
            ) : null}
            {selectedService && bookableSlots.length === 0 ? (
              <p className="small-text">No available slots for this date.</p>
            ) : null}
            <input
              value={form.appointment_time ? new Date(form.appointment_time).toLocaleString() : ''}
              readOnly
              placeholder="Select a slot above"
              required
            />
            <input
              placeholder="Note (optional)"
              value={form.note}
              onChange={(e) => setForm((prev) => ({ ...prev, note: e.target.value }))}
            />
            <div className="pay-actions">
              <button className="btn primary" type="submit">
                Pay &amp; book
              </button>
              <button
                type="button"
                className="btn"
                disabled={linkSending}
                onClick={handleSendPaymentLink}
              >
                {linkSending ? 'Sending…' : 'Email payment link'}
              </button>
            </div>
          </form>
          {linkMessage ? <p className="footnote">{linkMessage}</p> : null}
          {error ? <p className="error">{error}</p> : null}
        </div>

        <div className="card">
          <h3>My Appointments</h3>
          <div className="form appointments-toolbar">
            <label className="small-text" htmlFor="appointments-view">
              Show
            </label>
            <select
              id="appointments-view"
              value={appointmentsView}
              onChange={(e) => setAppointmentsView(e.target.value)}
            >
              <option value="bookings">Bookings</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </div>
          <div className="list">
            {filteredAppointments.length === 0 ? (
              <p className="small-text">
                {appointments.length === 0
                  ? 'No appointments yet.'
                  : appointmentsView === 'bookings'
                    ? 'No active bookings.'
                    : 'No cancelled appointments.'}
              </p>
            ) : null}
            {filteredAppointments.map((item) => (
              <div className="list-item" key={item.id}>
                <div>
                  <strong>{item.service.name}</strong>
                  <p className="small-text">{new Date(item.appointment_time).toLocaleString()}</p>
                  <p className="small-text">Status: {item.status}</p>
                </div>
                {appointmentsView === 'bookings' && item.status === 'booked' ? (
                  <button type="button" className="btn" onClick={() => handleCancel(item.id)}>
                    Cancel
                  </button>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      </div>
    </AppShell>
  )
}

export default DashboardPage
