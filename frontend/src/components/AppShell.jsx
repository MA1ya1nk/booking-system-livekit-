import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

function AppShell({ title, children }) {
  const { user, isAuthenticated, isAdmin, logout } = useAuth()

  return (
    <div className="app-shell">
      <nav className="top-nav">
        <Link to="/">Hospital Booking</Link>
        <div className="top-nav-links">
          {isAuthenticated ? (
            <>
              <Link to="/dashboard">Dashboard</Link>
              {isAdmin && <Link to="/admin/services">Admin Services</Link>}
              <span className="small-text">{user?.name}</span>
              <button className="btn" type="button" onClick={logout}>
                Logout
              </button>
            </>
          ) : (
            <>
              <Link to="/login">Login</Link>
              <Link to="/register">Register</Link>
            </>
          )}
        </div>
      </nav>
      <section className="page-content">
        <h1>{title}</h1>
        {children}
      </section>
    </div>
  )
}

export default AppShell
