/**
 * KİŞİSEL BLOG & PORTFOLYO — YENİ NESİL ANİMASYON & ETKİLEŞİM MOTORU
 */

document.addEventListener("DOMContentLoaded", async () => {
  initTheme();
  initTabTitleRotator();
  initIntroCurtain();
  initHeroCanvas();

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
  renderProjects(data.projects || []);
  renderEvents(data.events || [], "all");
  renderIdeas(data.ideas || []);
  renderSocialFeed(data.socialPosts || [], "all");
  renderFooterSocials(data.profile?.socialLinks || []);

  initDossierTabs();
  initHeroTicker(data.profile?.interests || []);
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
  initCopyEmail(data.profile?.email || "", data.contact?.phoneDisplay || "0537 775 12 24");
  initChatbot(data);
});

/* ==========================================================================
   ARCHITECTURAL INTRO CURTAIN
   ========================================================================== */
function initIntroCurtain() {
  const curtain = document.getElementById("introCurtain");
  if (!curtain) return;
  setTimeout(() => {
    curtain.classList.add("done");
  }, 550);
}

/* ==========================================================================
   DYNAMIC TAB TITLE ROTATOR
   ========================================================================== */
function initTabTitleRotator() {
  window.__tabTitleConfig = window.__tabTitleConfig || {
    baseName: "Emir Zencircioğlu",
    roles: ["Sermaye Piyasaları", "Finans", "Hazine & Yatırım", "Teknoloji", "Fintech & Analiz"],
  };
  let idx = 0;
  const apply = () => {
    const cfg = window.__tabTitleConfig;
    const list = cfg.roles && cfg.roles.length ? cfg.roles : ["Portfolyo"];
    idx = idx % list.length;
    document.title = `${cfg.baseName || "Emir Zencircioğlu"} · ${list[idx]}`;
  };
  apply();

  setInterval(() => {
    const list = window.__tabTitleConfig?.roles || [];
    if (!list.length) return;
    idx = (idx + 1) % list.length;
    apply();
  }, 2400);
}

/* ==========================================================================
   THEME TOGGLE
   ========================================================================== */
function initTheme() {
  const root = document.documentElement;
  const saved = localStorage.getItem("blog-theme-v3") || "dark";
  root.setAttribute("data-theme", saved);

  const btn = document.getElementById("themeToggle");
  btn?.addEventListener("click", () => {
    const current = root.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    localStorage.setItem("blog-theme-v3", next);
  });
}

/* ==========================================================================
   PROFILE & EXECUTIVE DOSSIER HYDRATION
   ========================================================================== */
