import { Link } from "react-router";
import { Card, PageHeader } from "../components/ui";

export function NotFoundPage() {
  return (
    <div className="mx-auto max-w-[1180px]">
      <PageHeader title="Page not found" />
      <Card className="p-6">
        <p className="text-[15px] text-ink-300">There’s nothing at this address.</p>
        <Link to="/" className="mt-4 inline-flex h-9 items-center rounded-lg bg-lime px-4 text-[15px] font-semibold text-ink-950 hover:bg-[#c6ff3d]">
          Open Workspace
        </Link>
      </Card>
    </div>
  );
}
