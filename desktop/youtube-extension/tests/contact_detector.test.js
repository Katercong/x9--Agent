const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const detector = require("../contact_detector.js");
const utils = require("../youtube_utils.js");

function typesFor(text) {
  return detector.detectContacts(text).map((item) => item.type);
}

function emailsFor(text) {
  return detector.detectContacts(text)
    .filter((item) => item.type === "email")
    .map((item) => item.value);
}

{
  const contacts = detector.detectContacts(
    "Business: hello@example.com IG: @maker.lab WhatsApp +1 (415) 555-0199 wx: maker_2024 linktr.ee/maker"
  );
  assert.deepEqual(
    contacts.map((item) => [item.type, item.value]),
    [
      ["email", "hello@example.com"],
      ["whatsapp", "+14155550199"],
      ["instagram", "@maker.lab"],
      ["wechat", "maker_2024"],
      ["website", "https://linktr.ee/maker"]
    ]
  );
}

{
  const contacts = detector.detectContacts("Thanks @friend, this ordinary mention is not Instagram contact info.");
  assert.equal(contacts.length, 0);
}

{
  const contacts = detector.detectContacts("Watch https://www.youtube.com/watch?v=abc and visit https://example.org/contact.");
  assert.deepEqual(contacts.map((item) => [item.type, item.value]), [["website", "https://example.org/contact"]]);
}

{
  assert.deepEqual(typesFor("example@example.com test@test.com yourname@email.com"), []);
}

{
  const contacts = detector.detectContacts("For brand deals email creator.brand@example.co or visit our about page.");
  assert.deepEqual(contacts.map((item) => [item.type, item.value]), [["email", "creator.brand@example.co"]]);
}

{
  assert.deepEqual(emailsFor("Business: collab@example.com"), ["collab@example.com"]);
  assert.deepEqual(emailsFor("Business: collab [at] example [dot] com"), ["collab@example.com"]);
  assert.deepEqual(emailsFor("Business: collab(at)example(dot)com"), ["collab@example.com"]);
  assert.deepEqual(emailsFor("Business: CoLLab  [ AT ]  Example [ DOT ] CoM"), ["collab@example.com"]);
}

{
  assert.deepEqual(emailsFor("Ignore example [at] example [dot] com and test(at)test(dot)com."), []);
}

{
  assert.deepEqual(typesFor("Follow @NoPriorsPodcast and @andrej for more context."), []);
}

{
  assert.equal(utils.extractVideoId("https://www.youtube.com/watch?v=kwSVtQ7dziU&t=30s"), "kwSVtQ7dziU");
  assert.equal(utils.normalizeVideoUrl("https://www.youtube.com/watch?v=kwSVtQ7dziU&t=30s"), "https://www.youtube.com/watch?v=kwSVtQ7dziU");
  assert.equal(utils.normalizeVideoUrl("https://www.youtube.com/shorts/WBBLt94himk?feature=share"), "https://www.youtube.com/shorts/WBBLt94himk");
  assert.equal(utils.detectContentType("https://www.youtube.com/watch?v=kwSVtQ7dziU&t=30s"), "video");
  assert.equal(utils.detectContentType("https://www.youtube.com/shorts/WBBLt94himk?feature=share"), "shorts");
  assert.equal(utils.normalizeChannelUrl("https://www.youtube.com/@NoPriorsPodcast/videos"), "https://www.youtube.com/@NoPriorsPodcast");
  assert.equal(utils.channelHomeUrl("https://www.youtube.com/@NoPriorsPodcast/about"), "https://www.youtube.com/@NoPriorsPodcast");
  assert.equal(utils.channelAboutUrl("https://www.youtube.com/@NoPriorsPodcast/videos"), "https://www.youtube.com/@NoPriorsPodcast/about");
  assert.equal(utils.channelVideosUrl("https://www.youtube.com/@NoPriorsPodcast/about"), "https://www.youtube.com/@NoPriorsPodcast/videos");
}

{
  const manifestPath = path.join(__dirname, "..", "manifest.json");
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  assert.equal(manifest.manifest_version, 3);
  assert.equal(manifest.background.service_worker, "youtube_runner.js");
  assert.ok(manifest.permissions.includes("sidePanel"));
  assert.ok(manifest.content_scripts[0].js.includes("contact_detector.js"));
  assert.ok(manifest.content_scripts[0].js.includes("youtube_utils.js"));
  assert.ok(manifest.content_scripts[0].js.includes("youtube_content.js"));
}

console.log("youtube-extension tests passed");
