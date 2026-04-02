import { useState } from "react";
import api from "../lib/api";

function LoginPanel({ onLogin }) {
  const [mode, setMode] = useState("login");
  const [rememberMe, setRememberMe] = useState(true);
  const [teachers, setTeachers] = useState([]);
  const teacherOptions = Array.isArray(teachers) ? teachers : [];

  const [userCode, setUserCode] = useState("");
  const [password, setPassword] = useState("");

  const [name, setName] = useState("");
  const [department, setDepartment] = useState("");
  const [signupCode, setSignupCode] = useState("");
  const [role, setRole] = useState("student");
  const [email, setEmail] = useState("");
  const [contactNumber, setContactNumber] = useState("");
  const [teacherUserId, setTeacherUserId] = useState("");
  const [signupPassword, setSignupPassword] = useState("");

  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

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
    if (typeof detail === "string") {
      return detail;
    }
    if (typeof requestError?.message === "string" && requestError.message.trim()) {
      return requestError.message;
    }
    return fallback;
  };

  const loadTeachers = async () => {
    try {
      const response = await api.get("/auth/teachers");
      const nextTeachers = Array.isArray(response.data) ? response.data : [];
      setTeachers(nextTeachers);
      if (nextTeachers.length > 0 && !teacherUserId) {
        setTeacherUserId(String(nextTeachers[0].user_id));
      }
    } catch {
      setTeachers([]);
    }
  };

  const submitLogin = async (event) => {
    event.preventDefault();
    setError("");
    setMessage("");
    try {
      const response = await api.post("/auth/login-id", { user_code: userCode, password });
      onLogin(response.data.user, response.data.access_token);
    } catch (requestError) {
      setError(extractErrorMessage(requestError, "Login failed. Check backend/CORS and try again."));
    }
  };

  const submitSignup = async (event) => {
    event.preventDefault();
    setError("");
    setMessage("");
    try {
      const payload = {
        name,
        department,
        user_code: signupCode,
        role,
        email,
        contact_number: contactNumber,
        password: signupPassword,
      };
      if (role === "student") {
        if (!teacherUserId) {
          setError("Please select an assigned teacher");
          return;
        }
        payload.teacher_user_id = Number(teacherUserId);
      }
      const response = await api.post("/auth/signup", payload);
      setMessage(response.data.message || "Signup submitted. Please wait for approval.");
    } catch (requestError) {
      setError(extractErrorMessage(requestError, "Signup failed. Check backend/CORS and try again."));
    }
  };

  const switchMode = (nextMode) => {
    setMode(nextMode);
    setError("");
    setMessage("");
    if (nextMode === "signup") {
      loadTeachers();
    }
  };

  return (
    <div className="login-shell">
      <section className="login-brand">
        <p className="brand-kicker">Smart Exam Systems & AI Surveillance</p>
        <h1>{mode === "login" ? "Welcome Back" : "Create Your Account"}</h1>
        <p>Secure examination and surveillance platform.</p>
        <ul>
          <li>Authority and teacher approval workflow</li>
          <li>Room-based exam access with secure IDs</li>
          <li>Live risk monitoring and forensic reports</li>
        </ul>
        <div className="brand-shape" aria-hidden="true" />
      </section>

      <section className="login-stage">
        <div className="login-card">
          <p className="muted">Secure access portal</p>
          <h3 className="panel-caption">Account Gateway</h3>
          <div className="tab-row">
            <button
              type="button"
              className={mode === "login" ? "active-tab" : "secondary-tab"}
              onClick={() => switchMode("login")}
            >
              Login
            </button>
            <button
              type="button"
              className={mode === "signup" ? "active-tab" : "secondary-tab"}
              onClick={() => switchMode("signup")}
            >
              Sign Up
            </button>
          </div>

          {mode === "login" ? (
            <form onSubmit={submitLogin} className="form-grid form-grid-login">
              <label>
                User ID
                <input
                  value={userCode}
                  onChange={(event) => setUserCode(event.target.value)}
                  placeholder="Enter your registered ID"
                  required
                />
              </label>
              <label>
                Password
                <input
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  type="password"
                  placeholder="Enter password"
                  required
                />
              </label>
              <div className="auth-meta-row">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(event) => setRememberMe(event.target.checked)}
                  />
                  Remember me
                </label>
                <button
                  type="button"
                  className="ghost-link"
                  onClick={() => setMessage("Contact Authority/Admin to retrieve a temporary password.")}
                >
                  Forgot password?
                </button>
              </div>
              <button type="submit">Sign In</button>
            </form>
          ) : (
            <form onSubmit={submitSignup} className="form-grid">
              <label>
                Full Name
                <input value={name} onChange={(event) => setName(event.target.value)} required />
              </label>
              <label>
                Department
                <input value={department} onChange={(event) => setDepartment(event.target.value)} required />
              </label>
              <label>
                User ID
                <input value={signupCode} onChange={(event) => setSignupCode(event.target.value)} required />
              </label>
              <label>
                Role
                <select
                  value={role}
                  onChange={(event) => {
                    const nextRole = event.target.value;
                    setRole(nextRole);
                    if (nextRole === "student") {
                      loadTeachers();
                    }
                  }}
                >
                  <option value="student">Student</option>
                  <option value="teacher">Teacher</option>
                  <option value="authority">Authority</option>
                </select>
              </label>
              <label>
                Email
                <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" required />
              </label>
              <label>
                Contact Number
                <input value={contactNumber} onChange={(event) => setContactNumber(event.target.value)} required />
              </label>
              <label>
                Password
                <input
                  value={signupPassword}
                  onChange={(event) => setSignupPassword(event.target.value)}
                  type="password"
                  required
                />
              </label>

              {role === "student" ? (
                <label>
                  Assigned Teacher
                  <select
                    value={teacherUserId}
                    onChange={(event) => setTeacherUserId(event.target.value)}
                    required
                  >
                    {teacherOptions.length === 0 ? <option value="">No approved teachers</option> : null}
                    {teacherOptions.map((teacher) => (
                      <option key={teacher.user_id} value={teacher.user_id}>
                        {teacher.name} ({teacher.user_code})
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}

              <button type="submit">Create Account</button>
            </form>
          )}

          {message ? <p className="muted">{message}</p> : null}
          {error ? <p className="error">{error}</p> : null}
        </div>
      </section>
    </div>
  );
}

export default LoginPanel;

