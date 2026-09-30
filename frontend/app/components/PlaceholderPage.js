export default function PlaceholderPage({ eyebrow, title, description }) {
  return (
    <div className="mx-auto w-full max-w-[1280px] flex-1 p-6">
      <div className="feature-card max-w-2xl">
        <span className="badge-pill mb-3 inline-block">{eyebrow}</span>
        <h1 className="text-heading-2 text-ink mb-2">{title}</h1>
        <p className="text-body-md text-ink-muted mb-4">{description}</p>
        <p className="text-caption text-ink-faint">TODO: 담당자 구현</p>
      </div>
    </div>
  );
}
