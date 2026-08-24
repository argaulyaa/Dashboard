import React, { useState } from "react";
import { useNavigate, Link, useLocation } from "react-router-dom";
import { login } from "../auth.js";
import { setUser } from "../user.js";
import {
  requestPasswordReset,
  verifyPasswordResetOtp,
  confirmPasswordReset,
  resendPasswordResetOtp,
} from "../api.js";

// Pesan error ramah utk kode ValueError dari backend reset-password
const RESET_ERROR_MESSAGES = {
  otp_invalid: "Incorrect code. Please check your email and try again.",
  otp_expired: "This code has expired. Request a new code and try again.",
  pending_not_found: "No active reset request. Start again from your username.",
  invalid_reset_token: "Your reset session has expired. Please start again.",
  passwords_do_not_match: "Passwords do not match.",
  password_too_short: "Password must be at least 8 characters.",
  password_needs_uppercase: "Password must include at least 1 uppercase letter.",
  password_needs_digit: "Password must include at least 1 number.",
  email_service_unavailable: "Could not send the email right now. Please try again later.",
};

function validateNewPassword(pwd) {
  if (pwd.length < 8) return "Password must be at least 8 characters.";
  if (!/[A-Z]/.test(pwd)) return "Password must include at least 1 uppercase letter.";
  if (!/[0-9]/.test(pwd)) return "Password must include at least 1 number.";
  return null;
}