function hydrateProfile(data) {
  const profile = data.profile || {};
  setText("navBrandName", profile.brandName);
  setText("curtainName", (profile.name || "emir.").toLowerCase());
  setText("heroStatus", profile.status);
  setText("profileName", profile.name);
  setText("profileRole", profile.role);
  setText("profileBio", profile.bio);
  setText("emailText", profile.email);
  setText("footerName", profile.name);
  setText("currentYear", new Date().getFullYear());

  const mailtoBtn = document.getElementById("mailtoBtn");
  if (mailtoBtn && profile.email) mailtoBtn.href = `mailto:${profile.email}`;
  const mailtoActionBtn = document.getElementById("mailtoActionBtn");
  if (mailtoActionBtn && profile.email) mailtoActionBtn.href = `mailto:${profile.email}`;

  // Hero Strip & Display Name
  const firstName = (profile.name || "Emir").trim().split(/\s+/)[0];
  setText("heroDisplayName", firstName);
  setText("heroName", profile.name);
  setText("heroRole", profile.role);
  setText("heroProjCount", (data.projects || []).length);
  setText("heroEventCount", (data.events || []).length);
  setText("heroIdeaCount", (data.ideas || []).length);
  setText("heroSocialCount", (data.socialPosts || []).length);

  const latestSocial = (data.socialPosts || [])[0];
  const latestIdea = (data.ideas || [])[0];
  setText("heroLatestPost", latestSocial?.title || latestIdea?.title || profile.status);
  setText("heroLatestExcerpt", latestSocial?.excerpt || latestIdea?.summary || "");

  const heroTags = document.getElementById("heroTags");
  if (heroTags && profile.interests) {
    heroTags.innerHTML = profile.interests
      .slice(0, 4)
      .map((tag) => `<span class="tag-chip">${escapeHtml(tag)}</span>`)
      .join("");
  }

  const heroNowList = document.getElementById("heroNowList");
  if (heroNowList && profile.now) {
    heroNowList.innerHTML = profile.now
      .map((item) => `<li>${escapeHtml(item)}</li>`)
      .join("");
  }

  const statProj = document.getElementById("statProjCount");
  if (statProj && data.projects) statProj.dataset.count = String(data.projects.length);
  const statEvent = document.getElementById("statEventCount");
  if (statEvent && data.events) statEvent.dataset.count = String(data.events.length);

  const avatar = document.getElementById("profileAvatar");
  const safeProfileAvatar = profile.avatar && !profile.avatar.startsWith("file://") ? profile.avatar : "";
  if (avatar && safeProfileAvatar) avatar.src = safeProfileAvatar;

  const hero = data.hero || {};
  const site = data.site || {};
  const contact = data.contact || {};

  const safeHeroImg = hero.portraitImage && !hero.portraitImage.startsWith("file://")
    ? hero.portraitImage
    : safeProfileAvatar;
  const heroAvatar = document.getElementById("heroAvatar");
  if (heroAvatar && safeHeroImg) heroAvatar.src = safeHeroImg;

  // Dinamik sekme başlıkları & en üst ticker
  if (window.__tabTitleConfig) {
    if (profile.name) window.__tabTitleConfig.baseName = profile.name;
    if (Array.isArray(site.tabRoles) && site.tabRoles.length) {
      window.__tabTitleConfig.roles = site.tabRoles;
    }
  }
  const tickerTrack = document.getElementById("topTickerTrack");
  if (tickerTrack && Array.isArray(site.tickerItems) && site.tickerItems.length) {
    const doubled = [...site.tickerItems, ...site.tickerItems];
    tickerTrack.innerHTML = doubled
      .map((item) => `<span>${escapeHtml(item)}</span><i>◆</i>`)
      .join("");
  }
  if (site.topCtaText) setText("topbarCta", site.topCtaText);

  // Giriş (Hero) yazıları ve rozetleri
  if (hero.kicker) setText("heroKicker", hero.kicker);
  if (hero.titleLine1) setText("heroTitleLine1", hero.titleLine1);
  if (hero.titlePrefix) setText("heroTitlePrefix", hero.titlePrefix);
  if (hero.titleHighlight) setText("heroTitleHighlight", hero.titleHighlight);
  if (hero.titleLine3) setText("heroTitleLine3", hero.titleLine3);
  if (hero.subtitle) setText("heroSubtitle", hero.subtitle);
  if (hero.primaryCtaText) setText("heroCtaPrimaryText", hero.primaryCtaText);
  if (hero.secondaryCtaText) setText("heroCtaSecondaryText", hero.secondaryCtaText);
  const heroPillarsWrap = document.getElementById("heroPillars");
  if (heroPillarsWrap && Array.isArray(hero.pillars) && hero.pillars.length) {
    heroPillarsWrap.innerHTML = hero.pillars
      .map((item, idx) => `<div class="pillar-chip"><span>${String(idx + 1).padStart(2, "0")}</span> ${escapeHtml(item)}</div>`)
      .join("");
  }

  // Bölüm başlıkları
  if (site.aboutTag) setText("aboutTag", site.aboutTag);
  if (site.aboutTitlePrefix) setText("aboutTitlePrefix", site.aboutTitlePrefix);
  if (site.aboutTitleHighlight) setText("aboutTitleHighlight", site.aboutTitleHighlight);
  if (site.projectsTag) setText("projectsTag", site.projectsTag);
  if (site.projectsTitlePrefix) setText("projectsTitlePrefix", site.projectsTitlePrefix);
  if (site.projectsTitleHighlight) setText("projectsTitleHighlight", site.projectsTitleHighlight);
  if (site.projectsSub) setText("projectsSub", site.projectsSub);
  if (site.eventsTag) setText("eventsTag", site.eventsTag);
  if (site.eventsTitlePrefix) setText("eventsTitlePrefix", site.eventsTitlePrefix);
  if (site.eventsTitleHighlight) setText("eventsTitleHighlight", site.eventsTitleHighlight);
  if (site.ideasTag) setText("ideasTag", site.ideasTag);
  if (site.ideasTitlePrefix) setText("ideasTitlePrefix", site.ideasTitlePrefix);
  if (site.ideasTitleHighlight) setText("ideasTitleHighlight", site.ideasTitleHighlight);
  if (site.ideasSub) setText("ideasSub", site.ideasSub);
  if (site.socialTag) setText("socialTag", site.socialTag);
  if (site.socialTitlePrefix) setText("socialTitlePrefix", site.socialTitlePrefix);
  if (site.socialTitleHighlight) setText("socialTitleHighlight", site.socialTitleHighlight);

  // Tanışalım (Contact) & Footer
  if (contact.tag) setText("contactTag", contact.tag);
  if (contact.titlePrefix) setText("contactTitlePrefix", contact.titlePrefix);
  if (contact.titleHighlight) setText("contactTitleHighlight", contact.titleHighlight);
  if (contact.description) setText("contactDesc", contact.description);
  if (contact.footerNote) setText("footerNote", contact.footerNote);
  if (contact.phoneDisplay) {
    setText("phoneText", contact.phoneDisplay);
    const digits = contact.phoneDisplay.replace(/\D/g, "");
    const normalized = digits.startsWith("0") ? `+90${digits.slice(1)}` : `+${digits}`;
    const href = contact.phoneHref || (digits ? `tel:${normalized}` : "");
    if (href) {
      const phoneLink = document.getElementById("phoneLink");
      const phoneCallBtn = document.getElementById("phoneCallBtn");
      if (phoneLink) phoneLink.href = href;
      if (phoneCallBtn) phoneCallBtn.href = href;
    }
  }

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

function initDossierTabs() {
  const tabsWrap = document.getElementById("dossierTabs");
  if (!tabsWrap) return;
  tabsWrap.addEventListener("click", (e) => {
    const btn = e.target.closest(".dossier-tab");
    if (!btn) return;
    const target = btn.dataset.dtab;
    tabsWrap.querySelectorAll(".dossier-tab").forEach((t) => t.classList.remove("active"));
    btn.classList.add("active");
    document.querySelectorAll(".dossier-pane").forEach((p) => {
      p.classList.toggle("active", p.dataset.dpane === target);
    });
  });
}

function initHeroTicker(interests) {
  const el = document.getElementById("heroTicker");
  if (!el) return;
  const items = interests && interests.length ? interests : ["Yazılım Mimarisi", "Ürün Geliştirme", "Topluluk & Zirveler"];
  let idx = 0;
  el.textContent = items[0];
  if (items.length < 2) return;

  setInterval(() => {
    el.classList.add("switching");
    setTimeout(() => {
      idx = (idx + 1) % items.length;
      el.textContent = items[idx];
      el.classList.remove("switching");
    }, 320);
  }, 3000);
}

function renderMarquee(items) {
  const track = document.getElementById("marqueeTrack");
  const trackRev = document.getElementById("marqueeTrackReverse");
  if (!items.length) return;
  const doubled = [...items, ...items];
  const html = doubled.map((name) => `<span class="marquee-item">${escapeHtml(name)}</span>`).join("");
  if (track) track.innerHTML = html;
  if (trackRev) {
    const reversedDoubled = [...items].reverse().concat([...items].reverse());
    trackRev.innerHTML = reversedDoubled
      .map((name) => `<span class="marquee-item">${escapeHtml(name)}</span>`)
      .join("");
  }
}

/* ==========================================================================
   PROJECTS RENDERING (NUMBERED ARCHITECTURAL CARDS)
   ========================================================================== */
function renderProjects(projects) {
  const grid = document.getElementById("projectsGrid");
  if (!grid) return;

  grid.innerHTML = projects
    .map((proj, idx) => {
      const num = String(idx + 1).padStart(2, "0");
      return `
      <article class="project-card tilt-card reveal-up" data-tilt="4" data-cursor="Aç" style="--delay: ${idx * 0.08}s">
        <span class="project-index" aria-hidden="true">${num}</span>
        <div>
          <div class="project-top">
            <span class="project-year">${escapeHtml(proj.year)}</span>
            <span class="project-status">${escapeHtml(proj.status)}</span>
          </div>
          <h3 class="project-title" style="margin-top: 16px;">${escapeHtml(proj.title)}</h3>
          <p class="project-desc">${escapeHtml(proj.description)}</p>
          ${proj.image ? `<div class="project-cover"><img src="${escapeHtml(proj.image)}" alt="${escapeHtml(proj.title)}" loading="lazy" /></div>` : ""}
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
    `;
    })
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
   SLIDING FILTER PILLS & PLATFORM JUMP
   ========================================================================== */
function moveFilterPill(bar) {
  if (!bar) return;
  const bg = bar.querySelector(".filter-pill-bg");
  const active = bar.querySelector(".filter-btn.active");
  if (!bg || !active) return;
  const barRect = bar.getBoundingClientRect();
  const actRect = active.getBoundingClientRect();
  bg.style.width = `${actRect.width}px`;
  bg.style.transform = `translateX(${actRect.left - barRect.left - 5}px)`;
}

function initFilters(data) {
  const socialBar = document.getElementById("socialFilters");
  const eventBar = document.getElementById("eventFilters");

  requestAnimationFrame(() => {
    moveFilterPill(socialBar);
    moveFilterPill(eventBar);
  });
  window.addEventListener("resize", () => {
    moveFilterPill(socialBar);
    moveFilterPill(eventBar);
  });

  socialBar?.addEventListener("click", (e) => {
    const btn = e.target.closest(".filter-btn");
    if (!btn) return;
    socialBar.querySelectorAll(".filter-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    moveFilterPill(socialBar);
    renderSocialFeed(data.socialPosts || [], btn.dataset.filter);
  });

  document.querySelectorAll("[data-jump-platform]").forEach((pill) => {
    pill.addEventListener("click", () => {
      const platform = pill.dataset.jumpPlatform;
      const targetBtn = socialBar?.querySelector(`[data-filter="${platform}"]`);
      if (targetBtn) {
        socialBar.querySelectorAll(".filter-btn").forEach((b) => b.classList.remove("active"));
        targetBtn.classList.add("active");
        moveFilterPill(socialBar);
        renderSocialFeed(data.socialPosts || [], platform);
      }
    });
  });

  eventBar?.addEventListener("click", (e) => {
    const btn = e.target.closest(".filter-btn");
    if (!btn) return;
    eventBar.querySelectorAll(".filter-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    moveFilterPill(eventBar);
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

function initHeroCanvas() {
  const canvas = document.getElementById("heroCanvas");
  if (!canvas || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  let w = (canvas.width = window.innerWidth);
  let h = (canvas.height = window.innerHeight);
  const count = Math.min(48, Math.floor((w * h) / 28000));
  const mouse = { x: w * 0.5, y: h * 0.4 };

  const nodes = Array.from({ length: count }, (_, i) => ({
    x: Math.random() * w,
    y: Math.random() * h,
    vx: (Math.random() - 0.5) * 0.32,
    vy: (Math.random() - 0.5) * 0.32,
    r: 1.4 + Math.random() * 1.6,
    gold: i % 3 === 0,
  }));

  window.addEventListener("resize", () => {
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
  });

  window.addEventListener(
    "mousemove",
    (e) => {
      mouse.x = e.clientX;
      mouse.y = e.clientY;
    },
    { passive: true }
  );

  function frame() {
    ctx.clearRect(0, 0, w, h);
    const isLight = document.documentElement.getAttribute("data-theme") === "light";

    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      a.x += a.vx;
      a.y += a.vy;
      if (a.x < 0 || a.x > w) a.vx *= -1;
      if (a.y < 0 || a.y > h) a.vy *= -1;

      const dxm = mouse.x - a.x;
      const dym = mouse.y - a.y;
      const dm = Math.hypot(dxm, dym);
      if (dm < 170) {
        a.x -= dxm * 0.0025;
        a.y -= dym * 0.0025;
      }

      ctx.beginPath();
      ctx.arc(a.x, a.y, a.r, 0, Math.PI * 2);
      ctx.fillStyle = a.gold
        ? isLight ? "rgba(180, 134, 11, 0.45)" : "rgba(212, 175, 55, 0.55)"
        : isLight ? "rgba(5, 150, 105, 0.38)" : "rgba(16, 185, 129, 0.45)";
      ctx.fill();

      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j];
        const dist = Math.hypot(a.x - b.x, a.y - b.y);
        if (dist < 145) {
          const alpha = (1 - dist / 145) * (isLight ? 0.14 : 0.18);
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.strokeStyle = a.gold ? `rgba(212, 175, 55, ${alpha})` : `rgba(16, 185, 129, ${alpha})`;
          ctx.lineWidth = 0.8;
          ctx.stroke();
        }
      }
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

function initNavIndicator() {
  const railWrap = document.getElementById("navLinks");
  if (!railWrap) return;

  const links = Array.from(railWrap.querySelectorAll(".rail-item"));
  const sectionIds = links.map((l) => l.dataset.section).filter(Boolean);
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          const match = links.find((l) => l.dataset.section === entry.target.id);
          if (match) {
            links.forEach((l) => l.classList.remove("active"));
            match.classList.add("active");
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

function initCopyEmail(email, phone) {
  const emailBtn = document.getElementById("copyEmailBtn");
  const phoneBtn = document.getElementById("copyPhoneBtn");
  const toast = document.getElementById("toast");
  if (!toast) return;

  function showCopyToast(msg) {
    toast.textContent = msg;
    toast.classList.add("show");
    setTimeout(() => toast.classList.remove("show"), 2400);
  }

  emailBtn?.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(email);
    } catch {
      // Clipboard fallback
    }
    showCopyToast("E-posta adresi kopyalandı!");
  });

  phoneBtn?.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(phone || "0537 775 12 24");
    } catch {
      // Clipboard fallback
    }
    showCopyToast("Telefon numarası kopyalandı!");
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

/* ==========================================================================
   FLOATING FACE CHATBOT (GEMINI AI)
   ========================================================================== */
function initChatbot(data) {
  const widget = document.getElementById("chatWidget");
  const fab = document.getElementById("chatFab");
  const panel = document.getElementById("chatPanel");
  const closeBtn = document.getElementById("chatCloseBtn");
  const resetBtn = document.getElementById("chatResetBtn");
  const messagesEl = document.getElementById("chatMessages");
  const suggestionsEl = document.getElementById("chatSuggestions");
  const form = document.getElementById("chatForm");
  const input = document.getElementById("chatInput");
  const sendBtn = document.getElementById("chatSendBtn");
  const headAvatar = document.getElementById("chatHeadAvatar");
  const headWrap = document.getElementById("chatHeadAvatarWrap");
  const tooltipEl = document.getElementById("chatFabTooltip");

  if (!widget || !fab || !panel || !messagesEl || !form || !input) return;

  const profile = data.profile || {};
  const firstName = (profile.name || "Emir").trim().split(/\s+/)[0];
  setText("chatBotTitle", `${firstName} AI`);

  // Sohbet başlığı mini avatarı: geçerli profil görseli varsa kullan, yoksa animasyonlu yüz kalsın
  const avatarUrl = profile.avatar || "";
  if (headAvatar && headWrap) {
    if (!avatarUrl || avatarUrl.startsWith("file://")) {
      headWrap.classList.add("is-fallback");
    } else {
      headAvatar.onload = () => headWrap.classList.remove("is-fallback");
      headAvatar.onerror = () => headWrap.classList.add("is-fallback");
      headAvatar.src = avatarUrl;
    }
  }

  // Gezinen animasyonlu yüz topu (60fps GPU translate3d + fare takibi + dokununca yumuşak yavaşlama)
  initRoamingFaceOrb(widget, fab, tooltipEl, firstName);

  let history = [];
  let isBusy = false;

  function formatChatText(raw) {
    let safe = escapeHtml(raw || "");
    safe = safe.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    safe = safe.replace(/\n/g, "<br>");
    return safe;
  }

  function appendMessage(role, text, isError = false) {
    const bubble = document.createElement("div");
    bubble.className = `chat-msg ${role === "user" ? "chat-msg-user" : "chat-msg-bot"}${isError ? " chat-msg-error" : ""}`;
    bubble.innerHTML = formatChatText(text);
    messagesEl.appendChild(bubble);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return bubble;
  }

  function renderWelcome() {
    messagesEl.innerHTML = "";
    history = [];
    suggestionsEl?.classList.remove("hidden");
    appendMessage(
      "model",
      `Merhaba! Ben **${firstName}'in AI asistanıyım.**\n\nSermaye piyasaları, hazine ve bankacılık ilgisi, yazılım projeleri, katıldığı zirveler veya iletişim bilgileri hakkında merak ettiğiniz her şeyi sorabilirsiniz.`
    );
  }

  function setOpen(nextOpen) {
    widget.classList.toggle("open", nextOpen);
    fab.setAttribute("aria-expanded", String(nextOpen));
    panel.setAttribute("aria-hidden", String(!nextOpen));
    if (nextOpen) {
      setTimeout(() => input.focus(), 120);
    }
  }

  async function sendQuestion(questionText) {
    const trimmed = questionText.trim();
    if (!trimmed || isBusy) return;

    isBusy = true;
    sendBtn.disabled = true;
    suggestionsEl?.classList.add("hidden");

    appendMessage("user", trimmed);
    input.value = "";

    const typingBubble = document.createElement("div");
    typingBubble.className = "chat-msg chat-msg-bot";
    typingBubble.innerHTML = `<div class="chat-typing" aria-label="Yazıyor"><span></span><span></span><span></span></div>`;
    messagesEl.appendChild(typingBubble);
    messagesEl.scrollTop = messagesEl.scrollHeight;

    async function callChatOnce() {
      const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
      const timer = controller ? setTimeout(() => controller.abort(), 24000) : null;
      try {
        const res = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: trimmed, history }),
          signal: controller ? controller.signal : undefined,
        });
        const payload = await res.json().catch(() => ({}));
        return { res, payload };
      } finally {
        if (timer) clearTimeout(timer);
      }
    }

    try {
      let attempt;
      try {
        attempt = await callChatOnce();
      } catch {
        // Mobil ağ dalgalanması veya ilk soğuk başlangıçta tek otomatik tekrar dene
        await new Promise((r) => setTimeout(r, 650));
        attempt = await callChatOnce();
      }

      if ((attempt.res.status === 502 || attempt.res.status === 503) && !attempt.payload?.code) {
        await new Promise((r) => setTimeout(r, 700));
        attempt = await callChatOnce();
      }

      typingBubble.remove();

      if (!attempt.res.ok || !attempt.payload?.reply) {
        appendMessage(
          "model",
          attempt.payload?.error || "Şu anda yanıt oluşturulamadı. Lütfen birkaç saniye sonra tekrar deneyin.",
          true
        );
      } else {
        appendMessage("model", attempt.payload.reply);
        history.push({ role: "user", text: trimmed });
        history.push({ role: "model", text: attempt.payload.reply });
        if (history.length > 20) history = history.slice(-20);
      }
    } catch {
      typingBubble.remove();
      appendMessage("model", "Sunucuya bağlanılamadı. Lütfen internet bağlantınızı kontrol edip tekrar deneyin.", true);
    } finally {
      isBusy = false;
      sendBtn.disabled = false;
      if (!window.matchMedia("(pointer: coarse)").matches) {
        input.focus();
      }
    }
  }

  renderWelcome();

  fab.addEventListener("click", () => {
    setOpen(!widget.classList.contains("open"));
  });

  closeBtn?.addEventListener("click", () => setOpen(false));
  resetBtn?.addEventListener("click", renderWelcome);

  suggestionsEl?.querySelectorAll(".chat-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const prompt = chip.dataset.prompt || chip.textContent || "";
      sendQuestion(prompt);
    });
  });

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    sendQuestion(input.value);
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && widget.classList.contains("open")) {
      setOpen(false);
    }
  });
}

