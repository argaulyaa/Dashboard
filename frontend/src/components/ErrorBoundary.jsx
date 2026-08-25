import React from "react";

// ErrorBoundary level-route: menahan error render dari satu page supaya
// seluruh app tidak white-screen diam-diam (bug lama: satu page crash ->
// layar blank tanpa pesan apa pun). Class component sengaja dipakai karena
// error boundary hanya bisa dibuat dengan class (keterbatasan React).
//
// Cakupan: error saat RENDER anak di bawahnya (termasuk efek render-phase).
// Tidak menahan error di event handler / callback async — itu tanggungan
// masing-masing page (try/catch).
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // Tetap dilog supaya kelihatan di devtools / log observability.
    console.error("[ErrorBoundary] render crash ditahan:", error, info?.componentStack || "");
  }

  handleReset = () => {
    this.setState({ error: null });
  };

  render() {
    if (this.state.error) {
      const message = String(
        (this.state.error && this.state.error.message) || this.state.error || "Unknown error"
      );
      return (
        <div className="rounded-xl border border-error bg-error-container/20 p-6 max-w-2xl">
          <h2 className="text-title-lg font-bold text-on-surface mb-2">
            Something went wrong
          </h2>
          <p className="text-body-md text-on-surface-variant mb-4">
            Halaman ini gagal dirender. Navigasi ke menu lain tetap bisa dilakukan;
            atau coba render ulang halaman ini.
          </p>
          <pre className="text-xs font-mono whitespace-pre-wrap bg-surface-container-low text-error p-3 rounded-lg overflow-auto max-h-48">
            {message}
          </pre>
          <button
            type="button"
            onClick={this.handleReset}
            className="mt-4 px-5 py-2 rounded-lg bg-primary text-on-primary font-label-lg hover:brightness-110 active:scale-95 transition-all"
          >
            Coba render ulang
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
