/**
 * KİŞİSEL BLOG & PORTFOLYO — ÜST DÜZEY ANİMASYON & ETKİLEŞİM MOTORU
 */

document.addEventListener("DOMContentLoaded", async () => {
  initTheme();

  let data = window.BLOG_DATA;
  if (window.location.protocol !== "file:") {
    try {
      const res = await fetch("/api/content", { cache: "no-store" });
      if (res.ok) data = await res.json();
    } catch {
      // Sunucu yoksa js/data.js yedeğini kullan
    }
  }
  if (!data) return;

  hydrateProfile(data);
  renderMarquee(data.institutions || []);
  renderSocialFeed(data.socialPosts || [], "all");
  renderProjects(data.projects || []);
  renderIdeas(data.ideas || []);
  renderEvents(data.events || [], "all");
  renderFooterSocials(data.profile?.socialLinks || []);

  initScrollEffects();
  initNavIndicator();
  initRevealObserver();
  initCounters();
  initMagneticElements();
  initTiltCards();
  initViewportSpotlight();
  initCustomCursor();
  initFilters(data);
  initModals(data);
  initMobileMenu();
  initCopyEmail(data.profile?.email || "");
});

/* ==========================================================================
   THEME TOGGLE
   ========================================================================== */
function initTheme() {
  const root = document.documentElement;
  const saved = localStorage.getItem("blog-theme") || "dark";
  root.setAttribute("data-theme", saved);

  const btn = document.getElementById("themeToggle");
  btn?.addEventListener("click", () => {
    const current = root.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    localStorage.setItem("blog-theme", next);
  });
}

/* ==========================================================================
   PROFILE & HERO STAGE HYDRATION
   ========================================================================== */
function hydrateProfile(data) {
  const profile = data.profile || {};
  setText("navBrandName", profile.brandName);
  setText("heroStatus", profile.status);
  setText("profileName", profile.name);
  setText("profileRole", profile.role);
  setText("profileBio", profile.bio);
  setText("emailText", profile.email);
  setText("footerName", profile.name);
  setText("currentYear", new Date().getFullYear());

  // Hero Stage Card
  setText("heroName", profile.name);
  setText("heroRole", profile.role);
  setText("heroProjCount", (data.projects || []).length);
  setText("heroSocialCount", (data.socialPosts || []).length);
  setText("heroEventCount", (data.events || []).length);

  const latestSocial = (data.socialPosts || [])[0];
  const latestIdea = (data.ideas || [])[0];
  const latestTitle = latestSocial?.title || latestIdea?.title || profile.status;
  setText("heroLatestPost", latestTitle);

  const statProj = document.getElementById("statProjCount");
  if (statProj && data.projects) statProj.dataset.count = String(data.projects.length);
  const statEvent = document.getElementById("statEventCount");
  if (statEvent && data.events) statEvent.dataset.count = String(data.events.length);

  const avatar = document.getElementById("profileAvatar");
  if (avatar && profile.avatar) avatar.src = profile.avatar;
  const heroAvatar = document.getElementById("heroAvatar");
  if (heroAvatar && profile.avatar) heroAvatar.src = profile.avatar;

  const interestsWrap = document.getElementById("profileInterests");
  if (interestsWrap && profile.interests) {
    interestsWrap.innerHTML = profile.interests
      .map((tag) => `<span class="tag-chip">${escapeHtml(tag)}</span>`)
      .join("");
  }

  const nowList = document.getElementById("nowList");
  if (nowList && profile.now) {
    nowList.innerHTML = profile.now
      .map((item) => `<li>${escapeHtml(item)}</li>`)
      .join("");
  }
}

function renderMarquee(items) {
  const track = document.getElementById("marqueeTrack");
  if (!track) return;
  const doubled = [...items, ...items];
  track.innerHTML = doubled
    .map((name) => `<span class="marquee-item">${escapeHtml(name)}</span>`)
    .join("");
}

/* ==========================================================================
   SOCIAL FEED RENDERING
   ========================================================================== */
