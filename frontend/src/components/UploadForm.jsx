import { useState } from "react";
import { uploadResume, uploadJD, startInterview } from "../services/api";

const DEFAULT_RESUME_TEXT = `Alex Johnson
Software Engineer

Summary
Full-stack software engineer with 3 years of experience building reliable web applications.

Skills
JavaScript, React, Node.js, Python, FastAPI, SQL, PostgreSQL, Docker, Git

Experience
Software Engineer, Acme Labs | 2023 - Present
- Built and maintained React and FastAPI features for a SaaS platform.
- Designed REST APIs and optimized PostgreSQL queries.

Projects
AI Interview Platform — Built a voice-enabled mock interview app using React, FastAPI, and WebSockets.
Analytics Dashboard — Created a responsive dashboard with role-based access and data visualizations.`;

const DEFAULT_JD_TEXT = `Job Title: Full-Stack Software Engineer

We are looking for a Full-Stack Software Engineer to build scalable, user-friendly web applications.

Required skills
- JavaScript and React
- Node.js or Python with FastAPI
- REST API design
- SQL and PostgreSQL
- Git and Docker

Nice to have
- WebSockets
- Cloud deployment experience

You will collaborate with product and engineering teams, write maintainable code, and deliver high-quality features.`;

export default function UploadForm({ onInterviewStarted, onPrimePlayback }) {
  const [step, setStep] = useState("upload"); // "upload" | "skills" | "starting"
  const [resumeFile, setResumeFile] = useState(null);
  const [jdFile, setJdFile] = useState(null);
  const [resumeText, setResumeText] = useState(DEFAULT_RESUME_TEXT);
  const [jdText, setJdText] = useState(DEFAULT_JD_TEXT);
  const [jdSkills, setJdSkills] = useState([]);
  const [uploadedIds, setUploadedIds] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleUpload = async (e) => {
    e.preventDefault();
    if ((!resumeFile && !resumeText.trim()) || (!jdFile && !jdText.trim())) {
      setError("Please provide both a resume and a job description.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      onPrimePlayback?.();
      const [resumeRes, jdRes] = await Promise.all([
        uploadResume(resumeFile || new File([resumeText], "resume.txt", { type: "text/plain" })),
        uploadJD(jdFile || new File([jdText], "job-description.txt", { type: "text/plain" })),
      ]);
      setUploadedIds({ resumeId: resumeRes.file_id, jdId: jdRes.file_id });
      // Extract skills from JD file for preview
      const skills = extractSkillsFromJD(jdRes);
      setJdSkills(skills);
      setStep("skills");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleStart = async () => {
    setStep("starting");
    setLoading(true);
    setError(null);
    try {
      const startRes = await startInterview(uploadedIds.resumeId, uploadedIds.jdId);
      onInterviewStarted(startRes);
    } catch (err) {
      setError(err.message);
      setStep("skills");
    } finally {
      setLoading(false);
    }
  };

  // Extract skills from JD response (use the filename as hint or return placeholder)
  function extractSkillsFromJD(jdRes) {
    // The JD is parsed server-side; we show skills after interview starts
    // For the preview, we show a generic message
    return [];
  }

  if (step === "skills") {
    return (
      <div className="upload-container">
        <div className="upload-card skills-card">
          <div className="card-icon">🎯</div>
          <h2>Interview Ready</h2>
          <p className="subtitle">
            Your resume and job description have been uploaded successfully.
            <br />
            Click below to start your AI-powered interview.
          </p>

          <div className="file-summary">
            <div className="file-badge">
              <span className="badge-icon">📄</span>
              <span>{resumeFile?.name || "Resume text"}</span>
            </div>
            <div className="file-badge">
              <span className="badge-icon">💼</span>
              <span>{jdFile?.name || "Job description text"}</span>
            </div>
          </div>

          <div className="interview-info">
            <div className="info-item">
              <span className="info-icon">👋</span>
              <span>Introduction</span>
            </div>
            <div className="info-item">
              <span className="info-icon">🚀</span>
              <span>2 Project Questions</span>
            </div>
            <div className="info-item">
              <span className="info-icon">🧠</span>
              <span>JD Skill Questions</span>
            </div>
            <div className="info-item">
              <span className="info-icon">✅</span>
              <span>Wrap Up</span>
            </div>
          </div>

          {error && <p className="error">{error}</p>}

          <button className="start-btn" onClick={handleStart} disabled={loading}>
            <span className="btn-icon">🎙️</span>
            Start Interview
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="upload-container">
      <div className="upload-card">
        <div className="card-icon">🤖</div>
        <h2>AI Mock Interview</h2>
        <p className="subtitle">
          Start with the sample resume and job description below, edit them for
          your profile, or upload files instead.
        </p>

        <form className="upload-form" onSubmit={handleUpload}>
          <div className="document-grid">
            <section className="document-panel">
              <div className="document-header"><span className="document-icon">📄</span><div><span className="file-title">Resume</span><p>Paste your resume or upload a document.</p></div></div>
              <label className="text-field"><textarea aria-label="Resume text" value={resumeText} onChange={(e) => setResumeText(e.target.value)} disabled={Boolean(resumeFile)} rows={9} /></label>
              <label className="file-field compact-file-field">
                <span>Upload resume · PDF, DOCX, or TXT</span>
                <input type="file" accept=".pdf,.docx,.doc,.txt" onChange={(e) => setResumeFile(e.target.files[0])} />
                {resumeFile && <span className="file-name">Using: {resumeFile.name}</span>}
                {resumeFile && <span className="file-hint">The uploaded file replaces the text above.</span>}
              </label>
            </section>

            <section className="document-panel">
              <div className="document-header"><span className="document-icon">💼</span><div><span className="file-title">Job description</span><p>Paste the role details or upload a document.</p></div></div>
              <label className="text-field"><textarea aria-label="Job description text" value={jdText} onChange={(e) => setJdText(e.target.value)} disabled={Boolean(jdFile)} rows={9} /></label>
              <label className="file-field compact-file-field">
                <span>Upload job description · PDF or TXT</span>
                <input type="file" accept=".pdf,.txt" onChange={(e) => setJdFile(e.target.files[0])} />
                {jdFile && <span className="file-name">Using: {jdFile.name}</span>}
                {jdFile && <span className="file-hint">The uploaded file replaces the text above.</span>}
              </label>
            </section>
          </div>

          {error && <p className="error">{error}</p>}

          <button className="analyze-btn" type="submit" disabled={loading}>
            {loading ? (
              <>
                <span className="spinner"></span>
                Processing...
              </>
            ) : (
              <>
                <span className="btn-icon">📤</span>
                Analyze & Start Interview
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
