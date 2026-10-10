import { useState } from "react";
import { Link } from "react-router-dom";
import { forgotPassword } from "../auth";
import AuthCard from "../components/AuthCard";
import { ErrorNote } from "../components/ui";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<unknown>();
  if (sent) {
    return (
      <AuthCard title="Check your email">
        <p className="text-sm text-slate-600">If {email} has an account, a link to choose a new password is on its way. It works for an hour.</p>
        <Link to="/signin" className="btn-secondary mt-5 w-full justify-center">Back to sign in</Link>
      </AuthCard>
    );
  }
  return (
    <AuthCard title="Reset your password" subtitle="We'll email you a link to choose a new one.">
      <form className="space-y-3" onSubmit={async (e) => {
        e.preventDefault(); setError(undefined);
        try { await forgotPassword(email); setSent(true); } catch (err) { setError(err); }
      }}>
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Email</span>
          <input className="input mt-1" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <ErrorNote error={error} />
        <button className="btn-primary w-full justify-center py-2.5">Send reset link</button>
        <Link to="/signin" className="block text-center text-sm text-accent-700 hover:underline">Back to sign in</Link>
      </form>
    </AuthCard>
  );
}
