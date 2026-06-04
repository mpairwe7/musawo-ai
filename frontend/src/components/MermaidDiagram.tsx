"use client";

import { useEffect, useRef, useState } from "react";

// Mermaid is heavy (~loaded once, on demand) — keep it out of the main bundle.
let _mermaidPromise: Promise<typeof import("mermaid").default> | null = null;
function loadMermaid() {
  if (!_mermaidPromise) {
    _mermaidPromise = import("mermaid").then((m) => {
      const mermaid = m.default;
      mermaid.initialize({
        startOnLoad: false,
        theme: "dark",
        securityLevel: "strict", // no scripts/click-handlers in LLM-authored diagrams
        fontFamily: "inherit",
      });
      return mermaid;
    });
  }
  return _mermaidPromise;
}

let _seq = 0;

/**
 * Renders a Mermaid diagram from `code`. If the (LLM-authored) syntax is
 * invalid it degrades to showing the source — it never throws into the chat.
 */
export default function MermaidDiagram({ code }: { code: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const id = `mmd-${(_seq += 1)}`;
    const src = code.trim();
    if (!src) return;
    loadMermaid()
      .then((mermaid) => mermaid.render(id, src))
      .then(({ svg }) => {
        if (!cancelled && ref.current) {
          ref.current.innerHTML = svg;
          setFailed(false);
        }
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [code]);

  if (failed) {
    return (
      <pre className="mermaid-fallback" aria-label="diagram source">
        <code>{code.trim()}</code>
      </pre>
    );
  }
  return <div className="mermaid-diagram" ref={ref} role="img" aria-label="diagram" />;
}
