"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div style={{ padding: "2rem", fontFamily: "system-ui, sans-serif" }}>
      <h2>Algo deu errado</h2>
      <p style={{ color: "#8b9cb3", marginBottom: "1rem" }}>{error.message}</p>
      <button
        type="button"
        onClick={reset}
        style={{
          padding: "0.5rem 1rem",
          background: "#3b82f6",
          color: "white",
          border: "none",
          borderRadius: "6px",
          cursor: "pointer",
        }}
      >
        Tentar novamente
      </button>
    </div>
  );
}
