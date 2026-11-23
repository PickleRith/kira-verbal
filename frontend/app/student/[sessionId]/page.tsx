import { StudentSession } from "@/components/StudentSession";

export default async function StudentPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await params;
  return <StudentSession sessionId={sessionId} />;
}
