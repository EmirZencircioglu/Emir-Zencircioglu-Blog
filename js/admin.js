/**
 * ADMIN PANELİ İSTEMCİ MANTIĞI (AYRI SAYFA / GÖRÜNÜM YÖNETİMİ)
 */

const VALID_VIEWS = ["overview", "blog", "events", "projects", "social", "automation", "profile"];
let ADMIN_CONTENT = {};

document.addEventListener("DOMContentLoaded", async () => {
  initNavigation();
  initPlatformSelector();
  initImageUpload("ideaFile", "ideaImageUrl", "ideaPreview", "ideaAddImgBtn", "ideaRemoveImgBtn");
  initImageUpload("socFile", "socImageUrl", "socPreview", "socAddImgBtn", "socRemoveImgBtn");
  initImageUpload("evFile", "evImageUrl", "evPreview", "evAddImgBtn", "evRemoveImgBtn");
  initAuthForms();
  initPublishForms();
  initCancelEditButtons();
  initAutomationControls();

  await checkAuthAndBoot();
});

async function checkAuthAndBoot() {
  try {
    const res = await fetch("/api/auth/status");
    const state = await res.json();

    const authShell = document.getElementById("authShell");
    const setupView = document.getElementById("setupView");
    const loginView = document.getElementById("loginView");
    const dashboard = document.getElementById("dashboardShell");

    if (state.authenticated) {
      authShell.classList.add("hidden");
      dashboard.classList.remove("hidden");
      document.getElementById("loggedUserBadge").textContent = `@${state.username}`;
      syncViewFromHash();
      await loadAdminContent();
    } else {
      dashboard.classList.add("hidden");
      authShell.classList.remove("hidden");
      if (state.needsSetup) {
        setupView.classList.remove("hidden");
        loginView.classList.add("hidden");
      } else {
        setupView.classList.add("hidden");
        loginView.classList.remove("hidden");
      }
    }
  } catch {
    showToast("Sunucuya bağlanılamadı. Lütfen server.py'yi çalıştır.", true);
  }
}

/* ==========================================================================
   SAYFA / GÖRÜNÜM GEÇİŞLERİ (HASH ROUTING)
   ========================================================================== */
function initNavigation() {
  window.addEventListener("hashchange", syncViewFromHash);

  document.querySelectorAll("[data-view]").forEach((el) => {
    el.addEventListener("click", (e) => {
      const target = el.dataset.view;
      if (VALID_VIEWS.includes(target)) {
        e.preventDefault();
        window.location.hash = target;
      }
    });
  });
}

function syncViewFromHash() {
  const raw = window.location.hash.replace("#", "").trim();
  const viewName = VALID_VIEWS.includes(raw) ? raw : "overview";

  document.querySelectorAll(".sidebar-link").forEach((link) => {
    link.classList.toggle("active", link.dataset.view === viewName);
  });

  document.querySelectorAll(".admin-view").forEach((sec) => {
    sec.classList.toggle("active", sec.id === `view-${viewName}`);
  });
}

/* ==========================================================================
   PLATFORM SEÇİCİ (INSTAGRAM / LINKEDIN / GITHUB / YOUTUBE)
   ========================================================================== */
function initPlatformSelector() {
  const selector = document.getElementById("platformSelector");
  const hiddenInput = document.getElementById("socPlatform");
  const ytField = document.getElementById("ytIdField");
  if (!selector || !hiddenInput) return;

  selector.addEventListener("click", (e) => {
    const btn = e.target.closest(".plat-choice");
    if (!btn) return;
    const plat = btn.dataset.plat;
    hiddenInput.value = plat;

    selector.querySelectorAll(".plat-choice").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");

    if (ytField) {
      ytField.classList.toggle("hidden", plat !== "youtube");
    }
  });
}

/* ==========================================================================
   AUTH FORMS (SETUP, LOGIN, LOGOUT)
   ========================================================================== */
