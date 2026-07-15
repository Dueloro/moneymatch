/**
 * Bottom-right uppercase, letter-spaced mono breadcrumb (02-design §1).
 * Doubles as a stable QA/e2e locator — hence the data-testid.
 */
export function FooterBreadcrumb({ segments }: { segments: string[] }) {
  return (
    <div
      className="footer-breadcrumb pointer-events-none fixed bottom-4 right-6 select-none"
      data-testid="footer-breadcrumb"
    >
      {segments.join(' · ')}
    </div>
  );
}
