import { useEffect, useId, useLayoutEffect, useRef, type ElementType, type ReactNode } from 'react';

interface FuzzyProps {
  as?: ElementType;
  /** Idle displacement as a fraction of the element's font size; text settles sharp on hover. */
  amount?: number;
  /** When set, the parent decides when the text is sharp (e.g. while a whole card is hovered). */
  active?: boolean;
  className?: string;
  children: ReactNode;
}

const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/**
 * Text pushed around by fractal noise (an SVG feTurbulence → feDisplacementMap filter) that pulls
 * itself together when you point at it. Each instance owns its filter so they animate separately,
 * and the displacement follows the font size so small and large text look equally fuzzy.
 */
export function Fuzzy({ as: Tag = 'span', amount = 0.3, active, className, children }: FuzzyProps) {
  const id = `fz-${useId().replace(/[^a-zA-Z0-9]/g, '')}`;
  const elRef = useRef<HTMLElement>(null);
  const mapRef = useRef<SVGFEDisplacementMapElement>(null);
  const idle = useRef(0);
  const current = useRef(0);
  const sharp = useRef(false);
  const frame = useRef(0);

  const write = (v: number) => {
    current.current = v;
    mapRef.current?.setAttribute('scale', v.toFixed(2));
  };

  const settle = (toSharp: boolean) => {
    sharp.current = toSharp;
    cancelAnimationFrame(frame.current);
    const from = current.current;
    const to = toSharp ? 0 : idle.current;
    if (reducedMotion()) return write(to);
    const ms = toSharp ? 1100 : 650;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / ms);
      write(from + (to - from) * (1 - (1 - t) ** 4));
      if (t < 1) frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
  };

  // Size the idle fuzz from the rendered font size, and again when it changes (clamp() type).
  useLayoutEffect(() => {
    const el = elRef.current;
    if (!el) return;
    const measure = () => {
      idle.current = parseFloat(getComputedStyle(el).fontSize) * amount;
      if (!sharp.current) {
        cancelAnimationFrame(frame.current);
        write(idle.current);
      }
    };
    measure();
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, [amount]);

  const controlled = active !== undefined;
  useEffect(() => {
    if (controlled) settle(active);
    // settle only touches refs; re-run when the controlling flag flips.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, controlled]);

  useEffect(() => () => cancelAnimationFrame(frame.current), []);

  const own = controlled
    ? {}
    : {
        onPointerEnter: () => settle(true),
        onPointerLeave: () => settle(false),
        onFocus: () => settle(true),
        onBlur: () => settle(false),
      };

  return (
    <Tag ref={elRef} className={className} style={{ filter: `url(#${id})` }} {...own}>
      {children}
      <svg className="fuzzy-defs" aria-hidden="true" focusable="false" width="0" height="0">
        <filter id={id} x="0%" y="0%" width="100%" height="100%">
          <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves={1} result="noise" />
          <feDisplacementMap
            ref={mapRef}
            in="SourceGraphic"
            in2="noise"
            scale={0}
            xChannelSelector="R"
            yChannelSelector="B"
          />
        </filter>
      </svg>
    </Tag>
  );
}