function initAuthForms() {
  const setupForm = document.getElementById("setupForm");
  setupForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const errEl = document.getElementById("setupError");
    errEl.classList.add("hidden");

    const username = document.getElementById("setupUser").value.trim();
    const password = document.getElementById("setupPass").value;
    const confirm = document.getElementById("setupPassConfirm").value;

    if (password !== confirm) {
      errEl.textContent = "Şifreler eşleşmiyor.";
      errEl.classList.remove("hidden");
      return;
    }

    const res = await fetch("/api/auth/setup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();
    if (!res.ok) {
      errEl.textContent = data.error || "Kurulum başarısız.";
      errEl.classList.remove("hidden");
      return;
    }

    showToast("Hesap oluşturuldu! Hoş geldin.");
    await checkAuthAndBoot();
  });

  const loginForm = document.getElementById("loginForm");
  loginForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const errEl = document.getElementById("loginError");
    errEl.classList.add("hidden");

    const username = document.getElementById("loginUser").value.trim();
    const password = document.getElementById("loginPass").value;

    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();
    if (!res.ok) {
      errEl.textContent = data.error || "Giriş başarısız.";
      errEl.classList.remove("hidden");
      return;
    }

    showToast("Giriş başarılı!");
    await checkAuthAndBoot();
  });

  document.getElementById("logoutBtn")?.addEventListener("click", async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    showToast("Çıkış yapıldı.");
    await checkAuthAndBoot();
  });
}

/* ==========================================================================
   IMAGE UPLOAD
   ========================================================================== */
function syncImagePreview(urlInputId, previewId, removeBtnId) {
  const urlVal = val(urlInputId);
  const preview = document.getElementById(previewId);
  const removeBtn = document.getElementById(removeBtnId);
  if (preview) {
    if (urlVal) {
      preview.src = urlVal;
      preview.classList.remove("hidden");
    } else {
      preview.removeAttribute("src");
      preview.classList.add("hidden");
    }
  }
  if (removeBtn) {
    removeBtn.classList.toggle("hidden", !urlVal);
  }
}

function initImageUpload(fileInputId, urlInputId, previewId, addBtnId, removeBtnId) {
  const fileInput = document.getElementById(fileInputId);
  const urlInput = document.getElementById(urlInputId);
  const addBtn = document.getElementById(addBtnId);
  const removeBtn = document.getElementById(removeBtnId);
  if (!fileInput || !urlInput) return;

  addBtn?.addEventListener("click", () => {
    fileInput.click();
  });

  removeBtn?.addEventListener("click", () => {
    urlInput.value = "";
    fileInput.value = "";
    syncImagePreview(urlInputId, previewId, removeBtnId);
    showToast("Resim kaldırıldı.");
  });

  urlInput.addEventListener("input", () => {
    syncImagePreview(urlInputId, previewId, removeBtnId);
  });

  fileInput.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = async () => {
      try {
        const res = await fetch("/api/admin/upload", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            filename: file.name,
            dataUrl: reader.result,
          }),
        });
        const data = await res.json();
        if (!res.ok) {
          showToast(data.error || "Görsel yüklenemedi.", true);
          return;
        }
        urlInput.value = data.url;
        syncImagePreview(urlInputId, previewId, removeBtnId);
        showToast("Görsel sunucuya yüklendi!");
      } catch {
        showToast("Görsel yüklenirken hata oluştu.", true);
      }
    };
    reader.readAsDataURL(file);
  });
}

/* ==========================================================================
   LOAD & RENDER PER-SECTION CONTENT
   ========================================================================== */
async function loadAdminContent() {
  const res = await fetch("/api/content", { cache: "no-store" });
  if (!res.ok) return;
  const content = await res.json();
  ADMIN_CONTENT = content;

  hydrateProfileForm(content.profile, content.institutions);
  updateOverviewCounts(content);

  renderSectionList("listIdeas", "blogListCount", "ideas", content.ideas || [], (x) => `${x.tag} · ${x.date}`, "yazı");
  renderSectionList("listEvents", "eventsListCount", "events", content.events || [], (x) => `${x.categoryLabel} · ${x.place} · ${x.date}`, "etkinlik");
  renderSectionList("listProjects", "projectsListCount", "projects", content.projects || [], (x) => `${x.year} · ${x.status}`, "proje");
  renderSectionList("listSocial", "socialListCount", "socialPosts", content.socialPosts || [], (x) => `${x.platformLabel} · ${x.date}`, "gönderi");

  await loadAutomationInfo();
}