export default function Login({ onLoginSuccess }) {
  const navigate = useNavigate();
  const location = useLocation();
  const justVerified = location.state?.verified === true;
  const justReset = location.state?.passwordReset === true;

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);

  // Forgot credentials wizard state
  // Step: 'identify' (username/email) -> 'otp' (kode dari email)
  //       -> 'newpass' (2 field password baru) -> 'done'
  const [showForgotModal, setShowForgotModal] = useState(false);
  const [forgotStep, setForgotStep] = useState("identify");
  const [forgotUsername, setForgotUsername] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmNewPassword, setConfirmNewPassword] = useState("");
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [resetToken, setResetToken] = useState("");
  const [forgotBusy, setForgotBusy] = useState(false);
  const [forgotError, setForgotError] = useState(null);

  const closeForgotModal = () => {
    setShowForgotModal(false);
    setForgotStep("identify");
    setForgotUsername("");
    setOtpCode("");
    setNewPassword("");
    setConfirmNewPassword("");
    setResetToken("");
    setForgotError(null);
    setForgotBusy(false);
  };

  // Langkah 1: minta OTP dikirim ke email akun.
  // Backend sengaja selalu sukses untuk username yang tidak dikenal
  // (anti-enumeration), jadi error di sini hanya jaringan/SMTP mati.
  const handleIdentifySubmit = async () => {
    if (!forgotUsername.trim()) {
      setForgotError("Please enter your username or email.");
      return;
    }
    setForgotError(null);
    setForgotBusy(true);
    try {
      await requestPasswordReset(forgotUsername.trim());
      setForgotStep("otp");
    } catch (err) {
      setForgotError(RESET_ERROR_MESSAGES[err.message] || "Could not submit request. Please try again.");
    } finally {
      setForgotBusy(false);
    }
  };

  const handleResendOtp = async () => {
    setForgotError(null);
    setForgotBusy(true);
    try {
      await resendPasswordResetOtp(forgotUsername.trim());
    } catch (err) {
      setForgotError(RESET_ERROR_MESSAGES[err.message] || "Could not resend the code. Please try again.");
    } finally {
      setForgotBusy(false);
    }
  };

  // Langkah 2: verifikasi OTP -> dapat reset_token sekali pakai
  const handleOtpSubmit = async () => {
    if (!otpCode.trim()) {
      setForgotError("Please enter the 6-digit code from your email.");
      return;
    }
    setForgotError(null);
    setForgotBusy(true);
    try {
      const data = await verifyPasswordResetOtp(forgotUsername.trim(), otpCode.trim());
      setResetToken(data.reset_token);
      setForgotStep("newpass");
    } catch (err) {
      setForgotError(RESET_ERROR_MESSAGES[err.message] || "Verification failed. Please try again.");
    } finally {
      setForgotBusy(false);
    }
  };

  // Langkah 3: simpan password baru (2 field), lalu redirect ke login
  const handleNewPasswordSubmit = async () => {
    const pwdError = validateNewPassword(newPassword);
    if (pwdError) {
      setForgotError(pwdError);
      return;
    }
    if (newPassword !== confirmNewPassword) {
      setForgotError("Passwords do not match.");
      return;
    }
    setForgotError(null);
    setForgotBusy(true);
    try {
      await confirmPasswordReset(resetToken, newPassword, confirmNewPassword);
      setForgotStep("done");
      // Redirect ke halaman login dengan banner konfirmasi
      setTimeout(() => {
        closeForgotModal();
        navigate("/login", { replace: true, state: { passwordReset: true } });
      }, 1600);
    } catch (err) {
      setForgotError(RESET_ERROR_MESSAGES[err.message] || "Could not reset password. Please try again.");
    } finally {
      setForgotBusy(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
        await login(username, password);
        const name = username.trim();
        setUser(name);
        onLoginSuccess?.(name);
        navigate("/", { replace: true });
    } catch (err) {
      setError(
        err.status === 401
          ? "Invalid username or password."
          : "Failed to log in. Please try again shortly."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="font-display bg-mesh min-h-screen flex items-center justify-center antialiased selection:bg-primary selection:text-white px-4">
      <main className="w-full max-w-[440px]">
        <div className="bg-surface-container-lowest rounded-xl p-8 md:p-10 border border-outline-variant shadow-[0_4px_12px_rgba(0,0,0,0.06),0_8px_24px_rgba(0,0,0,0.04)] transition-all duration-300">
          <div className="flex flex-col items-center mb-8">
            <div className="w-12 h-12 bg-primary rounded-lg flex items-center justify-center mb-6 shadow-sm">
              <span
                className="material-symbols-outlined text-white text-[28px]"
                style={{ fontVariationSettings: "'FILL' 1" }}
              >
                memory
              </span>
            </div>
            <h1 className="text-2xl font-semibold text-on-surface text-center mb-2">
              Open RAN Control Panel
            </h1>
            <p className="text-sm text-on-surface-variant text-center">
              Enterprise Infrastructure Management
            </p>
          </div>

          {/* Banner verifikasi berhasil — muncul kalau redirect dari /verify */}
          {justVerified && (
            <div className="mb-6 flex items-start gap-3 bg-secondary-container text-on-secondary-container rounded-lg px-4 py-3 border border-secondary-container">
              <span className="material-symbols-outlined text-lg mt-0.5" style={{ fontVariationSettings: "'FILL' 1" }}>check_circle</span>
              <p className="text-sm font-medium">Account verified! You can now log in.</p>
            </div>
          )}

          {/* Banner reset password berhasil — muncul setelah wizard forgot selesai */}
          {justReset && (
            <div className="mb-6 flex items-start gap-3 bg-secondary-container text-on-secondary-container rounded-lg px-4 py-3 border border-secondary-container">
              <span className="material-symbols-outlined text-lg mt-0.5" style={{ fontVariationSettings: "'FILL' 1" }}>lock_reset</span>
              <p className="text-sm font-medium">Password updated successfully! Log in with your new password.</p>
            </div>
          )}

          <form className="space-y-6" onSubmit={handleSubmit}>
            <div className="space-y-2">
              <label className="text-sm font-medium text-on-surface-variant block" htmlFor="username">
                Username or Email
              </label>
              <div className="relative group">
                <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline group-focus-within:text-primary transition-colors">
                  person
                </span>
                <input
                  className="w-full bg-white border border-outline-variant rounded-lg pl-10 pr-4 py-3 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all text-sm"
                  id="username"
                  name="username"
                  placeholder="Username or email address"
                  required
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  disabled={isSubmitting}
                />
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <label className="text-sm font-medium text-on-surface-variant" htmlFor="password">
                  Password
                </label>
                <button
                  type="button"
                  className="text-xs text-primary hover:underline transition-all bg-transparent border-none cursor-pointer p-0"
                  onClick={() => setShowForgotModal(true)}
                >
                  Forgot credentials?
                </button>
              </div>
              <div className="relative group">
                <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline group-focus-within:text-primary transition-colors">
                  lock
                </span>
                <input
                  className="w-full bg-white border border-outline-variant rounded-lg pl-10 pr-12 py-3 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all text-sm"
                  id="password"
                  name="password"
                  placeholder="••••••••"
                  required
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={isSubmitting}
                />
                <button
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-outline hover:text-on-surface transition-colors p-1"
                  onClick={() => setShowPassword((v) => !v)}
                  type="button"
                  tabIndex={-1}
                >
                  <span className="material-symbols-outlined text-[20px]">
                    {showPassword ? "visibility_off" : "visibility"}
                  </span>
                </button>
              </div>
            </div>

            {error && (
              <p className="text-error text-sm -mt-2" role="alert">
                {error}
              </p>
            )}

            <div className="bg-surface-container-low rounded-lg p-3 flex items-start gap-3 border border-outline-variant/30">
              <span className="material-symbols-outlined text-primary text-sm mt-0.5">
                verified_user
              </span>
              <p className="text-xs text-on-surface-variant">
                Secure 256-bit encrypted session. Use of this system is audited.
              </p>
            </div>

            <button
              className="w-full bg-primary text-white py-3.5 rounded-lg font-semibold text-base hover:bg-on-primary-fixed-variant active:scale-[0.98] transition-all flex items-center justify-center gap-2 shadow-sm disabled:opacity-70 disabled:cursor-not-allowed"
              type="submit"
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                <>
                  <span className="material-symbols-outlined animate-spin">progress_activity</span>
                  Authenticating...
                </>
              ) : (
                <>
                  Login
                  <span className="material-symbols-outlined text-[20px]">login</span>
                </>
              )}
            </button>

            <div className="text-center mt-4">
              <p className="text-xs text-on-surface-variant">
                Don't have an account yet?{" "}
                <Link className="text-primary font-semibold hover:underline" to="/register">
                  Register
                </Link>
              </p>
            </div>
          </form>

          <div className="mt-8 pt-8 border-t border-outline-variant flex flex-col gap-4 text-center">
            <p className="text-sm text-on-surface-variant">Internal Access Only</p>
            <div className="flex justify-center items-center gap-6">
              <a className="text-xs text-outline hover:text-primary transition-colors flex items-center gap-1" href="#">
                <span className="material-symbols-outlined text-sm">support_agent</span> Help Desk
              </a>
              <a className="text-xs text-outline hover:text-primary transition-colors flex items-center gap-1" href="#">
                <span className="material-symbols-outlined text-sm">gavel</span> Policy
              </a>
            </div>
          </div>
        </div>

        <div className="mt-8 flex justify-center items-center gap-2 opacity-40 select-none grayscale">
          <div className="w-2 h-2 rounded-full bg-healthy" />
          <div className="w-2 h-2 rounded-full bg-restarting" />
          <div className="w-2 h-2 rounded-full bg-degraded" />
          <span className="font-mono text-xs ml-2 tracking-widest uppercase">System v2.4.0</span>
        </div>
      </main>

      {/* Forgot Credentials Modal */}
      {showForgotModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-surface-container-lowest rounded-xl p-8 w-full max-w-sm border border-outline-variant shadow-xl">
            <div className="flex items-center gap-3 mb-6">
              <span className="material-symbols-outlined text-primary">lock_reset</span>
              <h2 className="text-lg font-semibold text-on-surface">Reset Credentials</h2>
              <button
                className="ml-auto text-outline hover:text-on-surface transition-colors"
                onClick={closeForgotModal}
                type="button"
              >
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>

            {forgotStep === "identify" && (
              <>
                <p className="text-sm text-on-surface-variant mb-4">
                  Enter your username or email. We'll send a 6-digit reset code to the registered email address.
                </p>
                <div className="relative group mb-4">
                  <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline group-focus-within:text-primary transition-colors">
                    person
                  </span>
                  <input
                    className="w-full bg-white border border-outline-variant rounded-lg pl-10 pr-4 py-3 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all text-sm"
                    placeholder="Username or email address"
                    value={forgotUsername}
                    onChange={(e) => setForgotUsername(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleIdentifySubmit()}
                    disabled={forgotBusy}
                    autoFocus
                  />
                </div>
                {forgotError && (
                  <p className="text-error text-xs mb-3" role="alert">{forgotError}</p>
                )}
                <button
                  className="w-full bg-primary text-white py-3 rounded-lg font-semibold hover:brightness-110 transition-all disabled:opacity-60 flex items-center justify-center gap-2"
                  onClick={handleIdentifySubmit}
                  disabled={forgotBusy}
                  type="button"
                >
                  {forgotBusy ? (
                    <>
                      <span className="material-symbols-outlined animate-spin text-sm">progress_activity</span>
                      Sending code...
                    </>
                  ) : (
                    "Send Reset Code"
                  )}
                </button>
              </>
            )}

            {forgotStep === "otp" && (
              <>
                <p className="text-sm text-on-surface-variant mb-4">
                  Enter the 6-digit code we sent to your registered email address.
                </p>
                <div className="relative group mb-4">
                  <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline group-focus-within:text-primary transition-colors">
                    password
                  </span>
                  <input
                    className="w-full bg-white border border-outline-variant rounded-lg pl-10 pr-4 py-3 text-center text-lg tracking-[0.5em] font-mono focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
                    placeholder="••••••"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    maxLength={6}
                    value={otpCode}
                    onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, ""))}
                    onKeyDown={(e) => e.key === "Enter" && handleOtpSubmit()}
                    disabled={forgotBusy}
                    autoFocus
                  />
                </div>
                {forgotError && (
                  <p className="text-error text-xs mb-3" role="alert">{forgotError}</p>
                )}
                <button
                  className="w-full bg-primary text-white py-3 rounded-lg font-semibold hover:brightness-110 transition-all disabled:opacity-60 flex items-center justify-center gap-2"
                  onClick={handleOtpSubmit}
                  disabled={forgotBusy || otpCode.length < 6}
                  type="button"
                >
                  {forgotBusy ? (
                    <>
                      <span className="material-symbols-outlined animate-spin text-sm">progress_activity</span>
                      Verifying...
                    </>
                  ) : (
                    "Verify Code"
                  )}
                </button>
                <button
                  className="w-full mt-2 text-xs text-on-surface-variant hover:text-primary transition-colors bg-transparent border-none cursor-pointer p-1"
                  onClick={handleResendOtp}
                  disabled={forgotBusy}
                  type="button"
                >
                  Didn't receive the code? Resend
                </button>
              </>
            )}

            {forgotStep === "newpass" && (
              <>
                <p className="text-sm text-on-surface-variant mb-4">
                  Choose a new password for <strong>{forgotUsername}</strong>.
                </p>
                <div className="space-y-3 mb-4">
                  <div className="relative group">
                    <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline group-focus-within:text-primary transition-colors">
                      lock
                    </span>
                    <input
                      className="w-full bg-white border border-outline-variant rounded-lg pl-10 pr-12 py-3 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all text-sm"
                      placeholder="New password (min 8 chars, 1 uppercase, 1 number)"
                      type={showNewPassword ? "text" : "password"}
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && handleNewPasswordSubmit()}
                      disabled={forgotBusy}
                      autoFocus
                    />
                    <button
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-outline hover:text-on-surface transition-colors p-1"
                      onClick={() => setShowNewPassword((v) => !v)}
                      type="button"
                      tabIndex={-1}
                    >
                      <span className="material-symbols-outlined text-[20px]">
                        {showNewPassword ? "visibility_off" : "visibility"}
                      </span>
                    </button>
                  </div>
                  <div className="relative group">
                    <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline group-focus-within:text-primary transition-colors">
                      lock_reset
                    </span>
                    <input
                      className="w-full bg-white border border-outline-variant rounded-lg pl-10 pr-4 py-3 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all text-sm"
                      placeholder="Confirm new password"
                      type={showNewPassword ? "text" : "password"}
                      value={confirmNewPassword}
                      onChange={(e) => setConfirmNewPassword(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && handleNewPasswordSubmit()}
                      disabled={forgotBusy}
                    />
                  </div>
                </div>
                {forgotError && (
                  <p className="text-error text-xs mb-3" role="alert">{forgotError}</p>
                )}
                <button
                  className="w-full bg-primary text-white py-3 rounded-lg font-semibold hover:brightness-110 transition-all disabled:opacity-60 flex items-center justify-center gap-2"
                  onClick={handleNewPasswordSubmit}
                  disabled={forgotBusy}
                  type="button"
                >
                  {forgotBusy ? (
                    <>
                      <span className="material-symbols-outlined animate-spin text-sm">progress_activity</span>
                      Saving...
                    </>
                  ) : (
                    "Reset Password"
                  )}
                </button>
              </>
            )}

            {forgotStep === "done" && (
              <div className="text-center py-4">
                <span
                  className="material-symbols-outlined text-5xl text-secondary mb-4 block"
                  style={{ fontVariationSettings: "'FILL' 1" }}
                >
                  check_circle
                </span>
                <p className="font-semibold text-on-surface mb-2">Password Updated</p>
                <p className="text-sm text-on-surface-variant">
                  Your password has been changed. Redirecting you to login...
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}