import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Privacy · Case Intel",
  description: "What Case Intel stores, why, and which other services handle your data.",
};

const CONTACT = "samallabhagath@gmail.com";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="font-serif text-xl text-gray-900">{title}</h2>
      <div className="mt-2 space-y-3 text-sm leading-relaxed text-gray-600">{children}</div>
    </section>
  );
}

function List({ children }: { children: React.ReactNode }) {
  return <ul className="list-disc space-y-1.5 pl-5">{children}</ul>;
}

/** Plain-language privacy notice. Every statement here is read off the code
 * (models, settings, services); retention periods and certifications are
 * deliberately absent because the code doesn't define any. */
export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-page px-5 py-12">
      <div className="mx-auto w-full max-w-[720px]">
        <Link href="/" className="text-[13px] text-gray-400 hover:underline">
          ← Case Intel
        </Link>

        <div className="ci-card mt-4 p-6 sm:p-8">
          <h1 className="font-serif text-[28px] text-gray-900">Privacy</h1>
          <p className="mt-2 text-sm text-gray-500">Last updated 13 October 2026</p>
          <p className="mt-4 text-sm leading-relaxed text-gray-600">
            Case Intel is case-management software for advocates practising before Indian courts, run by
            Bhagath Samalla in Hyderabad. This page says what it stores about you and your work, and which other
            services see it. Questions: <a className="text-accent font-semibold hover:underline" href={`mailto:${CONTACT}`}>{CONTACT}</a>.
          </p>

          <Section title="Your account">
            <List>
              <li>A username, an email address if you give one, and a password. The password is kept only as a hash, never in readable form.</li>
              <li>
                If you sign in with Google: your name and verified email address from Google, and Google&apos;s
                identifier for your account. Case Intel never receives your Google password.
              </li>
              <li>Each account is separate. You see your own cases and documents, and no one else&apos;s.</li>
            </List>
          </Section>

          <Section title="Your case data">
            <p>What you import, upload or enter is stored against your account:</p>
            <List>
              <li>Cases, parties, hearings, tasks and deadlines, and your notes on them.</li>
              <li>Documents and court orders you upload or that Case Intel downloads for a case you track, together with the text extracted from them.</li>
              <li>Case Bot conversations: your questions and the answers.</li>
              <li>Client contacts, appearance fees and invoices, and travel bookings you upload.</li>
              <li>If you choose to connect Gmail (optional, read-only access): the emails and attachments Case Intel fetches from it.</li>
            </List>
          </Section>

          <Section title="Sign-in sessions">
            <p>
              Each time you sign in, Case Intel records a session: the browser and operating system, the IP address
              the request came from, and when the session was created and last used. The IP address is kept for
              security and is not shown anywhere in the app. The session key itself is stored only as a hash.
            </p>
            <p>
              Your browser keeps your session key and username in its local storage so you stay signed in. Case
              Intel does not use advertising or analytics trackers. Google&apos;s sign-in button, when shown, is
              Google&apos;s own and may set its own cookies.
            </p>
          </Section>

          <Section title="Court data">
            <p>
              Case status, orders, advocate search results and cause lists come from the public eCourts portals
              (the District Courts and High Courts services). Case Intel looks things up there for the cases you
              track or search for. It is not affiliated with eCourts or with any court.
            </p>
          </Section>

          <Section title="Who else handles your data">
            <List>
              <li>
                <strong>Amazon Web Services</strong> hosts the Case Intel server and database, and stores uploaded
                files, in the Asia Pacific (Mumbai) region.
              </li>
              <li>
                <strong>Vercel</strong> hosts the website you are looking at.
              </li>
              <li>
                <strong>An AI language-model provider</strong>: when you ask Case Bot a question, generate an order
                summary or a hearing briefing, the question and the relevant text from your documents are sent to
                the language-model service Case Intel is configured with. The code supports Groq, OpenAI, or a
                self-hosted Ollama model.
              </li>
              <li>
                <strong>An embedding provider</strong>: the text of documents you upload is sent to turn it into
                searchable vectors. The code supports Google Gemini, OpenAI, or a self-hosted Ollama model.
              </li>
              <li>
                <strong>Resend</strong> delivers email you choose to send from Case Intel, such as an invoice. It
                receives the recipient, the message and any attachment.
              </li>
              <li>
                <strong>Google</strong> handles the sign-in itself, and Gmail access if you connect it.
              </li>
            </List>
            <p>Which of the AI providers is in use can change as the service changes.</p>
          </Section>

          <Section title="Your choices">
            <p>
              You can sign other devices out from Settings, and disconnect Google there. To ask what is
              held about you, or to have your account and data deleted, write to{" "}
              <a className="text-accent font-semibold hover:underline" href={`mailto:${CONTACT}`}>{CONTACT}</a>.
            </p>
          </Section>

          <Section title="Changes">
            <p>If this page changes, the date at the top changes with it.</p>
          </Section>
        </div>
      </div>
    </div>
  );
}