function renderSocialFeed(posts, filter) {
  const grid = document.getElementById("socialGrid");
  if (!grid) return;

  const filtered = filter === "all" ? posts : posts.filter((p) => p.platform === filter);

  grid.innerHTML = filtered
    .map((post, idx) => {
      const hasImage = Boolean(post.image);
      const isVideo = post.platform === "youtube" && post.youtubeId;
      const cursorHint = isVideo ? "İzle" : "İncele";
      return `
        <article class="social-card platform-${escapeHtml(post.platform)} ${hasImage ? "has-image" : "no-image"}" data-cursor="${cursorHint}" style="animation-delay: ${idx * 0.06}s">
          ${
            hasImage
              ? `
            <div class="social-card-media" ${isVideo ? `data-youtube-id="${escapeHtml(post.youtubeId)}" data-video-title="${escapeHtml(post.title)}" style="cursor:pointer"` : ""}>
              <img src="${escapeHtml(post.image)}" alt="${escapeHtml(post.title)}" loading="lazy" />
              ${
                isVideo
                  ? `<div class="play-overlay"><div class="play-btn-circle">▶</div></div>`
                  : ""
              }
            </div>`
              : ""
          }
          <div class="social-card-body">
            <div class="social-card-top">
              <span class="platform-badge ${escapeHtml(post.platform)}">${escapeHtml(post.platformLabel)}</span>
              <span class="social-date">${escapeHtml(post.date)}</span>
            </div>
            <h3 class="social-title">${escapeHtml(post.title)}</h3>
            <p class="social-excerpt">${escapeHtml(post.excerpt)}</p>
          </div>
          <div class="social-footer">
            <span>${escapeHtml(post.metric)}</span>
            ${
              post.url && post.url !== "#"
                ? `<a href="${escapeHtml(post.url)}" target="_blank" rel="noopener noreferrer" class="social-link">İncele <span>→</span></a>`
                : ""
            }
          </div>
        </article>
      `;
    })
    .join("");
}

/* ==========================================================================
   PROJECTS RENDERING + 3D TILT
   ========================================================================== */
function renderProjects(projects) {
  const grid = document.getElementById("projectsGrid");
  if (!grid) return;

  grid.innerHTML = projects
    .map(
      (proj, idx) => `
      <article class="project-card tilt-card reveal-up" data-tilt="4" data-cursor="Aç" style="--delay: ${idx * 0.08}s">
        <div>
          <div class="project-top">
            <span class="project-year">${escapeHtml(proj.year)}</span>
            <span class="project-status">${escapeHtml(proj.status)}</span>
          </div>
          <h3 class="project-title" style="margin-top: 16px;">${escapeHtml(proj.title)}</h3>
          <p class="project-desc">${escapeHtml(proj.description)}</p>
        </div>
        <div>
          <div class="project-stack" style="margin-bottom: 18px;">
            ${(proj.stack || []).map((tech) => `<span class="tag-chip">${escapeHtml(tech)}</span>`).join("")}
          </div>
          <div class="project-links">
            ${proj.githubUrl && proj.githubUrl !== "#" ? `<a href="${escapeHtml(proj.githubUrl)}" target="_blank" rel="noopener noreferrer">GitHub ↗</a>` : ""}
            ${proj.liveUrl && proj.liveUrl !== "#" ? `<a href="${escapeHtml(proj.liveUrl)}" target="_blank" rel="noopener noreferrer">Canlı Önizleme ↗</a>` : ""}
          </div>
        </div>
      </article>
    `
    )
    .join("");
}

/* ==========================================================================
   IDEAS & BLOG RENDERING
   ========================================================================== */
function renderIdeas(ideas) {
  const list = document.getElementById("ideasList");
  if (!list) return;

  list.innerHTML = ideas
    .map(
      (idea, idx) => `
      <article class="idea-row reveal-up" data-idea-id="${escapeHtml(idea.id)}" data-cursor="Oku" style="--delay: ${idx * 0.06}s">
        <span class="idea-date">${escapeHtml(idea.date)}</span>
        <div class="idea-main">
          <h3>${escapeHtml(idea.title)}</h3>
          <p>${escapeHtml(idea.summary)}</p>
        </div>
        <div class="idea-meta">
          <span class="tag-chip">${escapeHtml(idea.tag)}</span>
          <span>${escapeHtml(idea.readTime)}</span>
          <span class="idea-arrow">→</span>
        </div>
      </article>
    `
    )
    .join("");
}

