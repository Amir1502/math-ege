import { useMemo } from 'react';
import katex from 'katex';
import 'katex/dist/katex.min.css';

export function MathFormula({ value, display = true }: { value: string; display?: boolean }) {
  const markup = useMemo(() => {
    try {
      return katex.renderToString(value, {
        displayMode: display,
        output: 'htmlAndMathml',
        trust: false,
        strict: 'error',
        throwOnError: true,
        maxExpand: 100,
        maxSize: 10,
        macros: {},
      });
    } catch {
      return null;
    }
  }, [value, display]);
  if (!markup) return <code className="formula-fallback">{value}</code>;
  // Only KaTeX output enters this sink; API text is never interpreted as HTML.
  return <span className={display ? 'math-block' : 'math-inline'} role={display ? 'group' : undefined} aria-label={display ? 'Формула' : undefined} tabIndex={display ? 0 : undefined} dangerouslySetInnerHTML={{ __html: markup }} />;
}

export function RichText({ text }: { text: string }) {
  const parts = text.split(/(\$\$[\s\S]+?\$\$|\$[^$\n]+?\$|\\\([\s\S]+?\\\)|\\\[[\s\S]+?\\\])/g);
  return <>{parts.map((part, index) => {
    if (part.startsWith('$$') && part.endsWith('$$')) return <MathFormula key={index} value={part.slice(2, -2)} />;
    if (part.startsWith('$') && part.endsWith('$')) return <MathFormula key={index} value={part.slice(1, -1)} display={false} />;
    if (part.startsWith('\\(') && part.endsWith('\\)')) return <MathFormula key={index} value={part.slice(2, -2)} display={false} />;
    if (part.startsWith('\\[') && part.endsWith('\\]')) return <MathFormula key={index} value={part.slice(2, -2)} />;
    return <span key={index}>{part}</span>;
  })}</>;
}
