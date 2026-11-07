export function FooterBreadcrumb({ segments }: { segments: string[] }) {
  return (
    <div
      className="footer-breadcrumb pointer-events-none fixed bottom-4 right-6 hidden select-none md:block"
      data-testid="footer-breadcrumb"
    >
      {segments.join(' · ')}
    </div>
  );
}
