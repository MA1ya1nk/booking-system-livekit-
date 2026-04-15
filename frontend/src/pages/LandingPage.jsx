import { Link } from 'react-router-dom'
import AppShell from '../components/AppShell'

function LandingPage() {
  return (
    <AppShell title="Hospital Appointment Booking">
      <p className="text">
        Book appointments for available services, manage your bookings, and let admins add
        new services with slot windows and pricing.
      </p>
      <div className="actions">
        <Link className="btn primary" to="/register">
          Create Account
        </Link>
        <Link className="btn" to="/login">
          Login
        </Link>
      </div>
    </AppShell>
  )
}

export default LandingPage
