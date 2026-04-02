import { useEffect, useMemo, useRef, useState } from "react";
import api from "../lib/api";

function StudentExam({ user }) {
  const [exam, setExam] = useState(null);
  const [roomId, setRoomId] = useState("");
  const [activeRoom, setActiveRoom] = useState(null);
  const [submissionId, setSubmissionId] = useState(null);
  const [answers, setAnswers] = useState({});
  const [secondsLeft, setSecondsLeft] = useState(0);
  const [startedAtMs, setStartedAtMs] = useState(null);
  const [result, setResult] = useState(null);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [warnings, setWarnings] = useState([]);
  const [cameraStatus, setCameraStatus] = useState("off");
  const [cameraNote, setCameraNote] = useState("");
  const [eyeTrackingActive, setEyeTrackingActive] = useState(false);
  const [fullscreenActive, setFullscreenActive] = useState(false);
  const eventBufferRef = useRef([]);
  const flushTimerRef = useRef(null);
  const previousKeyTsRef = useRef(null);
  const hiddenStartRef = useRef(null);
  const blurStartRef = useRef(null);
  const lastAnswerMetaRef = useRef({});
  const warningCooldownRef = useRef({});
  const videoRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const webcamTimerRef = useRef(null);
  const eyeTrackingTimerRef = useRef(null);
  const fullscreenActiveRef = useRef(false);
  const frameCanvasRef = useRef(null);
  const flushSoonTimerRef = useRef(null);
  const lastEyeTrackingAlertsRef = useRef({});
  const fullscreenGraceWarnedRef = useRef(false);

  const canSubmit = useMemo(() => status === "running" && submissionId != null, [status, submissionId]);
  const examLocked = useMemo(
    () => status === "running" && exam && (cameraStatus !== "on" || !fullscreenActive),
    [status, exam, cameraStatus, fullscreenActive]
  );
  const examReady = useMemo(
    () => status === "running" && exam && cameraStatus === "on" && fullscreenActive,
    [status, exam, cameraStatus, fullscreenActive]
  );

  const formattedTime = useMemo(() => {
    const h = Math.floor(secondsLeft / 3600);
    const m = Math.floor((secondsLeft % 3600) / 60);
    const s = secondsLeft % 60;
    return [h, m, s].map((item) => String(item).padStart(2, "0")).join(":");
  }, [secondsLeft]);

  const extractErrorMessage = (requestError, fallback) => {
    const detail = requestError?.response?.data?.detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0];
      if (typeof first === "string") {
        return first;
      }
      if (first?.msg) {
        return first.msg;
      }
      return fallback;
    }
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
    if (typeof requestError?.message === "string" && requestError.message.trim()) {
      return requestError.message;
    }
    return fallback;
  };

  const addEvent = (eventType, metadata = {}) => {
    if (status !== "running" || !startedAtMs) {
      return;
    }
    eventBufferRef.current.push({
      event_type: eventType,
      timestamp_ms: Date.now() - startedAtMs,
      metadata
    });
  };

  const issueWarning = (message, category, metadata = {}, cooldownMs = 3500) => {
    if (status !== "running") {
      return;
    }
    const now = Date.now();
    const last = warningCooldownRef.current[category] || 0;
    if (now - last < cooldownMs) {
      return;
    }
    warningCooldownRef.current[category] = now;

    setWarnings((current) => {
      const next = [
        {
          id: `${Date.now()}-${category}`,
          text: message,
          at: new Date().toLocaleTimeString(),
        },
        ...current,
      ];
      return next.slice(0, 6);
    });
    addEvent("warning_issued", { category, ...metadata });
    if (flushSoonTimerRef.current) {
      window.clearTimeout(flushSoonTimerRef.current);
    }
    flushSoonTimerRef.current = window.setTimeout(() => {
      flushEvents();
    }, 450);
  };

  const stopCameraMonitoring = async () => {
    if (webcamTimerRef.current) {
      window.clearInterval(webcamTimerRef.current);
      webcamTimerRef.current = null;
    }
    if (eyeTrackingTimerRef.current) {
      window.clearInterval(eyeTrackingTimerRef.current);
      eyeTrackingTimerRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setEyeTrackingActive(false);
    setCameraStatus("off");
    setCameraNote("");
    addEvent("webcam_disabled");

    if (submissionId) {
      try {
        await api.post(`/vision/reset-tracker?submission_id=${submissionId}`);
      } catch {
        // Non-blocking cleanup.
      }
    }
  };

  const captureFrameAsBase64 = () => {
    const video = videoRef.current;
    if (!video || video.readyState < 2) {
      return null;
    }

    try {
      if (!frameCanvasRef.current) {
        frameCanvasRef.current = document.createElement("canvas");
      }
      
      const canvas = frameCanvasRef.current;
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext("2d");
      if (!ctx) {
        return null;
      }

      ctx.drawImage(video, 0, 0);
      return canvas.toDataURL("image/jpeg", 0.7).split(",")[1]; // Remove data: prefix
    } catch {
      return null;
    }
  };

  const processEyeTrackingFrame = async () => {
    if (!submissionId || !videoRef.current || videoRef.current.readyState < 2) {
      return;
    }

    try {
      const frameBase64 = captureFrameAsBase64();
      if (!frameBase64) {
        return;
      }

      // Send frame to backend for eye tracking
      const response = await api.post("/vision/process-frame", {
        submission_id: submissionId,
        frame_base64: frameBase64,
      });

      if (response.data?.status === "success") {
        const data = response.data;
        
        // Add eye tracking event
        addEvent("eye_tracking_processed", {
          frame_timestamp: data.timestamp_ms,
          detections: data.detections || {},
        });

        // Handle alerts
        const alerts = data.alerts || [];
        alerts.forEach((alert) => {
          // Avoid alert spam - only issue if not recently alerted
          const alertKey = alert.type;
          const now = Date.now();
          const lastTime = lastEyeTrackingAlertsRef.current[alertKey] || 0;
          const previousCount = lastEyeTrackingAlertsRef.current[`${alertKey}_count`] || 0;
          const nextCount = previousCount + 1;
          lastEyeTrackingAlertsRef.current[`${alertKey}_count`] = nextCount;
          
          // Cooldown based on severity
          const cooldownMs = alert.severity === "high" ? 3000 : alert.severity === "medium" ? 5000 : 7000;
          
          if (now - lastTime >= cooldownMs) {
            lastEyeTrackingAlertsRef.current[alertKey] = now;
            issueWarning(alert.description, `eye_${alert.type}`, {
              eye_alert_type: alert.type,
              alert_severity: alert.severity,
            }, cooldownMs);

            addEvent("eye_movement_alert", {
              alert_type: alert.type,
              severity: alert.severity,
              description: alert.description,
            });

            if ((alert.type === "looking_left" || alert.type === "looking_right") && nextCount >= 5) {
              issueWarning(
                `${alert.type === "looking_left" ? "Left" : "Right"} eye movement crossed 5 alerts.`,
                `eye_threshold_${alert.type}`,
                {
                  eye_alert_type: alert.type,
                  alert_count: nextCount,
                },
                10000
              );
            }
          }
        });
      }
    } catch (err) {
      addEvent("eye_tracking_error", { error: err?.message || "unknown" });
      issueWarning(
        "Eye tracking service unavailable. Re-enable webcam or check backend.",
        "eye_tracking_service_error",
        { error: err?.message || "unknown" },
        9000
      );
    }
  };

  const startCameraMonitoring = async () => {
    if (status !== "running" || cameraStatus === "on" || cameraStatus === "starting") {
      return;
    }
    if (!navigator?.mediaDevices?.getUserMedia) {
      setCameraNote("Webcam not supported in this browser.");
      issueWarning("Webcam is not supported in this browser.", "webcam_not_supported", {}, 10000);
      return;
    }
    try {
      setCameraStatus("starting");

      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 640 }, height: { ideal: 480 } }, audio: false });
      mediaStreamRef.current = stream;
      
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        
        // Wait for video to be ready and then play
        const playPromise = videoRef.current.play();
        if (playPromise !== undefined) {
          playPromise
            .then(() => {
              setCameraStatus("on");
              addEvent("webcam_enabled");
            })
            .catch((error) => {
              setCameraStatus("denied");
              addEvent("webcam_play_failed", { error: error.name });
              issueWarning("Webcam stream failed to initialize. Please try again.", "webcam_play_error", {}, 10000);
            });
        } else {
          // Older browsers - assume success
          setCameraStatus("on");
          addEvent("webcam_enabled");
        }
      } else {
        // If ref is still missing, keep camera enabled and attach on next render.
        setCameraStatus("on");
        addEvent("webcam_enabled_ref_pending");
      }

      setCameraNote("YOLO + FaceLandmarker monitoring active.");

      webcamTimerRef.current = window.setInterval(() => {
        const activeTrack = mediaStreamRef.current?.getVideoTracks?.()[0];
        if (!activeTrack || activeTrack.readyState !== "live") {
          addEvent("webcam_feed_unavailable");
          issueWarning("Webcam feed interrupted. Re-enable webcam monitoring.", "webcam_feed_interrupted", {}, 8000);
        }
      }, 1800);

      // Start eye tracking stream (more frequent for real-time gaze detection)
      setEyeTrackingActive(true);
      eyeTrackingTimerRef.current = window.setInterval(() => {
        processEyeTrackingFrame();
      }, 350);
    } catch (error) {
      setCameraStatus("denied");
      setCameraNote("Camera permission denied. Enable it for full monitoring.");
      addEvent("webcam_permission_denied", { error_name: error?.name });
      issueWarning("Webcam permission denied. Monitoring accuracy will be lower.", "webcam_denied", {}, 10000);
    }
  };

  useEffect(() => {
    if (cameraStatus !== "on") {
      return;
    }
    if (!videoRef.current || !mediaStreamRef.current || videoRef.current.srcObject === mediaStreamRef.current) {
      return;
    }
    videoRef.current.srcObject = mediaStreamRef.current;
    const playPromise = videoRef.current.play();
    if (playPromise && typeof playPromise.then === "function") {
      playPromise.catch(() => {
        addEvent("webcam_play_retry_failed");
      });
    }
  }, [cameraStatus]);

  const handleAnswerChange = (questionId, nextValue) => {
    const currentValue = answers[questionId] || "";
    const deltaChars = nextValue.length - currentValue.length;
    const now = Date.now();
    const previous = lastAnswerMetaRef.current[questionId];
    const deltaMs = previous ? now - previous.timestamp : null;

    setAnswers((current) => ({
      ...current,
      [questionId]: nextValue,
    }));

    lastAnswerMetaRef.current[questionId] = {
      timestamp: now,
      length: nextValue.length,
    };

    addEvent("answer_change", {
      question_id: questionId,
      char_count: nextValue.length,
      delta_chars: deltaChars,
      delta_ms: deltaMs,
    });

    if (deltaMs && deltaMs < 750 && Math.abs(deltaChars) > 180) {
      issueWarning("Rapid answer change detected. Avoid large instant inserts.", "answer_jump", {
        question_id: questionId,
      });
    }
  };

  const flushEvents = async () => {
    if (!submissionId || eventBufferRef.current.length === 0) {
      return;
    }
    const payload = [...eventBufferRef.current];
    eventBufferRef.current = [];
    try {
      const chunkSize = 180;
      for (let index = 0; index < payload.length; index += chunkSize) {
        const chunk = payload.slice(index, index + chunkSize);
        // Keep each request below backend max event count.
        await api.post("/events/batch", { submission_id: submissionId, events: chunk });
      }
    } catch {
      eventBufferRef.current = [...payload, ...eventBufferRef.current];
    }
  };

  const startExam = async () => {
    setError("");
    setResult(null);
    try {
      const roomResponse = await api.get(`/rooms/resolve/${roomId}`);
      const examResponse = await api.get(`/exams/${roomResponse.data.exam_id}`);
      const submissionResponse = await api.post("/submissions/start", {
        exam_id: examResponse.data.id
      });
      setActiveRoom(roomResponse.data);
      setExam(examResponse.data);
      setSubmissionId(submissionResponse.data.submission_id);
      setAnswers({});
      setWarnings([]);
      setSecondsLeft(examResponse.data.duration_minutes * 60);
      setStartedAtMs(Date.now());
      setStatus("running");
      setFullscreenActive(Boolean(document.fullscreenElement));
      fullscreenGraceWarnedRef.current = false;
      previousKeyTsRef.current = null;
      hiddenStartRef.current = null;
      blurStartRef.current = null;
      lastAnswerMetaRef.current = {};
    } catch (requestError) {
      const detail = extractErrorMessage(requestError, "Could not start exam. Check room ID or ask your teacher to approve your account.");
      if (/already attempted this exam once/i.test(detail) || /already submitted this exam/i.test(detail)) {
        setError("You have already attempted this exam once. You cannot start it again.");
      } else {
        setError(detail);
      }
    }
  };

  const submitExam = async () => {
    if (!submissionId || !startedAtMs) {
      return;
    }
    setStatus("submitting");
    await flushEvents();
    try {
      const timeTakenSeconds = Math.max(1, Math.round((Date.now() - startedAtMs) / 1000));
      const response = await api.post(`/submissions/${submissionId}/submit`, {
        answers,
        time_taken_seconds: timeTakenSeconds
      });
      setResult(response.data);
      setStatus("done");
      stopCameraMonitoring();
    } catch {
      setError("Submission failed");
      setStatus("running");
    }
  };

  const resetToHome = () => {
    stopCameraMonitoring();
    setExam(null);
    setActiveRoom(null);
    setRoomId("");
    setSubmissionId(null);
    setAnswers({});
    setSecondsLeft(0);
    setStartedAtMs(null);
    setResult(null);
    setStatus("idle");
    setWarnings([]);
    setCameraNote("");
    setError("");
    fullscreenActiveRef.current = false;
    setFullscreenActive(false);
    fullscreenGraceWarnedRef.current = false;
    lastAnswerMetaRef.current = {};
    previousKeyTsRef.current = null;
    hiddenStartRef.current = null;
    blurStartRef.current = null;
    eventBufferRef.current = [];
  };

  useEffect(() => {
    if (status !== "running") {
      return undefined;
    }
    const timer = window.setInterval(() => {
      setSecondsLeft((current) => {
        if (current <= 1) {
          window.clearInterval(timer);
          submitExam();
          return 0;
        }
        return current - 1;
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [status]);

  const requestFullscreenMode = async () => {
    if (!document.fullscreenElement && document.documentElement?.requestFullscreen) {
      try {
        await document.documentElement.requestFullscreen();
        fullscreenActiveRef.current = true;
        setFullscreenActive(true);
        addEvent("fullscreen_requested");
      } catch {
        addEvent("fullscreen_request_denied");
        issueWarning("Fullscreen permission denied. This increases risk visibility.", "fullscreen_denied", {}, 10000);
      }
    }
  };

  useEffect(() => {
    if (status !== "running") {
      return undefined;
    }
    const fullscreenGraceTimer = window.setTimeout(() => {
      if (status === "running" && !fullscreenActiveRef.current && !fullscreenGraceWarnedRef.current) {
        fullscreenGraceWarnedRef.current = true;
        addEvent("fullscreen_not_entered");
        issueWarning("Enter fullscreen to reduce risk score.", "fullscreen_not_entered", {}, 10000);
      }
    }, 60000);

    const onVisibility = () => {
      if (document.hidden) {
        hiddenStartRef.current = Date.now();
        addEvent("tab_hidden");
        issueWarning("Tab switching detected. Stay on the exam page.", "tab_switch", {}, 2500);
        flushEvents();
      } else {
        const hiddenDuration = hiddenStartRef.current ? Date.now() - hiddenStartRef.current : 0;
        addEvent("tab_visible", { hidden_duration_ms: hiddenDuration });
        hiddenStartRef.current = null;
      }
    };
    const onBlur = () => {
      blurStartRef.current = Date.now();
      addEvent("window_blur");
    };
    const onFocus = () => {
      const blurDuration = blurStartRef.current ? Date.now() - blurStartRef.current : 0;
      addEvent("window_focus", { blur_duration_ms: blurDuration });
      blurStartRef.current = null;
    };
    const onPaste = (event) => {
      const pastedText = event.clipboardData?.getData("text") || "";
      const lines = pastedText
        .split(/\r?\n/)
        .map((item) => item.trim())
        .filter(Boolean);
      addEvent("paste", {
        char_count: pastedText.length,
        line_count: lines.length,
        first_line_preview: lines[0] ? lines[0].slice(0, 80) : "",
        pasted_lines_preview: lines.slice(0, 3).map((item) => item.slice(0, 120)),
      });
      if (pastedText.length > 180) {
        issueWarning("Large paste detected. This may increase your risk score.", "large_paste", {
          char_count: pastedText.length,
        });
      }
    };
    const onKeyDown = () => {
      const now = Date.now();
      const prev = previousKeyTsRef.current;
      previousKeyTsRef.current = now;
      const deltaMs = prev ? now - prev : null;
      addEvent("keystroke", deltaMs ? { delta_ms: deltaMs } : {});
      if (deltaMs && deltaMs > 10000) {
        addEvent("idle_gap", { delta_ms: deltaMs });
      }
      if (deltaMs && deltaMs < 25) {
        addEvent("typing_burst", { delta_ms: deltaMs });
      }
    };

    const onFullscreenChange = () => {
      if (!document.fullscreenElement && fullscreenActiveRef.current) {
        addEvent("fullscreen_exit");
        issueWarning("Fullscreen exit detected. Please return to exam mode.", "fullscreen_exit", {}, 3000);
        fullscreenActiveRef.current = false;
        setFullscreenActive(false);
        flushEvents();
      } else if (document.fullscreenElement) {
        fullscreenActiveRef.current = true;
        setFullscreenActive(true);
      }
    };

    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("blur", onBlur);
    window.addEventListener("focus", onFocus);
    document.addEventListener("paste", onPaste);
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("fullscreenchange", onFullscreenChange);

    flushTimerRef.current = window.setInterval(() => {
      flushEvents();
    }, 5000);

    return () => {
      window.clearTimeout(fullscreenGraceTimer);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("blur", onBlur);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("paste", onPaste);
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("fullscreenchange", onFullscreenChange);
      if (flushTimerRef.current) {
        window.clearInterval(flushTimerRef.current);
      }
      if (flushSoonTimerRef.current) {
        window.clearTimeout(flushSoonTimerRef.current);
      }
    };
  }, [status, startedAtMs, submissionId]);

  useEffect(() => {
    if (status === "running") {
      return undefined;
    }
    stopCameraMonitoring();
    return undefined;
  }, [status]);

  useEffect(() => {
    return () => {
      stopCameraMonitoring();
    };
  }, []);

  return (
    <>
      <div className="panel student-exam-panel">
      <div className="panel-hero">
        <p className="brand-kicker">Candidate Workspace</p>
        <h2>Student Exam</h2>
      </div>
      <p className="muted">
        Monitoring is enabled: tab activity, typing rhythm, and paste events. Welcome {user.name}.
      </p>

      {status === "idle" ? (
        <div className="inline-row">
          <label>
            Room ID
            <input
              value={roomId}
              onChange={(event) => setRoomId(event.target.value.toUpperCase())}
              placeholder="TR12-ABC123"
            />
          </label>
          <button onClick={startExam}>Start Exam</button>
        </div>
      ) : null}

      {activeRoom ? (
        <p className="muted">
          Joined: {activeRoom.course_title} ({activeRoom.course_code}) - Teacher: {activeRoom.teacher_name}
        </p>
      ) : null}

      {status === "running" && exam ? (
        <>
          <div className="timer">Time Left: {formattedTime}</div>
          <div className="inline-row">
            <button
              type="button"
              onClick={() => requestFullscreenMode()}
              title="Enter fullscreen to reduce distractions"
            >
              Enter Fullscreen
            </button>
            <button
              type="button"
              disabled={cameraStatus === "starting"}
              className={cameraStatus === "on" ? "secondary-btn" : ""}
              onClick={() => {
                if (cameraStatus === "on") {
                  stopCameraMonitoring();
                } else {
                  startCameraMonitoring();
                }
              }}
            >
              {cameraStatus === "starting"
                ? "Starting Webcam..."
                : cameraStatus === "on"
                ? "Disable Webcam Monitoring"
                : "Enable Webcam Monitoring"}
            </button>
            <p className="muted">
              Webcam status: {cameraStatus === "on" ? "active" : cameraStatus === "starting" ? "starting" : cameraStatus === "denied" ? "denied" : "off"}
            </p>
            {cameraNote ? <p className="muted">{cameraNote}</p> : null}
          </div>
          {examLocked ? (
            <div className="warning-feed">
              <div className="warning-item">
                <strong>Exam Locked:</strong> enable webcam and enter fullscreen before questions appear.
              </div>
            </div>
          ) : null}
          {warnings.length > 0 ? (
            <div className="warning-feed">
              {warnings.map((item) => (
                <div key={item.id} className="warning-item">
                  <strong>Warning:</strong> {item.text} <span className="muted">({item.at})</span>
                </div>
              ))}
            </div>
          ) : null}
          {examReady ? (
            <>
              {exam.questions.map((question, index) => (
                <div className="question-card" key={question.id}>
                  <p>
                    <strong>Question {index + 1}</strong>
                    {" "}
                    <span className="muted">(Marks: {Number(question.max_marks ?? 10)})</span>
                  </p>
                  <p>{question.prompt}</p>
                  {question.type === "mcq" ? (
                    <select
                      value={answers[question.id] || ""}
                      onChange={(event) => handleAnswerChange(question.id, event.target.value)}
                    >
                      <option value="">Select one option</option>
                      {(question.options || []).map((option, index) => (
                        <option key={`${question.id}-opt-${index}`} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <textarea
                      value={answers[question.id] || ""}
                      onChange={(event) => handleAnswerChange(question.id, event.target.value)}
                      rows={4}
                    />
                  )}
                </div>
              ))}
              <button onClick={submitExam} disabled={!canSubmit}>
                Submit Now
              </button>
            </>
          ) : null}
        </>
      ) : null}

      {result ? (
        <div className="result-box">
          <h3>Result</h3>
          <p>Suspicion Score: {result.suspicion_score}</p>
          <p>Risk Band: {result.risk_band}</p>
          <button type="button" onClick={resetToHome}>
            Back to Exam Start
          </button>
        </div>
      ) : null}

      {error ? <p className="error">{error}</p> : null}
      </div>
      {(cameraStatus === "on" || cameraStatus === "starting") && (
        <div className="camera-box-floating">
          <video ref={videoRef} autoPlay muted playsInline />
        </div>
      )}
    </>
  );
}

export default StudentExam;

