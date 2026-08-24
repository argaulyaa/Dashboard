import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { login } from "../auth.js";
import { setUser } from "../user.js";
import { requestPasswordReset } from "../api.js";

export default function Login({ onLoginSuccess }) {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);

  // Forgot credentials modal state
  const [showForgotModal, setShowForgotModal] = useState(false);
  const [forgotUsername, setForgotUsername] = useState("");
  const [forgotStep, setForgotStep] = useState("idle"); // 'idle'|'submitting'|'done'|'error'
  const [forgotError, setForgotError] = useState(null);

  const closeForgotModal = () => {
    setShowForgotModal(false);
    setForgotStep("idle");
    setForgotUsername("");
    setForgotError(null);
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

          <form className="space-y-6" onSubmit={handleSubmit}>
            <div className="space-y-2">
              <label className="text-sm font-medium text-on-surface-variant block" htmlFor="username">
                Username
              </label>
              <div className="relative group">
                <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline group-focus-within:text-primary transition-colors">
                  person
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

            {forgotStep !== "done" ? (
              <>
                <p className="text-sm text-on-surface-variant mb-4">
                  Enter your username. Your administrator will be notified to reset your credentials.
                </p>
                <div className="relative group mb-4">
                  <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline group-focus-within:text-primary transition-colors">
                    person
                  </span>
                  <input
                    className="w-full bg-white border border-outline-variant rounded-lg pl-10 pr-4 py-3 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all text-sm"
                    placeholder="Your username"
                    value={forgotUsername}
                    onChange={(e) => setForgotUsername(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && e.currentTarget.nextSibling?.click?.()}
                    disabled={forgotStep === "submitting"}
                    autoFocus
                  />
                </div>
                {forgotError && (
                  <p className="text-error text-xs mb-3" role="alert">{forgotError}</p>
                )}
                <button
                  className="w-full bg-primary text-white py-3 rounded-lg font-semibold hover:brightness-110 transition-all disabled:opacity-60 flex items-center justify-center gap-2"
                  onClick={async () => {
                    if (!forgotUsername.trim()) {
                      setForgotError("Please enter your username.");
                      return;
                    }
                    setForgotError(null);
                    setForgotStep("submitting");
                    try {
                      await requestPasswordReset(forgotUsername.trim());
                      setForgotStep("done");
                    } catch {
                      setForgotStep("error");
                      setForgotError("Could not submit request. Please try again.");
                    }
                  }}
                  disabled={forgotStep === "submitting"}
                  type="button"
                >
                  {forgotStep === "submitting" ? (
                    <>
                      <span className="material-symbols-outlined animate-spin text-sm">progress_activity</span>
                      Submitting...
                    </>
                  ) : (
                    "Request Reset"
                  )}
                </button>
              </>
            ) : (
              <div className="text-center py-4">
                <span
                  className="material-symbols-outlined text-5xl text-secondary mb-4 block"
                  style={{ fontVariationSettings: "'FILL' 1" }}
                >
                  check_circle
                </span>
                <p className="font-semibold text-on-surface mb-2">Request Submitted</p>
                <p className="text-sm text-on-surface-variant">
                  Please contact your system administrator to complete the password reset.
                </p>
                <button
                  className="mt-6 w-full bg-surface-container text-on-surface py-2.5 rounded-lg font-semibold hover:bg-surface-container-high transition-all"
                  onClick={closeForgotModal}
                  type="button"
                >
                  Close
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}