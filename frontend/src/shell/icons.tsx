import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Base({ size = 14, children, ...rest }: IconProps & { children: React.ReactNode }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor"
         strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" {...rest}>
      {children}
    </svg>
  );
}

export const Icon = {
  search: (p: IconProps) => <Base {...p}><circle cx="7.2" cy="7.2" r="4.4" /><path d="M10.6 10.6L14 14" /></Base>,
  server: (p: IconProps) => <Base {...p}><rect x="2.2" y="2.6" width="11.6" height="4.4" rx="1.2" /><rect x="2.2" y="9" width="11.6" height="4.4" rx="1.2" /><path d="M4.6 4.8h.01M4.6 11.2h.01" /></Base>,
  db: (p: IconProps) => <Base {...p}><ellipse cx="8" cy="4" rx="5.2" ry="2" /><path d="M2.8 4v8c0 1.1 2.33 2 5.2 2s5.2-.9 5.2-2V4" /><path d="M2.8 8c0 1.1 2.33 2 5.2 2s5.2-.9 5.2-2" /></Base>,
  folder: (p: IconProps) => <Base {...p}><path d="M2.2 4.6c0-.7.6-1.2 1.2-1.2h2.4l1.3 1.5h5.5c.7 0 1.2.5 1.2 1.2v5.5c0 .7-.5 1.2-1.2 1.2H3.4c-.7 0-1.2-.5-1.2-1.2z" /></Base>,
  history: (p: IconProps) => <Base {...p}><path d="M2.4 8a5.6 5.6 0 105.6-5.6c-1.9 0-3.6 1-4.6 2.4" /><path d="M2.6 3v2.4h2.4M8 5.4V8l1.9 1.2" /></Base>,
  star: (p: IconProps) => <Base {...p}><path d="M8 2.4l1.7 3.5 3.8.5-2.8 2.7.7 3.8L8 11.1l-3.4 1.8.7-3.8L2.5 6.4l3.8-.5z" /></Base>,
  plus: (p: IconProps) => <Base {...p}><path d="M8 3.4v9.2M3.4 8h9.2" /></Base>,
  terminal: (p: IconProps) => <Base {...p}><rect x="1.8" y="3" width="12.4" height="10" rx="1.4" /><path d="M4.4 6.6l1.8 1.8-1.8 1.8M8.2 10.4h3.2" /></Base>,
  sun: (p: IconProps) => <Base {...p} strokeWidth={1.3}><circle cx="8" cy="8" r="2.6" /><path d="M8 1.4v1.4M8 13.2v1.4M1.4 8h1.4M13.2 8h1.4M3.4 3.4l1 1M11.6 11.6l1 1M12.6 3.4l-1 1M4.4 11.6l-1 1" /></Base>,
  moon: (p: IconProps) => <Base {...p} strokeWidth={1.3}><path d="M13.5 9.9A5.9 5.9 0 016.1 2.5a5.9 5.9 0 107.4 7.4z" /></Base>,
  gear: (p: IconProps) => (
    <svg width={p.size ?? 14} height={p.size ?? 14} viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 11-4 0v-.09A1.65 1.65 0 008 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 110-4h.09A1.65 1.65 0 004.6 8a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 112.83-2.83l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 114 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 112.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 110 4h-.09a1.65 1.65 0 00-1.51 1z" />
    </svg>
  ),
  panel: (p: IconProps) => <Base {...p}><rect x="1.8" y="2.8" width="12.4" height="10.4" rx="1.4" /><path d="M10.2 2.8v10.4" /></Base>,
  chevronDown: (p: IconProps) => <Base {...p}><path d="M4.4 6.4L8 10l3.6-3.6" /></Base>,
  doc: (p: IconProps) => <Base {...p}><path d="M3.6 2.4h5.2l3.6 3.6v7.6c0 .5-.4.9-.9.9H4.5c-.5 0-.9-.4-.9-.9z" /><path d="M8.6 2.4V6h3.8" /></Base>,
  tools: (p: IconProps) => <Base {...p}><path d="M9.6 2.6a2.8 2.8 0 003.8 3.8l-6.4 6.4a1.4 1.4 0 01-2-2z" /><path d="M10.4 12.2l2.2 2.2M12.6 10l2.4 2.4" /></Base>,
  tasks: (p: IconProps) => <Base {...p}><path d="M3 4.6l1.4 1.4L7.2 3.2M3 10.6l1.4 1.4L7.2 9.2M9.4 5h4M9.4 11h4" /></Base>,
  logs: (p: IconProps) => <Base {...p}><path d="M3.4 3.6h9.2M3.4 6.8h9.2M3.4 10h6M3.4 13.2h4" /></Base>,
  send: (p: IconProps) => <Base {...p} strokeWidth={1.6}><path d="M14 8L2.4 2.8 4.6 8l-2.2 5.2z" /><path d="M4.6 8H14" /></Base>,
  lock: (p: IconProps) => <Base {...p} size={p.size ?? 11} strokeWidth={1.6}><rect x="3.4" y="7" width="9.2" height="6.4" rx="1.6" /><path d="M5.7 7V5.3a2.3 2.3 0 014.6 0V7" /></Base>,
  shieldOk: (p: IconProps) => <Base {...p} size={p.size ?? 11} strokeWidth={1.6}><path d="M8 1.8l6 2.6v4c0 3.2-2.4 5.3-6 6.4-3.6-1.1-6-3.2-6-6.4v-4z" /><path d="M5.6 8.2l1.7 1.7 3.2-3.4" /></Base>,
  shieldWarn: (p: IconProps) => <Base {...p} size={p.size ?? 12} strokeWidth={1.6}><path d="M8 1.8l6 2.6v4c0 3.2-2.4 5.3-6 6.4-3.6-1.1-6-3.2-6-6.4v-4z" /><path d="M8 5.4v3M8 10.6h.01" /></Base>,
  alert: (p: IconProps) => <Base {...p}><path d="M8 2.6l5.6 9.8H2.4z" /><path d="M8 6.6v2.6M8 11.2h.01" /></Base>,
  check: (p: IconProps) => <Base {...p} strokeWidth={1.8}><path d="M3.2 8.4l3.2 3.2 6.4-7.2" /></Base>,
  close: (p: IconProps) => <Base {...p}><path d="M4 4l8 8M12 4l-8 8" /></Base>,
  file: (p: IconProps) => <Base {...p}><path d="M9 1.8H4.4c-.6 0-1 .4-1 1v10.4c0 .6.4 1 1 1h7.2c.6 0 1-.4 1-1V5.4z" /><path d="M9 1.8v3.6h3.6" /></Base>,
};
