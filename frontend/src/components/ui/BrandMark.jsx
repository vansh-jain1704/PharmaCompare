import { useId } from "react";

/** PharmaCompare mark: a capsule on a violet tile with a teal check. Original artwork, pure SVG. */
export default function BrandMark({ size = 34 }) {
  const id = useId();
  return (
    <svg className="brand-mark" width={size} height={size} viewBox="0 0 40 40" aria-hidden="true">
      <defs>
        <linearGradient id={`${id}-g`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#5a60c9" />
          <stop offset="1" stopColor="#2c3380" />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="11" fill={`url(#${id}-g)`} />
      <g transform="rotate(-38 20 20)">
        <rect x="7" y="13.5" width="26" height="13" rx="6.5" fill="#fffaf0" />
        <path d="M20 13.5h6.5a6.5 6.5 0 0 1 0 13H20z" fill="#ee7f62" />
      </g>
      <circle cx="31" cy="11" r="6" fill="#2b8577" />
      <path d="M28.2 11.1l2 2 3.6-4" fill="none" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
