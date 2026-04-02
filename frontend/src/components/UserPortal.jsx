import { useState } from "react";
import api from "../lib/api";

function UserPortal({ user, onUserUpdated }) {
  const [name, setName] = useState(user.name || "");
  const [department, setDepartment] = useState(user?.profile?.department || "");
  const [contactNumber, setContactNumber] = useState(user?.profile?.contact_number || "");

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");

  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const saveProfile = async (event) => {
    event.preventDefault();
    setError("");
    setMessage("");
    try {
      const response = await api.patch("/auth/me", {
        name,
        department,
        contact_number: contactNumber
      });
      onUserUpdated(response.data);
      setMessage("Profile updated successfully");
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Could not update profile");
    }
  };

  const savePassword = async (event) => {
    event.preventDefault();
    setError("");
    setMessage("");
    try {
      await api.post("/auth/change-password", {
        current_password: currentPassword,
        new_password: newPassword
      });
      setCurrentPassword("");
      setNewPassword("");
      setMessage("Password changed successfully");
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || "Could not change password");
    }
  };

  return (
    <div className="replay-box">
      <h3>My Portal</h3>
      <p className="muted">Update your profile details and password.</p>

      <form className="form-grid" onSubmit={saveProfile}>
        <label>
          Name
          <input value={name} onChange={(event) => setName(event.target.value)} required />
        </label>
        <label>
          Department
          <input value={department} onChange={(event) => setDepartment(event.target.value)} required />
        </label>
        <label>
          Contact Number
          <input value={contactNumber} onChange={(event) => setContactNumber(event.target.value)} required />
        </label>
        <button type="submit">Save Profile</button>
      </form>

      <form className="form-grid" onSubmit={savePassword}>
        <label>
          Current Password
          <input
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
            type="password"
            required
          />
        </label>
        <label>
          New Password
          <input
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
            type="password"
            minLength={8}
            required
          />
        </label>
        <button type="submit">Change Password</button>
      </form>

      {message ? <p className="muted">{message}</p> : null}
      {error ? <p className="error">{error}</p> : null}
    </div>
  );
}

export default UserPortal;
