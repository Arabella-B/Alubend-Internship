"use strict";

const $ = (id) => document.getElementById(id);
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
    const res = await fetch(`/api/headlines${refresh ? "?refresh=1" : ""}`);
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

  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
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

function renderBriefing(c) {
  currentBriefingTitle = c.story_title;
  $("b-title").textContent = c.story_title;
  $("b-current").textContent = c.current_situation;
  $("b-why").textContent = c.why_it_matters;

  $("b-background").replaceChildren(
    ...c.background.split(/\n\s*\n/).filter((p) => p.trim()).map((p) => el("p", {}, p.trim()))
  );

  $("b-timeline").replaceChildren(
    ...c.timeline.map((t) => el("li", {}, el("span", { class: "date" }, t.date), t.event))
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
