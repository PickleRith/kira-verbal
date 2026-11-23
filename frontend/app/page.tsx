import { LessonPicker } from "@/components/LessonPicker";

export default function Home() {
  return (
    <main className="mx-auto max-w-2xl px-4 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">Kira Verbal</h1>
      <p className="mt-4 text-lg leading-relaxed">
        A short oral assessment that asks adaptive, rubric-grounded questions
        and gives teachers transcript-backed evidence to review.
      </p>

      <h2 className="mt-10 text-lg font-semibold">Try a text assessment</h2>
      <LessonPicker />

      <p className="mt-12 rounded-md border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
        Independent portfolio prototype. Not affiliated with Kira Learning.
        Synthetic learners and data only; no real student records.
      </p>
    </main>
  );
}
