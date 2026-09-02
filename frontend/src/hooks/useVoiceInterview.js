import { useCallback, useRef, useState } from "react";
import { voiceWebSocketUrl } from "../services/api";

const TARGET_SAMPLE_RATE = 16000;
const FRAME_SIZE = 320; // 20ms @ 16kHz
const AUTO_SUBMIT_SILENCE_MS = 700;
const SILENCE_RMS_THRESHOLD = 0.012;
const INDIAN_FEMALE_VOICE_NAMES = /neerja|heera|priya/i;
const FEMALE_ENGLISH_VOICE_NAMES =
  /neerja|heera|priya|zira|aria|jenny|sonia|hazel|susan|samantha|karen|moira|natasha|female/i;

function getPreferredVoice() {
  const voices = window.speechSynthesis?.getVoices?.() || [];
  const indianEnglish = voices.filter((voice) =>
    voice.lang?.toLowerCase().startsWith("en-in")
  );
  const english = voices.filter((voice) =>
    voice.lang?.toLowerCase().startsWith("en")
  );
  return (
    indianEnglish.find((voice) => INDIAN_FEMALE_VOICE_NAMES.test(voice.name)) ||
    english.find((voice) => FEMALE_ENGLISH_VOICE_NAMES.test(voice.name)) ||
    null
  );
}

