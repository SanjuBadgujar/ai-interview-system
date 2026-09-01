export default function VoiceRecorder({ connected, listening, thinking, onStart, onStop, isComplete }) {
  if (isComplete) {
    return (
      <div className="voice-controls complete">
        <div className="complete-icon">✅</div>
        <p className="done">Interview Complete!</p>
        <p className="complete-sub">Thank you for your time. Great effort!</p>
      </div>
    );
  }

  return (
    <div className="voice-controls">
      <div className="status-section">
        <div className={`status-dot ${connected ? "connected" : ""}`} />
        <span className="status-text">
          {connected ? "Connected" : "Connecting..."}
        </span>
      </div>

      {thinking ? (
        <div className="thinking-section">
          <div className="thinking-dots">
            <span></span>
            <span></span>
            <span></span>
          </div>
          <span className="thinking-label">AI is preparing...</span>
        </div>
      ) : (
        <>
          {!listening ? (
            <button className="listen-btn" onClick={onStart} disabled={!connected}>
              <span className="mic-icon">🎙️</span>
              Start Speaking
            </button>
          ) : (
            <button className="listen-btn stop" onClick={onStop}>
              <span className="mic-icon">⏹️</span>
              Stop & Send
            </button>
          )}

          {listening && (
            <div className="listening-indicator">
              <div className="pulse-ring"></div>
              <span>Listening...</span>
            </div>
          )}
        </>
      )}
    </div>
  );
}
