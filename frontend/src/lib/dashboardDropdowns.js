/**
 * Options for <select> elements on the user dashboard (booking slots + cancel flow).
 */

export function bookableSlotOptions(slots, toIsoLocal) {
  return slots.map((slot) => {
    const value = toIsoLocal(slot)
    return {
      value,
      label: slot.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }),
    }
  })
}

export function cancellableAppointmentOptions(appointments) {
  return appointments
    .filter((a) => a.status === 'booked')
    .map((a) => ({
      value: String(a.id),
      label: `${a.service.name} — ${new Date(a.appointment_time).toLocaleString()}`,
    }))
}
