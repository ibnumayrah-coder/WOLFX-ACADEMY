// ===== API client: the page gets its content from the backend =====
const API = (window.WOLFX_API_BASE || "").replace(/\/$/, "");

async function api(path) {
    const res = await fetch(API + path);
    if (!res.ok) throw new Error("HTTP " + res.status);
    return res.json();
}

// tiny DOM helper (uses textContent, so admin-entered text can never inject HTML)
function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    Object.entries(props).forEach(([k, v]) => {
        if (k === "class") node.className = v;
        else if (k === "text") node.textContent = v;
        else node.setAttribute(k, v);
    });
    children.flat().forEach((c) => c && node.appendChild(c));
    return node;
}

function showError(container, message, retry) {
    container.replaceChildren(
        el("p", { class: "api-state", text: message + " " }, el("button", { type: "button", class: "api-retry", text: "Retry" }))
    );
    container.querySelector("button").addEventListener("click", retry);
}

function renderPrograms(list) {
    const grid = document.getElementById("program-grid");
    grid.replaceChildren(...list.map((p, i) =>
        el("article", { class: "program-card" + (p.featured ? " featured" : "") },
            p.featured ? el("div", { class: "program-badge", text: "POPULAR" }) : null,
            el("div", { class: "program-number", text: String(i + 1).padStart(2, "0") }),
            el("h3", { text: p.title }),
            el("p", { text: p.description }),
            el("ul", {}, p.topics.map((t) => el("li", { text: t }))),
            el("a", { href: p.coming_soon ? "#contact" : "#register", text: p.coming_soon ? "Coming Soon →" : "Learn More →" })
        )
    ));
    const select = document.querySelector("#register-form select[name=program]");
    if (select) {
        select.querySelectorAll("option:not([value=''])").forEach((o) => o.remove());
        list.forEach((p) => select.appendChild(el("option", { text: p.title })));
    }
}

function renderMentors(list) {
    const grid = document.getElementById("mentor-grid");
    grid.replaceChildren(...list.map((m) =>
        el("article", { class: "mentor-card" },
            el("div", { class: "mentor-avatar", text: (m.name.charAt(0) || "W").toUpperCase() }),
            el("h3", { text: m.name }),
            el("p", { text: m.role })
        )
    ));
}

function renderVideos(list) {
    const section = document.getElementById("videos");
    if (!list.length) { section.hidden = true; return; }
    document.getElementById("video-grid").replaceChildren(...list.map((v) =>
        el("article", { class: "video-card" },
            el("video", { src: API + v.url, controls: "", preload: "metadata", playsinline: "" }),
            el("h3", { text: v.title }),
            v.description ? el("p", { text: v.description }) : null
        )
    ));
    section.hidden = false;
}

function loadSection(containerId, path, render, label) {
    const container = document.getElementById(containerId);
    const run = () => api(path).then(render).catch(() => showError(container, "Couldn't load " + label + ".", run));
    run();
}

loadSection("program-grid", "/api/programs", renderPrograms, "programs");
loadSection("mentor-grid", "/api/mentors", renderMentors, "mentors");
api("/api/videos").then(renderVideos).catch(() => {});

// Mobile menu
const menuButton = document.querySelector(".menu-btn");
const nav = document.querySelector(".nav-links");

menuButton.addEventListener("click", () => {
    nav.classList.toggle("mobile-open");
});

// Close mobile menu after clicking a link
document.querySelectorAll(".nav-links a").forEach(link => {
    link.addEventListener("click", () => {
        nav.classList.remove("mobile-open");
    });
});

// Registration form -> backend
const form = document.getElementById("register-form");
const statusEl = document.getElementById("form-status");

form.addEventListener("submit", async (e) => {
    e.preventDefault();
    statusEl.className = "form-status";
    statusEl.textContent = "Sending...";
    const btn = form.querySelector("button");
    btn.disabled = true;
    try {
        const res = await fetch(API + "/api/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(Object.fromEntries(new FormData(form)))
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Something went wrong");
        form.reset();
        statusEl.className = "form-status ok";
        statusEl.textContent = "Thank you! We'll contact you soon.";
    } catch (err) {
        statusEl.className = "form-status err";
        statusEl.textContent = err.message;
    } finally {
        btn.disabled = false;
    }
});

// Founders: image fades out, text fades in while scrolling
(function () {
    const founders = Array.from(document.querySelectorAll(".founder"));
    if (!founders.length) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const clamp = (v) => Math.min(1, Math.max(0, v));
    const smooth = (t) => t * t * (3 - 2 * t);
    let ticking = false;

    function update() {
        const vh = window.innerHeight;
        founders.forEach((f) => {
            const r = f.getBoundingClientRect();
            if (r.bottom < -vh || r.top > vh * 2) return;
            const s = -r.top; // how far we've scrolled into this founder
            const img = smooth(clamp((s - vh * 0.1) / (vh * 0.65)));
            const txt = smooth(clamp((s - vh * 0.12) / (vh * 0.5)));
            f.style.setProperty("--img-o", (1 - 0.88 * img).toFixed(3));
            f.style.setProperty("--img-s", (1 + 0.06 * img).toFixed(3));
            f.style.setProperty("--cap-o", (1 - clamp((s - vh * 0.02) / (vh * 0.28))).toFixed(3));
            f.style.setProperty("--hint-o", (1 - clamp(s / (vh * 0.15))).toFixed(3));
            f.style.setProperty("--txt-o", txt.toFixed(3));
            f.style.setProperty("--txt-y", ((1 - txt) * 40).toFixed(1) + "px");
        });
    }

    window.addEventListener("scroll", () => {
        if (!ticking) {
            ticking = true;
            requestAnimationFrame(() => { update(); ticking = false; });
        }
    }, { passive: true });
    window.addEventListener("resize", update);
    update();
})();

// Copy payment number
(function () {
    const btn = document.getElementById("copy-number");
    if (!btn) return;
    const num = document.getElementById("pay-number").textContent.trim();
    const status = document.getElementById("copy-status");
    btn.addEventListener("click", async () => {
        try {
            await navigator.clipboard.writeText(num);
        } catch (e) {
            const t = document.createElement("textarea");
            t.value = num; document.body.appendChild(t); t.select();
            document.execCommand("copy"); t.remove();
        }
        status.textContent = "Copied!";
        setTimeout(() => (status.textContent = ""), 2000);
    });
})();
