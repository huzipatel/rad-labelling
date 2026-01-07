interface RAGStatusProps {
  status: 'green' | 'amber' | 'red'
  label?: string
}

export default function RAGStatus({ status, label }: RAGStatusProps) {
  return (
    <span className="govuk-body">
      <span className={`rag-status rag-status--${status}`} />
      {label && <span>{label}</span>}
    </span>
  )
}

