export default function InterviewChat({ transcript, candidateChunks, aiTextChunks, thinking, questionNumber, totalQuestions, jdSkills }) {
  const progress = Math.round((questionNumber / Math.max(totalQuestions, 1)) * 100);
  return (
    <div className="interview-chat">
      <div className="chat-header">
        <div className="header-left">
          <div className="header-avatar">🤖</div>
          <div className="header-info">
            <h2>AI Interview</h2>
            <span className="progress">
              Question {questionNumber} / {totalQuestions}
            </span>
          </div>
        </div>
        <span className="question-counter">{progress}%</span>
      </div>
      <div className="question-progress"><span style={{ width: `${progress}%` }} /></div>
      {jdSkills?.length > 0 && <div className="stage-pills">
        {jdSkills.slice(0, 6).map((skill, index) => <span className={index === 0 ? "selected" : ""} key={skill}>{skill}</span>)}
      </div>}

      <div className="chat-body">
        {transcript.map((turn, i) => (
          <div key={i} className={`bubble ${turn.role}`}>
            <span className="speaker">
              {turn.role === "ai" ? "🤖 AI" : turn.role === "nudge" ? "⏳ Nudge" : "👤 You"}
            </span>
            <p>{turn.text}</p>
          </div>
        ))}

        {candidateChunks.length > 0 && (
          <div className="bubble candidate streaming">
            <span className="speaker">👤 You</span>
            <p>
              {[...candidateChunks]
                .sort((a, b) => a.seq - b.seq)
                .map((c) => c.text)
                .join(" ")}
            </p>
          </div>
        )}

        {thinking && (
          <div className="bubble ai streaming">
            <span className="speaker">🤖 AI</span>
            <div className="thinking-dots">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
        )}

        {aiTextChunks.length > 0 && (
          <div className="bubble ai streaming">
            <span className="speaker">🤖 AI</span>
            <p>{aiTextChunks.map((c) => c.text).join(" ")}</p>
          </div>
        )}
      </div>
    </div>
  );
}
