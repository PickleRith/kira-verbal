// Landing page. The student (Day 2) and teacher (Day 5) experiences are not
// built yet; this page only states what the prototype is and is not.
export default function Home() {
  return (
    <main className="mx-auto max-w-2xl px-4 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">Kira Verbal</h1>
      <p className="mt-4 text-lg leading-relaxed">
        A short oral assessment that asks adaptive, rubric-grounded questions
        and gives teachers transcript-backed evidence to review.
      </p>

      <ul className="mt-8 space-y-2 text-sm">
        <li>Student assessment: not built yet (Day 2)</li>
        <li>Teacher review: not built yet (Day 5)</li>
      </ul>

      <p className="mt-12 rounded-md border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
        Independent portfolio prototype. Not affiliated with Kira Learning.
        Synthetic learners and data only; no real student records.
      </p>
    </main>
  );
}
