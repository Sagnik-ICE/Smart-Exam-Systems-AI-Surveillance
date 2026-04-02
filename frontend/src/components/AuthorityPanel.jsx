import { useEffect, useState } from "react";
import api from "../lib/api";

function AuthorityPanel({ user, onTogglePortal, portalOpen, onLogout }) {
  const [section, setSection] = useState("pending");
  const [pendingUsers, setPendingUsers] = useState([]);
  const [users, setUsers] = useState([]);
  const [roleFilter, setRoleFilter] = useState("teacher");
  const [rooms, setRooms] = useState([]);
  const [message, setMessage] = useState("");
  const [teachers, setTeachers] = useState([]);
  const [userSearch, setUserSearch] = useState("");
  const [resetTargetUserId, setResetTargetUserId] = useState(null);
  const [resetPasswordDraft, setResetPasswordDraft] = useState({});
  const [newUser, setNewUser] = useState({
    name: "",
    department: "",
    user_code: "",
    role: "teacher",
    email: "",
    contact_number: "",
    password: "",
    teacher_user_id: ""
  });

  const loadPending = async () => {
    try {
      const response = await api.get("/management/pending");
      setPendingUsers(Array.isArray(response.data) ? response.data : []);
    } catch {
      setPendingUsers([]);
    }
  };

  const loadUsers = async (nextRole = roleFilter, nextSearch = userSearch) => {
    try {
      const query = `/management/users?role=${nextRole}${
        nextSearch.trim() ? `&user_code=${encodeURIComponent(nextSearch.trim())}` : ""
      }`;
      const response = await api.get(query);
      setUsers(Array.isArray(response.data) ? response.data : []);
    } catch {
      setUsers([]);
    }
  };

  const loadRooms = async () => {
    try {
      const response = await api.get("/rooms/mine");
      setRooms(Array.isArray(response.data) ? response.data : []);
    } catch {
      setRooms([]);
    }
  };

  const loadTeacherDirectory = async () => {
    try {
      const response = await api.get("/auth/teachers");
      const rows = Array.isArray(response.data) ? response.data : [];
      setTeachers(rows);
      setNewUser((current) => {
        if (rows.length === 0) {
          return { ...current, teacher_user_id: "" };
        }
        const exists = rows.some((teacher) => String(teacher.user_id) === String(current.teacher_user_id));
        if (exists) {
          return current;
        }
        return { ...current, teacher_user_id: String(rows[0].user_id) };
      });
    } catch {
      setTeachers([]);
    }
  };

  const approveUser = async (userId, approve) => {
    try {
      await api.post(`/management/approve/${userId}`, { approve });
      setMessage(approve ? "User approved" : "User rejected");
      loadPending();
      loadUsers(roleFilter);
    } catch (requestError) {
      setMessage(requestError?.response?.data?.detail || "Could not update approval");
    }
  };

  const setAccess = async (userId, isActive) => {
    try {
      await api.post(`/management/access/${userId}`, { is_active: isActive });
      setMessage(isActive ? "User access enabled" : "User access disabled");
      loadUsers(roleFilter);
    } catch (requestError) {
      setMessage(requestError?.response?.data?.detail || "Could not update access");
    }
  };

  const deleteUser = async (userId) => {
    try {
      await api.delete(`/management/users/${userId}`);
      setMessage("User deleted");
      loadPending();
      loadUsers(roleFilter);
    } catch (requestError) {
      setMessage(requestError?.response?.data?.detail || "Could not delete user");
    }
  };

  const openResetPassword = (userId) => {
    setResetTargetUserId(userId);
    setResetPasswordDraft((current) => ({
      ...current,
      [userId]: current[userId] || "",
    }));
  };

  const cancelResetPassword = () => {
    setResetTargetUserId(null);
  };

  const setTemporaryPassword = async (row) => {
    const candidate = String(resetPasswordDraft[row.id] || "").trim();
    if (candidate.length < 8) {
      setMessage("Temporary password must be at least 8 characters");
      return;
    }

    try {
      await api.post(`/management/reset-password/${row.id}`, {
        new_password: candidate,
      });
      setMessage(`Temporary password set for ${row.name} (${row.profile.user_code})`);
      setResetPasswordDraft((current) => ({
        ...current,
        [row.id]: "",
      }));
      setResetTargetUserId(null);
    } catch (requestError) {
      setMessage(requestError?.response?.data?.detail || "Could not reset password");
    }
  };

  const createUserManual = async (event) => {
    event.preventDefault();
    if (newUser.role === "student" && !newUser.teacher_user_id) {
      await loadTeacherDirectory();
      setMessage("Select an assigned teacher before creating a student account");
      return;
    }

    try {
      const payload = {
        ...newUser,
        teacher_user_id: newUser.role === "student" ? Number(newUser.teacher_user_id) : null,
        approve_now: true
      };
      await api.post("/management/create-user", payload);
      setMessage("User created manually");

      if (payload.role === "teacher") {
        await loadTeacherDirectory();
      }

      setNewUser({
        name: "",
        department: "",
        user_code: "",
        role: "teacher",
        email: "",
        contact_number: "",
        password: "",
        teacher_user_id: teachers.length > 0 ? String(teachers[0].user_id) : ""
      });
      loadUsers(roleFilter);
      loadPending();
    } catch (requestError) {
      setMessage(requestError?.response?.data?.detail || "Could not create user");
    }
  };

  useEffect(() => {
    loadPending();
    loadUsers(roleFilter);
    loadRooms();
    loadTeacherDirectory();
  }, []);

  const openSection = (nextSection) => {
    setSection(nextSection);
    if (nextSection === "pending") {
      loadPending();
      return;
    }
    if (nextSection === "access") {
      loadUsers(roleFilter, userSearch);
      return;
    }
    if (nextSection === "rooms") {
      loadRooms();
    }
  };

  return (
    <div className="teacher-layout">
      <aside className="teacher-sidebar">
        <h3>Authority Menu</h3>
        <button
          className={section === "pending" ? "menu-nav-btn menu-nav-btn-active" : "menu-nav-btn"}
          onClick={() => openSection("pending")}
        >
          Pending Approvals
        </button>
        <button
          className={section === "add-user" ? "menu-nav-btn menu-nav-btn-active" : "menu-nav-btn"}
          onClick={() => openSection("add-user")}
        >
          Manual Add User
        </button>
        <button
          className={section === "access" ? "menu-nav-btn menu-nav-btn-active" : "menu-nav-btn"}
          onClick={() => openSection("access")}
        >
          User Access
        </button>
        <button
          className={section === "rooms" ? "menu-nav-btn menu-nav-btn-active" : "menu-nav-btn"}
          onClick={() => openSection("rooms")}
        >
          All Exam Rooms
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
        <p className="brand-kicker">Governance Console</p>
        <h2>Authority Control Panel</h2>
      </div>
      <p className="muted">
        Logged in as {user.name}. Approve teachers/students, manage user access, and inspect all rooms.
      </p>

      {section === "pending" ? (
        <div className="replay-box">
          <div className="exams-toolbar">
            <h3>Pending Approvals</h3>
            <button onClick={loadPending}>Refresh Pending</button>
          </div>
          {pendingUsers.length === 0 ? (
            <p className="muted">No pending approvals.</p>
          ) : (
            <div className="list-grid">
              {pendingUsers.map((row) => (
                <div key={`pending-${row.id}`} className="list-card">
                  <div>
                    <strong>{row.name}</strong> ({row.role})
                  </div>
                  <div className="muted">ID: {row.profile.user_code}</div>
                  <div className="muted">Department: {row.profile.department}</div>
                  <div className="row-actions">
                    <button onClick={() => approveUser(row.id, true)}>Approve</button>
                    <button className="danger-btn" onClick={() => approveUser(row.id, false)}>
                      Reject
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : null}

      {section === "add-user" ? (
        <div className="replay-box">
          <h3>Manual Add User</h3>
          <form onSubmit={createUserManual} className="form-grid">
            <label>
              Full Name
              <input
                value={newUser.name}
                onChange={(event) => setNewUser((current) => ({ ...current, name: event.target.value }))}
                required
              />
            </label>
            <label>
              Department
              <input
                value={newUser.department}
                onChange={(event) => setNewUser((current) => ({ ...current, department: event.target.value }))}
                required
              />
            </label>
            <label>
              User ID
              <input
                value={newUser.user_code}
                onChange={(event) => setNewUser((current) => ({ ...current, user_code: event.target.value }))}
                required
              />
            </label>
            <label>
              Role
              <select
                value={newUser.role}
                onChange={(event) => {
                  const nextRole = event.target.value;
                  setNewUser((current) => ({ ...current, role: nextRole }));
                  if (nextRole === "student") {
                    loadTeacherDirectory();
                  }
                }}
              >
                <option value="authority">Authority</option>
                <option value="teacher">Teacher</option>
                <option value="student">Student</option>
              </select>
            </label>
            <label>
              Email
              <input
                value={newUser.email}
                type="email"
                onChange={(event) => setNewUser((current) => ({ ...current, email: event.target.value }))}
                required
              />
            </label>
            <label>
              Contact Number
              <input
                value={newUser.contact_number}
                onChange={(event) => setNewUser((current) => ({ ...current, contact_number: event.target.value }))}
                required
              />
            </label>
            <label>
              Temporary Password
              <input
                value={newUser.password}
                type="password"
                minLength={8}
                onChange={(event) => setNewUser((current) => ({ ...current, password: event.target.value }))}
                required
              />
            </label>

            {newUser.role === "student" ? (
              <label>
                Assigned Teacher
                <select
                  value={newUser.teacher_user_id}
                  onChange={(event) =>
                    setNewUser((current) => ({ ...current, teacher_user_id: event.target.value }))
                  }
                  required
                >
                  {teachers.length === 0 ? <option value="">No teacher available</option> : null}
                  {teachers.map((teacher) => (
                    <option key={`assign-${teacher.user_id}`} value={teacher.user_id}>
                      {teacher.name} ({teacher.user_code})
                    </option>
                  ))}
                </select>
              </label>
            ) : null}

            <button type="submit">Create User</button>
          </form>
        </div>
      ) : null}

      {section === "access" ? (
        <div className="replay-box">
          <h3>User Access Management</h3>
          <div className="inline-row">
            <label>
              Search User ID
              <input
                value={userSearch}
                onChange={(event) => {
                  const next = event.target.value;
                  setUserSearch(next);
                }}
                placeholder="STD-001 / TCH-001"
              />
            </label>
            <label>
              Role Filter
              <select
                value={roleFilter}
                onChange={(event) => {
                  const nextRole = event.target.value;
                  setRoleFilter(nextRole);
                  loadUsers(nextRole, userSearch);
                }}
              >
                <option value="authority">Authority</option>
                <option value="teacher">Teacher</option>
                <option value="student">Student</option>
              </select>
            </label>
            <button onClick={() => loadUsers(roleFilter, userSearch)}>Search</button>
            <button
              onClick={() => {
                setUserSearch("");
                loadUsers(roleFilter, "");
              }}
            >
              Clear
            </button>
          </div>

          {users.length === 0 ? (
            <p className="muted">No users found for selected role.</p>
          ) : (
            <div className="list-grid authority-access-list">
              {users.map((row) => (
                <div key={`user-${row.id}`} className="list-card">
                  <div>
                    <strong>{row.name}</strong> ({row.role})
                  </div>
                  <div className="auth-user-meta-grid">
                    <div className="muted">ID: {row.profile.user_code}</div>
                    <div className="muted">Status: {row.profile.approval_status}</div>
                    <div className="muted">Access: {row.profile.is_active ? "enabled" : "disabled"}</div>
                  </div>
                  <div className="row-actions auth-access-actions">
                    <button
                      className={row.profile.is_active ? "danger-btn" : ""}
                      onClick={() => setAccess(row.id, !row.profile.is_active)}
                    >
                      {row.profile.is_active ? "Disable Access" : "Enable Access"}
                    </button>
                    <button className="secondary-btn" onClick={() => openResetPassword(row.id)}>
                      Retrieve Password
                    </button>
                    <button className="danger-btn" onClick={() => deleteUser(row.id)}>
                      Delete
                    </button>
                  </div>
                  {resetTargetUserId === row.id ? (
                    <div className="auth-reset-box">
                      <label>
                        Set Temporary Password
                        <input
                          type="password"
                          minLength={8}
                          value={resetPasswordDraft[row.id] || ""}
                          onChange={(event) =>
                            setResetPasswordDraft((current) => ({
                              ...current,
                              [row.id]: event.target.value,
                            }))
                          }
                          placeholder="Minimum 8 characters"
                        />
                      </label>
                      <div className="auth-reset-actions">
                        <button onClick={() => setTemporaryPassword(row)}>Set Temporary Password</button>
                        <button className="secondary-btn" onClick={cancelResetPassword}>Cancel</button>
                      </div>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </div>
      ) : null}

      {section === "rooms" ? (
        <div className="replay-box">
          <div className="exams-toolbar">
            <h3>All Exam Rooms</h3>
            <button onClick={loadRooms}>Refresh Rooms</button>
          </div>
          {rooms.length === 0 ? (
            <p className="muted">No rooms available.</p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Room ID</th>
                    <th>Course</th>
                    <th>Code</th>
                    <th>Teacher</th>
                    <th>Exam ID</th>
                  </tr>
                </thead>
                <tbody>
                  {rooms.map((room) => (
                    <tr key={room.room_id}>
                      <td>{room.room_id}</td>
                      <td>{room.course_title}</td>
                      <td>{room.course_code}</td>
                      <td>{room.teacher_name}</td>
                      <td>{room.exam_id}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : null}

      {message ? <p className="muted">{message}</p> : null}
      </div>
    </div>
  );
}

export default AuthorityPanel;