// Downsample Float32 audio from the mic's native rate to 16kHz PCM16.
function downsampleAndEncode(float32Buffer, inputSampleRate) {
  const ratio = inputSampleRate / TARGET_SAMPLE_RATE;
  const outLength = Math.floor(float32Buffer.length / ratio);
  const pcm16 = new Int16Array(outLength);

  for (let i = 0; i < outLength; i++) {
    const srcIndex = Math.floor(i * ratio);
    const sample = Math.max(-1, Math.min(1, float32Buffer[srcIndex]));
    pcm16[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return pcm16;
}

export function useVoiceInterview(interviewId) {
  const [connected, setConnected] = useState(false);
  const [transcript, setTranscript] = useState([]); // [{role, text}]
  const [candidateChunks, setCandidateChunks] = useState([]); // [{seq, text}] live STT blocks
  const [aiTextChunks, setAiTextChunks] = useState([]); // [{seq, text}] live ai_text blocks
  const [isComplete, setIsComplete] = useState(false);
  const [listening, setListening] = useState(false);
  const [thinking, setThinking] = useState(false);

  const wsRef = useRef(null);
  const audioCtxRef = useRef(null);
  const processorRef = useRef(null);
  const sourceRef = useRef(null);
  const pcmQueueRef = useRef(new Int16Array(0));
  const playbackCtxRef = useRef(null);
  const audioQueueRef = useRef([]); // decoded buffers waiting to play, in order
  const playingRef = useRef(false);
  const listeningRef = useRef(false);
  const pendingAudioEndRef = useRef(false); // true after question_complete, until AI audio drains
  const heardSpeechRef = useRef(false);
  const silenceStartedAtRef = useRef(null);
  const autoSubmitPendingRef = useRef(false);
  const fallbackTextRef = useRef([]);
  const receivedServerAudioRef = useRef(false);

  const sendAudioEnd = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "audio_end" }));
    }
  }, []);

  const stopMic = useCallback(() => {
    processorRef.current?.disconnect();
    sourceRef.current?.disconnect();
    sourceRef.current?.getTracks?.().forEach((t) => t.stop());
    audioCtxRef.current?.close().catch(() => {});
    processorRef.current = null;
    sourceRef.current = null;
    audioCtxRef.current = null;
    listeningRef.current = false;
    setListening(false);
  }, []);

  // refs so playNext (empty deps) and the socket handler can call them
  const sendAudioEndRef = useRef(sendAudioEnd);
  sendAudioEndRef.current = sendAudioEnd;
  const startListeningRef = useRef(null);
  const stopMicRef = useRef(stopMic);
  stopMicRef.current = stopMic;
  const stopListeningRef = useRef(null);

  // Create/resume the playback AudioContext inside a real user gesture (the
  // "Start Interview" click). Browsers suspend a context created lazily inside
  // ws.onmessage (no gesture), which would otherwise mute all TTS audio.
  const primePlayback = useCallback(async () => {
    if (playbackCtxRef.current) {
      if (playbackCtxRef.current.state === "suspended") {
        await playbackCtxRef.current.resume().catch(() => {});
      }
      return playbackCtxRef.current;
    }
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.state === "suspended") {
      await ctx.resume().catch(() => {});
    }
    playbackCtxRef.current = ctx;
    return ctx;
  }, []);


  const playNext = useCallback(() => {
    if (playingRef.current) return;
    if (audioQueueRef.current.length === 0) {
      playingRef.current = false;
      // AI finished speaking this question -> tell the backend and auto-open the
      // mic after a brief 150ms delay to let room acoustic echo decay cleanly.
      if (pendingAudioEndRef.current) {
        pendingAudioEndRef.current = false;
        setTimeout(() => {
          if (wsRef.current?.readyState === WebSocket.OPEN) {
            sendAudioEndRef.current();
            startListeningRef.current?.();
          }
        }, 150);
      }
      return;
    }
    const ctx = playbackCtxRef.current;
    if (!ctx) return;
    const buffer = audioQueueRef.current.shift();
    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(ctx.destination);
    src.onended = () => {
      playingRef.current = false;
      playNext();
    };
    playingRef.current = true;
    src.start();
  }, []);

  const enqueueAudio = useCallback(
    async (arrayBuffer) => {
      if (!arrayBuffer || arrayBuffer.byteLength === 0) return; // TTS stub returns empty bytes
      if (!playbackCtxRef.current) {
        await primePlayback();
      }
      const ctx = playbackCtxRef.current;
      if (!ctx) return;
      if (ctx.state === "suspended") {
        await ctx.resume().catch(() => {});
      }
      try {
        const audioBuffer = await ctx.decodeAudioData(arrayBuffer.slice(0));
        audioQueueRef.current.push(audioBuffer);
        playNext();
      } catch (e) {
        // Depending on your TTS provider's output format you may need a
        // different decode path (e.g. raw PCM) instead of decodeAudioData.
        console.warn("Could not decode TTS audio chunk", e);
      }
    },
    [playNext, primePlayback]
  );

  // Keep the interview usable when the server cannot synthesize audio (for
  // example, an ElevenLabs free-plan key using a library voice). This is only
  // used when the backend explicitly reports that no audio bytes were sent.
  const speakFallback = useCallback(
    (text) => {
      if (!text || !window.speechSynthesis) return;
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = "en-IN";
      const preferredVoice = getPreferredVoice();
      if (preferredVoice) {
        utterance.voice = preferredVoice;
        console.info("Interview TTS voice:", preferredVoice.name, preferredVoice.lang);
      } else {
        console.warn("No recognized female English system voice is installed.");
      }
      utterance.rate = 1;
      utterance.onend = () => {
        playingRef.current = false;
        playNext();
      };
      utterance.onerror = utterance.onend;
      playingRef.current = true;
      window.speechSynthesis.speak(utterance);
    },
    [playNext]
  );

  const startListening = useCallback(async () => {
    if (listeningRef.current) return; // already listening
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    if (!stream) return;
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const source = audioCtx.createMediaStreamSource(stream);
    const processor = audioCtx.createScriptProcessor(4096, 1, 1);
    // ScriptProcessor must be connected to an output to keep firing in some
    // browsers. Route it through a zero-gain node instead of the speakers:
    // playing the mic back creates acoustic feedback, which VAD interprets as
    // continuous speech and therefore never commits the answer.
    const silentOutput = audioCtx.createGain();
    silentOutput.gain.value = 0;
    heardSpeechRef.current = false;
    silenceStartedAtRef.current = null;
    autoSubmitPendingRef.current = false;

    processor.onaudioprocess = (e) => {
      const input = e.inputBuffer.getChannelData(0);

      // Browser-side silence detection is the authoritative end-of-answer
      // fallback. It prevents background/VAD quirks from leaving the complete
      // PCM buffer open forever after the candidate has finished speaking.
      let energy = 0;
      for (let i = 0; i < input.length; i++) energy += input[i] * input[i];
      const rms = Math.sqrt(energy / input.length);
      if (rms >= SILENCE_RMS_THRESHOLD) {
        heardSpeechRef.current = true;
        silenceStartedAtRef.current = null;
      } else if (heardSpeechRef.current && !autoSubmitPendingRef.current) {
        const now = Date.now();
        silenceStartedAtRef.current ??= now;
        if (now - silenceStartedAtRef.current >= AUTO_SUBMIT_SILENCE_MS) {
          autoSubmitPendingRef.current = true;
          // Defer teardown until this audio callback has returned.
          setTimeout(() => stopListeningRef.current?.(), 0);
        }
      }

      const pcm16 = downsampleAndEncode(input, audioCtx.sampleRate);

      // append to queue, then flush complete FRAME_SIZE frames to the socket
      const merged = new Int16Array(pcmQueueRef.current.length + pcm16.length);
      merged.set(pcmQueueRef.current);
      merged.set(pcm16, pcmQueueRef.current.length);

      let offset = 0;
      while (offset + FRAME_SIZE <= merged.length) {
        const frame = merged.slice(offset, offset + FRAME_SIZE);
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(frame.buffer);
        }
        offset += FRAME_SIZE;
      }
      pcmQueueRef.current = merged.slice(offset);
    };

    source.connect(processor);
    processor.connect(silentOutput);
    silentOutput.connect(audioCtx.destination);

    audioCtxRef.current = audioCtx;
    processorRef.current = processor;
    sourceRef.current = source;
    listeningRef.current = true;
    setListening(true);
  }, []);
  startListeningRef.current = startListening;

  const stopListening = useCallback(() => {
    if (!listeningRef.current) return;
    stopMic();
    // tell the backend the candidate is done, in case VAD alone doesn't catch it
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "end_of_answer" }));
    }
  }, [stopMic]);
  stopListeningRef.current = stopListening;

  const connect = useCallback(() => {
    // Close any prior socket first (e.g. React StrictMode double-mount / re-connect)
    // so we never leave an orphaned WebSocket speaking to the backend.
    wsRef.current?.close();
    const ws = new WebSocket(voiceWebSocketUrl(interviewId));
    ws.binaryType = "arraybuffer";

    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      // Stop the mic so the UI can never sit "stuck listening" on a dead socket.
      if (listeningRef.current) stopMicRef.current();
    };
    ws.onerror = () => {
      // onerror is always followed by onclose; just stop the mic here too.
      if (listeningRef.current) stopMicRef.current();
    };

    ws.onmessage = async (event) => {
      try {
        if (typeof event.data === "string") {
          const msg = JSON.parse(event.data);

          switch (msg.type) {
            case "partial_transcript":
              setCandidateChunks((chunks) => [...chunks, { seq: msg.seq, text: msg.text }]);
              break;
            case "transcript":
              if (msg.role === "candidate") {
                setTranscript((t) => [...t, { role: msg.role, text: msg.text }]);
                setCandidateChunks([]);
              } else {
                setTranscript((t) => [...t, { role: msg.role, text: msg.text }]);
              }
              break;
            case "thinking_start":
              // AI turn begins: stop mic + show "thinking".
              setThinking(true);
              stopMicRef.current();
              break;
            case "ai_text":
              // AI is now speaking -> hide "thinking".
              setThinking(false);
              setAiTextChunks((chunks) => [...chunks, { seq: msg.seq, text: msg.text }]);
              break;
            case "audio_chunk":
              if (msg.has_audio) receivedServerAudioRef.current = true;
              else fallbackTextRef.current.push(msg.text);
              break;
            case "ai_response":
              setThinking(false);
              setTranscript((t) => [...t, { role: "ai", text: msg.text }]);
              setAiTextChunks([]);
              break;
            case "nudge":
              // Reassurance is spoken guidance, not an interview question.
              setTranscript((t) => [...t, { role: "nudge", text: msg.text }]);
              setAiTextChunks([]);
              break;
            case "question_complete":
              // All AI audio has been sent; when it finishes draining (or drains
              // right away) we'll send audio_end and auto-open the mic.
              pendingAudioEndRef.current = true;
              if (!receivedServerAudioRef.current && fallbackTextRef.current.length) {
                const fallbackText = fallbackTextRef.current.join(" ");
                fallbackTextRef.current = [];
                speakFallback(fallbackText);
              } else {
                fallbackTextRef.current = [];
                playNext();
              }
              receivedServerAudioRef.current = false;
              break;
            case "listening":
              // Backend re-armed listening (e.g. empty answer) -> open mic.
              setThinking(false);
              startListeningRef.current?.();
              break;
            case "prompt_timeout":
              // AI asks "Are you still there?" -> show as AI message, keep mic open
              setTranscript((t) => [...t, { role: "ai", text: msg.text }]);
              break;
            case "interview_complete":
              setIsComplete(true);
              break;
            case "error":
              console.error("Voice WS error:", msg.message);
              break;
            default:
              break;
          }
        } else {
          // Binary frame = synthesized audio for the chunk announced just before it.
          await enqueueAudio(event.data);
        }
      } catch (e) {
        // A processing error must never kill message handling for later frames.
        console.error("Voice WS message handler error:", e);
      }
    };

    wsRef.current = ws;
  }, [interviewId, enqueueAudio, playNext, speakFallback]);

  const disconnect = useCallback(() => {
    window.speechSynthesis?.cancel();
    wsRef.current?.close();
  }, []);

  return {
    connect,
    disconnect,
    primePlayback,
    startListening,
    stopListening,
    connected,
    listening,
    thinking,
    transcript,
    candidateChunks,
    aiTextChunks,
    isComplete,
  };
}
