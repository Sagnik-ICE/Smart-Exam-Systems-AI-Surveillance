import { useEffect, useMemo, useRef, useState } from "react";
import api from "../lib/api";
import QuestionBuilder from "./QuestionBuilder";

function TeacherPanel({ user, onTogglePortal, portalOpen, onLogout }) {
  const [section, setSection] = useState("overview");
  const [examId, setExamId] = useState(1);
  const [loading, setLoading] = useState(false);
  const [dashboard, setDashboard] = useState(null);
  const [message, setMessage] = useState("");
  const [selectedSubmissionId, setSelectedSubmissionId] = useState(null);
  const [replayIndex, setReplayIndex] = useState(0);
  const [liveMode, setLiveMode] = useState(false);
  const [refreshSeconds, setRefreshSeconds] = useState(1);
  const [recentNewIds, setRecentNewIds] = useState([]);
  const [lastUpdatedAt, setLastUpdatedAt] = useState(null);
  const [alertText, setAlertText] = useState("");
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [alertHistory, setAlertHistory] = useState([]);
  const [eyeSheetData, setEyeSheetData] = useState(null);
  const [monitorDetailOpen, setMonitorDetailOpen] = useState(false);

  const [courseName, setCourseName] = useState("");
  const [courseCode, setCourseCode] = useState("");
  const [examName, setExamName] = useState("");
  const [durationMinutes, setDurationMinutes] = useState(20);
  const [scheduledAt, setScheduledAt] = useState("");
  const [scheduledEndAt, setScheduledEndAt] = useState("");
  const [rooms, setRooms] = useState([]);
  const [builderRoom, setBuilderRoom] = useState(null);

  const [pendingStudents, setPendingStudents] = useState([]);
  const [students, setStudents] = useState([]);
  const [newStudent, setNewStudent] = useState({
    name: "",
    department: "",
    user_code: "",
    email: "",
    contact_number: "",
    password: ""
  });

  const [teacherExams, setTeacherExams] = useState([]);
  const [selectedExamSummary, setSelectedExamSummary] = useState(null);
  const [answerRows, setAnswerRows] = useState([]);
  const [markDraft, setMarkDraft] = useState({});
  const [selectedAnswerRow, setSelectedAnswerRow] = useState(null);
  const [perQuestionDraft, setPerQuestionDraft] = useState({});
  const [studentFilter, setStudentFilter] = useState("");

  const seenSubmissionIdsRef = useRef(new Set());
  const alertTimerRef = useRef(null);
  const dashboardTopRef = useRef(null);

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
    }
    if (typeof detail === "string") {
      return detail;
    }
    return fallback;
  };

  const loadRooms = async () => {
    try {
      const response = await api.get("/rooms/mine");
      setRooms(Array.isArray(response.data) ? response.data : []);
    } catch {
      setRooms([]);
    }
  };

  const loadTeacherExams = async () => {
    try {
      const response = await api.get("/analytics/teacher/exams");
      setTeacherExams(Array.isArray(response.data) ? response.data : []);
    } catch {
      setTeacherExams([]);
    }
  };

  const toIsoDateTime = (value) => {
    if (!value) {
      return null;
    }
    return new Date(value).toISOString();
  };

  const formatScheduleWindow = (startAt, endAt) => {
    if (!startAt && !endAt) {
      return "Not scheduled";
    }

    const startDate = startAt ? new Date(startAt) : null;
    const endDate = endAt ? new Date(endAt) : null;
    if (!startDate || Number.isNaN(startDate.getTime())) {
      return "Not scheduled";
    }

    const dateText = startDate.toLocaleDateString();
    const startText = startDate.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    if (!endDate || Number.isNaN(endDate.getTime())) {
      return `${dateText} · ${startText}`;
    }

    const endText = endDate.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    return `${dateText} · ${startText} - ${endText}`;
  };

  const createRoom = async () => {
    const normalizedCourseName = courseName.trim();
    const normalizedCourseCode = courseCode.trim();
    const normalizedExamName = examName.trim();
    const hasScheduleStart = Boolean(scheduledAt);
    const hasScheduleEnd = Boolean(scheduledEndAt);

    if (normalizedCourseName.length < 3) {
      setMessage("Course Name must be at least 3 characters");
      return;
    }
    if (normalizedCourseCode.length < 2) {
      setMessage("Course Code must be at least 2 characters");
      return;
    }
    if (normalizedExamName.length < 3) {
      setMessage("Exam Name must be at least 3 characters");
      return;
    }

    if (!Number.isFinite(durationMinutes) || durationMinutes < 1 || durationMinutes > 300) {
      setMessage("Duration must be between 1 and 300 minutes");
      return;
    }
    if (hasScheduleStart !== hasScheduleEnd) {
      setMessage("Please provide both schedule start and end, or leave both blank");
      return;
    }
    if (hasScheduleStart && hasScheduleEnd && new Date(scheduledEndAt) <= new Date(scheduledAt)) {
      setMessage("Schedule end must be after schedule start");
      return;
    }

    setLoading(true);
    setMessage("");
    try {
      let response;
      let stripAutogeneratedQuestions = false;
      try {
        response = await api.post("/rooms", {
          course_name: normalizedCourseName,
          course_code: normalizedCourseCode,
          exam_name: normalizedExamName,
          duration_minutes: durationMinutes,
          scheduled_at: toIsoDateTime(scheduledAt),
          scheduled_end_at: toIsoDateTime(scheduledEndAt)
        });
      } catch (requestError) {
        const detail = requestError?.response?.data?.detail;
        const detailText = Array.isArray(detail)
          ? JSON.stringify(detail)
          : typeof detail === "string"
          ? detail
          : "";

        if (/Either questions or total_questions must be provided/i.test(detailText)) {
          response = await api.post("/rooms", {
            course_name: normalizedCourseName,
            course_code: normalizedCourseCode,
            exam_name: normalizedExamName,
            duration_minutes: durationMinutes,
            scheduled_at: toIsoDateTime(scheduledAt),
            scheduled_end_at: toIsoDateTime(scheduledEndAt),
            total_questions: 1,
          });
          stripAutogeneratedQuestions = true;
        } else {
          throw requestError;
        }
      }

      const responseRoom = response.data;
      setExamId(responseRoom.exam_id);
      setBuilderRoom({
        room_id: responseRoom.room_id,
        exam_id: responseRoom.exam_id,
        course_title: normalizedCourseName,
        course_code: normalizedCourseCode,
        strip_autogenerated_questions: stripAutogeneratedQuestions,
      });
      setCourseName("");
      setCourseCode("");
      setExamName("");
      setDurationMinutes(20);
      setScheduledAt("");
      setScheduledEndAt("");
      setMessage(`Room created: ${responseRoom.room_id}. Opened paper builder.`);
      loadRooms();
      loadTeacherExams();
    } catch (requestError) {
      setMessage(extractErrorMessage(requestError, "Could not create room"));
    } finally {
      setLoading(false);
    }
  };

  const deleteRoom = async (roomId) => {
    try {
      await api.delete(`/rooms/${roomId}`);
      setMessage(`Room ${roomId} deleted`);
      loadRooms();
      loadTeacherExams();
    } catch (requestError) {
      setMessage(requestError?.response?.data?.detail || "Could not delete room");
    }
  };

  const copyRoomId = async (roomId) => {
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(roomId);
      } else {
        const textArea = document.createElement("textarea");
        textArea.value = roomId;
        textArea.setAttribute("readonly", "");
        textArea.style.position = "absolute";
        textArea.style.left = "-9999px";
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand("copy");
        document.body.removeChild(textArea);
      }
      setMessage(`Room ID copied: ${roomId}`);
    } catch {
      setMessage("Could not copy room ID");
    }
  };

  const deleteExamWithData = async (examId) => {
    try {
      await api.delete(`/rooms/exam/${examId}`);
      setMessage(`Exam ${examId} deleted permanently`);
      setDashboard(null);
      loadRooms();
      loadTeacherExams();
    } catch (requestError) {
      setMessage(requestError?.response?.data?.detail || "Could not permanently delete exam");
    }
  };

  const loadPendingStudents = async () => {
    try {
      const response = await api.get("/management/pending");
      setPendingStudents(Array.isArray(response.data) ? response.data : []);
    } catch {
      setPendingStudents([]);
    }
  };

  const loadStudents = async () => {
    try {
      const response = await api.get("/management/users?role=student");
      setStudents(Array.isArray(response.data) ? response.data : []);
    } catch {
      setStudents([]);
    }
  };

  const approveStudent = async (userId, approve) => {
    try {
      await api.post(`/management/approve/${userId}`, { approve });
      setMessage(approve ? "Student approved" : "Student rejected");
      loadPendingStudents();
      loadStudents();
    } catch (requestError) {
      setMessage(requestError?.response?.data?.detail || "Could not update student approval");
    }
  };

  const setStudentAccess = async (userId, isActive) => {
    try {
      await api.post(`/management/access/${userId}`, { is_active: isActive });
      setMessage(isActive ? "Student access enabled" : "Student access disabled");
      loadStudents();
    } catch (requestError) {
      setMessage(requestError?.response?.data?.detail || "Could not update student access");
    }
  };

  const deleteStudent = async (userId) => {
    try {
      await api.delete(`/management/users/${userId}`);
      setMessage("Student deleted");
      loadPendingStudents();
      loadStudents();
    } catch (requestError) {
      setMessage(requestError?.response?.data?.detail || "Could not delete student");
    }
  };

  const createStudentManual = async (event) => {
    event.preventDefault();
    try {
      await api.post("/management/create-user", {
        ...newStudent,
        role: "student",
        approve_now: true
      });
      setMessage("Student created manually");
      setNewStudent({
        name: "",
        department: "",
        user_code: "",
        email: "",
        contact_number: "",
        password: ""
      });
      loadStudents();
      loadPendingStudents();
    } catch (requestError) {
      setMessage(requestError?.response?.data?.detail || "Could not create student");
    }
  };

  const loadDashboard = async (targetExamId, options = {}) => {
    const { fromLiveTick = false } = options;
    const effectiveExamId = targetExamId || examId;
    if (!fromLiveTick) {
      setSection("monitoring");
      setLiveMode(true);
      setLoading(true);
    }
    try {
      const response = await api.get(`/analytics/exam/${effectiveExamId}`);
      setDashboard(response.data);

      const incomingIds = response.data.submissions.map((item) => item.submission_id);
      const newIds = incomingIds.filter((id) => !seenSubmissionIdsRef.current.has(id));
      setRecentNewIds(newIds);

      const newHighRisk = response.data.submissions.filter(
        (row) => newIds.includes(row.submission_id) && row.risk_band === "High Risk"
      );
      if (newHighRisk.length > 0) {
        const names = newHighRisk.map((row) => row.student_name).join(", ");
        setAlertText(`ALERT: New High Risk submission detected (${names})`);
        setAlertHistory((current) => {
          const next = [
            {
              id: `${Date.now()}-${newHighRisk.length}`,
              time: new Date().toLocaleTimeString(),
              names,
              count: newHighRisk.length
            },
            ...current
          ];
          return next.slice(0, 12);
        });
        if (alertTimerRef.current) {
          window.clearTimeout(alertTimerRef.current);
        }
        alertTimerRef.current = window.setTimeout(() => setAlertText(""), 7000);

        if (soundEnabled) {
          try {
            const context = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = context.createOscillator();
            const gain = context.createGain();
            oscillator.type = "triangle";
            oscillator.frequency.value = 880;
            gain.gain.value = 0.04;
            oscillator.connect(gain);
            gain.connect(context.destination);
            oscillator.start();
            oscillator.stop(context.currentTime + 0.18);
          } catch {
            // Visual alert remains if sound is blocked.
          }
        }
      }

      seenSubmissionIdsRef.current = new Set(incomingIds);

      if (response.data.submissions.length > 0) {
        const currentExists = response.data.submissions.some(
          (item) => item.submission_id === selectedSubmissionId
        );
        if (!selectedSubmissionId || !currentExists) {
          setSelectedSubmissionId(response.data.submissions[0].submission_id);
          setReplayIndex(0);
        }
      }
      setLastUpdatedAt(new Date().toLocaleTimeString());
      setExamId(effectiveExamId);
      setMessage("");
      if (!fromLiveTick) {
        window.setTimeout(() => {
          dashboardTopRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 60);
      }
    } catch (requestError) {
      setDashboard(null);
      setMessage(requestError?.response?.data?.detail || "No submissions found yet for this exam");
    } finally {
      if (!fromLiveTick) {
        setLoading(false);
      }
    }
  };

  const downloadReport = async (format) => {
    setLoading(true);
    try {
      const response = await api.get(`/analytics/exam/${examId}/export.${format}`, {
        responseType: "blob"
      });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = url;
      link.download = `exam_${examId}_report.${format}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setMessage(`Downloaded ${format.toUpperCase()} report for exam ${examId}`);
    } catch (requestError) {
      setMessage(requestError?.response?.data?.detail || `Could not download ${format.toUpperCase()} report`);
    } finally {
      setLoading(false);
    }
  };

  const loadAnswerStatus = async (examSummary, keepCurrentView = false) => {
    setLoading(true);
    setSelectedExamSummary(examSummary);
    try {
      const response = await api.get(`/analytics/exam/${examSummary.exam_id}/answers`);
      const rows = Array.isArray(response.data) ? response.data : [];
      setAnswerRows(rows);
      const draft = {};
      rows.forEach((row) => {
        draft[row.submission_id] = {
          marks: row.marks ?? "",
          evaluation_status: row.evaluation_status || "pending"
        };
      });
      setMarkDraft(draft);
      if (!keepCurrentView) {
        setSelectedAnswerRow(null);
        setPerQuestionDraft({});
        setSection("answers");
      }
    } catch (requestError) {
      setMessage(requestError?.response?.data?.detail || "Could not load exam answer status");
    } finally {
      setLoading(false);
    }
  };

  const saveMark = async (submissionId) => {
    const draft = markDraft[submissionId] || {};
    const row = answerRows.find((item) => item.submission_id === submissionId);
    const totalMaxMarks = Object.values(row?.question_max_marks || {}).reduce(
      (sum, value) => sum + Number(value || 0),
      0
    );
    const enteredMarks = Number(draft.marks || 0);

    if (enteredMarks < 0) {
      setMessage("Marks cannot be negative");
      return;
    }

    if (totalMaxMarks > 0 && enteredMarks > totalMaxMarks) {
      setMessage(`Marks cannot exceed fixed paper marks (${totalMaxMarks})`);
      return;
    }

    try {
      const response = await api.post(`/analytics/submission/${submissionId}/mark`, {
        marks: enteredMarks,
        evaluation_status: draft.evaluation_status || "pending"
      });
      setMessage("Marks updated");
      // Update markDraft immediately with the saved values to prevent race conditions
      // with the auto-refresh interval
      const { marks, evaluation_status } = response.data || {};
      if (marks !== undefined && evaluation_status) {
        setMarkDraft(prev => ({
          ...prev,
          [submissionId]: {
            marks,
            evaluation_status
          }
        }));
      }
      // Still refresh to ensure the full table is up to date
      if (selectedExamSummary) {
        loadAnswerStatus(selectedExamSummary);
      }
    } catch (requestError) {
      setMessage(requestError?.response?.data?.detail || "Could not save marks");
    }
  };

  const openAnswerDetail = (row) => {
    setSelectedAnswerRow(row);
    const nextDraft = {};
    Object.keys(row.answers || {}).forEach((questionId) => {
      nextDraft[questionId] = row.question_marks?.[questionId] ?? 0;
    });
    setPerQuestionDraft(nextDraft);
  };

  const saveDetailedMarks = async () => {
    if (!selectedAnswerRow) {
      return;
    }
    const invalidQuestion = Object.entries(perQuestionDraft).find(([questionId, value]) => {
      const mark = Number(value || 0);
      const max = Number(selectedAnswerRow.question_max_marks?.[questionId] ?? 0);
      if (mark < 0) {
        return true;
      }
      if (max > 0 && mark > max) {
        return true;
      }
      return false;
    });

    if (invalidQuestion) {
      const [questionId] = invalidQuestion;
      const max = Number(selectedAnswerRow.question_max_marks?.[questionId] ?? 0);
      setMessage(`Marks for ${questionId} cannot exceed fixed max marks (${max})`);
      return;
    }

    const total = Object.values(perQuestionDraft).reduce((sum, value) => sum + Number(value || 0), 0);
    const currentStatus = markDraft[selectedAnswerRow.submission_id]?.evaluation_status || "pending";

    try {
      const response = await api.post(`/analytics/submission/${selectedAnswerRow.submission_id}/mark`, {
        marks: total,
        evaluation_status: currentStatus,
        question_marks: perQuestionDraft
      });
      setMessage("Detailed marks saved");
      // Update markDraft immediately with the saved values to prevent race conditions
      // with the auto-refresh interval
      const { marks, evaluation_status } = response.data || {};
      if (marks !== undefined && evaluation_status) {
        setMarkDraft(prev => ({
          ...prev,
          [selectedAnswerRow.submission_id]: {
            marks,
            evaluation_status
          }
        }));
      }
      if (selectedExamSummary) {
        await loadAnswerStatus(selectedExamSummary);
      }
      setSelectedAnswerRow(null);
      setPerQuestionDraft({});
    } catch (requestError) {
      setMessage(requestError?.response?.data?.detail || "Could not save detailed marks");
    }
  };

  const downloadResultSheet = async () => {
    if (!selectedExamSummary) {
      return;
    }
    try {
      const response = await api.get(
        `/analytics/exam/${selectedExamSummary.exam_id}/result-sheet.pdf`,
        { responseType: "blob" }
      );
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = url;
      link.download = `exam_${selectedExamSummary.exam_id}_result_sheet.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (requestError) {
      setMessage(requestError?.response?.data?.detail || "Could not generate result sheet PDF");
    }
  };

  const printStudentDetail = async (submissionId) => {
    try {
      const response = await api.get(`/analytics/submission/${submissionId}/detail.pdf`, {
        responseType: "blob"
      });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = url;
      link.download = `submission_${submissionId}_detail.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (requestError) {
      setMessage(requestError?.response?.data?.detail || "Could not print student detail");
    }
  };

  const printStudentProfile = async (studentId) => {
    try {
      const response = await api.get(`/management/users/${studentId}/student-report.pdf`, {
        responseType: "blob"
      });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = url;
      link.download = `student_${studentId}_report.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (requestError) {
      setMessage(requestError?.response?.data?.detail || "Could not print student report");
    }
  };

  useEffect(() => {
    loadRooms();
    loadPendingStudents();
    loadStudents();
    loadTeacherExams();
  }, []);

  useEffect(() => {
    return () => {
      if (alertTimerRef.current) {
        window.clearTimeout(alertTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!liveMode) {
      return undefined;
    }
    const intervalMs = Math.max(1, Number(refreshSeconds) || 2) * 1000;
    const interval = window.setInterval(() => {
      loadDashboard(examId, { fromLiveTick: true });
    }, intervalMs);
    return () => window.clearInterval(interval);
  }, [liveMode, refreshSeconds, examId]);

  useEffect(() => {
    if (section !== "answers" || !selectedExamSummary) {
      return undefined;
    }
    const interval = window.setInterval(() => {
      loadAnswerStatus(selectedExamSummary, true);
    }, 4000);
    return () => window.clearInterval(interval);
  }, [section, selectedExamSummary]);

  const selectedSubmission = dashboard?.submissions?.find(
    (item) => item.submission_id === selectedSubmissionId
  );
  const replayTimeline = selectedSubmission?.timeline || [];
  const currentReplayEvent = replayTimeline[replayIndex] || null;
  const liveStreamEvents = useMemo(
    () => replayTimeline.slice(-24).reverse(),
    [replayTimeline]
  );

  const formatEventType = (row) => {
    const raw = row?.event_type || row?.type || "unknown";
    return String(raw).replace(/_/g, " ");
  };

  const formatEventMetadata = (row) => {
    const eventType = row?.event_type || row?.type;
    const metadata = row?.metadata || {};
    if (eventType === "external_site_opened") {
      const hostname = String(metadata?.hostname || "").trim();
      const title = String(metadata?.title || "").trim();
      const url = String(metadata?.url || "").trim();
      const trigger = String(metadata?.trigger || "tab_switch").trim();
      const core = hostname || url || "unknown-site";
      return `${core}${title ? ` | ${title}` : ""} | trigger=${trigger}`;
    }
    return JSON.stringify(metadata);
  };

  const normalizeEyeAlertType = (value) => {
    const type = String(value || "").toLowerCase().trim();
    if (!type) {
      return "";
    }
    if (type.includes("left")) {
      return "looking_left";
    }
    if (type.includes("right")) {
      return "looking_right";
    }
    if (type.includes("up")) {
      return "looking_up";
    }
    if (type.includes("down")) {
      return "looking_down";
    }
    return type;
  };

  const getEyeDirectionCounts = (sourceRow, timeline = []) => {
    const hasServerCounts =
      sourceRow?.eye_movement_counts &&
      Object.keys(sourceRow.eye_movement_counts).length > 0;

    const counts = {
      left: Number(sourceRow?.eye_movement_counts?.looking_left || 0),
      right: Number(sourceRow?.eye_movement_counts?.looking_right || 0),
      up: Number(sourceRow?.eye_movement_counts?.looking_up || 0),
      down: Number(sourceRow?.eye_movement_counts?.looking_down || 0)
    };

    if (hasServerCounts) {
      return counts;
    }

    const events = Array.isArray(timeline) ? timeline : [];
    events.forEach((eventItem) => {
      const eventType = eventItem?.event_type || eventItem?.type;
      if (eventType !== "eye_movement_alert") {
        return;
      }
      const normalizedType = normalizeEyeAlertType(
        eventItem?.metadata?.eye_alert_type || eventItem?.metadata?.alert_type
      );
      if (normalizedType === "looking_left") {
        counts.left += 1;
      } else if (normalizedType === "looking_right") {
        counts.right += 1;
      } else if (normalizedType === "looking_up") {
        counts.up += 1;
      } else if (normalizedType === "looking_down") {
        counts.down += 1;
      }
    });

    return counts;
  };

  const openEyeMovementSheet = (row, timeline = [], source = "monitoring") => {
    const counts = getEyeDirectionCounts(row, timeline);
    const alertEvents = (Array.isArray(timeline) ? timeline : [])
      .filter((eventItem) => {
        const eventType = eventItem?.event_type || eventItem?.type;
        if (eventType !== "eye_movement_alert") {
          return false;
        }
        const normalizedType = normalizeEyeAlertType(
          eventItem?.metadata?.eye_alert_type || eventItem?.metadata?.alert_type
        );
        return (
          normalizedType === "looking_left" ||
          normalizedType === "looking_right" ||
          normalizedType === "looking_up" ||
          normalizedType === "looking_down"
        );
      })
      .slice(-14)
      .reverse();

    setEyeSheetData({
      studentName: row?.student_name || "Student",
      studentCode: row?.student_code || "N/A",
      submissionId: row?.submission_id,
      counts,
      alertEvents,
      source,
    });
  };

  useEffect(() => {
    if (!eyeSheetData?.submissionId) {
      return;
    }

    const source = eyeSheetData.source || "monitoring";
    let latestRow = null;
    let latestTimeline = [];

    if (source === "answers") {
      latestRow = answerRows.find((row) => row.submission_id === eyeSheetData.submissionId) || null;
      latestTimeline = latestRow?.recent_events || [];
    } else {
      latestRow = dashboard?.submissions?.find((row) => row.submission_id === eyeSheetData.submissionId) || null;
      latestTimeline = latestRow?.timeline || [];
    }

    if (!latestRow) {
      return;
    }

    const counts = getEyeDirectionCounts(latestRow, latestTimeline);
    const alertEvents = (Array.isArray(latestTimeline) ? latestTimeline : [])
      .filter((eventItem) => {
        const eventType = eventItem?.event_type || eventItem?.type;
        if (eventType !== "eye_movement_alert") {
          return false;
        }
        const normalizedType = normalizeEyeAlertType(
          eventItem?.metadata?.eye_alert_type || eventItem?.metadata?.alert_type
        );
        return (
          normalizedType === "looking_left" ||
          normalizedType === "looking_right" ||
          normalizedType === "looking_up" ||
          normalizedType === "looking_down"
        );
      })
      .slice(-14)
      .reverse();

    setEyeSheetData((current) => {
      if (!current || current.submissionId !== eyeSheetData.submissionId) {
        return current;
      }
      return {
        ...current,
        counts,
        alertEvents,
      };
    });
  }, [dashboard, answerRows, eyeSheetData?.submissionId, eyeSheetData?.source]);

  const getDirectionSeverity = (value) => {
    const numeric = Number(value || 0);
    if (numeric >= 8) {
      return "high";
    }
    if (numeric >= 4) {
      return "medium";
    }
    return "low";
  };

  const getDominantDirection = (counts) => {
    const entries = [
      ["left", Number(counts?.left || 0)],
      ["right", Number(counts?.right || 0)],
      ["up", Number(counts?.up || 0)],
      ["down", Number(counts?.down || 0)]
    ];
    entries.sort((a, b) => b[1] - a[1]);
    return entries[0]?.[1] > 0 ? entries[0][0] : null;
  };

  const getOpenedWebsites = (timeline = []) => {
    const events = Array.isArray(timeline) ? timeline : [];
    const siteMap = new Map();

    events.forEach((eventItem) => {
      const eventType = eventItem?.event_type || eventItem?.type;
      if (eventType !== "external_site_opened") {
        return;
      }
      const metadata = eventItem?.metadata || {};
      const hostname = String(metadata?.hostname || "").trim().toLowerCase();
      const url = String(metadata?.url || "").trim();
      const label = hostname || (url ? String(url).replace(/^https?:\/\//i, "") : "unknown-site");
      if (!label) {
        return;
      }

      const current = siteMap.get(label) || { count: 0, lastTs: 0 };
      current.count += 1;
      current.lastTs = Math.max(current.lastTs, Number(eventItem?.timestamp_ms || 0));
      siteMap.set(label, current);
    });

    return [...siteMap.entries()]
      .sort((a, b) => b[1].lastTs - a[1].lastTs)
      .map(([site, info]) => ({ site, count: info.count }))
      .slice(0, 6);
  };

  const downloadEyeSheetCsv = () => {
    if (!eyeSheetData) {
      return;
    }
    const header = "student_name,student_code,submission_id,left,right,up,down\n";
    const summaryRow = [
      eyeSheetData.studentName,
      eyeSheetData.studentCode,
      eyeSheetData.submissionId,
      eyeSheetData.counts.left,
      eyeSheetData.counts.right,
      eyeSheetData.counts.up,
      eyeSheetData.counts.down
    ]
      .map((item) => `"${String(item).replace(/"/g, '""')}"`)
      .join(",");

    const eventsHeader = "\n\nrecent_suspicious_events\ntimestamp_ms,event_type,severity\n";
    const eventRows = (eyeSheetData.alertEvents || [])
      .map((eventItem) => {
        const values = [
          eventItem?.timestamp_ms,
          String(eventItem?.metadata?.eye_alert_type || eventItem?.metadata?.alert_type || "unknown").replace(/_/g, " "),
          String(eventItem?.metadata?.alert_severity || "low").toUpperCase()
        ];
        return values.map((item) => `"${String(item).replace(/"/g, '""')}"`).join(",");
      })
      .join("\n");

    const csv = `${header}${summaryRow}${eventsHeader}${eventRows}`;
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `eye_movement_${eyeSheetData.submissionId}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  };

  const printEyeSheetPdf = () => {
    if (!eyeSheetData) {
      return;
    }
    const popup = window.open("", "_blank", "width=980,height=760");
    if (!popup) {
      setMessage("Popup blocked. Please allow popups to generate PDF print view.");
      return;
    }

    const rows = (eyeSheetData.alertEvents || [])
      .map(
        (eventItem) =>
          `<tr><td>${eventItem?.timestamp_ms ?? ""}</td><td>${String(
            eventItem?.metadata?.eye_alert_type || eventItem?.metadata?.alert_type || "unknown"
          ).replace(/_/g, " ")}</td><td>${String(eventItem?.metadata?.alert_severity || "low").toUpperCase()}</td></tr>`
      )
      .join("");

    popup.document.write(`
      <html>
        <head>
          <title>Eye Movement Datasheet</title>
          <style>
            body { font-family: Segoe UI, Arial, sans-serif; padding: 20px; color: #1f2933; }
            h1 { margin: 0 0 8px; }
            .meta { margin-bottom: 16px; color: #4b5563; }
            .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 16px; }
            .card { border: 1px solid #d7d3cb; border-radius: 8px; padding: 10px; }
            table { width: 100%; border-collapse: collapse; }
            th, td { border: 1px solid #d7d3cb; padding: 8px; text-align: left; }
            th { background: #f5f5f5; }
          </style>
        </head>
        <body>
          <h1>Eye Movement Datasheet</h1>
          <div class="meta">${eyeSheetData.studentName} (${eyeSheetData.studentCode}) | Submission ${eyeSheetData.submissionId}</div>
          <div class="grid">
            <div class="card"><strong>Left</strong><div>${eyeSheetData.counts.left}</div></div>
            <div class="card"><strong>Right</strong><div>${eyeSheetData.counts.right}</div></div>
            <div class="card"><strong>Up</strong><div>${eyeSheetData.counts.up}</div></div>
            <div class="card"><strong>Down</strong><div>${eyeSheetData.counts.down}</div></div>
          </div>
          <h3>Recent Suspicious Eye Events</h3>
          <table>
            <thead><tr><th>Timestamp (ms)</th><th>Type</th><th>Severity</th></tr></thead>
            <tbody>${rows || '<tr><td colspan="3">No suspicious events found.</td></tr>'}</tbody>
          </table>
        </body>
      </html>
    `);
    popup.document.close();
    popup.focus();
    popup.print();
  };

  const maxScore =
    dashboard?.submissions?.reduce((max, row) => Math.max(max, row.suspicion_score), 0) || 1;

  const activeExams = useMemo(() => teacherExams.filter((item) => item.status === "active"), [teacherExams]);
  const completedExams = useMemo(() => teacherExams.filter((item) => item.status === "completed"), [teacherExams]);
  const filteredStudents = useMemo(() => {
    const keyword = studentFilter.trim().toLowerCase();
    if (!keyword) {
      return students;
    }
    return students.filter((item) => {
      const code = item?.profile?.user_code?.toLowerCase?.() || "";
      const name = item?.name?.toLowerCase?.() || "";
      return code.includes(keyword) || name.includes(keyword);
    });
  }, [students, studentFilter]);

  const filteredAnswerRows = useMemo(() => {
    const keyword = studentFilter.trim().toLowerCase();
    if (!keyword) {
      return answerRows;
    }
    return answerRows.filter((item) => {
      const code = item?.student_code?.toLowerCase?.() || "";
      const name = item?.student_name?.toLowerCase?.() || "";
      return code.includes(keyword) || name.includes(keyword);
    });
  }, [answerRows, studentFilter]);
  const canCreateRoom =
    courseName.trim().length >= 3 &&
    courseCode.trim().length >= 2 &&
    examName.trim().length >= 3 &&
    Number.isFinite(durationMinutes) &&
    durationMinutes >= 1 &&
    durationMinutes <= 300 &&
    ((scheduledAt === "" && scheduledEndAt === "") || (scheduledAt !== "" && scheduledEndAt !== ""));

  if (builderRoom) {
    return (
      <QuestionBuilder
        room={builderRoom}
        onBack={() => setBuilderRoom(null)}
        onSaved={({ exam_id, title }) => {
          setExamId(exam_id);
          setExamName("");
          setBuilderRoom(null);
          setMessage("Exam paper updated. Open dashboard to monitor submissions.");
          loadRooms();
          loadTeacherExams();
        }}
      />
    );
  }

  return (
    <div className="teacher-layout">
      <aside className="teacher-sidebar">
        <h3>Teacher Menu</h3>
        <button
          onClick={() => setSection("overview")}
          className={section === "overview" ? "menu-nav-btn menu-nav-btn-active" : "menu-nav-btn"}
        >
          Overview
        </button>
        <button
          onClick={() => setSection("exams")}
          className={section === "exams" ? "menu-nav-btn menu-nav-btn-active" : "menu-nav-btn"}
        >
          Exams
        </button>
        <button
          onClick={() => setSection("students")}
          className={section === "students" ? "menu-nav-btn menu-nav-btn-active" : "menu-nav-btn"}
        >
          Students
        </button>
        <button className="menu-utility-btn" onClick={onTogglePortal}>
          {portalOpen ? "Close Portal" : "My Portal"}
        </button>
        <button className="menu-utility-btn" onClick={onLogout}>
          Logout
        </button>
      </aside>

      <div className="panel">
        <div className="panel-hero">
          <p className="brand-kicker">Evaluation Studio</p>
          <h2>Teacher Dashboard</h2>
        </div>
        <p className="muted">Logged in as {user.name}. Manage exams, students, and anti-cheating analytics.</p>

        {section === "overview" ? (
          <>
            <div className="replay-box">
              <h3>Create Exam Room</h3>
              <div className="create-room-grid">
                <label className="room-field room-field-wide">
                  Course Name
                  <input value={courseName} onChange={(event) => setCourseName(event.target.value)} required />
                </label>
                <label className="room-field room-field-wide">
                  Course Code
                  <input value={courseCode} onChange={(event) => setCourseCode(event.target.value)} required />
                </label>
                <label className="room-field room-field-narrow">
                  Exam Name
                  <input value={examName} onChange={(event) => setExamName(event.target.value)} required />
                </label>
                <label className="room-field room-field-small">
                  Duration (min)
                  <input
                    type="number"
                    value={durationMinutes}
                    min="1"
                    max="300"
                    onChange={(event) => setDurationMinutes(Number(event.target.value))}
                  />
                </label>
                <div className="schedule-window-card room-field room-field-schedule">
                  <div className="schedule-window-label">Schedule Window</div>
                  <div className="schedule-window-inputs">
                    <label>
                      Start
                      <input
                        type="datetime-local"
                        value={scheduledAt}
                        onChange={(event) => setScheduledAt(event.target.value)}
                      />
                    </label>
                    <label>
                      End
                      <input
                        type="datetime-local"
                        value={scheduledEndAt}
                        onChange={(event) => setScheduledEndAt(event.target.value)}
                      />
                    </label>
                  </div>
                </div>
              </div>
              <div className="room-actions">
                <button onClick={createRoom} disabled={loading || !canCreateRoom}>
                  Create Room
                </button>
                <button className="secondary-btn" onClick={loadRooms}>
                  Refresh Rooms
                </button>
              </div>
              {rooms.length === 0 ? (
                <p className="muted">No rooms created yet.</p>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Room ID</th>
                        <th>Course</th>
                        <th>Exam</th>
                        <th>Schedule</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rooms.map((room) => (
                        <tr key={room.room_id}>
                          <td>
                            <div
                              className="room-id-chip room-id-chip-clickable"
                              role="button"
                              tabIndex={0}
                              title="Click to copy room ID"
                              onClick={() => copyRoomId(room.room_id)}
                              onKeyDown={(event) => {
                                if (event.key === "Enter" || event.key === " ") {
                                  event.preventDefault();
                                  copyRoomId(room.room_id);
                                }
                              }}
                            >
                              {room.room_id}
                            </div>
                          </td>
                          <td>
                            <div className="room-cell-stack">
                              <div className="room-cell-title">{room.course_title}</div>
                              <div className="room-cell-subtitle">({room.course_code})</div>
                            </div>
                          </td>
                          <td>
                            <div className="room-cell-stack">
                              <div className="room-cell-title">{room.exam_title || "Untitled Exam"}</div>
                            </div>
                          </td>
                          <td>
                            <div className="room-schedule-card">
                              <div className="room-schedule-value">
                                {formatScheduleWindow(room.scheduled_at, room.scheduled_end_at)}
                              </div>
                            </div>
                          </td>
                          <td>
                            <div className="room-action-stack">
                              <div className="room-action-row">
                                <button className="room-icon-btn" onClick={() => setBuilderRoom(room)} aria-label={`Edit paper for ${room.room_id}`} title="Edit paper">
                                  <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                                    <path d="M4 17.25V20h2.75L17.8 8.95l-2.75-2.75L4 17.25Zm17.71-10.04a1.003 1.003 0 0 0 0-1.42l-1.5-1.5a1.003 1.003 0 0 0-1.42 0l-1.18 1.18 2.75 2.75 1.35-1.01Z" fill="currentColor"/>
                                  </svg>
                                </button>
                                <button className="danger-btn room-action-btn" onClick={() => deleteRoom(room.room_id)}>
                                  Delete Room
                                </button>
                              </div>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        ) : null}

        {section === "students" ? (
          <>
            <div className="replay-box">
              <h3>Manual Add Student</h3>
              <form onSubmit={createStudentManual} className="form-grid">
                <label>
                  Full Name
                  <input
                    value={newStudent.name}
                    onChange={(event) =>
                      setNewStudent((current) => ({ ...current, name: event.target.value }))
                    }
                    required
                  />
                </label>
                <label>
                  Department
                  <input
                    value={newStudent.department}
                    onChange={(event) =>
                      setNewStudent((current) => ({ ...current, department: event.target.value }))
                    }
                    required
                  />
                </label>
                <label>
                  User ID
                  <input
                    value={newStudent.user_code}
                    onChange={(event) =>
                      setNewStudent((current) => ({ ...current, user_code: event.target.value }))
                    }
                    required
                  />
                </label>
                <label>
                  Email
                  <input
                    value={newStudent.email}
                    type="email"
                    onChange={(event) =>
                      setNewStudent((current) => ({ ...current, email: event.target.value }))
                    }
                    required
                  />
                </label>
                <label>
                  Contact Number
                  <input
                    value={newStudent.contact_number}
                    onChange={(event) =>
                      setNewStudent((current) => ({ ...current, contact_number: event.target.value }))
                    }
                    required
                  />
                </label>
                <label>
                  Temporary Password
                  <input
                    value={newStudent.password}
                    type="password"
                    minLength={8}
                    onChange={(event) =>
                      setNewStudent((current) => ({ ...current, password: event.target.value }))
                    }
                    required
                  />
                </label>
                <button type="submit">Create Student</button>
              </form>
            </div>

            <div className="replay-box">
              <h3>Student Approval Queue</h3>
              <button onClick={loadPendingStudents}>Refresh Pending</button>
              {pendingStudents.length === 0 ? (
                <p className="muted">No pending student approvals.</p>
              ) : (
                <div className="list-grid">
                  {pendingStudents.map((row) => (
                    <div key={`pending-${row.id}`} className="list-card">
                      <div>
                        <strong>{row.name}</strong>
                      </div>
                      <div className="muted">ID: {row.profile.user_code}</div>
                      <div className="row-actions">
                        <button onClick={() => approveStudent(row.id, true)}>Approve</button>
                        <button className="danger-btn" onClick={() => approveStudent(row.id, false)}>
                          Reject
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="replay-box">
              <h3>Assigned Students</h3>
              <button onClick={loadStudents}>Refresh Students</button>
              <div className="inline-row">
                <label>
                  Search by Student ID
                  <input
                    value={studentFilter}
                    onChange={(event) => setStudentFilter(event.target.value)}
                    placeholder="STD-001"
                  />
                </label>
              </div>
              {filteredStudents.length === 0 ? (
                <p className="muted">No assigned students found.</p>
              ) : (
                <div className="list-grid">
                  {filteredStudents.map((row) => (
                    <div key={`student-${row.id}`} className="list-card">
                      <div>
                        <strong>{row.name}</strong>
                      </div>
                      <div className="muted">ID: {row.profile.user_code}</div>
                      <div className="muted">Status: {row.profile.approval_status}</div>
                      <div className="muted">Access: {row.profile.is_active ? "enabled" : "disabled"}</div>
                      <div className="row-actions">
                        <button onClick={() => setStudentAccess(row.id, true)}>Enable</button>
                        <button onClick={() => setStudentAccess(row.id, false)}>Disable</button>
                        <button onClick={() => printStudentProfile(row.id)}>Print Data</button>
                        <button className="danger-btn" onClick={() => deleteStudent(row.id)}>
                          Delete
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        ) : null}

        {section === "exams" ? (
          <div className="replay-box">
            <div className="exams-toolbar">
              <h3>Exams</h3>
              <div className="row-actions">
                <button onClick={loadTeacherExams}>Refresh Exams</button>
                {dashboard ? (
                  <button className="secondary-btn" onClick={() => setSection("monitoring")}>
                    Open Last Dashboard
                  </button>
                ) : null}
              </div>
            </div>
            <p className="muted">Active: {activeExams.length} | Completed: {completedExams.length}</p>
            {teacherExams.length === 0 ? (
              <p className="muted">No exams found.</p>
            ) : (
              <div className="list-grid exams-list-vertical">
                {teacherExams.map((exam) => (
                  <div key={`exam-${exam.exam_id}`} className="list-card exam-summary-card">
                    <div className="exam-card-top-grid">
                      <div className="exam-title-chip">{exam.title}</div>
                      <div className="exam-meta-chip">{exam.room_id}</div>
                      <div className="exam-meta-chip">{exam.course_title} ({exam.course_code})</div>
                      <div className="exam-meta-chip">{exam.submitted_count}/{exam.total_submissions}</div>
                      <span className={`exam-status-pill exam-status-${exam.status}`}>{exam.status}</span>
                    </div>
                    <div className="row-actions exam-actions-row">
                      <button
                        onClick={() => {
                          loadDashboard(exam.exam_id);
                        }}
                      >
                        Load Dashboard
                      </button>
                      <button onClick={() => loadAnswerStatus(exam)}>Exam Answer Status</button>
                      <button className="danger-btn" onClick={() => deleteExamWithData(exam.exam_id)}>
                        Delete Exam Permanently
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : null}

        {section === "monitoring" ? (
          <div className="replay-box" ref={dashboardTopRef}>
            <div className="monitoring-header">
              <h3>Exam Monitoring Dashboard</h3>
              <button className="secondary-btn" onClick={() => setSection("exams")}>Back to Exams</button>
            </div>
            <p className="muted">Exam ID: {examId}</p>

            <details className="advanced-tools">
              <summary>Advanced Monitoring Tools</summary>
              <div className="inline-row live-controls">
                <label className="toggle-label">
                  <input
                    type="checkbox"
                    checked={liveMode}
                    onChange={(event) => {
                      const next = event.target.checked;
                      setLiveMode(next);
                      if (next) {
                        loadDashboard(examId);
                      }
                    }}
                  />
                  Live Demo Mode
                </label>
                <label>
                  Refresh (sec)
                  <input
                    type="number"
                    min="1"
                    max="60"
                    value={refreshSeconds}
                    onChange={(event) => setRefreshSeconds(Number(event.target.value))}
                  />
                </label>
                <label className="toggle-label">
                  <input
                    type="checkbox"
                    checked={soundEnabled}
                    onChange={(event) => setSoundEnabled(event.target.checked)}
                  />
                  Alert sound
                </label>
                <button
                  type="button"
                  onClick={() => {
                    setAlertText("Test alert is active");
                    if (soundEnabled) {
                      try {
                        const context = new (window.AudioContext || window.webkitAudioContext)();
                        const oscillator = context.createOscillator();
                        const gain = context.createGain();
                        oscillator.type = "triangle";
                        oscillator.frequency.value = 740;
                        gain.gain.value = 0.05;
                        oscillator.connect(gain);
                        gain.connect(context.destination);
                        oscillator.start();
                        oscillator.stop(context.currentTime + 0.15);
                      } catch {
                        // Keep visual test alert only.
                      }
                    }
                  }}
                >
                  Test Alert
                </button>
                {lastUpdatedAt ? <span className="muted">Last update: {lastUpdatedAt}</span> : null}
              </div>
            </details>

            {alertText ? <div className="alert-banner">{alertText}</div> : null}

            <div className="report-actions">
              <button onClick={() => downloadReport("csv")} disabled={loading || !dashboard}>
                Download CSV Report
              </button>
              <button onClick={() => downloadReport("pdf")} disabled={loading || !dashboard}>
                Download PDF Report
              </button>
            </div>

            {dashboard ? (
              <>
                <div className="summary-grid">
                  <div className="summary-card">
                    <strong>Total Submissions</strong>
                    <div>{dashboard.summary.total_submissions}</div>
                  </div>
                  <div className="summary-card">
                    <strong>Average Suspicion</strong>
                    <div>{dashboard.summary.avg_suspicion_score}</div>
                  </div>
                  <div className="summary-card">
                    <strong>Safe / Suspicious / High</strong>
                    <div>
                      {dashboard.summary.safe_count} / {dashboard.summary.suspicious_count} / {dashboard.summary.high_risk_count}
                    </div>
                  </div>
                  <div className="summary-card">
                    <strong>Paste / Tab Events</strong>
                    <div>
                      {dashboard.summary.total_paste_events} / {dashboard.summary.total_tab_hidden_events}
                    </div>
                  </div>
                </div>

                <div className="monitor-student-grid">
                  {dashboard.submissions.map((submission) => {
                    const eyeCounts = getEyeDirectionCounts(submission, submission.timeline || []);
                    const dominantDirection = getDominantDirection(eyeCounts);
                    const openedWebsites = getOpenedWebsites(submission.timeline || []);
                    return (
                      <div
                        key={`monitor-card-${submission.submission_id}`}
                        className={`monitor-student-card ${
                          submission.risk_band === "Safe" ? "monitor-student-card-safe" : "monitor-student-card-warning"
                        } ${recentNewIds.includes(submission.submission_id) ? "row-new" : ""}`.trim()}
                      >
                        <div className="monitor-student-head">
                          <div className="monitor-student-identity">
                            <strong>{submission.student_name}</strong>
                            <span className="monitor-score-inline">
                              Score: {submission.suspicion_score} | paste {submission.event_counts?.paste || 0} | tab/blur {(submission.event_counts?.tab_hidden || 0) + (submission.event_counts?.window_blur || 0)}
                            </span>
                          </div>
                          <span
                            className={
                              submission.risk_band === "Safe"
                                ? "student-status-badge student-status-safe"
                                : "student-status-badge student-status-warning"
                            }
                          >
                            {submission.risk_band === "Safe" ? "Safe" : "Warning"}
                          </span>
                        </div>
                        <div className="monitor-metrics-row">
                          <div className="monitor-eye-stats">
                            <div className="monitor-section-title">Eye Movement</div>
                            <div className="monitor-eye-badges">
                            <span className={`eye-dir-badge eye-dir-${getDirectionSeverity(eyeCounts.left)} ${dominantDirection === "left" ? "eye-dir-dominant" : ""}`}>
                              L {eyeCounts.left}
                            </span>
                            <span className={`eye-dir-badge eye-dir-${getDirectionSeverity(eyeCounts.right)} ${dominantDirection === "right" ? "eye-dir-dominant" : ""}`}>
                              R {eyeCounts.right}
                            </span>
                            <span className={`eye-dir-badge eye-dir-${getDirectionSeverity(eyeCounts.up)} ${dominantDirection === "up" ? "eye-dir-dominant" : ""}`}>
                              U {eyeCounts.up}
                            </span>
                            <span className={`eye-dir-badge eye-dir-${getDirectionSeverity(eyeCounts.down)} ${dominantDirection === "down" ? "eye-dir-dominant" : ""}`}>
                              D {eyeCounts.down}
                            </span>
                            </div>
                          </div>
                          <div className="opened-sites-block">
                            <div className="monitor-section-title">Opened Websites</div>
                            {openedWebsites.length === 0 ? (
                              <p className="muted opened-sites-empty">No external websites detected yet.</p>
                            ) : (
                              <div className="opened-sites-list">
                                {openedWebsites.map((item) => (
                                  <span key={`${submission.submission_id}-${item.site}`} className="opened-site-chip">
                                    <span className="opened-site-name">{item.site}</span>
                                    {item.count > 1 ? ` x${item.count}` : ""}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                        <div className="row-actions">
                          <button
                            className="secondary-btn"
                            onClick={() => {
                              setSelectedSubmissionId(submission.submission_id);
                              setReplayIndex(0);
                              setMonitorDetailOpen(true);
                            }}
                          >
                            Open Student Monitor
                          </button>
                          <button
                            className="secondary-btn eye-sheet-trigger"
                            onClick={() => openEyeMovementSheet(submission, submission.timeline || [], "monitoring")}
                          >
                            Check Eye Movement
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>

                {monitorDetailOpen && selectedSubmission ? (
                  <div className="monitor-detail-overlay" onClick={() => setMonitorDetailOpen(false)}>
                    <div className="monitor-detail-card" onClick={(event) => event.stopPropagation()}>
                      <div className="monitor-detail-header">
                        <div>
                          <h3>{selectedSubmission.student_name}</h3>
                          <p className="muted">
                            Submission {selectedSubmission.submission_id} | Risk: {selectedSubmission.risk_band}
                          </p>
                        </div>
                        <div className="row-actions">
                          <button className="secondary-btn" onClick={() => setMonitorDetailOpen(false)}>
                            Back to Student List
                          </button>
                        </div>
                      </div>

                      <div className="chart-wrap monitor-mini-chart">
                        <h4>Suspicion Score Chart</h4>
                        <div className="bar-row">
                          <span className="bar-label">{selectedSubmission.student_name}</span>
                          <div className="bar-track">
                            <div
                              className={`bar-fill ${
                                selectedSubmission.risk_band === "High Risk"
                                  ? "risk-high"
                                  : selectedSubmission.risk_band === "Suspicious"
                                  ? "risk-mid"
                                  : "risk-safe"
                              }`}
                              style={{ width: `${Math.max(8, (selectedSubmission.suspicion_score / maxScore) * 100)}%` }}
                            >
                              {selectedSubmission.suspicion_score}
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="replay-box">
                        <h3>Behavior Replay</h3>
                        <div className="monitor-counter-grid">
                          <div className="monitor-counter-card">
                            <span>Answer Paste Attempts</span>
                            <strong>{selectedSubmission.event_counts?.paste || 0}</strong>
                          </div>
                          <div className="monitor-counter-card">
                            <span>Background Tab Switches</span>
                            <strong>{selectedSubmission.event_counts?.tab_hidden || 0}</strong>
                          </div>
                        </div>
                        <input
                          type="range"
                          min="0"
                          max={Math.max(0, replayTimeline.length - 1)}
                          value={Math.min(replayIndex, Math.max(0, replayTimeline.length - 1))}
                          onChange={(event) => setReplayIndex(Number(event.target.value))}
                        />
                        {currentReplayEvent ? (
                          <div className="timeline-cell">
                            <div>
                              Step: {replayIndex + 1} / {replayTimeline.length}
                            </div>
                            <div>Timestamp: {currentReplayEvent.timestamp_ms} ms</div>
                            <div>Type: {formatEventType(currentReplayEvent)}</div>
                            <div>Metadata: {formatEventMetadata(currentReplayEvent)}</div>
                          </div>
                        ) : (
                          <p className="muted">No events captured for this submission yet.</p>
                        )}

                        <div className="live-stream-box">
                          <h4>Live Student Activity Stream</h4>
                          {liveStreamEvents.length === 0 ? (
                            <p className="muted">No live events received yet.</p>
                          ) : (
                            <div className="live-stream-list">
                              {liveStreamEvents.map((eventItem, index) => {
                                const eventType = eventItem?.event_type || eventItem?.type || "";
                                return (
                                  <div
                                    key={`live-${selectedSubmission.submission_id}-${eventItem.timestamp_ms}-${index}`}
                                    className={`live-stream-item ${String(eventType).includes("eye") ? "live-stream-item-eye" : ""} ${eventType === "external_site_opened" ? "live-stream-item-site" : ""}`}
                                  >
                                    <span className="live-stream-time">{eventItem.timestamp_ms}ms</span>
                                    <span className="live-stream-type">{formatEventType(eventItem)}</span>
                                    <span className="live-stream-meta">{formatEventMetadata(eventItem)}</span>
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </div>

                        {(() => {
                          const eyeMovementAlerts = replayTimeline.filter((eventItem) => {
                            const eventType = eventItem?.event_type || eventItem?.type;
                            const normalizedType = normalizeEyeAlertType(
                              eventItem?.metadata?.eye_alert_type || eventItem?.metadata?.alert_type
                            );
                            return (
                              eventType === "eye_movement_alert" &&
                              ["looking_left", "looking_right", "looking_up", "looking_down"].includes(normalizedType)
                            );
                          });

                          return eyeMovementAlerts.length > 0 ? (
                            <div className="eye-movement-box">
                              <h4>Eye Movement & Gaze Tracking</h4>
                              <div className="eye-stats">
                                <div className="eye-stat-item">
                                  <strong>Total Alerts:</strong> {eyeMovementAlerts.length}
                                </div>
                                <div className="eye-stat-item">
                                  <strong>Types Detected:</strong>
                                  {" "}
                                  {[
                                    ...new Set(
                                      eyeMovementAlerts.map((eventItem) =>
                                        normalizeEyeAlertType(
                                          eventItem?.metadata?.eye_alert_type || eventItem?.metadata?.alert_type || "unknown"
                                        )
                                      )
                                    )
                                  ].join(", ")}
                                </div>
                              </div>
                              <details className="eye-events-detail">
                                <summary>View Eye Movement Events</summary>
                                <div className="eye-events-list">
                                  {eyeMovementAlerts.slice(-10).reverse().map((evt, idx) => {
                                    const severity = evt?.metadata?.alert_severity || evt?.metadata?.severity || "low";
                                    return (
                                      <div key={`eye-evt-${idx}`} className="eye-event-row">
                                        <div className="eye-event-time">{evt.timestamp_ms}ms</div>
                                        <div className="eye-event-details">
                                          <span className="eye-event-type">
                                            {normalizeEyeAlertType(evt?.metadata?.eye_alert_type || evt?.metadata?.alert_type || "unknown").replace(/_/g, " ")}
                                          </span>
                                          <span
                                            className="eye-event-severity"
                                            style={{
                                              color: severity === "high" ? "#d32f2f" : severity === "medium" ? "#f57c00" : "#558b2f"
                                            }}
                                          >
                                            [{String(severity).toUpperCase()}]
                                          </span>
                                          <div className="eye-event-desc">{evt?.metadata?.description}</div>
                                        </div>
                                      </div>
                                    );
                                  })}
                                </div>
                              </details>
                            </div>
                          ) : (
                            <p className="muted">No suspicious eye movement alerts yet.</p>
                          );
                        })()}
                      </div>
                    </div>
                  </div>
                ) : null}
              </>
            ) : (
              <p className="muted">Open an exam dashboard from the Exams page first.</p>
            )}
          </div>
        ) : null}

        {section === "answers" ? (
          <div className="replay-box">
            <h3>Exam Answer Status</h3>
            {selectedExamSummary ? (
              <p className="muted">
                {selectedExamSummary.title} | Room {selectedExamSummary.room_id}
              </p>
            ) : null}
            <div className="answers-toolbar">
              <label>
                Search by Student ID
                <input
                  value={studentFilter}
                  onChange={(event) => setStudentFilter(event.target.value)}
                  placeholder="STD-001"
                />
              </label>
              <button onClick={downloadResultSheet}>Generate Result Sheet PDF</button>
              <button onClick={() => setSection("exams")}>Back to Exams</button>
            </div>

            <div className="table-wrap">
              <table className="answer-status-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Name</th>
                    <th>Attended</th>
                    <th>Cheat Score</th>
                    <th>Signals</th>
                    <th>Marks</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredAnswerRows.map((row) => (
                    <tr key={`ans-${row.submission_id}`}>
                      <td className="answer-id-cell">{row.student_code}</td>
                      <td className="answer-name-cell">{row.student_name}</td>
                      <td>{row.status === "submitted" ? "Yes" : "In Progress"}</td>
                      <td className="answer-score-cell">
                        {row.suspicion_score} ({row.risk_band})
                      </td>
                      <td className="answer-signal-cell">
                        {(() => {
                          const eyeCounts = getEyeDirectionCounts(row, row.recent_events || []);
                          const dominantDirection = getDominantDirection(eyeCounts);
                          return (
                            <>
                        tab/focus: {(row.event_counts?.tab_hidden || 0) + (row.event_counts?.window_blur || 0)}
                        <br />
                        paste: {row.event_counts?.paste || 0}
                        <br />
                        fullscreen exits: {row.event_counts?.fullscreen_exit || 0}
                        <br />
                        warnings: {row.event_counts?.warning_issued || 0}
                        <br />
                        eye L/R/U/D:
                        <span className={`eye-dir-badge eye-dir-${getDirectionSeverity(eyeCounts.left)} ${dominantDirection === "left" ? "eye-dir-dominant" : ""}`}>
                          L {eyeCounts.left}
                        </span>
                        <span className={`eye-dir-badge eye-dir-${getDirectionSeverity(eyeCounts.right)} ${dominantDirection === "right" ? "eye-dir-dominant" : ""}`}>
                          R {eyeCounts.right}
                        </span>
                        <span className={`eye-dir-badge eye-dir-${getDirectionSeverity(eyeCounts.up)} ${dominantDirection === "up" ? "eye-dir-dominant" : ""}`}>
                          U {eyeCounts.up}
                        </span>
                        <span className={`eye-dir-badge eye-dir-${getDirectionSeverity(eyeCounts.down)} ${dominantDirection === "down" ? "eye-dir-dominant" : ""}`}>
                          D {eyeCounts.down}
                        </span>
                        {dominantDirection ? (
                          <>
                            <br />
                            dominant: <strong>{dominantDirection.toUpperCase()}</strong>
                          </>
                        ) : null}
                        <br />
                        <button
                          className="secondary-btn eye-sheet-trigger"
                          onClick={() => openEyeMovementSheet(row, row.recent_events || [], "answers")}
                        >
                          Check Eye Movement
                        </button>
                            </>
                          );
                        })()}
                      </td>
                      <td className="answer-input-cell">
                        <input
                          type="number"
                          disabled={row.status !== "submitted"}
                          value={markDraft[row.submission_id]?.marks ?? ""}
                          onChange={(event) =>
                            setMarkDraft((current) => ({
                              ...current,
                              [row.submission_id]: {
                                ...(current[row.submission_id] || {}),
                                marks: event.target.value
                              }
                            }))
                          }
                        />
                      </td>
                      <td className="answer-input-cell">
                        <select
                          disabled={row.status !== "submitted"}
                          value={markDraft[row.submission_id]?.evaluation_status || "pending"}
                          onChange={(event) =>
                            setMarkDraft((current) => ({
                              ...current,
                              [row.submission_id]: {
                                ...(current[row.submission_id] || {}),
                                evaluation_status: event.target.value
                              }
                            }))
                          }
                        >
                          <option value="pending">Pending</option>
                          <option value="pass">Pass</option>
                          <option value="fail">Fail</option>
                        </select>
                      </td>
                      <td className="answer-actions-cell">
                        <div className="answer-action-stack">
                          <button onClick={() => openAnswerDetail(row)} disabled={row.status !== "submitted"}>
                            Check Answer
                          </button>
                          <button onClick={() => saveMark(row.submission_id)} disabled={row.status !== "submitted"}>
                            Save Marks
                          </button>
                          <button onClick={() => printStudentDetail(row.submission_id)}>Print Details</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {selectedAnswerRow ? (
          <div className="answer-detail-overlay" onClick={() => setSelectedAnswerRow(null)}>
            <div className="answer-detail-modal" onClick={(event) => event.stopPropagation()}>
              <div className="answer-detail-header">
                <div>
                  <h3>Check Answer: {selectedAnswerRow.student_name}</h3>
                  <p className="muted">
                    Student ID: {selectedAnswerRow.student_code} | Cheat Score: {selectedAnswerRow.suspicion_score} ({selectedAnswerRow.risk_band})
                  </p>
                </div>
                <button className="secondary-btn" onClick={() => setSelectedAnswerRow(null)}>
                  Back to List
                </button>
              </div>

              <div className="answer-sheet">
                {Object.entries(selectedAnswerRow.answers || {}).map(([questionId, answerText]) => (
                  <div key={`${selectedAnswerRow.submission_id}-${questionId}`} className="answer-card">
                    <div className="answer-card-header">
                      <strong>
                        {questionId} (Max: {Number(selectedAnswerRow.question_max_marks?.[questionId] ?? 0)})
                      </strong>
                      <label>
                        Marks
                        <input
                          type="number"
                          min="0"
                          max={Number(selectedAnswerRow.question_max_marks?.[questionId] ?? 0)}
                          step="0.5"
                          value={perQuestionDraft[questionId] ?? 0}
                          onChange={(event) =>
                            setPerQuestionDraft((current) => ({
                              ...current,
                              [questionId]: Number(event.target.value || 0)
                            }))
                          }
                        />
                      </label>
                    </div>
                    <pre className="answer-text">{String(answerText)}</pre>
                  </div>
                ))}
              </div>

              <div className="inline-row answer-detail-actions">
                <label>
                  Evaluation
                  <select
                    value={markDraft[selectedAnswerRow.submission_id]?.evaluation_status || "pending"}
                    onChange={(event) =>
                      setMarkDraft((current) => ({
                        ...current,
                        [selectedAnswerRow.submission_id]: {
                          ...(current[selectedAnswerRow.submission_id] || {}),
                          evaluation_status: event.target.value
                        }
                      }))
                    }
                  >
                    <option value="pending">Pending</option>
                    <option value="pass">Pass</option>
                    <option value="fail">Fail</option>
                  </select>
                </label>
                <strong>
                  Total: {Object.values(perQuestionDraft).reduce((sum, value) => sum + Number(value || 0), 0)} / {Object.values(selectedAnswerRow.question_max_marks || {}).reduce((sum, value) => sum + Number(value || 0), 0)}
                </strong>
                <button onClick={saveDetailedMarks}>Save Student Result</button>
                <button onClick={() => printStudentDetail(selectedAnswerRow.submission_id)}>Print Details</button>
              </div>
            </div>
          </div>
        ) : null}

        {eyeSheetData ? (
          <div className="eye-sheet-overlay" onClick={() => setEyeSheetData(null)}>
            <div className="eye-sheet-card" onClick={(event) => event.stopPropagation()}>
              <div className="eye-sheet-header">
                <div>
                  <h3>Eye Movement Datasheet</h3>
                  <p className="muted">
                    {eyeSheetData.studentName} ({eyeSheetData.studentCode}) | Submission {eyeSheetData.submissionId}
                  </p>
                </div>
                <div className="row-actions">
                  <button className="secondary-btn" onClick={downloadEyeSheetCsv}>Export CSV</button>
                  <button className="secondary-btn" onClick={printEyeSheetPdf}>Export PDF</button>
                  <button className="secondary-btn" onClick={() => setEyeSheetData(null)}>
                    Back
                  </button>
                </div>
              </div>

              <div className="eye-sheet-grid">
                <div
                  className={`eye-sheet-stat eye-sheet-stat-${getDirectionSeverity(eyeSheetData.counts.left)} ${
                    getDominantDirection(eyeSheetData.counts) === "left" ? "eye-sheet-stat-dominant" : ""
                  }`}
                >
                  <strong>Left</strong>
                  <span>{eyeSheetData.counts.left}</span>
                </div>
                <div
                  className={`eye-sheet-stat eye-sheet-stat-${getDirectionSeverity(eyeSheetData.counts.right)} ${
                    getDominantDirection(eyeSheetData.counts) === "right" ? "eye-sheet-stat-dominant" : ""
                  }`}
                >
                  <strong>Right</strong>
                  <span>{eyeSheetData.counts.right}</span>
                </div>
                <div
                  className={`eye-sheet-stat eye-sheet-stat-${getDirectionSeverity(eyeSheetData.counts.up)} ${
                    getDominantDirection(eyeSheetData.counts) === "up" ? "eye-sheet-stat-dominant" : ""
                  }`}
                >
                  <strong>Up</strong>
                  <span>{eyeSheetData.counts.up}</span>
                </div>
                <div
                  className={`eye-sheet-stat eye-sheet-stat-${getDirectionSeverity(eyeSheetData.counts.down)} ${
                    getDominantDirection(eyeSheetData.counts) === "down" ? "eye-sheet-stat-dominant" : ""
                  }`}
                >
                  <strong>Down</strong>
                  <span>{eyeSheetData.counts.down}</span>
                </div>
              </div>
              <p className="muted">
                Dominant suspicious direction: <strong>{(getDominantDirection(eyeSheetData.counts) || "none").toUpperCase()}</strong>
              </p>

              <div className="eye-sheet-events">
                <h4>Recent Suspicious Eye Events</h4>
                {eyeSheetData.alertEvents.length === 0 ? (
                  <p className="muted">No recent left/right/up/down alerts found.</p>
                ) : (
                  <div className="eye-sheet-events-list">
                    {eyeSheetData.alertEvents.map((eventItem, index) => (
                      <div
                        key={`sheet-${eyeSheetData.submissionId}-${eventItem.timestamp_ms}-${index}`}
                        className="eye-sheet-event-row"
                      >
                        <span>{eventItem.timestamp_ms} ms</span>
                        <span>{String(eventItem?.metadata?.eye_alert_type || eventItem?.metadata?.alert_type || "unknown").replace(/_/g, " ")}</span>
                        <span>{String(eventItem?.metadata?.alert_severity || "low").toUpperCase()}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : null}

        {message ? <p className="muted">{message}</p> : null}
      </div>
    </div>
  );
}

export default TeacherPanel;
