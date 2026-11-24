# Two-minute demo script

Setup before recording: API, frontend and (for voice) the worker running; `EVALUATOR_PROVIDER=llm`.
Use headphones. Have the teacher dashboard open in one tab.

| Time | Show | Say |
|---|---|---|
| 0:00–0:15 | Home page | "Kira Verbal is an independent prototype of a short oral check-in. A learner explains a topic; the teacher gets their exact words as evidence. Synthetic data only." |
| 0:15–0:30 | Teacher signs up → class code; in a private window a student signs up with the code → picks Photosynthesis | "A teacher shares a class code; a student joins and starts a check-in. It's already on the teacher's board." |
| 0:30–0:55 | Learner tab, by voice: answer question 1 well. For question 2 say **"From the soil, through its roots."** | "Questions are fixed in advance, but the follow-up depends on the answer. That was a common misconception, so it asks an approved follow-up about leaves." |
| 0:55–1:10 | Ask **"What are stomata?"** then answer | "The learner can ask things. It replies, but won't give the answer away, and that turn isn't scored." Finish the session; let the closing line play. |
| 1:10–1:35 | Teacher tab → review board → open the check-in (By question) | "Each suggested level is backed by an exact quote, linked to the transcript. Here is the misconception. 'Light' is unknown, not zero, because there was no evidence." |
| 1:35–1:50 | Change a level → reason required → Approve → Export | "The teacher decides. A change needs a reason, every decision is a new revision in the audit trail, and only an approved result can be exported, once." |
| 1:50–2:00 | Open the downloaded JSON, or the evaluation doc | "On 60 scripted learners the levels were within one of the labels 98% of the time and every scripted misconception was found. That's synthetic data, not classroom validation. A real integration would need Kira's authorized APIs and a privacy review." |

If voice misbehaves during recording, type the same answers: the flow is identical.
