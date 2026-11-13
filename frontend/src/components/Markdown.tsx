import ReactMarkdown, { Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'

const components: Components = {
  h1: ({ children }) => <h1 className="text-lg font-bold mt-4 mb-2 first:mt-0">{children}</h1>,
  h2: ({ children }) => <h2 className="text-base font-bold mt-4 mb-2 first:mt-0">{children}</h2>,
  h3: ({ children }) => <h3 className="text-sm font-bold mt-3 mb-1.5 first:mt-0">{children}</h3>,
  h4: ({ children }) => <h4 className="text-sm font-semibold mt-3 mb-1.5 first:mt-0">{children}</h4>,
  p: ({ children }) => <p className="text-sm leading-relaxed mb-2.5 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="list-disc pl-5 mb-2.5 space-y-1 text-sm">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-5 mb-2.5 space-y-1 text-sm">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" className="text-primary underline underline-offset-2 hover:text-primary/80">
      {children}
    </a>
  ),
  strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-border/60 pl-3 my-2.5 text-muted-foreground italic">{children}</blockquote>
  ),
  hr: () => <hr className="border-border/50 my-3" />,
  code: ({ className, children, ...props }) => {
    const isBlock = /language-/.test(className || '')
    if (isBlock) {
      return (
        <code className={`font-mono text-xs ${className || ''}`} {...props}>
          {children}
        </code>
      )
    }
    return (
      <code className="font-mono text-[0.85em] bg-muted/60 border border-border/50 rounded px-1 py-0.5" {...props}>
        {children}
      </code>
    )
  },
  pre: ({ children }) => (
    <pre className="bg-muted/40 border border-border/50 rounded-lg p-3 mb-2.5 overflow-x-auto">{children}</pre>
  ),
  table: ({ children }) => (
    <div className="overflow-x-auto mb-2.5">
      <table className="text-xs border-collapse w-full">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="border-b border-border/60">{children}</thead>,
  th: ({ children }) => <th className="text-left font-semibold px-2.5 py-1.5">{children}</th>,
  td: ({ children }) => <td className="px-2.5 py-1.5 border-t border-border/30">{children}</td>,
}

export function Markdown({ content }: { content: string }) {
  return (
    <div className="text-sm leading-relaxed text-foreground/90 [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  )
}
