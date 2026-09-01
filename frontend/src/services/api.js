const BASE_URL = import.meta.env.VITE_API_URL || "";

async function handle(res) {
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Request failed (${res.status}): ${body}`);
  }
  return res.json();
}

export async function uploadResume(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE_URL}/upload/resume`, { method: "POST", body: form });
  return handle(res);
}

export async function uploadJD(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE_URL}/upload/jd`, { method: "POST", body: form });
  return handle(res);
}

export async function startInterview(resumeId, jdId) {
  const res = await fetch(`${BASE_URL}/interview/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resume_id: resumeId, jd_id: jdId }),
  });
  return handle(res);
}

export async function submitAnswer(interviewId, answerText) {
  const res = await fetch(`${BASE_URL}/interview/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ interview_id: interviewId, answer_text: answerText }),
  });
  return handle(res);
}

export function voiceWebSocketUrl(interviewId) {
  const base = BASE_URL || window.location.origin;
  const wsProtocol = base.startsWith("https") ? "wss" : "ws";
  const host = base.replace(/^https?:\/\//, "");
  return `${wsProtocol}://${host}/interview/voice/${interviewId}`;
}