function initRoamingFaceOrb(widget, fab, tooltipEl, firstName) {
  const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const getPad = () => (window.innerWidth <= 540 ? 14 : 24);
  const getSize = () => fab.offsetWidth || (window.innerWidth <= 540 ? 60 : 72);

  let posX = window.innerWidth - getSize() - getPad();
  let posY = window.innerHeight - getSize() - getPad();
  let vx = -1.15;
  let vy = -0.82;
  let mouseX = posX;
  let mouseY = posY;
  let isHovering = false;
  let phase = 0;

  window.addEventListener("mousemove", (e) => {
    mouseX = e.clientX;
    mouseY = e.clientY;
  }, { passive: true });

  fab.addEventListener("mouseenter", () => { isHovering = true; });
  fab.addEventListener("mouseleave", () => { isHovering = false; });

  // Ziyaretçinin dikkatini çekmek için periyodik konuşma balonu
  const teasers = [
    `Merhaba! ${firstName}'i sor ✨`,
    "Sermaye piyasaları & finans? 💼",
    "Projelerimi merak ediyor musun?",
    "Bana tıklayıp soru sorabilirsin 👋",
  ];
  let teaserIdx = 0;
  function showTeaserBriefly() {
    if (widget.classList.contains("open") || !tooltipEl) return;
    tooltipEl.textContent = teasers[teaserIdx % teasers.length];
    teaserIdx += 1;
    fab.classList.add("is-peeking");
    setTimeout(() => fab.classList.remove("is-peeking"), 2800);
  }
  setTimeout(showTeaserBriefly, 1800);
  setInterval(showTeaserBriefly, 7500);

  function tick() {
    const size = getSize();
    const pad = getPad();
    const minX = pad;
    const maxX = Math.max(minX, window.innerWidth - size - pad);
    const minY = Math.min(88, Math.max(16, window.innerHeight * 0.14));
    const maxY = Math.max(minY, window.innerHeight - size - pad);
    const isOpen = widget.classList.contains("open");

    if (isOpen || prefersReduced) {
      // Sohbet açıkken sağ alt köşedeki yuvasına yumuşakça yerleş
      posX += (maxX - posX) * 0.18;
      posY += (maxY - posY) * 0.18;
      fab.style.transform = `translate3d(${posX.toFixed(1)}px, ${posY.toFixed(1)}px, 0) rotate(0deg)`;
      fab.style.setProperty("--eye-x", "0px");
      fab.style.setProperty("--eye-y", "0px");
      requestAnimationFrame(tick);
      return;
    }

    phase += 0.032;
    const cx = posX + size / 2;
    const cy = posY + size / 2;
    const dist = Math.hypot(mouseX - cx, mouseY - cy);

    // İmleç yaklaşınca tıklamayı kolaylaştırmak için top nazikçe yavaşlar
    const speedFactor = isHovering ? 0.06 : dist < 130 ? 0.28 : 1;
    const bobOffset = Math.sin(phase * 1.4) * 0.35 * speedFactor;

    posX += vx * speedFactor;
    posY += (vy * speedFactor) + bobOffset;

    if (posX <= minX) {
      posX = minX;
      vx = Math.abs(vx);
    } else if (posX >= maxX) {
      posX = maxX;
      vx = -Math.abs(vx);
    }

    if (posY <= minY) {
      posY = minY;
      vy = Math.abs(vy);
    } else if (posY >= maxY) {
      posY = maxY;
      vy = -Math.abs(vy);
    }

    // Tooltip ekran kenarlarından taşmasın
    if (tooltipEl) {
      if (posY < 96) {
        tooltipEl.style.bottom = "auto";
        tooltipEl.style.top = "calc(100% + 10px)";
      } else {
        tooltipEl.style.top = "auto";
        tooltipEl.style.bottom = "calc(100% + 12px)";
      }
      fab.classList.toggle("tooltip-right", posX > window.innerWidth - 220);
      fab.classList.toggle("tooltip-left", posX < 180);
    }

    // Göz bebekleri imleci takip eder (imleç uzaktaysa gittiği yöne bakar)
    const lookDx = dist < 420 ? (mouseX - cx) / 70 : vx * 1.8;
    const lookDy = dist < 420 ? (mouseY - cy) / 70 : vy * 1.8;
    const eyeX = Math.max(-2.6, Math.min(2.6, lookDx));
    const eyeY = Math.max(-2.4, Math.min(2.4, lookDy));
    const tiltDeg = Math.max(-10, Math.min(10, vx * 4.5 * speedFactor));

    fab.style.transform = `translate3d(${posX.toFixed(1)}px, ${posY.toFixed(1)}px, 0) rotate(${tiltDeg.toFixed(2)}deg)`;
    fab.style.setProperty("--eye-x", `${eyeX.toFixed(2)}px`);
    fab.style.setProperty("--eye-y", `${eyeY.toFixed(2)}px`);

    requestAnimationFrame(tick);
  }

  requestAnimationFrame(tick);
}
