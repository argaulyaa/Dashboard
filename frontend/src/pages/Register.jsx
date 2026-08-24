import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { register } from "../auth.js";

const SERVER_ERROR_MESSAGES = {
  username_taken: "That username is already registered.",
  username_required: "Please enter a username.",
  email_taken: "That email address is already registered.",
  invalid_email: "Please enter a valid email address.",
  password_too_short: "Password must be at least 8 characters.",
  password_needs_uppercase: "Password must include at least 1 uppercase letter.",
  password_needs_digit: "Password must include at least 1 number.",
};

function validatePassword(pwd) {
  if (pwd.length < 8) return "Password must be at least 8 characters.";
  if (!/[A-Z]/.test(pwd)) return "Password must include at least 1 uppercase letter.";
  if (!/[0-9]/.test(pwd)) return "Password must include at least 1 number.";
  return null;
}

export default function Register({ onLoginSuccess }) {
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    const pwdError = validatePassword(password);
    if (pwdError) { setError(pwdError); return; }
    if (password !== confirmPassword) { setError("Passwords do not match."); return; }

    setIsSubmitting(true);
    try {
      // No role field — backend always assigns 'user' for self-register.
      await register(fullName, username, email, password);
      // Backend mengirim OTP ke email — arahkan ke halaman verifikasi
      navigate("/verify", { state: { username, email } });
    } catch (err) {
      setError(SERVER_ERROR_MESSAGES[err.message] || "Failed to create account. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="font-display bg-background min-h-screen flex items-center justify-center antialiased selection:bg-primary selection:text-white px-4">
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
            <p className="text-sm text-on-surface-variant text-center">Create Account</p>
          </div>

          <form className="space-y-5" onSubmit={handleSubmit}>
            <div className="space-y-2">
              <label className="text-sm font-medium text-on-surface-variant block" htmlFor="fullName">
                Full Name
              </label>
              <div className="relative group">
                <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline group-focus-within:text-primary transition-colors">
                  person
                </span>
                <input
                  className="w-full bg-white border border-outline-variant rounded-lg pl-10 pr-4 py-3 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all text-sm"
                  id="fullName"
                  name="fullName"
                  placeholder="Full Name"
                  required
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  disabled={isSubmitting}
                />
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-on-surface-variant block" htmlFor="email">
                Email Address
              </label>
              <div className="relative group">
                <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline group-focus-within:text-primary transition-colors">
                  mail
                </span>
                <input
                  className="w-full bg-white border border-outline-variant rounded-lg pl-10 pr-4 py-3 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all text-sm"
                  id="email"
                  name="email"
                  placeholder="you@example.com"
                  required
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={isSubmitting}
                />
              </div>
              <p className="text-xs text-on-surface-variant mt-1 ml-1">
                A verification code will be sent to this address.
              </p>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-on-surface-variant block" htmlFor="username">
                Network ID
              </label>
              <div className="relative group">
                <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline group-focus-within:text-primary transition-colors">
                  badge
                </span>
                <input
                  className="w-full bg-white border border-outline-variant rounded-lg pl-10 pr-4 py-3 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all text-sm"
                  id="username"
                  name="username"
                  placeholder="Network ID"
                  required
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  disabled={isSubmitting}
                />
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-on-surface-variant block" htmlFor="password">
                Password
              </label>
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
              <p className="text-xs text-on-surface-variant mt-1 ml-1 leading-tight">
                Min. 8 characters, at least 1 uppercase letter and 1 number.
              </p>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-on-surface-variant block" htmlFor="confirmPassword">
                Confirm Password
              </label>
              <div className="relative group">
                <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline group-focus-within:text-primary transition-colors">
                  lock
                </span>
                <input
                  className="w-full bg-white border border-outline-variant rounded-lg pl-10 pr-12 py-3 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all text-sm"
                  id="confirmPassword"
                  name="confirmPassword"
                  placeholder="••••••••"
                  required
                  type={showConfirmPassword ? "text" : "password"}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  disabled={isSubmitting}
                />
                <button
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-outline hover:text-on-surface transition-colors p-1"
                  onClick={() => setShowConfirmPassword((v) => !v)}
                  type="button"
                  tabIndex={-1}
                >
                  <span className="material-symbols-outlined text-[20px]">
                    {showConfirmPassword ? "visibility_off" : "visibility"}
                  </span>
                </button>
              </div>
            </div>

            {error && (
              <p className="text-error text-sm -mt-1" role="alert">
                {error}
              </p>
            )}

            <div className="bg-surface-container-low rounded-lg p-3 flex items-start gap-3 border border-outline-variant/30">
              <span className="material-symbols-outlined text-primary text-sm mt-0.5">verified_user</span>
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
                  Creating account...
                </>
              ) : (
                <>
                  Create Account
                  <span className="material-symbols-outlined text-[20px]">arrow_forward</span>
                </>
              )}
            </button>
          </form>

          <div className="mt-8 pt-8 border-t border-outline-variant flex flex-col gap-4 text-center">
            <p className="text-sm text-on-surface-variant">
              Already have an account?{" "}
              <Link className="text-primary font-semibold hover:underline" to="/login">
                Log in
              </Link>
            </p>
          </div>
        </div>

        <div className="mt-8 flex justify-center items-center gap-2 opacity-40 select-none grayscale">
          <div className="w-2 h-2 rounded-full bg-healthy" />
          <div className="w-2 h-2 rounded-full bg-restarting" />
          <div className="w-2 h-2 rounded-full bg-degraded" />
          <span className="font-mono text-xs ml-2 tracking-widest uppercase">System v2.4.0</span>
        </div>
      </main>
    </div>
  );
}