
import codecs

content = """import { useEffect, useRef } from "react";
import TypewriterText from "./TypewriterText.jsx";

export default function InterviewChat({ transcript, candidateChunks, aiTextChunks, thinking, questionNumber, totalQuestions, jdSkills }) {
  const progress = Math.round((questionNumber / Math.max(totalQuestions, 1)) * 100);
  const chatBodyRef = useRef(null);

  useEffect(() => {
    if (chatBodyRef.current) {
      chatBodyRef.current.scrollTop = chatBodyRef.current.scrollHeight;
    }
  }, [transcript, candidateChunks, aiTextChunks, thinking]);

  return (
    <div className="interview-chat">
      <div className="chat-header">
        <div className="header-left">
          <div className="header-avatar">\U0001f916</div>
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

      <div className="chat-body" ref={chatBodyRef}>
        {transcript.map((turn, i) => (
          <div key={i} className={`bubble ${turn.role}`}>
            <span className="speaker">
              {turn.role === "ai" ? "\U0001f916 AI" : turn.role === "nudge" ? "\u23B3 Nudge" : "\U0001f464 You"}
            </span>
            <p><TypewriterText text={turn.text} active={i === transcript.length - 1} /></p>
          </div>
        ))}

        {candidateChunks.length > 0 && (
          <div className="bubble candidate streaming">
            <span className="speaker">\U0001f464 You</span>
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
            <span className="speaker">\U0001f916 AI</span>
            <div className="thinking-dots">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
        )}

        {aiTextChunks.length > 0 && (
          <div className="bubble ai streaming">
            <span className="speaker">\U0001f916 AI</span>
            <p>{aiTextChunks.map((c) => c.text).join(" ")}</p>
          </div>
        )}
      </div>
    </div>
  );
}
"""

# Convert \U0001f916 etc to actual emoji
content = content.encode("utf-8").decode("unicode_escape")
# Actually, that will mess things up. Let me use a different approach.

path = "E:/ai-interview-system_1/ai-interview-system/frontend/src/components/InterviewChat.jsx"
with codecs.open(path, "w", encoding="utf-8") as f:
    f.write(content)
print("Done")

