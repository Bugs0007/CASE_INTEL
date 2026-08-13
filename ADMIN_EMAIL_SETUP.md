# Setting up invoice emails (one-time, ~5 minutes)

This lets Case Intel actually email invoices to your clients' billing
contacts, instead of just recording that it *would have* sent one. You only
need to do this once. Nothing here needs to be repeated for new advocates
using the app — it's a single setting for the whole server.

## What you're setting up

Case Intel sends invoice emails through a service called **Resend**. You
don't need to configure your own email inbox, an app password, or anything
technical about email servers — you just need one secret code ("API key")
from Resend, which you paste into one place.

## Steps

1. **Sign up.** Go to [resend.com](https://resend.com) and create a free
   account (a work or personal email is fine). The free plan covers 3,000
   emails a month, 100 a day — far more than a solo practice needs.

2. **Get your API key.** Once logged in, go to **API Keys** in the left
   sidebar, click **Create API Key**, give it any name (e.g. "Case Intel"),
   and leave the permission as "Full access". Click **Add**, then **copy
   the key it shows you** — it starts with `re_`. You won't be able to see
   it again after you close that screen, so copy it somewhere safe now.

3. **Give the key to whoever manages the server** (or paste it yourself if
   that's you). It goes into the server's `.env` file as one line:

   ```
   RESEND_API_KEY=re_the_key_you_copied
   ```

4. **Restart the app** so it picks up the new setting. (If you don't know
   how to do this, ask whoever manages the server — it's a standard
   restart, nothing email-specific.)

That's it. From then on, clicking "Send" on an invoice actually emails it.

## About the "From" address

By default, Resend will only let you send test emails to the address you
signed up with, using a shared address (`onboarding@resend.dev`) as the
sender. That's fine for confirming everything works, but to send real
invoices to your clients from your own address (e.g.
`billing@yourfirm.com`), you need one more step:

1. In the Resend dashboard, go to **Domains** and click **Add Domain**.
2. Enter the domain you want to send from (e.g. `yourfirm.com`).
3. Resend gives you 2–3 DNS records to add. If you or your web host manage
   that domain's DNS, add those records there (this is the same kind of
   thing as setting up a website or business email — if that phrase means
   nothing to you, your web/domain provider's support team can usually add
   these for you in a couple of minutes).
4. Wait for Resend to show the domain as "Verified" (usually a few minutes
   to an hour).
5. Set `DEFAULT_FROM_EMAIL` in the same `.env` file to an address on that
   domain, e.g.:

   ```
   DEFAULT_FROM_EMAIL=billing@yourfirm.com
   ```

If you skip this step, invoice sending will fail for any client whose
email isn't your own Resend account email — the app will tell you clearly
if that happens, it won't fail silently.

## How to tell it's working

- **Not set up yet:** clicking "Send" on an invoice still succeeds, but the
  app tells you it only *logged* the send (nothing was actually emailed).
  This is the safe default — the app never pretends to send an email it
  didn't.
- **Set up correctly:** clicking "Send" actually delivers the email, and
  the invoice shows as "sent", not "logged".

## If something goes wrong

- **"Invoice not sent" / an error mentioning Resend:** double-check the API
  key was pasted correctly (no extra spaces) and that the app was restarted
  after adding it.
- **Emails aren't arriving:** check the Resend dashboard's **Logs** page —
  it shows every send attempt and why it failed, most commonly an
  unverified sending domain (see above).
- Any other issue: the Resend dashboard's logs are the first place to look;
  they show far more detail than the app itself needs to surface to you.
