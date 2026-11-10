"use strict";

const $ = (id) => document.getElementById(id);
// The age group this page is for (11-13, 13-17 or 18-plus); it shapes the news and the writing.
const AUDIENCE = document.body.dataset.audience || "18-plus";
let headlines = [];
let busy = false;

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else node.setAttribute(key, value);
  }
  for (const child of children) {
    if (child != null) node.append(child instanceof Node ? child : String(child));
  }
  return node;
}

function timeAgo(timestamp) {
  if (!timestamp) return "";
  const minutes = Math.round((Date.now() / 1000 - timestamp) / 60);
  if (minutes < 60) return `${Math.max(minutes, 1)} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

// ---------- Headlines ----------

async function loadHeadlines(refresh = false) {
  const list = $("headlines");
  list.replaceChildren(el("li", { class: "muted" }, "Loading headlines…"));
  try {
    const res = await fetch(`/api/headlines?audience=${encodeURIComponent(AUDIENCE)}${refresh ? "&refresh=1" : ""}`);
    headlines = await res.json();
  } catch {
    headlines = [];
  }
  const sources = [...new Set(headlines.map((h) => h.source))].sort();
  const select = $("source-filter");
  const current = select.value;
  select.replaceChildren(el("option", { value: "" }, "All sources"), ...sources.map((s) => el("option", { value: s }, s)));
  select.value = sources.includes(current) ? current : "";
  renderHeadlines();
}

function renderHeadlines() {
  const source = $("source-filter").value;
  const query = $("search").value.trim().toLowerCase();
  const shown = headlines.filter(
    (h) => (!source || h.source === source) && (!query || `${h.title} ${h.summary}`.toLowerCase().includes(query))
  );
  const list = $("headlines");
  if (!shown.length) {
    list.replaceChildren(el("li", { class: "muted" }, headlines.length ? "No matching headlines." : "Couldn't load headlines."));
    return;
  }
  list.replaceChildren(
    ...shown.map((h) => {
      const button = el(
        "button",
        { class: "headline", type: "button", title: h.summary || h.title },
        el("span", { class: "meta" }, [h.source, timeAgo(h.timestamp)].filter(Boolean).join(" · ")),
        el("span", { class: "title" }, h.title)
      );
      button.addEventListener("click", () => {
        document.querySelectorAll(".headline.active").forEach((b) => b.classList.remove("active"));
        button.classList.add("active");
        requestContext({ title: h.title, summary: h.summary, url: h.url });
      });
      return el("li", {}, button);
    })
  );
}

// ---------- Context request ----------

// ---------- Timer ----------
// Shows elapsed time, and an estimate based on how long this browser's recent requests took.

let timerInterval = null;

function formatDuration(seconds) {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function recentDurations(kind) {
  try {
    return JSON.parse(localStorage.getItem(`durations:${AUDIENCE}:${kind}`) || "[]");
  } catch {
    return [];
  }
}

function recordDuration(kind, seconds) {
  try {
    const list = [...recentDurations(kind), seconds].slice(-8);
    localStorage.setItem(`durations:${AUDIENCE}:${kind}`, JSON.stringify(list));
  } catch {
    /* storage unavailable: estimates just won't be shown */
  }
}

function typicalDuration(kind) {
  const list = recentDurations(kind);
  if (!list.length) return null;
  const sorted = [...list].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)];
}

function startTimer(kind) {
  const started = Date.now();
  const typical = typicalDuration(kind);
  const tick = () => {
    const elapsed = (Date.now() - started) / 1000;
    $("elapsed").textContent = formatDuration(elapsed);
    let note = "";
    if (typical) {
      note = elapsed < typical
        ? `about ${formatDuration(typical - elapsed)} left (typical: ${formatDuration(typical)})`
        : `taking longer than usual (typical: ${formatDuration(typical)})`;
    } else {
      note = "first run: timing will be learned from it";
    }
    $("estimate").textContent = note;
  };
  tick();
  clearInterval(timerInterval);
  timerInterval = setInterval(tick, 1000);
  return () => {
    clearInterval(timerInterval);
    return (Date.now() - started) / 1000;
  };
}

const VIEWS = ["empty", "loading", "error", "briefing", "guide"];
let currentBriefingTitle = "";

function show(view) {
  for (const id of VIEWS) $(id).hidden = id !== view;
  $("back-to-briefing").hidden = view === "briefing" || !currentBriefingTitle;
}

function setBusy(value) {
  busy = value;
  document
    .querySelectorAll(".headline, #custom-form button, #source-form button, .guide-button")
    .forEach((b) => (b.disabled = value));
}

// Runs a streamed Claude job, showing progress, and passes the result to `onResult`.
async function runJob(endpoint, body, loadingLabel, onResult) {
  if (busy) return;
  setBusy(true);
  $("loading-label").textContent = loadingLabel;
  $("progress").replaceChildren();
  show("loading");
  const stopTimer = startTimer(endpoint);
  let succeeded = false;

  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...body, audience: AUDIENCE }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.error || `Request failed (${res.status})`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let finished = false;
    while (!finished) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let split;
      while ((split = buffer.indexOf("\n\n")) !== -1) {
        const chunk = buffer.slice(0, split);
        buffer = buffer.slice(split + 2);
        if (!chunk.startsWith("data: ")) continue;
        const event = JSON.parse(chunk.slice(6));
        if (event.type === "status") {
          $("progress").append(el("li", {}, event.message));
        } else if (event.type === "result") {
          onResult(event.data);
          finished = true;
          succeeded = true;
        } else if (event.type === "error") {
          throw new Error(event.message);
        }
      }
    }
    if (!finished) throw new Error("The connection closed before the result was ready.");
  } catch (err) {
    $("error").textContent = err.message || String(err);
    show("error");
  } finally {
    const seconds = stopTimer();
    // Cached results come back instantly; only learn from real runs.
    if (succeeded && seconds > 5) recordDuration(endpoint, seconds);
    setBusy(false);
  }
}

function requestContext(story) {
  runJob("/api/context", story, `Researching “${story.title || "your story"}”`, renderBriefing);
}

function requestSourceGuide(source) {
  const label = `Reading “${source.title || source.url || "your source"}”`;
  runJob("/api/source", { ...source, story_title: currentBriefingTitle }, label, renderGuide);
}

// ---------- Rendering ----------

function safeUrl(url) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : null;
  } catch {
    return null;
  }
}

const WIDE_KINDS = new Set(["map", "chart", "document"]);

// A primary-source image with its caption, relevance, critical reading and credit.
function figure(image, size) {
  const src = safeUrl(image.image_url);
  if (!src) return null;
  const page = safeUrl(image.page_url);
  const credit = image.credit || {};
  const creditBits = [credit.creator, credit.date, credit.source].filter(Boolean).join(" · ");
  const licence = credit.licence
    ? safeUrl(credit.licence_url)
      ? el("a", { href: safeUrl(credit.licence_url), target: "_blank", rel: "noopener noreferrer" }, credit.licence)
      : credit.licence
    : null;

  const img = el("img", { src, alt: image.alt || image.caption || "", loading: "lazy", decoding: "async" });
  if (image.width && image.height) {
    img.setAttribute("width", image.width);
    img.setAttribute("height", image.height);
  }
  const node = el(
    "figure",
    { class: `figure figure-${size}` },
    page ? el("a", { href: page, target: "_blank", rel: "noopener noreferrer", class: "figure-img" }, img) : img,
    el(
      "figcaption",
      {},
      el("p", { class: "figure-caption" }, el("span", { class: "kind" }, image.kind), image.caption),
      image.why_relevant ? el("p", { class: "figure-why" }, image.why_relevant) : null,
      image.read_critically
        ? el("p", { class: "figure-critical" }, el("strong", {}, "Reading this image: "), image.read_critically)
        : null,
      el(
        "p",
        { class: "figure-credit" },
        creditBits ? `${creditBits}. ` : "",
        licence,
        licence ? " · " : "",
        page ? el("a", { href: page, target: "_blank", rel: "noopener noreferrer" }, "Wikimedia Commons") : null,
        page ? guideButton({ title: image.caption, url: page }) : null
      )
    )
  );
  img.addEventListener("error", () => node.remove());
  return node;
}

function figuresFor(images, placement, size) {
  return images
    .filter((image) => image.placement === placement)
    .map((image) => figure(image, size))
    .filter(Boolean);
}

function renderBriefing(c) {
  currentBriefingTitle = c.story_title;
  $("b-title").textContent = c.story_title;
  $("b-current").textContent = c.current_situation;
  $("b-why").textContent = c.why_it_matters;

  const images = c.images || [];
  $("b-figures-top").replaceChildren(...figuresFor(images, "top", "wide"));
  $("b-figures-perspectives").replaceChildren(...figuresFor(images, "perspectives", "wide"));
  $("b-figures-contested").replaceChildren(...figuresFor(images, "contested", "wide"));

  // Background images follow the paragraph they illustrate; maps and charts run full width.
  const paragraphs = c.background.split(/\n\s*\n/).filter((p) => p.trim());
  const afterParagraph = (image) => Math.min(Math.max(image.anchor || 1, 1), paragraphs.length);
  const backgroundImages = images.filter((image) => image.placement === "background");
  $("b-background").replaceChildren(
    ...paragraphs.flatMap((p, i) => [
      ...backgroundImages
        .filter((image) => afterParagraph(image) === i + 1 && !WIDE_KINDS.has(image.kind))
        .map((image) => figure(image, "side")),
      el("p", {}, p.trim()),
      ...backgroundImages
        .filter((image) => afterParagraph(image) === i + 1 && WIDE_KINDS.has(image.kind))
        .map((image) => figure(image, "wide")),
    ].filter(Boolean))
  );

  const timelineImages = images.filter((image) => image.placement === "timeline");
  const entryFor = (image) => Math.min(Math.max(image.anchor || 1, 1), c.timeline.length);
  $("b-timeline").replaceChildren(
    ...c.timeline.map((t, i) =>
      el(
        "li",
        {},
        el("span", { class: "date" }, t.date),
        t.event,
        ...timelineImages.filter((image) => entryFor(image) === i + 1).map((image) => figure(image, "inline"))
      )
    )
  );

  $("b-parallels").replaceChildren(
    ...c.historical_parallels.map((p) =>
      el(
        "div",
        { class: "card" },
        el("h4", {}, p.name),
        el("p", { class: "period" }, p.period),
        el("p", {}, el("strong", {}, "Similar: "), p.similarities),
        el("p", {}, el("strong", {}, "Different: "), p.differences)
      )
    )
  );

  $("b-perspectives").replaceChildren(
    ...c.perspectives.flatMap((p) => [
      el("dt", {}, p.group),
      el("dd", {}, p.view),
      p.historical_memory
        ? el("dd", { class: "memory" }, el("strong", {}, "Rooted in: "), p.historical_memory)
        : null,
    ].filter(Boolean))
  );

  const contested = c.contested_accounts || [];
  $("b-contested-wrap").hidden = contested.length === 0;
  $("b-contested").replaceChildren(
    ...contested.map((item) =>
      el(
        "div",
        { class: "card" },
        el("h4", {}, item.event),
        ...item.accounts.map((a) => el("p", {}, el("strong", {}, `${a.held_by}: `), a.account))
      )
    )
  );

  $("b-terms").replaceChildren(
    ...c.key_terms.map((t) => el("div", {}, el("dt", {}, t.term), el("dd", {}, t.explanation)))
  );

  $("b-questions").replaceChildren(...c.open_questions.map((q) => el("li", {}, q)));

  $("b-sources").replaceChildren(
    ...c.sources.map((s) => {
      const href = safeUrl(s.url);
      return el(
        "li",
        {},
        s.kind ? el("span", { class: `kind kind-${s.kind}` }, s.kind) : null,
        href ? el("a", { href, target: "_blank", rel: "noopener noreferrer" }, s.title || href) : s.title,
        href ? guideButton({ title: s.title, url: href }) : null
      );
    })
  );

  show("briefing");
  document.querySelector(".content").scrollIntoView({ behavior: "smooth", block: "start" });
}

function guideButton(source) {
  const button = el("button", { type: "button", class: "guide-button" }, "Reading guide");
  button.addEventListener("click", () => requestSourceGuide(source));
  return button;
}

function section(title, ...content) {
  const items = content.filter((c) => c != null && !(Array.isArray(c) && !c.length));
  if (!items.length) return null;
  return el("section", {}, el("h3", { class: "section" }, title), ...items.flat());
}

function renderGuide(g) {
  const passages = g.key_passages.map((p) =>
    el("li", {}, el("blockquote", {}, `“${p.passage}”`), el("p", {}, p.meaning))
  );
  const terms = g.difficult_terms.map((t) => el("div", {}, el("dt", {}, t.term), el("dd", {}, t.explanation)));
  const views = g.other_viewpoints.flatMap((v) => [el("dt", {}, v.group), el("dd", {}, v.view)]);
  const reading = g.further_reading.map((r) => {
    const href = safeUrl(r.url);
    return el(
      "li",
      {},
      href ? el("a", { href, target: "_blank", rel: "noopener noreferrer" }, r.title || href) : r.title
    );
  });

  $("guide-body").replaceChildren(
    el("p", { class: "kicker" }, `Reading guide · ${g.source_type} source`),
    el("h2", {}, g.title),
    el("p", { class: "byline" }, [g.author, g.date].filter(Boolean).join(" · ")),
    el("div", { class: "lede single" }, el("div", {}, el("h3", {}, "In plain words"), el("p", {}, g.plain_summary))),
    section("Context", el("p", { class: "prose-p" }, g.context)),
    section("Author and purpose", el("p", { class: "prose-p" }, g.author_and_purpose)),
    section("Perspective", el("p", { class: "prose-p" }, g.perspective)),
    section("Key passages", passages.length ? el("ul", { class: "passages" }, ...passages) : null),
    section("Difficult terms", terms.length ? el("dl", { class: "pairs terms" }, ...terms) : null),
    section("How far to trust it", el("p", { class: "prose-p" }, g.reliability)),
    section("Other viewpoints", views.length ? el("dl", { class: "pairs" }, ...views) : null),
    section(
      "Questions to ask",
      g.questions_to_ask.length ? el("ul", { class: "questions" }, ...g.questions_to_ask.map((q) => el("li", {}, q))) : null
    ),
    section("Further reading", reading.length ? el("ul", { class: "sources" }, ...reading) : null),
    el("p", { class: "disclaimer" }, "Generated by Claude. Check important details against the source itself.")
  );
  show("guide");
  document.querySelector(".content").scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---------- Wiring ----------

$("back-to-briefing").addEventListener("click", () => show("briefing"));
$("source-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  const source = { url: form.get("url").trim(), text: form.get("text").trim() };
  if (!source.url && !source.text) {
    $("error").textContent = "Enter a link to the source or paste its text.";
    show("error");
    return;
  }
  requestSourceGuide(source);
});

$("source-filter").addEventListener("change", renderHeadlines);
$("search").addEventListener("input", renderHeadlines);
$("refresh").addEventListener("click", () => loadHeadlines(true));
$("custom-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  const story = {
    title: form.get("title").trim(),
    url: form.get("url").trim(),
    text: form.get("text").trim(),
  };
  if (!story.title && !story.text) {
    $("error").textContent = "Enter a headline or paste the article text.";
    show("error");
    return;
  }
  document.querySelectorAll(".headline.active").forEach((b) => b.classList.remove("active"));
  requestContext(story);
});

loadHeadlines();