/* ==========================================================================
   EVENTS & SUMMITS GALLERY
   ========================================================================== */
let currentVisibleEvents = [];

function renderEvents(events, filter) {
  const grid = document.getElementById("eventsGrid");
  if (!grid) return;

  currentVisibleEvents = filter === "all" ? events : events.filter((e) => e.category === filter);

  grid.innerHTML = currentVisibleEvents
    .map((ev, idx) => {
      const hasImage = Boolean(ev.image);
      if (hasImage) {
        return `
          <article class="event-card tilt-card has-image" data-tilt="4" data-cursor="Gör" data-event-index="${idx}" style="animation-delay: ${idx * 0.06}s">
            <img src="${escapeHtml(ev.image)}" alt="${escapeHtml(ev.title)}" loading="lazy" />
            <div class="event-overlay">
              <span class="event-place">${escapeHtml(ev.place)} · ${escapeHtml(ev.categoryLabel)}</span>
              <h3 class="event-title">${escapeHtml(ev.title)}</h3>
              <span class="event-date">${escapeHtml(ev.date)}</span>
            </div>
          </article>
        `;
      }
      return `
        <article class="event-card tilt-card no-image" data-tilt="4" data-cursor="Gör" data-event-index="${idx}" style="animation-delay: ${idx * 0.06}s">
          <div class="event-text-top">
            <span class="event-cat-pill">${escapeHtml(ev.categoryLabel)}</span>
            <span class="social-date">${escapeHtml(ev.date)}</span>
          </div>
          <div class="event-text-body">
            <h3>${escapeHtml(ev.title)}</h3>
            <p>${escapeHtml(ev.description)}</p>
          </div>
          <span class="mono-sub">📍 ${escapeHtml(ev.place)}</span>
        </article>
      `;
    })
    .join("");

  bindTiltToElements(grid.querySelectorAll(".tilt-card"));
}

function renderFooterSocials(links) {
  const wrap = document.getElementById("footerSocials");
  if (!wrap) return;
  wrap.innerHTML = links
    .map(
      (link) => `
      <a href="${escapeHtml(link.url)}" target="_blank" rel="noopener noreferrer" class="social-pill-link magnetic" data-magnetic="0.18">
        ${escapeHtml(link.label)} ↗
      </a>
    `
    )
    .join("");
}

/* ==========================================================================
   FILTERS & PLATFORM JUMP PILLS
   ========================================================================== */
