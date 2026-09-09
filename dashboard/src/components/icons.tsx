import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

const COMMON: IconProps = {
  width: 16,
  height: 16,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": true,
};

export function SunIcon(props: IconProps) {
  return (
    <svg {...COMMON} {...props}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

export function MoonIcon(props: IconProps) {
  return (
    <svg {...COMMON} {...props}>
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    </svg>
  );
}

export function LaptopIcon(props: IconProps) {
  return (
    <svg {...COMMON} {...props}>
      <rect x="3" y="5" width="18" height="12" rx="2" />
      <path d="M2 20h20" />
    </svg>
  );
}

export function AlertIcon(props: IconProps) {
  return (
    <svg {...COMMON} {...props}>
      <path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
    </svg>
  );
}

export function ChevronRightIcon(props: IconProps) {
  return (
    <svg {...COMMON} {...props}>
      <path d="m9 18 6-6-6-6" />
    </svg>
  );
}

export function ArrowLeftIcon(props: IconProps) {
  return (
    <svg {...COMMON} {...props}>
      <path d="M19 12H5M12 19l-7-7 7-7" />
    </svg>
  );
}

export function PlusIcon(props: IconProps) {
  return (
    <svg {...COMMON} {...props}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

export function CopyIcon(props: IconProps) {
  return (
    <svg {...COMMON} {...props}>
      <rect x="9" y="9" width="12" height="12" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

export function CheckIcon(props: IconProps) {
  return (
    <svg {...COMMON} {...props}>
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}

export function PlayIcon(props: IconProps) {
  return (
    <svg {...COMMON} {...props}>
      <path d="M6 4v16l14-8z" fill="currentColor" stroke="none" />
    </svg>
  );
}
