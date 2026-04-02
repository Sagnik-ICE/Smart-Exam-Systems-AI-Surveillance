import { useState } from "react";
import AuthorityPanel from "./components/AuthorityPanel";
import LoginPanel from "./components/LoginPanel";
import StudentExam from "./components/StudentExam";
import TeacherPanel from "./components/TeacherPanel";
import UserPortal from "./components/UserPortal";
import { setAuthToken } from "./lib/api";

const USER_KEY = "exam_user";

function getStorage() {
  if (typeof window !== "undefined" && window.sessionStorage) {
    return window.sessionStorage;
  }
  return localStorage;
}

function App() {
  const [user, setUser] = useState(() => {
    const storage = getStorage();
    const raw = storage.getItem(USER_KEY);
    if (!raw) {
      return null;
    }
    try {
      return JSON.parse(raw);
    } catch {
      storage.removeItem(USER_KEY);
      return null;
    }
  });
  const [showPortal, setShowPortal] = useState(false);

  const handleLogin = (nextUser, token) => {
    const storage = getStorage();
    setAuthToken(token);
    storage.setItem(USER_KEY, JSON.stringify(nextUser));
    setUser(nextUser);
  };

  const logout = () => {
    const storage = getStorage();
    setAuthToken(null);
    storage.removeItem(USER_KEY);
    setUser(null);
  };

  const handleUserUpdated = (nextUser) => {
    getStorage().setItem(USER_KEY, JSON.stringify(nextUser));
    setUser(nextUser);
  };

  if (!user) {
    return <LoginPanel onLogin={handleLogin} />;
  }

  return (
    <div className="app-shell">
      <header className="top-bar">
        <div>
          <p className="brand-kicker">Unified Examination Workspace</p>
          <h1>Smart Exam Systems & AI Surveillance</h1>
        </div>
        <div className="top-actions">
          {showPortal ? (
            <button className="secondary-btn" onClick={() => setShowPortal(false)}>
              Back to Dashboard
            </button>
          ) : null}
          <div className="profile-chip">
            {user.name} ({user.role}) {user?.profile?.user_code ? `- ${user.profile.user_code}` : ""}
          </div>
        </div>
      </header>
      {showPortal ? (
        <section className="portal-page">
          <div className="panel-hero">
            <p className="brand-kicker">Account Center</p>
            <h2>My Portal</h2>
          </div>
          <UserPortal user={user} onUserUpdated={handleUserUpdated} />
        </section>
      ) : null}
      {user.role === "authority" && !showPortal ? (
        <AuthorityPanel
          user={user}
          portalOpen={showPortal}
          onTogglePortal={() => setShowPortal((current) => !current)}
          onLogout={logout}
        />
      ) : null}
      {user.role === "teacher" && !showPortal ? (
        <TeacherPanel
          user={user}
          portalOpen={showPortal}
          onTogglePortal={() => setShowPortal((current) => !current)}
          onLogout={logout}
        />
      ) : null}
      {user.role === "student" && !showPortal ? (
        <div className="teacher-layout">
          <aside className="teacher-sidebar">
            <h3>Student Menu</h3>
            <button className="menu-nav-btn" onClick={() => setShowPortal((current) => !current)}>
              {showPortal ? "Close Portal" : "My Portal"}
            </button>
            <button className="menu-utility-btn" onClick={logout}>
              Logout
            </button>
          </aside>
          <StudentExam user={user} />
        </div>
      ) : null}
    </div>
  );
}

export default App;

