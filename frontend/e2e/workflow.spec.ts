import { readFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

// The whole product in one path, with real accounts: a teacher signs up and gets a class
// code; a student signs up with the code (in a separate browser context) and takes a
// check-in, including a side question and the roots misconception; the check-in appears on
// the teacher's board; the teacher reads it answer by answer, revises a level with a
// reason, approves and exports. Fake providers, so it is deterministic and free.

const PASSWORD = "e2e-password-123";

async function answer(page: Page, text: string) {
  await page.locator("#answer").fill(text);
  await page.getByRole("button", { name: "Send" }).click();
}

async function signUp(page: Page, role: "teacher" | "student", name: string, email: string, extra?: string) {
  await page.goto(`/register?role=${role}`);
  await page.getByLabel("Display name").fill(name);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  if (extra && role === "student") await page.getByLabel(/Class code/).fill(extra);
  if (extra && role === "teacher") await page.getByLabel(/Class name/).fill(extra);
  await page.getByRole("button", { name: `Create ${role} account` }).click();
}

test("student check-in reaches the teacher, who reviews and exports", async ({ page, browser }) => {
  const run = Date.now();

  // --- teacher: sign up, get the class code --------------------------------------
  await signUp(page, "teacher", "Ms Rivera", `rivera-${run}@example.test`, "Period 3");
  await expect(page).toHaveURL(/\/teacher$/);
  const code = (await page.getByTestId("class-code").textContent())?.trim() ?? "";
  expect(code).toMatch(/^[A-Z0-9]{6}$/);

  // --- student: separate browser context, sign up with the code, take the lesson --
  const studentContext = await browser.newContext();
  const learner = await studentContext.newPage();
  await signUp(learner, "student", "Sam E2E", `sam-${run}@example.test`, code);
  await expect(learner).toHaveURL(/\/student$/);
  await expect(learner.getByText(/You.re in/)).toContainText("Period 3");
  // A student can't open the teacher pages.
  await learner.goto("/teacher");
  await expect(learner).toHaveURL(/\/student$/);

  await learner.getByRole("button", { name: "Start Photosynthesis" }).click();
  await expect(learner).toHaveURL(/\/student\/[0-9a-f-]{36}$/);
  await learner.getByRole("button", { name: /Begin/ }).click();
  const current = learner.getByRole("heading", { level: 2 });
  await expect(current).toHaveText("Explain photosynthesis in your own words.");

  // Voice states come from real events. This server has no LiveKit configured, so starting
  // voice gets a real 503 voice_unavailable: the panel shows the error state with a retry,
  // and the text form keeps working (checked by the answers below).
  const voiceState = learner.getByTestId("voice-state");
  await expect(voiceState).toHaveAttribute("data-state", "idle");
  await learner.getByRole("button", { name: "Start answering by voice" }).click();
  await expect(voiceState).toHaveAttribute("data-state", "error");
  await expect(learner.getByText(/Voice isn.t available on this server/)).toBeVisible();
  await expect(learner.getByRole("button", { name: "Retry voice" })).toBeVisible();
  await learner.getByRole("button", { name: "Retry voice" }).click(); // retries for real, fails the same way
  await expect(voiceState).toHaveAttribute("data-state", "error");

  // It shows on the teacher's board while the student is still answering.
  await expect(page.getByRole("region", { name: "In progress" }).getByRole("link", { name: /Sam E2E/ })).toBeVisible({
    timeout: 15_000,
  });

  // A question back is answered, re-asks the same question, and gives nothing away.
  await answer(learner, "What are stomata?");
  await expect(learner.getByText(/hear your own thinking/)).toBeVisible();
  await expect(current).toHaveText("Explain photosynthesis in your own words.");

  await answer(learner, "Plants use sunlight to make sugar from carbon dioxide and water.");
  await expect(current).toHaveText("Where does a plant get carbon dioxide?");

  // The misconception triggers the approved diagnostic follow-up.
  await answer(learner, "From the soil through its roots.");
  await expect(current).toHaveText("How do leaves exchange gases with the air?");

  await answer(learner, "Through tiny holes called stomata on the leaves.");
  await expect(current).toHaveText("What role does sunlight play for a plant?");

  await answer(learner, "Light gives the plant the energy it needs to make sugar.");
  await expect(learner.getByRole("heading", { name: /Check-in finished/ })).toBeVisible();
  await expect(learner.getByText(/Your teacher will review your answers/)).toBeVisible();
  // Nothing the evaluator concluded is shown to the student.
  await expect(learner.getByText(/misconception|level \d|Suggested/i)).toHaveCount(0);
  await learner.getByRole("link", { name: /Back to my check-ins/ }).click();
  await expect(learner.getByText("Waiting for your teacher")).toBeVisible();

  // --- teacher: the board moves it to Needs review --------------------------------
  const card = page.getByRole("region", { name: "Needs review" }).getByRole("link", { name: /Sam E2E/ });
  await expect(card).toBeVisible({ timeout: 15_000 });
  await expect(card.getByTestId("board-score")).toContainText(/\d+%/); // suggested score on the board
  await card.click();

  // By question: every answer, with what it shows.
  await expect(page.getByRole("heading", { name: /Sam E2E on Photosynthesis/ })).toBeVisible();
  await expect(page.getByText("From the soil through its roots.").first()).toBeVisible();
  await expect(page.getByText("Asked about the topic").first()).toBeVisible(); // the side question
  await expect(page.getByText("Misconception", { exact: true }).first()).toBeVisible();

  // Rubric view: the misconception, and a level change that needs a reason.
  await page.getByRole("tab", { name: /Rubric/ }).click();
  await expect(page.getByText("Believes carbon dioxide is absorbed by roots from the soil.")).toBeVisible();
  const co2 = page.getByRole("radiogroup", { name: "Level for Carbon dioxide", exact: true });
  const grade = page.getByRole("complementary").getByTestId("score-summary");
  const before = await grade.textContent();
  await co2.getByRole("radio", { name: "3", exact: true }).click();
  await expect(grade).not.toHaveText(before ?? ""); // the grade moves with the level
  const approve = page.getByRole("button", { name: "Approve edits" });
  await expect(approve).toBeDisabled();
  await page.getByLabel(/Reason/).fill("Corrected themselves in the follow-up answer.");
  await approve.click();
  await expect(page.getByText(/Approved as revision 2/)).toBeVisible();
  const approvedPercent = (await grade.textContent())?.match(/(\d+)%/)?.[1];
  expect(approvedPercent).toBeTruthy();

  // --- teacher: export ------------------------------------------------------------
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export to mock Kira" }).click();
  const file = await (await download).path();
  const payload = JSON.parse(readFileSync(file, "utf8"));
  expect(payload.schema_version).toBe("kira-verbal.mastery-update.v1");
  expect(payload.idempotency_key).toMatch(/:rev2$/);
  expect(JSON.stringify(payload)).not.toContain("Sam E2E"); // no names or emails leave
  expect(JSON.stringify(payload)).not.toContain("example.test");
  const exported = payload.objectives.find((o: { criterion_id: string }) => o.criterion_id === "carbon_dioxide");
  expect(exported.level).toBe(3);
  expect(exported.teacher_changed_level).toBe(true);
  expect(exported.misconceptions).toEqual(["co2_from_roots"]);
  await expect(page.getByRole("button", { name: "Download export again" })).toBeVisible();

  // The student now sees the approved grade and what each level means; no evidence or quotes.
  await learner.reload();
  await learner.getByRole("button", { name: "See results" }).click();
  const result = learner.getByTestId("score-summary");
  await expect(result).toContainText(`${approvedPercent}%`);
  await expect(result).toContainText("Graded by your teacher");
  await expect(learner.getByText("Carbon dioxide", { exact: true })).toBeVisible();
  await expect(learner.getByText(/Misconception|Suggested/)).toHaveCount(0);
  await studentContext.close();
});

test("signed-out visitors are sent to log in, and bad passwords are refused", async ({ page }) => {
  await page.goto("/teacher");
  await expect(page).toHaveURL(/\/login\?next=%2Fteacher/);
  await page.getByLabel("Email").fill("nobody@example.test");
  await page.getByLabel("Password").fill("wrong-password");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByText(/don.t match an account/)).toBeVisible();
});

test("a check-in can't be opened by someone who didn't start it", async ({ page }) => {
  await page.goto("/student/00000000-0000-4000-8000-000000000000");
  await expect(page.getByText(/isn.t available here/)).toBeVisible();
});
