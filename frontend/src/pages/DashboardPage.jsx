import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import AppShell from '../components/AppShell'
import { useAuth } from '../context/AuthContext'
import { apiRequest } from '../lib/api'
import { loadRazorpayScript } from '../lib/razorpay'
import {
  formatAppointmentWallDisplay,
  formatSlotTimeLabel,
  generateAppointmentSlots,
  nowIsoWallInAppointmentTz,
  todayDateStringInAppointmentTz,
} from '../lib/appointmentTimezone'

function DashboardPage() {
  const { token, user } = useAuth()
  const [services, setServices] = useState([])
  const [appointments, setAppointments] = useState([])
  const [bookedSlots, setBookedSlots] = useState([])
  const [selectedDate, setSelectedDate] = useState(() => todayDateStringInAppointmentTz())
  const [error, setError] = useState('')
  const [linkMessage, setLinkMessage] = useState('')
  const [linkSending, setLinkSending] = useState(false)
  const [linkPolling, setLinkPolling] = useState(false)
  const pollIntervalRef = useRef(null)
  const pollingPendingRef = useRef(null)
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

  const stopPaymentLinkPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current)
      pollIntervalRef.current = null
    }
    pollingPendingRef.current = null
    setLinkPolling(false)
  }, [])

  useEffect(() => () => stopPaymentLinkPolling(), [stopPaymentLinkPolling])

  /** When user returns from paying in another tab, refresh if we are waiting for a payment-link booking. */
  useEffect(() => {
    if (!linkPolling) return
    const onVis = () => {
      if (document.visibilityState === 'visible') loadData()
    }
    document.addEventListener('visibilitychange', onVis)
    return () => document.removeEventListener('visibilitychange', onVis)
  }, [linkPolling, loadData])

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
    stopPaymentLinkPolling()
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
      const pending = {
        serviceId: Number(form.service_id),
        appointmentTime: form.appointment_time,
      }
      pollingPendingRef.current = pending
      setLinkPolling(true)
      if (res.email_sent) {
        setLinkMessage(
          'Payment link sent to your email. This page will update automatically when your payment completes.',
        )
      } else {
        setLinkMessage(
          `Email not configured on the server — open this link to pay: ${res.short_url || '(no URL)'}. This page will update when your booking is confirmed.`,
        )
      }

      const matchesPending = (a) => {
        if (a.status !== 'booked' || !a.service) return false
        if (a.service.id !== pending.serviceId) return false
        const t1 = new Date(a.appointment_time).getTime()
        const t2 = new Date(pending.appointmentTime).getTime()
        return Number.isFinite(t1) && Number.isFinite(t2) && Math.abs(t1 - t2) < 120000
      }

      let attempts = 0
      const maxAttempts = 60
      pollIntervalRef.current = setInterval(async () => {
        attempts += 1
        if (attempts > maxAttempts) {
          stopPaymentLinkPolling()
          setLinkMessage(
            'Still waiting for payment. If you already paid, refresh this page or check back shortly.',
          )
          return
        }
        try {
          const appointmentsData = await apiRequest('/appointments/me', { token })
          const p = pollingPendingRef.current
          if (!p) return
          if (appointmentsData.some(matchesPending)) {
            if (pollIntervalRef.current) {
              clearInterval(pollIntervalRef.current)
              pollIntervalRef.current = null
            }
            pollingPendingRef.current = null
            setLinkPolling(false)
            setAppointments(appointmentsData)
            const servicesData = await apiRequest('/services')
            setServices(servicesData)
            setLinkMessage('Booking confirmed. Your appointment is listed below.')
          }
        } catch {
          /* ignore transient errors while polling */
        }
      }, 3000)
    } catch (err) {
      setError(err.message)
      stopPaymentLinkPolling()
    } finally {
      setLinkSending(false)
    }
  }

  const handleBook = async (e) => {
    e.preventDefault()
    setError('')
    setLinkMessage('')
    stopPaymentLinkPolling()
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
  const generatedSlots = generateAppointmentSlots(selectedService, selectedDate)
  const bookedSet = new Set(bookedSlots)
  const nowWall = nowIsoWallInAppointmentTz()
  const bookableSlots = generatedSlots.filter((value) => value > nowWall && !bookedSet.has(value))

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
              min={todayDateStringInAppointmentTz()}
              onChange={(e) => {
                setSelectedDate(e.target.value)
                setForm((prev) => ({ ...prev, appointment_time: '' }))
              }}
              required
            />
            {selectedService ? (
              <div className="slot-grid">
                {bookableSlots.map((value) => {
                  const selected = form.appointment_time === value
                  return (
                    <button
                      key={value}
                      type="button"
                      className={`btn slot-btn ${selected ? 'primary' : ''}`}
                      onClick={() => setForm((prev) => ({ ...prev, appointment_time: value }))}
                    >
                      {formatSlotTimeLabel(value)}
                    </button>
                  )
                })}
              </div>
            ) : null}
            {selectedService && bookableSlots.length === 0 ? (
              <p className="small-text">No available slots for this date.</p>
            ) : null}
            <input
              value={form.appointment_time ? formatAppointmentWallDisplay(form.appointment_time) : ''}
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
          {linkPolling ? (
            <p className="footnote">Checking for your booking every few seconds…</p>
          ) : null}
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
                  <p className="small-text">{formatAppointmentWallDisplay(item.appointment_time)}</p>
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
