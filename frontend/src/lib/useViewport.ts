import { useEffect, useState } from "react";

/** 与规格 §3.1 的断点保持一致（只有读，不写样式） */
export const BREAKPOINTS = {
  rightAutoCollapse: 1279,   // ≤1279px：右栏自动收起为 44px
  leftAutoCollapse: 959,     // ≤959px ：左栏自动收起为 48px
  wide: 1700,                // ≥1700px：聊天列限宽 1120
} as const;

export function useViewportWidth(): number {
  const [width, setWidth] = useState(() => window.innerWidth);
  useEffect(() => {
    const onResize = () => setWidth(window.innerWidth);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return width;
}
