import React, { useState, useEffect, useRef } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { verifyEmail, resendOtp } from "../api.js";

const OTP_ERROR_MESSAGES = {
  otp_invalid: "Incorrect code. Please try again.",
  otp_expired: "Code has expired. Please request a new one.",
  pending_not_found: "Registration session not found. Please register again.",
};

const RESEND_COOLDOWN = 60;

export default function VerifyEmail() {
  const navigate = useNavigate();
  const location = useLocation();
  const { username, email } = location.state || {};

  const [otp, setOtp] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [resendCooldown, setResendCooldown] = useState(RESEND_COOLDOWN);
  const [resendMsg, setResendMsg] = useState(null);
  const inputRef = useRef(null);

  // Kalau halaman diakses langsung tanpa state (bukan dari register), redirect ke register
  useEffect(() => {
    if (!username || !email) {
      navigate("/register", { replace: true });
    }
  }, [username, email, navigate]);

  // Countdown resend
  useEffect(() => {
    if (resendCooldown <= 0) return;
    const t = setTimeout(() => setResendCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [resendCooldown]);

  useEffect(() => { inputRef.current?.focus(); }, []);

  const handleVerify = async (e) => {
    e.preventDefault();
    if (!otp.trim()) { setError("Please enter the verification code."); return; }
    setError(null);
    setIsSubmitting(true);
    try {
      await verifyEmail(username, otp.trim());
      // Verifikasi berhasil — redirect ke login dengan pesan sukses
      navigate("/login", { state: { verified: true }, replace: true });
    } catch (err) {
      setError(OTP_ERROR_MESSAGES[err.message] || "Verification failed. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResend = async () => {
    if (resendCooldown > 0) return;
    setResendMsg(null);
    setError(null);
    try {
      await resendOtp(username);
      setResendCooldown(RESEND_COOLDOWN);
      setResendMsg("A new code has been sent to your email.");
    } catch {
      setError("Failed to resend code. Please try again.");
    }
  };

  if (!username || !email) return null;

  return (
    <div className="font-display bg-mesh min-h-screen flex items-center justify-center antialiased selection:bg-primary selection:text-white px-4">
      <main className="w-full max-w-[440px]">
        <div className="bg-surface-container-lowest rounded-xl p-8 md:p-10 border border-outline-variant shadow-[0_4px_12px_rgba(0,0,0,0.06),0_8px_24px_rgba(0,0,0,0.04)] transition-all duration-300">
          <div className="flex flex-col items-center mb-8">
            <div className="w-12 h-12 bg-primary rounded-lg flex items-center justify-center mb-6 shadow-sm">
              <span className="material-symbols-outlined text-white text-[28px]" style={{ fontVariationSettings: "'FILL' 1" }}>
                mark_email_read
              </span>
            </div>
            <h1 className="text-2xl font-semibold text-on-surface text-center mb-2">
              Verify Your Email
            </h1>
            <p className="text-sm text-on-surface-variant text-center">
              We sent a 6-digit code to
            </p>
            <p className="text-sm font-semibold text-primary text-center mt-1 break-all">{email}</p>
          </div>

          <form className="space-y-5" onSubmit={handleVerify}>
            <div className="space-y-2">
              <label className="text-sm font-medium text-on-surface-variant block" htmlFor="otp">
                Verification Code
              </label>
              <div className="relative group">
                <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline group-focus-within:text-primary transition-colors">
                  pin
                </span>
                <input
                  ref={inputRef}
                  className="w-full bg-white border border-outline-variant rounded-lg pl-10 pr-4 py-3 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all text-sm font-mono tracking-[0.4em] text-center"
                  id="otp"
                  name="otp"
                  placeholder="------"
                  maxLength={6}
                  required
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  value={otp}
                  onChange={(e) => setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  disabled={isSubmitting}
                />
              </div>
            </div>

            {error && (
              <p className="text-error text-sm -mt-1" role="alert">{error}</p>
            )}
            {resendMsg && (
              <p className="text-secondary text-sm -mt-1">{resendMsg}</p>
            )}

            <button
              className="w-full bg-primary text-white py-3.5 rounded-lg font-semibold text-base hover:bg-on-primary-fixed-variant active:scale-[0.98] transition-all flex items-center justify-center gap-2 shadow-sm disabled:opacity-70 disabled:cursor-not-allowed"
              type="submit"
              disabled={isSubmitting || otp.length < 6}
            >
              {isSubmitting ? (
                <>
                  <span className="material-symbols-outlined animate-spin">progress_activity</span>
                  Verifying...
                </>
              ) : (
                <>
                  Verify Code
                  <span className="material-symbols-outlined text-[20px]">verified</span>
                </>
              )}
            </button>
          </form>

          <div className="mt-6 pt-6 border-t border-outline-variant flex flex-col gap-3 items-center text-center">
            <p className="text-sm text-on-surface-variant">Didn't receive the email?</p>
            <button
              type="button"
              onClick={handleResend}
              disabled={resendCooldown > 0}
              className="text-sm font-semibold text-primary hover:underline disabled:text-outline disabled:no-underline disabled:cursor-not-allowed transition-colors"
            >
              {resendCooldown > 0 ? `Resend code in ${resendCooldown}s` : "Resend Code"}
            </button>
            <button
              type="button"
              onClick={() => navigate("/login", { replace: true })}
              className="text-xs text-outline hover:text-on-surface transition-colors"
            >
              Cancel — back to login
            </button>
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