async function loadAutomationInfo() {
  const res = await fetch("/api/admin/automation", { cache: "no-store" });
  if (!res.ok) return;
  const info = await res.json();
  setVal("webhookUrlInput", `${window.location.origin}${info.webhookPath}`);
  setVal("webhookSecretInput", info.webhookSecret);
  if (info.githubUsername) setVal("ghUsername", info.githubUsername);
  renderFeedsList(info.feeds || []);
  const statusEl = document.getElementById("botStatusText");
  if (statusEl && info.botLastRun?.time) {
    statusEl.textContent = `Son bot kontrolü: ${info.botLastRun.time} · Eklenen: ${info.botLastRun.added}${info.botLastRun.error ? ` · Hata: ${info.botLastRun.error}` : ""}`;
  }
}

function renderFeedsList(feeds) {
  const wrap = document.getElementById("feedsList");
  if (!wrap) return;
  if (feeds.length === 0) {
    wrap.innerHTML = `<p class="mono-sub">Henüz takip edilen RSS/Feed adresi yok.</p>`;
    return;
  }
  wrap.innerHTML = feeds
    .map(
      (f) => `
      <div class="admin-item-row">
        <div class="admin-item-info">
          <div class="admin-item-title">${escapeHtml(f.platform.toUpperCase())}</div>
          <div class="admin-item-meta">${escapeHtml(f.feedUrl)}</div>
        </div>
        <button type="button" class="delete-btn" data-del-feed="${escapeHtml(f.id)}">Kaldır</button>
      </div>
    `
    )
    .join("");

  wrap.querySelectorAll("[data-del-feed]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const res = await fetch("/api/admin/feeds", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: btn.dataset.delFeed }),
      });
      if (res.ok) {
        showToast("Bot takibinden kaldırıldı.");
        await loadAutomationInfo();
      }
    });
  });
}

function initAutomationControls() {
  document.getElementById("formFeedBot")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const platform = val("feedPlatform");
    const feedUrl = val("feedUrl");
    const res = await fetch("/api/admin/feeds", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ platform, feedUrl }),
    });
    const data = await res.json();
    if (res.ok) {
      e.target.reset();
      showToast("Takip botuna eklendi!");
      await loadAutomationInfo();
    } else {
      showToast(data.error || "Feed eklenemedi.", true);
    }
  });

  document.getElementById("runBotNowBtn")?.addEventListener("click", async () => {
    showToast("Bot çalıştırılıyor...");
    const res = await fetch("/api/admin/feeds/run", { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      showToast(`Bot tamamlandı! ${data.added} yeni gönderi eklendi.`);
      await loadAdminContent();
    } else {
      showToast(data.error || "Bot çalıştırılamadı.", true);
    }
  });

  document.getElementById("copyWebhookUrlBtn")?.addEventListener("click", async () => {
    await navigator.clipboard?.writeText(val("webhookUrlInput"));
    showToast("Webhook URL kopyalandı!");
  });

  document.getElementById("copyWebhookSecretBtn")?.addEventListener("click", async () => {
    await navigator.clipboard?.writeText(val("webhookSecretInput"));
    showToast("Gizli anahtar kopyalandı!");
  });

  document.getElementById("rotateSecretBtn")?.addEventListener("click", async () => {
    if (!confirm("Gizli anahtarı yenilersen eski bağlantıları güncellemen gerekir. Devam edilsin mi?")) return;
    const res = await fetch("/api/admin/automation/rotate-secret", { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      setVal("webhookSecretInput", data.webhookSecret);
      showToast("Yeni gizli anahtar oluşturuldu!");
    } else {
      showToast(data.error || "Anahtar yenilenemedi.", true);
    }
  });

  document.getElementById("formGithubSync")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = val("ghUsername");
    const res = await fetch("/api/admin/sync/github", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username }),
    });
    const data = await res.json();
    if (res.ok) {
      showToast(`${data.added} yeni GitHub reposu eklendi!`);
      await loadAdminContent();
    } else {
      showToast(data.error || "GitHub senkronizasyonu başarısız.", true);
    }
  });
}

