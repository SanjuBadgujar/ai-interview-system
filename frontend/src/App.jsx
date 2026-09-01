import { useEffect, useState } from "react";
import UploadForm from "./components/UploadForm.jsx";
import InterviewChat from "./components/InterviewChat.jsx";
import VoiceRecorder from "./components/VoiceRecorder.jsx";
import DashboardSidebar from "./components/DashboardSidebar.jsx";
import LiveAssistant from "./components/LiveAssistant.jsx";
import { useVoiceInterview } from "./hooks/useVoiceInterview.js";

export default function App() {
  const [interviewMeta, setInterviewMeta] = useState(null);
  const [assistantOpen, setAssistantOpen] = useState(true);
  const voice = useVoiceInterview(interviewMeta?.interview_id);

  useEffect(() => {
    if (interviewMeta) voice.connect();
    return () => voice.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [interviewMeta]);

  const combinedTranscript = interviewMeta ? voice.transcript : [];
  const questionNumber = interviewMeta
    ? Math.min(interviewMeta.total_questions, combinedTranscript.filter((turn) => turn.role === "ai").length)
    : 0;

  return (
    <div className={`app-shell dashboard-shell ${interviewMeta ? "session-active" : ""} ${!assistantOpen ? "assistant-collapsed" : ""}`}>
      <DashboardSidebar compact={Boolean(interviewMeta)} />
      <main className="dashboard-main">
        {!interviewMeta ? (
          <div className="upload-dashboard"><UploadForm onInterviewStarted={setInterviewMeta} onPrimePlayback={voice.primePlayback} /></div>
        ) : (
          <div className="interview-workspace">
            <div className="workspace-topline">
              <span>AI-powered mock interview</span>
              <div className="session-actions">
                <span className="secure-status">● Secure session</span>
                <button className="assistant-toggle" type="button" onClick={() => setAssistantOpen((open) => !open)} aria-expanded={assistantOpen}>
                  {assistantOpen ? "Hide details" : "Show details"}
                </button>
              </div>
            </div>
            <InterviewChat
              transcript={combinedTranscript}
              candidateChunks={voice.candidateChunks}
              aiTextChunks={voice.aiTextChunks}
              thinking={voice.thinking}
              questionNumber={questionNumber || 1}
              totalQuestions={interviewMeta.total_questions}
              jdSkills={interviewMeta.jd_skills}
            />
            <VoiceRecorder
              connected={voice.connected}
              listening={voice.listening}
              thinking={voice.thinking}
              isComplete={voice.isComplete}
              onStart={voice.startListening}
              onStop={voice.stopListening}
            />
          </div>
        )}
      </main>
      {interviewMeta && assistantOpen && <LiveAssistant
        connected={voice.connected}
        listening={voice.listening}
        thinking={voice.thinking}
        questionNumber={questionNumber || 1}
        totalQuestions={interviewMeta.total_questions}
        jdSkills={interviewMeta.jd_skills}
        transcript={combinedTranscript}
      />}
    </div>
  );
}