function initFilters(data) {
  const socialBar = document.getElementById("socialFilters");
  socialBar?.addEventListener("click", (e) => {
    const btn = e.target.closest(".filter-btn");
    if (!btn) return;
    socialBar.querySelectorAll(".filter-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    renderSocialFeed(data.socialPosts || [], btn.dataset.filter);
  });

  document.querySelectorAll("[data-jump-platform]").forEach((pill) => {
    pill.addEventListener("click", () => {
      const platform = pill.dataset.jumpPlatform;
      const targetBtn = socialBar?.querySelector(`[data-filter="${platform}"]`);
      if (targetBtn) {
        socialBar.querySelectorAll(".filter-btn").forEach((b) => b.classList.remove("active"));
        targetBtn.classList.add("active");
        renderSocialFeed(data.socialPosts || [], platform);
      }
    });
  });

  const eventBar = document.getElementById("eventFilters");
  eventBar?.addEventListener("click", (e) => {
    const btn = e.target.closest(".filter-btn");
    if (!btn) return;
    eventBar.querySelectorAll(".filter-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    renderEvents(data.events || [], btn.dataset.eventFilter);
  });
}

/* ==========================================================================
   MODALS: ARTICLE READER (+ PROGRESS), PHOTO LIGHTBOX (+ CROSSFADE), VIDEO
   ========================================================================== */
function initModals(data) {
  const articleModal = document.getElementById("articleModal");
  const articlePanel = document.getElementById("articlePanel");
  const readingBar = document.getElementById("modalReadingBar");
  const lightboxModal = document.getElementById("lightboxModal");
  const videoModal = document.getElementById("videoModal");
  let lightboxIndex = 0;

  articlePanel?.addEventListener("scroll", () => {
    if (!readingBar) return;
    const max = articlePanel.scrollHeight - articlePanel.clientHeight;
    const pct = max > 0 ? (articlePanel.scrollTop / max) * 100 : 0;
    readingBar.style.width = `${pct}%`;
  });

  // Open Article
  document.getElementById("ideasList")?.addEventListener("click", (e) => {
    const row = e.target.closest(".idea-row");
    if (!row) return;
    const idea = (data.ideas || []).find((i) => i.id === row.dataset.ideaId);
    if (!idea) return;

    setText("modalArticleMeta", `${idea.date} · ${idea.tag} · ${idea.readTime}`);
    setText("modalArticleTitle", idea.title);
    const body = document.getElementById("modalArticleBody");
    if (body) {
      const coverHtml = idea.image
        ? `<img src="${escapeHtml(idea.image)}" alt="${escapeHtml(idea.title)}" class="article-modal-cover" />`
        : "";
      body.innerHTML = coverHtml + (idea.content || []).map((p) => `<p>${escapeHtml(p)}</p>`).join("");
    }
    if (articlePanel) articlePanel.scrollTop = 0;
    if (readingBar) readingBar.style.width = "0%";
    openModal(articleModal);
  });

  // Open Photo Lightbox
  document.getElementById("eventsGrid")?.addEventListener("click", (e) => {
    const card = e.target.closest(".event-card");
    if (!card) return;
    lightboxIndex = Number(card.dataset.eventIndex) || 0;
    updateLightbox(lightboxIndex);
    openModal(lightboxModal);
  });

  function updateLightbox(index) {
    const item = currentVisibleEvents[index];
    if (!item) return;
    const img = document.getElementById("lightboxImg");
    const imgWrap = img?.closest(".lightbox-image-wrap");
    if (img && imgWrap) {
      if (item.image) {
        img.style.opacity = "0";
        setTimeout(() => {
          img.src = item.image;
          img.alt = item.title;
          img.onload = () => {
            img.style.opacity = "1";
          };
          if (img.complete) img.style.opacity = "1";
        }, 120);
        imgWrap.style.display = "block";
      } else {
        img.src = "";
        imgWrap.style.display = "none";
      }
    }
    setText("lightboxTitle", item.title);
    setText("lightboxDesc", item.description);
    const tags = document.getElementById("lightboxTags");
    if (tags) {
      tags.innerHTML = `<span class="tag-chip">${escapeHtml(item.place)}</span> <span class="tag-chip">${escapeHtml(item.date)}</span>`;
    }
  }

  document.getElementById("lightboxPrev")?.addEventListener("click", () => {
    lightboxIndex = (lightboxIndex - 1 + currentVisibleEvents.length) % currentVisibleEvents.length;
    updateLightbox(lightboxIndex);
  });

  document.getElementById("lightboxNext")?.addEventListener("click", () => {
    lightboxIndex = (lightboxIndex + 1) % currentVisibleEvents.length;
    updateLightbox(lightboxIndex);
  });

  // Open YouTube Video
  document.getElementById("socialGrid")?.addEventListener("click", (e) => {
    const media = e.target.closest("[data-youtube-id]");
    if (!media) return;
    const ytId = media.dataset.youtubeId;
    const title = media.dataset.videoTitle || "";
    const iframe = document.getElementById("videoIframe");
    if (iframe) iframe.src = `https://www.youtube.com/embed/${encodeURIComponent(ytId)}?autoplay=1`;
    setText("videoModalTitle", title);
    openModal(videoModal);
  });

  // Close Modals
  document.querySelectorAll("[data-close-modal]").forEach((btn) => {
    btn.addEventListener("click", () => closeAllModals());
  });

  document.querySelectorAll(".modal-backdrop").forEach((backdrop) => {
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) closeAllModals();
    });
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeAllModals();
    if (lightboxModal?.classList.contains("open")) {
      if (e.key === "ArrowLeft") document.getElementById("lightboxPrev")?.click();
      if (e.key === "ArrowRight") document.getElementById("lightboxNext")?.click();
    }
  });

  function openModal(modal) {
    modal?.classList.add("open");
    modal?.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
  }

  function closeAllModals() {
    document.querySelectorAll(".modal-backdrop").forEach((m) => {
      m.classList.remove("open");
      m.setAttribute("aria-hidden", "true");
    });
    const iframe = document.getElementById("videoIframe");
    if (iframe) iframe.src = "";
    document.body.style.overflow = "";
  }
}

