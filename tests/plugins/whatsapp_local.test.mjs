import test from "node:test";
import assert from "node:assert/strict";
import { compatibility, verifyOpenChat, finishVerification, readVerifiedChat, composeClaimedText, sendClaimedText } from "../../plugins/studio-archive/scripts/whatsapp_local.mjs";

const phone = "+41795550101";
const body = "Synthetic test";
function state(draft = "", alias = "Nickname") {
  return `1 window Description: WhatsApp
  2 text Description: Search, ID: TokenizedSearchBar_TextView
  3 button Description: ${alias}, ID: NavigationBar_HeaderViewButton
  4 container Description: Messages in chat with You, ID: ChatMessagesTableView
    5 text Description: selected synthetic message
  6 text Description: unrelated sidebar
  7 text entry area Description: Compose message${draft ? `, Value: ${draft}` : ""}, ID: ChatBar_ComposerTextView
${draft ? "  8 button Description: Send, ID: ChatBar_SendButton\n" : ""}The focused UI element is 7 text entry area Description: Compose message`;
}
function card(number) {
  return `${state().split("The focused UI element is")[0]}
  9 sheet
    10 button Description: close, ID: ContactInfo_CloseButton
    11 heading Description: \u200e\u2068Nickname\u2069 (You)
    12 text Description: ${number}`;
}
function appFixture(number = phone, initial = state()) {
  let value = initial;
  const clicks = [];
  return { clicks, set: v => { value = v; }, getAXState: async () => value,
    getScreenshot: async () => new Uint8Array(), pressKey: async () => {},
    typeText: async text => { value = state(text); },
    click: async index => { clicks.push(index); if (index === 3) value = card(number); if (index === 10) value = state(); if (index === 8) value = state(); },
  };
}
const verification = { status: "verified", phone, alias: "Nickname", tableDescription: "Messages in chat with You" };
const claim = () => ({ execute: true, operation: { id: crypto.randomUUID(), status: "submitting", phone, body, attachments: [] } });

test("current Mac contact sheet verifies a saved self alias by exact phone", async () => {
  const app = appFixture();
  assert.deepEqual(await verifyOpenChat({app, confirmedPhone:phone}), verification);
  const evidence = await readVerifiedChat({app, verification});
  assert.match(evidence, /selected synthetic message/);
  assert.doesNotMatch(evidence, /unrelated sidebar/);
});
test("a phone in message content cannot verify the wrong contact card", async () => {
  const app = appFixture("+41795550102");
  assert.equal((await verifyOpenChat({app, confirmedPhone:phone})).status, "blocked");
  assert.deepEqual(app.clicks, [3, 10]);
});
test("preserves existing user composer drafts without a click", async () => {
  const app = appFixture(phone, state("Existing user draft"));
  await assert.rejects(composeClaimedText({app, verification, claim:claim()}), /existing draft/);
  assert.deepEqual(app.clicks, []);
});
test("multiline messages retain their exact text and multiline drafts remain protected", async () => {
  const app = appFixture(); const dispatch=claim();
  dispatch.operation.body="Synthetic first line\n\nSecond line";
  assert.equal((await composeClaimedText({app,verification,claim:dispatch})).status,"composed");
  await assert.rejects(composeClaimedText({app,verification,claim:claim()}), /existing draft/);
  assert.equal((await sendClaimedText({app,verification,claim:dispatch})).composerEmpty,true);
});
test("changed chat cannot receive a prepared message", async () => {
  const app = appFixture(phone, state("", "Someone else"));
  await assert.rejects(composeClaimedText({app, verification, claim:claim()}), /Chat changed/);
  assert.deepEqual(app.clicks, []);
});
test("one claimed text can be composed and submitted only once", async () => {
  const app = appFixture(); const dispatch = claim();
  assert.equal((await composeClaimedText({app, verification, claim:dispatch})).status, "composed");
  assert.equal((await sendClaimedText({app, verification, claim:dispatch})).composerEmpty, true);
  await assert.rejects(sendClaimedText({app, verification, claim:dispatch}), /inspect persisted/);
  assert.deepEqual(app.clicks, [7,8]);
});
test("Windows screenshot-only host is a candidate, not a claimed live pass", async () => {
  const app = appFixture(phone, "Window: WhatsApp");
  const result = await compatibility({cua:{computer:{target:"windows"}}, app});
  assert.equal(result.status, "visual_check_required");
  assert.equal(result.liveVerified, false);
  assert.deepEqual(app.clicks, []);
});
test("new OS/app versions have no execution allowlist", async () => {
  assert.equal((await compatibility({cua:{computer:{target:"mac"}, version:"future"}, app:appFixture()})).status, "indexed_controls_available");
});

test("empty window after sheet closure requires a separate verified continuation", async () => {
  const app = appFixture();
  const click = app.click;
  app.click = async index => { await click(index); if (index === 10) app.set("0 standard window WhatsApp\n  1 container"); };
  const pending = await verifyOpenChat({app, confirmedPhone:phone});
  assert.equal(pending.status, "phone_verified_pending_chat");
  await assert.rejects(readVerifiedChat({app,verification:pending}), /changed/);
  app.set(state());
  assert.equal((await finishVerification({app,verification:pending})).status,"verified");
});
