// Flat, generated cover art for lesson cards (no image files): lavender, mint and cream
// shapes with thin ink lines, in the spirit of a hand-made worksheet.

import { cx } from "./ui";

const FILLS = ["#efe9ff", "#e4f9ee", "#fff4dc"];
const ACCENTS = ["#b196ff", "#74ebad", "#ffcf70"];

export function LessonArt({ index, className }: { index: number; className?: string }) {
  const fill = FILLS[index % FILLS.length];
  const accent = ACCENTS[index % ACCENTS.length];
  const variant = index % 3;
  return (
    <svg viewBox="0 0 300 200" preserveAspectRatio="xMidYMid slice" aria-hidden="true" className={cx("h-full w-full", className)}>
      <rect width="300" height="200" fill={fill} />
      <g stroke="#1a1a1a" strokeOpacity="0.08">
        {Array.from({ length: 10 }, (_, i) => (
          <path key={`v${i}`} d={`M${i * 32} 0V200`} />
        ))}
        {Array.from({ length: 7 }, (_, i) => (
          <path key={`h${i}`} d={`M0 ${i * 32}H300`} />
        ))}
      </g>
      {variant === 0 ? (
        // fraction bars
        <g>
          {[1, 2, 3, 4].map((parts, row) => (
            <g key={parts}>
              {Array.from({ length: parts }, (_, i) => (
                <rect
                  key={i}
                  x={40 + (i * 220) / parts}
                  y={30 + row * 36}
                  width={220 / parts - 4}
                  height="24"
                  rx="3"
                  fill={i === 0 ? accent : "#ffffff"}
                  stroke="#1a1a1a"
                  strokeWidth="1.2"
                />
              ))}
            </g>
          ))}
        </g>
      ) : variant === 1 ? (
        // sun and leaf
        <g stroke="#1a1a1a" strokeWidth="1.4" fill="none">
          <circle cx="215" cy="62" r="26" fill={accent} />
          <path d="M70 170 C 70 110, 130 70, 190 80 C 180 140, 130 170, 70 170 Z" fill="#ffffff" />
          <path d="M70 170 C 110 140, 140 115, 185 84" />
          <path d="M105 146 l-8 -22 M128 126 l-6 -24 M150 108 l-4 -20" />
        </g>
      ) : (
        // loop arrows
        <g stroke="#1a1a1a" strokeWidth="1.4" fill="none">
          <rect x="60" y="50" width="180" height="100" rx="12" fill="#ffffff" />
          <path d="M100 100 a 40 30 0 1 1 80 0" stroke={accent} strokeWidth="6" />
          <path d="M180 100 l -8 -12 M180 100 l 10 -10" />
          <text x="100" y="135" fontFamily="ui-monospace, monospace" fontSize="14" fill="#1a1a1a" stroke="none">
            for i in range(3):
          </text>
        </g>
      )}
    </svg>
  );
}
