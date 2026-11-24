import { ReportReview } from "@/components/ReportReview";

export default async function ReviewPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await params;
  return <ReportReview sessionId={sessionId} />;
}
