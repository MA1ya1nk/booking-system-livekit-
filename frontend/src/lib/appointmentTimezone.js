/**
 * Wall times for bookings match backend `APPOINTMENT_TIMEZONE` (naive local times in this zone).
 * Keep in sync with backend `app.core.config.settings.appointment_timezone`.
 */
export const APPOINTMENT_TIMEZONE =
  import.meta.env.VITE_APPOINTMENT_TIMEZONE || 'Asia/Kolkata'

/**
 * Calendar date YYYY-MM-DD and clock in APPOINTMENT_TIMEZONE (now).
 */
export function getWallDateTimePartsInTz(date = new Date()) {
  const f = new Intl.DateTimeFormat('en-CA', {
    timeZone: APPOINTMENT_TIMEZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
  const parts = f.formatToParts(date)
  const m = {}
  for (const p of parts) {
    if (p.type !== 'literal') m[p.type] = p.value
  }
  return {
    year: m.year,
    month: m.month,
    day: m.day,
    hour: m.hour,
    minute: m.minute,
    second: m.second,
  }
}

/** Today's date string YYYY-MM-DD in appointment timezone. */
export function todayDateStringInAppointmentTz() {
  const p = getWallDateTimePartsInTz()
  return `${p.year}-${p.month}-${p.day}`
}

/**
 * Current instant as comparable naive wall string YYYY-MM-DDTHH:MM:00 (appointment TZ).
 */
export function nowIsoWallInAppointmentTz() {
  const p = getWallDateTimePartsInTz()
  const pad = (n) => String(n).padStart(2, '0')
  return `${p.year}-${p.month}-${p.day}T${pad(Number(p.hour))}:${pad(Number(p.minute))}:00`
}

/**
 * Generate slot naive ISO strings for one calendar day: YYYY-MM-DDTHH:MM:00 (wall time in appointment TZ).
 */
export function generateAppointmentSlots(service, selectedDateYmd) {
  if (!service || !selectedDateYmd) return []
  const parseHmsToMinutes = (t) => {
    const [h, m, s] = t.split(':').map((x) => Number(x))
    return h * 60 + m + (s || 0) / 60
  }
  const startMin = Math.round(parseHmsToMinutes(service.slot_start_time))
  const endMin = Math.round(parseHmsToMinutes(service.slot_end_time))
  const step = Number(service.slot_duration_minutes)
  const slots = []
  const pad = (n) => String(n).padStart(2, '0')
  for (let curMin = startMin; curMin < endMin; curMin += step) {
    const h = Math.floor(curMin / 60)
    const mi = curMin % 60
    slots.push(`${selectedDateYmd}T${pad(h)}:${pad(mi)}:00`)
  }
  return slots
}

/**
 * Display label for a naive wall slot string (HH:MM from string, locale-formatted).
 */
export function formatSlotTimeLabel(isoWallNaive) {
  const t = isoWallNaive.split('T')[1]
  if (!t) return isoWallNaive
  const [hh, mm] = t.split(':').map(Number)
  if (Number.isNaN(hh) || Number.isNaN(mm)) return isoWallNaive
  const d = new Date(2000, 0, 1, hh, mm, 0, 0)
  return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

/** Date + time for summaries (wall clock from stored string). */
export function formatAppointmentWallDisplay(isoWallNaive) {
  const datePart = isoWallNaive.split('T')[0]
  if (!datePart) return isoWallNaive
  return `${datePart} ${formatSlotTimeLabel(isoWallNaive)}`
}