/* ==========================================================================
   SCROLL PROGRESS, NAVBAR, PARALLAX & SLIDING NAV INDICATOR
   ========================================================================== */
function initScrollEffects() {
  const progress = document.getElementById("scrollProgress");
  const navbar = document.getElementById("navbar");
  const orb1 = document.getElementById("orb1");
  const orb2 = document.getElementById("orb2");

  let ticking = false;
  window.addEventListener(
    "scroll",
    () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        const scrollTop = window.scrollY;
        const docHeight = document.documentElement.scrollHeight - window.innerHeight;
        const pct = docHeight > 0 ? (scrollTop / docHeight) * 100 : 0;
        if (progress) progress.style.width = `${pct}%`;
        if (navbar) navbar.classList.toggle("scrolled", scrollTop > 30);

        if (orb1) orb1.style.transform = `translate3d(0, ${scrollTop * 0.08}px, 0)`;
        if (orb2) orb2.style.transform = `translate3d(0, ${-scrollTop * 0.06}px, 0)`;
        ticking = false;
      });
    },
    { passive: true }
  );
}

function initNavIndicator() {
  const navLinksWrap = document.getElementById("navLinks");
  const indicator = document.getElementById("navIndicator");
  if (!navLinksWrap || !indicator) return;

  const links = Array.from(navLinksWrap.querySelectorAll(".nav-link"));
  let activeLink = null;

  function moveIndicatorTo(el) {
    if (!el) {
      indicator.style.opacity = "0";
      return;
    }
    const wrapRect = navLinksWrap.getBoundingClientRect();
    const elRect = el.getBoundingClientRect();
    indicator.style.width = `${elRect.width}px`;
    indicator.style.transform = `translateX(${elRect.left - wrapRect.left}px)`;
    indicator.style.opacity = "1";
  }

  links.forEach((link) => {
    link.addEventListener("mouseenter", () => moveIndicatorTo(link));
  });

  navLinksWrap.addEventListener("mouseleave", () => moveIndicatorTo(activeLink));

  const sectionIds = links.map((l) => l.dataset.section).filter(Boolean);
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          const match = links.find((l) => l.dataset.section === entry.target.id);
          if (match) {
            links.forEach((l) => l.classList.remove("active"));
            match.classList.add("active");
            activeLink = match;
            moveIndicatorTo(match);
          }
        }
      });
    },
    { rootMargin: "-40% 0px -50% 0px" }
  );

  sectionIds.forEach((id) => {
    const sec = document.getElementById(id);
    if (sec) observer.observe(sec);
  });

  window.addEventListener("resize", () => moveIndicatorTo(activeLink));
}

function initRevealObserver() {
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.1, rootMargin: "0px 0px -40px 0px" }
  );

  document.querySelectorAll(".reveal-up").forEach((el) => observer.observe(el));
}

function initCounters() {
  const counters = document.querySelectorAll("[data-count]");
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const el = entry.target;
        const target = Number(el.dataset.count) || 0;
        const duration = 1300;
        const start = performance.now();

        function tick(now) {
          const t = Math.min((now - start) / duration, 1);
          const eased = 1 - Math.pow(1 - t, 3);
          el.textContent = `${Math.round(target * eased)}+`;
          if (t < 1) requestAnimationFrame(tick);
        }

        requestAnimationFrame(tick);
        observer.unobserve(el);
      });
    },
    { threshold: 0.4 }
  );

  counters.forEach((c) => observer.observe(c));
}

/* ==========================================================================
   3D TILT CARDS, VIEWPORT SPOTLIGHT, MAGNETIC & CONTEXTUAL CURSOR
   ========================================================================== */
function bindTiltToElements(elements) {
  if (window.matchMedia("(hover: none)").matches) return;

  elements.forEach((card) => {
    if (card.dataset.tiltBound) return;
    card.dataset.tiltBound = "1";
    const maxTilt = parseFloat(card.dataset.tilt) || 5;

    card.addEventListener("mousemove", (e) => {
      const rect = card.getBoundingClientRect();
      const px = (e.clientX - rect.left) / rect.width;
      const py = (e.clientY - rect.top) / rect.height;
      const rotateY = (px - 0.5) * (maxTilt * 2);
      const rotateX = (0.5 - py) * (maxTilt * 2);

      card.style.setProperty("--glare-x", `${px * 100}%`);
      card.style.setProperty("--glare-y", `${py * 100}%`);
      card.style.transform = `perspective(1000px) rotateX(${rotateX.toFixed(2)}deg) rotateY(${rotateY.toFixed(2)}deg) translateY(-4px)`;
    });

    card.addEventListener("mouseleave", () => {
      card.style.transform = "";
    });
  });
}

