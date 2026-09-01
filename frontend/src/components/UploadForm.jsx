import { useState } from "react";
import { uploadResume, uploadJD, startInterview } from "../services/api";

export default function UploadForm({ onInterviewStarted, onPrimePlayback }) {
  const [step, setStep] = useState("upload"); // "upload" | "skills" | "starting"
  const [resumeFile, setResumeFile] = useState(null);
  const [jdFile, setJdFile] = useState(null);
  const [jdSkills, setJdSkills] = useState([]);
  const [uploadedIds, setUploadedIds] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!resumeFile || !jdFile) {
      setError("Please select both a resume and a job description file.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      onPrimePlayback?.();
      const [resumeRes, jdRes] = await Promise.all([
        uploadResume(resumeFile),
        uploadJD(jdFile),
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
              <span>{resumeFile?.name}</span>
            </div>
            <div className="file-badge">
              <span className="badge-icon">💼</span>
              <span>{jdFile?.name}</span>
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
          Upload your resume and a job description to start a personalized
          AI-powered technical interview.
        </p>

        <form className="upload-form" onSubmit={handleUpload}>
          <label className="file-field">
            <div className="file-label-row">
              <span className="file-icon">📄</span>
              <span className="file-title">Resume</span>
            </div>
            <span className="file-hint">PDF, DOCX, or TXT</span>
            <input
              type="file"
              accept=".pdf,.docx,.doc,.txt"
              onChange={(e) => setResumeFile(e.target.files[0])}
            />
            {resumeFile && (
              <span className="file-name">{resumeFile.name}</span>
            )}
          </label>

          <label className="file-field">
            <div className="file-label-row">
              <span className="file-icon">💼</span>
              <span className="file-title">Job Description</span>
            </div>
            <span className="file-hint">PDF or TXT</span>
            <input
              type="file"
              accept=".pdf,.txt"
              onChange={(e) => setJdFile(e.target.files[0])}
            />
            {jdFile && (
              <span className="file-name">{jdFile.name}</span>
            )}
          </label>

          {error && <p className="error">{error}</p>}

          <button type="submit" disabled={loading || !resumeFile || !jdFile}>
            {loading ? (
              <>
                <span className="spinner"></span>
                Processing...
              </>
            ) : (
              <>
                <span className="btn-icon">📤</span>
                Upload & Analyze
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
