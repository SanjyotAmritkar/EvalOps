/** Restrained EvalOps wordmark: a small mark suggesting a baseline/candidate
 * comparison, plus the name. Not a decorative logo. */
export function Wordmark() {
  return (
    <span className="flex items-center gap-2">
      <svg
        width="20"
        height="20"
        viewBox="0 0 20 20"
        aria-hidden
        className="text-accent"
      >
        <rect
          x="1"
          y="1"
          width="18"
          height="18"
          rx="5"
          fill="currentColor"
          opacity="0.12"
        />
        <rect x="5" y="6.4" width="10" height="2.4" rx="1.2" fill="currentColor" />
        <rect
          x="5"
          y="11.2"
          width="6"
          height="2.4"
          rx="1.2"
          fill="currentColor"
          opacity="0.55"
        />
      </svg>
      <span className="text-[15px] font-semibold tracking-tight text-fg">
        Eval<span className="text-fg-muted">Ops</span>
      </span>
    </span>
  );
}