function initTiltCards() {
  bindTiltToElements(document.querySelectorAll(".tilt-card"));
}

function initViewportSpotlight() {
  if (window.matchMedia("(hover: none)").matches) return;
  window.addEventListener(
    "mousemove",
    (e) => {
      document.documentElement.style.setProperty("--cursor-x", `${e.clientX}px`);
      document.documentElement.style.setProperty("--cursor-y", `${e.clientY}px`);
    },
    { passive: true }
  );
}

function initMagneticElements() {
  if (window.matchMedia("(hover: none)").matches) return;

  document.querySelectorAll(".magnetic").forEach((el) => {
    const strength = parseFloat(el.dataset.magnetic) || 0.22;
    el.addEventListener("mousemove", (e) => {
      const rect = el.getBoundingClientRect();
      const x = (e.clientX - rect.left - rect.width / 2) * strength;
      const y = (e.clientY - rect.top - rect.height / 2) * strength;
      el.style.transform = `translate3d(${x}px, ${y}px, 0)`;
    });
    el.addEventListener("mouseleave", () => {
      el.style.transform = "";
    });
  });
}

function initCustomCursor() {
  if (window.matchMedia("(hover: none)").matches) return;

  const dot = document.getElementById("cursorDot");
  const ring = document.getElementById("cursorRing");
  const labelEl = document.getElementById("cursorLabel");
  if (!dot || !ring) return;

  let mouseX = 0, mouseY = 0;
  let ringX = 0, ringY = 0;

  window.addEventListener("mousemove", (e) => {
    mouseX = e.clientX;
    mouseY = e.clientY;
    dot.style.opacity = "1";
    ring.style.opacity = "1";
    dot.style.left = `${mouseX}px`;
    dot.style.top = `${mouseY}px`;
  });

  function animateRing() {
    ringX += (mouseX - ringX) * 0.16;
    ringY += (mouseY - ringY) * 0.16;
    ring.style.left = `${ringX}px`;
    ring.style.top = `${ringY}px`;
    requestAnimationFrame(animateRing);
  }
  animateRing();

  document.addEventListener("mouseover", (e) => {
    const labeled = e.target.closest("[data-cursor]");
    const interactive = e.target.closest("a, button");
    if (labeled && labelEl && !interactive) {
      labelEl.textContent = labeled.dataset.cursor || "";
      ring.classList.add("has-label");
      ring.classList.remove("hovered");
      dot.style.opacity = "0";
    } else if (interactive || labeled) {
      ring.classList.remove("has-label");
      ring.classList.add("hovered");
      dot.style.opacity = "1";
    } else {
      ring.classList.remove("has-label", "hovered");
      dot.style.opacity = "1";
    }
  });
}

/* ==========================================================================
   MOBILE MENU & COPY EMAIL
   ========================================================================== */
function initMobileMenu() {
  const btn = document.getElementById("mobileMenuBtn");
  const drawer = document.getElementById("mobileDrawer");
  if (!btn || !drawer) return;

  btn.addEventListener("click", () => {
    drawer.classList.toggle("open");
  });

  drawer.querySelectorAll(".mobile-link").forEach((link) => {
    link.addEventListener("click", () => drawer.classList.remove("open"));
  });
}

function initCopyEmail(email) {
  const btn = document.getElementById("copyEmailBtn");
  const toast = document.getElementById("toast");
  if (!btn || !toast) return;

  btn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(email);
    } catch {
      // Clipboard fallback
    }
    toast.classList.add("show");
    setTimeout(() => toast.classList.remove("show"), 2400);
  });
}

/* ==========================================================================
   HELPERS
   ========================================================================== */
function setText(id, value) {
  const el = document.getElementById(id);
  if (el && value !== undefined) el.textContent = value;
}

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
