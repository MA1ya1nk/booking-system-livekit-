import { useCallback, useEffect, useRef, useState } from 'react'
import { Room, RoomEvent, Track } from 'livekit-client'
import { useAuth } from '../context/AuthContext'
import { apiRequest } from '../lib/api'

/**
 * Floating mic: requests a LiveKit token from the API, connects, enables mic, plays agent audio.
 * Requires LIVEKIT_* env on the FastAPI server and the agent worker running.
 */
export default function VoiceAssistantButton() {
  const { token } = useAuth()
  const roomRef = useRef(null)
  const audioContainerRef = useRef(null)
  const [status, setStatus] = useState('idle')
  const [error, setError] = useState(null)

  const cleanupAudioElements = () => {
    if (audioContainerRef.current) {
      audioContainerRef.current.innerHTML = ''
    }
  }

  const disconnect = useCallback(() => {
    setError(null)
    cleanupAudioElements()
    if (roomRef.current) {
      roomRef.current.disconnect()
      roomRef.current = null
    }
    setStatus('idle')
  }, [])

  const connect = useCallback(async () => {
    if (roomRef.current) return
    setError(null)
    setStatus('connecting')
    let room = null
    try {
      const data = await apiRequest('/livekit/token', {
        method: 'POST',
        body: {},
        token: token || undefined,
      })

      room = new Room({ adaptiveStream: true, dynacast: true })
      roomRef.current = room

      room.on(RoomEvent.TrackSubscribed, (track, _publication, participant) => {
        if (participant.isLocal) return
        if (track.kind === Track.Kind.Audio) {
          const el = track.attach()
          el.autoplay = true
          audioContainerRef.current?.appendChild(el)
        }
      })

      room.on(RoomEvent.Disconnected, () => {
        cleanupAudioElements()
        roomRef.current = null
        setStatus('idle')
      })

      await room.connect(data.server_url, data.token)
      await room.localParticipant.setMicrophoneEnabled(true)
      setStatus('live')
    } catch (e) {
      console.error(e)
      if (room) {
        room.disconnect()
      }
      roomRef.current = null
      cleanupAudioElements()
      setError(e instanceof Error ? e.message : 'Could not start voice')
      setStatus('idle')
    }
  }, [token])

  useEffect(() => {
    return () => {
      roomRef.current?.disconnect()
      roomRef.current = null
    }
  }, [])

  const onClick = () => {
    if (status === 'connecting') return
    if (status === 'live') disconnect()
    else connect()
  }

  const label =
    status === 'connecting' ? 'Connecting…' : status === 'live' ? 'Voice on' : 'Voice'

  return (
    <div className="voice-assistant-fab" role="region" aria-label="Hospital voice assistant">
      <div ref={audioContainerRef} className="voice-assistant-audio" aria-hidden="true" />
      {error ? <div className="voice-assistant-toast">{error}</div> : null}
      <button
        type="button"
        className={`voice-assistant-btn ${status === 'live' ? 'live' : ''}`}
        onClick={onClick}
        disabled={status === 'connecting'}
        title={status === 'live' ? 'Stop voice assistant' : 'Start voice assistant'}
      >
        {status === 'connecting' ? '…' : '🎤'}
      </button>
      <span className="voice-assistant-label">{label}</span>
    </div>
  )
}