function updateOverviewCounts(content) {
  setText("countIdeas", (content.ideas || []).length);
  setText("countEvents", (content.events || []).length);
  setText("countProjects", (content.projects || []).length);
  setText("countSocial", (content.socialPosts || []).length);
}

function renderSectionList(containerId, countId, section, items, metaFormatter, unitLabel) {
  const list = document.getElementById(containerId);
  const countEl = document.getElementById(countId);
  if (countEl) countEl.textContent = `${items.length} ${unitLabel}`;
  if (!list) return;

  if (items.length === 0) {
    list.innerHTML = `<p class="mono-sub">Henüz içerik eklenmemiş.</p>`;
    return;
  }

  list.innerHTML = items
    .map(
      (item) => `
      <div class="admin-item-row" data-row-id="${escapeHtml(item.id)}">
        <div class="admin-item-info">
          <div class="admin-item-title">${escapeHtml(item.title)}</div>
          <div class="admin-item-meta">${escapeHtml(metaFormatter(item))}</div>
        </div>
        <div class="item-actions">
          <button type="button" class="edit-btn" data-edit-section="${escapeHtml(section)}" data-edit-id="${escapeHtml(item.id)}">
            Düzenle
          </button>
          <button type="button" class="delete-btn" data-del-section="${escapeHtml(section)}" data-del-id="${escapeHtml(item.id)}">
            Sil
          </button>
        </div>
      </div>
    `
    )
    .join("");

  list.querySelectorAll("[data-edit-id]").forEach((btn) => {
    btn.addEventListener("click", () => {
      startEditingItem(btn.dataset.editSection, btn.dataset.editId);
    });
  });

  list.querySelectorAll("[data-del-id]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("Bu içeriği kalıcı olarak silmek istediğine emin misin?")) return;

      const res = await fetch("/api/admin/item", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          section: btn.dataset.delSection,
          id: btn.dataset.delId,
        }),
      });
      if (res.ok) {
        showToast("İçerik silindi.");
        await loadAdminContent();
      } else {
        showToast("Silme işlemi başarısız.", true);
      }
    });
  });
}

function initCancelEditButtons() {
  document.querySelectorAll("[data-cancel-edit]").forEach((btn) => {
    btn.addEventListener("click", () => {
      cancelEditing(btn.dataset.cancelEdit);
    });
  });
}

function setSocialPlatformUI(platform) {
  const hidden = document.getElementById("socPlatform");
  const selector = document.getElementById("platformSelector");
  const ytField = document.getElementById("ytIdField");
  if (hidden) hidden.value = platform;
  if (selector) {
    selector.querySelectorAll(".plat-choice").forEach((b) => {
      b.classList.toggle("active", b.dataset.plat === platform);
    });
  }
  if (ytField) ytField.classList.toggle("hidden", platform !== "youtube");
}

