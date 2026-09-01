export default function LiveAssistant({ listening, thinking, connected, questionNumber, totalQuestions, jdSkills, transcript }) {
  const status = thinking ? "Analyzing" : listening ? "Listening" : connected ? "Online" : "Connecting";
  const answers = transcript.filter((turn) => turn.role === "candidate");
  const lastAnswer = answers.at(-1)?.text;
  const remaining = Math.max(totalQuestions - questionNumber + 1, 0);
  return (
    <aside className="live-assistant">
      <div className="assistant-title"><b>Live Assistant</b><span><i /> {status}</span></div>
      <section className="assistant-card"><small>Interview progress</small><b>Question {questionNumber} of {totalQuestions || "—"}</b><em>{remaining} question{remaining === 1 ? "" : "s"} remaining</em><div className="mini-wave">⌁⌁⌁⌁⌁</div></section>
      <section className="assistant-card"><small>Current activity</small><b>{thinking ? "Preparing the next question" : listening ? "Listening to your answer" : connected ? "Waiting for the interview" : "Connecting to interview"}</b><em>{answers.length} submitted answer{answers.length === 1 ? "" : "s"}</em></section>
      {jdSkills.length > 0 && <section className="assistant-card"><small>Job-description skills</small><div className="assistant-skills">{jdSkills.slice(0, 6).map((skill) => <span key={skill}>{skill}</span>)}</div></section>}
      {lastAnswer && <section className="assistant-card tips"><small>Latest answer</small><p>{lastAnswer}</p></section>}
    </aside>
  );
}