function startEditingItem(section, id) {
  const item = (ADMIN_CONTENT[section] || []).find((x) => x.id === id);
  if (!item) return;

  const sectionFormMap = {
    ideas: "formIdea",
    events: "formEvent",
    projects: "formProject",
    socialPosts: "formSocial",
  };
  const formId = sectionFormMap[section];
  const form = document.getElementById(formId);
  if (!form) return;

  form.dataset.editId = id;

  // Görsel satır vurgusu
  document.querySelectorAll(".admin-item-row.editing").forEach((r) => r.classList.remove("editing"));
  document.querySelector(`.admin-item-row[data-row-id="${CSS.escape(id)}"]`)?.classList.add("editing");

  // Başlık, buton ve iptal butonunu güncelle
  const heading = document.querySelector(`[data-heading-for="${formId}"]`);
  if (heading) heading.textContent = `Düzenleniyor: ${item.title}`;
  const submitBtn = document.querySelector(`[data-submit-for="${formId}"]`);
  if (submitBtn) submitBtn.textContent = "Değişiklikleri Kaydet";
  document.querySelector(`[data-cancel-edit="${formId}"]`)?.classList.remove("hidden");

  if (section === "ideas") {
    setVal("ideaTag", item.tag || "");
    setVal("ideaDate", item.date || "");
    setVal("ideaReadTime", item.readTime || "");
    setVal("ideaTitle", item.title || "");
    setVal("ideaSummary", item.summary || "");
    setVal("ideaContent", Array.isArray(item.content) ? item.content.join("\n\n") : item.content || "");
    setVal("ideaImageUrl", item.image || "");
    syncImagePreview("ideaImageUrl", "ideaPreview", "ideaRemoveImgBtn");
  } else if (section === "events") {
    setVal("evCategory", item.category || "zirve");
    setVal("evDate", item.date || "");
    setVal("evPlace", item.place || "");
    setVal("evTitle", item.title || "");
    setVal("evDesc", item.description || "");
    setVal("evImageUrl", item.image || "");
    syncImagePreview("evImageUrl", "evPreview", "evRemoveImgBtn");
  } else if (section === "projects") {
    setVal("projTitle", item.title || "");
    setVal("projYear", item.year || "");
    setVal("projStatus", item.status || "");
    setVal("projDesc", item.description || "");
    setVal("projStack", Array.isArray(item.stack) ? item.stack.join(", ") : item.stack || "");
    setVal("projGithub", item.githubUrl || "");
    setVal("projLive", item.liveUrl || "");
  } else if (section === "socialPosts") {
    setSocialPlatformUI(item.platform || "instagram");
    setVal("socDate", item.date || "");
    setVal("socMetric", item.metric || "");
    setVal("socTitle", item.title || "");
    setVal("socExcerpt", item.excerpt || "");
    setVal("socYtId", item.youtubeId || "");
    setVal("socUrl", item.url && item.url !== "#" ? item.url : "");
    setVal("socImageUrl", item.image || "");
    syncImagePreview("socImageUrl", "socPreview", "socRemoveImgBtn");
  }

  form.scrollIntoView({ behavior: "smooth", block: "start" });
}

function cancelEditing(formId) {
  const form = document.getElementById(formId);
  if (!form) return;
  delete form.dataset.editId;
  form.reset();

  document.querySelectorAll(".admin-item-row.editing").forEach((r) => r.classList.remove("editing"));

  const heading = document.querySelector(`[data-heading-for="${formId}"]`);
  if (heading && heading.dataset.defaultTitle) heading.textContent = heading.dataset.defaultTitle;

  const submitBtn = document.querySelector(`[data-submit-for="${formId}"]`);
  if (submitBtn && submitBtn.dataset.defaultLabel) submitBtn.textContent = submitBtn.dataset.defaultLabel;

  document.querySelector(`[data-cancel-edit="${formId}"]`)?.classList.add("hidden");

  if (formId === "formSocial") {
    setSocialPlatformUI("instagram");
    syncImagePreview("socImageUrl", "socPreview", "socRemoveImgBtn");
  } else if (formId === "formEvent") {
    syncImagePreview("evImageUrl", "evPreview", "evRemoveImgBtn");
  } else if (formId === "formIdea") {
    syncImagePreview("ideaImageUrl", "ideaPreview", "ideaRemoveImgBtn");
  }
}

function hydrateProfileForm(profile, institutions) {
  if (!profile) return;
  setVal("profBrand", profile.brandName);
  setVal("profName", profile.name);
  setVal("profRole", profile.role);
  setVal("profStatus", profile.status);
  setVal("profBio", profile.bio);
  setVal("profEmail", profile.email);
  setVal("profAvatar", profile.avatar);
  setVal("profInterests", (profile.interests || []).join(", "));
  setVal("profNow", (profile.now || []).join("\n"));
  setVal("profInstitutions", (institutions || []).join(", "));
}

/* ==========================================================================
   PUBLISH FORMS
   ========================================================================== */
function initPublishForms() {
  const platformLabels = {
    instagram: "Instagram",
    linkedin: "LinkedIn",
    github: "GitHub",
    youtube: "YouTube",
  };

  const eventLabels = {
    zirve: "Zirve",
    sirket: "Şirket & Kurum",
    etkinlik: "Topluluk",
  };

  // Social Post
  document.getElementById("formSocial")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const platform = val("socPlatform") || "instagram";
    const item = {
      platform,
      platformLabel: platformLabels[platform] || platform,
      date: val("socDate"),
      title: val("socTitle"),
      excerpt: val("socExcerpt"),
      metric: val("socMetric") || "Yeni",
      url: val("socUrl") || "#",
      image: val("socImageUrl") || null,
    };
    const ytId = val("socYtId");
    item.youtubeId = platform === "youtube" && ytId ? ytId : null;

    await publishItem("socialPosts", item, e.target, "socPreview", "socRemoveImgBtn");
  });

  // Blog / Idea
  document.getElementById("formIdea")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const paragraphs = val("ideaContent")
      .split(/\n\s*\n/)
      .map((p) => p.trim())
      .filter(Boolean);

    const item = {
      tag: val("ideaTag"),
      date: val("ideaDate"),
      readTime: val("ideaReadTime"),
      title: val("ideaTitle"),
      summary: val("ideaSummary"),
      content: paragraphs,
      image: val("ideaImageUrl") || null,
    };
    await publishItem("ideas", item, e.target, "ideaPreview", "ideaRemoveImgBtn");
  });

  // Event / Summit
  document.getElementById("formEvent")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const category = val("evCategory");
    const item = {
      category,
      categoryLabel: eventLabels[category] || category,
      date: val("evDate"),
      place: val("evPlace"),
      title: val("evTitle"),
      description: val("evDesc"),
      image: val("evImageUrl") || null,
    };
    await publishItem("events", item, e.target, "evPreview", "evRemoveImgBtn");
  });

  // Project
  document.getElementById("formProject")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const item = {
      title: val("projTitle"),
      year: val("projYear"),
      status: val("projStatus"),
      description: val("projDesc"),
      stack: val("projStack")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      githubUrl: val("projGithub"),
      liveUrl: val("projLive") || "#",
    };
    await publishItem("projects", item, e.target);
  });

  // Profile
  document.getElementById("formProfile")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const profile = {
      brandName: val("profBrand"),
      name: val("profName"),
      role: val("profRole"),
      status: val("profStatus"),
      bio: val("profBio"),
      email: val("profEmail"),
      avatar: val("profAvatar"),
      interests: val("profInterests")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      now: val("profNow")
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean),
    };
    const institutions = val("profInstitutions")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);

    const res = await fetch("/api/admin/profile", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile, institutions }),
    });
    if (res.ok) {
      showToast("Profil ve kurumlar güncellendi!");
    } else {
      showToast("Güncelleme başarısız.", true);
    }
  });
}

async function publishItem(section, item, form, previewId, removeBtnId) {
  const editId = form.dataset.editId;
  const isEditing = Boolean(editId);

  const res = await fetch("/api/admin/item", {
    method: isEditing ? "PUT" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(isEditing ? { section, id: editId, item } : { section, item }),
  });

  if (res.ok) {
    if (isEditing) {
      cancelEditing(form.id);
      showToast("İçerik başarıyla güncellendi!");
    } else {
      form.reset();
      if (form.id === "formSocial") setSocialPlatformUI("instagram");
      if (previewId) document.getElementById(previewId)?.classList.add("hidden");
      if (removeBtnId) document.getElementById(removeBtnId)?.classList.add("hidden");
      showToast("İçerik başarıyla yayınlandı!");
    }
    await loadAdminContent();
  } else {
    const data = await res.json().catch(() => ({}));
    showToast(data.error || "İşlem başarısız.", true);
  }
}

/* ==========================================================================
   HELPERS
   ========================================================================== */
function val(id) {
  return (document.getElementById(id)?.value || "").trim();
}

function setVal(id, value) {
  const el = document.getElementById(id);
  if (el && value !== undefined) el.value = value;
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el && value !== undefined) el.textContent = value;
}

function showToast(msg, isError = false) {
  const toast = document.getElementById("adminToast");
  if (!toast) return;
  toast.textContent = msg;
  toast.style.background = isError ? "#ef4444" : "";
  toast.style.color = isError ? "#fff" : "";
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2600);
}

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
