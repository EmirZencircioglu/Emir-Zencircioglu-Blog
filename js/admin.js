/**
 * ADMIN PANELİ İSTEMCİ MANTIĞI (AYRI SAYFA / GÖRÜNÜM YÖNETİMİ)
 */

const VALID_VIEWS = ["overview", "blog", "events", "projects", "social", "credentials", "cv", "inbox", "automation", "hero", "profile"];
let ADMIN_CONTENT = {};

document.addEventListener("DOMContentLoaded", async () => {
  initNavigation();
  initPlatformSelector();
  initImageUpload("ideaFile", "ideaImageUrl", "ideaPreview", "ideaAddImgBtn", "ideaRemoveImgBtn");
  initImageUpload("socFile", "socImageUrl", "socPreview", "socAddImgBtn", "socRemoveImgBtn");
  initImageUpload("evFile", "evImageUrl", "evPreview", "evAddImgBtn", "evRemoveImgBtn");
  initImageUpload("projFile", "projImageUrl", "projPreview", "projAddImgBtn", "projRemoveImgBtn");
  initImageUpload("heroFile", "heroImageUrl", "heroPreview", "heroAddImgBtn", "heroRemoveImgBtn");
  initImageUpload("profFile", "profAvatar", "profPreview", "profAddImgBtn", "profRemoveImgBtn");
  initCvUpload();
  initAuthForms();
  initPublishForms();
  initCancelEditButtons();
  initAutomationControls();
  initInboxAndAnalyticsControls();

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

  hydrateSiteAndProfileForms(content);
  updateOverviewCounts(content);

  renderSectionList("listIdeas", "blogListCount", "ideas", content.ideas || [], (x) => `${x.tag} · ${x.date}`, "yazı");
  renderSectionList("listEvents", "eventsListCount", "events", content.events || [], (x) => `${x.categoryLabel} · ${x.place} · ${x.date}`, "etkinlik");
  renderSectionList("listProjects", "projectsListCount", "projects", content.projects || [], (x) => `${x.year} · ${x.status}`, "proje");
  renderSectionList("listSocial", "socialListCount", "socialPosts", content.socialPosts || [], (x) => `${x.platformLabel} · ${x.date}`, "gönderi");
  renderSectionList("listCredentials", "credentialsListCount", "credentials", content.credentials || [], (x) => `${x.kindLabel || x.kind} · ${x.org || ""}`, "kayıt");

  await loadAutomationInfo();
  await loadInboxAndAnalytics();
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
  updateGeminiStatusUI(info);
}

function updateGeminiStatusUI(info) {
  const geminiStatus = document.getElementById("geminiStatusText");
  if (!geminiStatus) return;
  if (info.geminiConfigured) {
    const srcLabel = info.geminiSource === "env" ? "Railway Ortam Değişkeni (GEMINI_API_KEY)" : "Admin Paneli";
    geminiStatus.textContent = `Bağlı (${srcLabel}) · Anahtar: ${info.geminiMasked || "****"}`;
  } else {
    geminiStatus.textContent = "Henüz Gemini API anahtarı bağlı değil.";
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

  document.getElementById("formGeminiKey")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const apiKey = val("geminiApiKeyInput");
    if (!apiKey) {
      showToast("Lütfen geçerli bir Gemini API anahtarı gir.", true);
      return;
    }
    const res = await fetch("/api/admin/gemini", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ apiKey }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      setVal("geminiApiKeyInput", "");
      updateGeminiStatusUI(data);
      showToast("Gemini API anahtarı kaydedildi!");
    } else {
      showToast(data.error || "API anahtarı kaydedilemedi.", true);
    }
  });

  document.getElementById("clearGeminiKeyBtn")?.addEventListener("click", async () => {
    if (!confirm("Admin panelinde kayıtlı Gemini API anahtarını silmek istediğine emin misin?")) return;
    const res = await fetch("/api/admin/gemini", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ apiKey: "" }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      updateGeminiStatusUI(data);
      showToast("Kayıtlı Gemini anahtarı temizlendi.");
    } else {
      showToast(data.error || "İşlem başarısız.", true);
    }
  });
}

function updateOverviewCounts(content) {
  setText("countIdeas", (content.ideas || []).length);
  setText("countEvents", (content.events || []).length);
  setText("countProjects", (content.projects || []).length);
  setText("countSocial", (content.socialPosts || []).length);
  setText("countCredentials", (content.credentials || []).length);
  const hasTr = Boolean((content.profile?.cvUrlTr || content.profile?.cvUrl || "").trim());
  const hasEn = Boolean((content.profile?.cvUrlEn || "").trim());
  const cvLabel = hasTr && hasEn ? "TR + EN ✓" : hasTr ? "TR ✓" : hasEn ? "EN ✓" : "Yok";
  setText("countCvStatus", cvLabel);
}

let REORDER_BUSY = false;

async function persistSectionOrder(section, orderedIds, listEl) {
  if (REORDER_BUSY) return;
  REORDER_BUSY = true;
  const prevScroll = listEl ? listEl.scrollTop : 0;
  try {
    const res = await fetch("/api/admin/reorder", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ section, ids: orderedIds }),
    });
    if (res.ok) {
      showToast("Sıralama güncellendi.");
      await loadAdminContent();
      if (listEl) listEl.scrollTop = prevScroll;
    } else {
      const data = await res.json().catch(() => ({}));
      showToast(data.error || "Sıralama kaydedilemedi.", true);
    }
  } catch {
    showToast("Sıralama kaydedilirken bağlantı hatası oluştu.", true);
  } finally {
    REORDER_BUSY = false;
  }
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
      (item, index) => `
      <div class="admin-item-row reorderable" draggable="true" data-section="${escapeHtml(section)}" data-row-id="${escapeHtml(item.id)}">
        <span class="drag-handle" title="Sürükleyerek sırayı değiştir" aria-hidden="true">⋮⋮</span>
        <span class="item-order-num">${index + 1}</span>
        <div class="admin-item-info">
          <div class="admin-item-title">${escapeHtml(item.title)}</div>
          <div class="admin-item-meta">${escapeHtml(metaFormatter(item))}</div>
        </div>
        <div class="item-actions">
          <button type="button" class="order-btn" data-move-section="${escapeHtml(section)}" data-move-id="${escapeHtml(item.id)}" data-move-dir="-1" title="Yukarı taşı" aria-label="Yukarı taşı" ${index === 0 ? "disabled" : ""}>
            ↑
          </button>
          <button type="button" class="order-btn" data-move-section="${escapeHtml(section)}" data-move-id="${escapeHtml(item.id)}" data-move-dir="1" title="Aşağı taşı" aria-label="Aşağı taşı" ${index === items.length - 1 ? "disabled" : ""}>
            ↓
          </button>
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

  // Yukarı / Aşağı butonları ile sıralama
  list.querySelectorAll("[data-move-id]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const targetId = btn.dataset.moveId;
      const dir = Number(btn.dataset.moveDir);
      const currentIds = items.map((x) => x.id);
      const idx = currentIds.indexOf(targetId);
      const swapIdx = idx + dir;
      if (idx < 0 || swapIdx < 0 || swapIdx >= currentIds.length) return;
      [currentIds[idx], currentIds[swapIdx]] = [currentIds[swapIdx], currentIds[idx]];
      await persistSectionOrder(section, currentIds, list);
    });
  });

  // Sürükle-bırak (Drag & Drop) ile sıralama
  let draggedId = null;
  const rows = list.querySelectorAll(".admin-item-row.reorderable");
  const clearDropMarks = () => {
    rows.forEach((r) => r.classList.remove("drag-over-top", "drag-over-bottom"));
  };

  rows.forEach((row) => {
    row.addEventListener("dragstart", (e) => {
      if (e.target.closest("button")) {
        e.preventDefault();
        return;
      }
      draggedId = row.dataset.rowId;
      row.classList.add("dragging");
      if (e.dataTransfer) {
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", draggedId || "");
      }
    });

    row.addEventListener("dragover", (e) => {
      if (!draggedId || draggedId === row.dataset.rowId) return;
      e.preventDefault();
      if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
      const rect = row.getBoundingClientRect();
      const isAfter = e.clientY > rect.top + rect.height / 2;
      clearDropMarks();
      row.classList.add(isAfter ? "drag-over-bottom" : "drag-over-top");
    });

    row.addEventListener("dragleave", () => {
      row.classList.remove("drag-over-top", "drag-over-bottom");
    });

    row.addEventListener("drop", async (e) => {
      e.preventDefault();
      const targetId = row.dataset.rowId;
      if (!draggedId || !targetId || draggedId === targetId) {
        clearDropMarks();
        return;
      }
      const rect = row.getBoundingClientRect();
      const isAfter = e.clientY > rect.top + rect.height / 2;
      clearDropMarks();

      const currentIds = items.map((x) => x.id);
      const fromIdx = currentIds.indexOf(draggedId);
      if (fromIdx < 0) return;
      currentIds.splice(fromIdx, 1);
      let toIdx = currentIds.indexOf(targetId);
      if (toIdx < 0) return;
      if (isAfter) toIdx += 1;
      currentIds.splice(toIdx, 0, draggedId);
      draggedId = null;
      await persistSectionOrder(section, currentIds, list);
    });

    row.addEventListener("dragend", () => {
      draggedId = null;
      row.classList.remove("dragging");
      clearDropMarks();
    });
  });

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
    credentials: "formCredential",
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
    setVal("evLinkedinUrl", item.linkedinUrl || "");
    setVal("evInstagramUrl", item.instagramUrl || "");
    setVal("evOtherUrl", item.otherUrl || "");
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
    setVal("projImageUrl", item.image || "");
    syncImagePreview("projImageUrl", "projPreview", "projRemoveImgBtn");
  } else if (section === "credentials") {
    setVal("credKind", item.kind || "egitim");
    setVal("credDate", item.date || "");
    setVal("credTitle", item.title || "");
    setVal("credOrg", item.org || "");
    setVal("credDetail", item.detail || "");
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
  } else if (formId === "formProject") {
    syncImagePreview("projImageUrl", "projPreview", "projRemoveImgBtn");
  }
}

function hydrateSiteAndProfileForms(content) {
  const profile = content.profile || {};
  const hero = content.hero || {};
  const site = content.site || {};
  const contact = content.contact || {};
  const institutions = content.institutions || [];

  // Giriş (Hero) & Vitrin
  setVal("heroImageUrl", hero.portraitImage || "");
  syncImagePreview("heroImageUrl", "heroPreview", "heroRemoveImgBtn");
  setVal("heroKickerInput", hero.kicker || "FİNANS · SERMAYE PİYASALARI · TEKNOLOJİ");
  setVal("heroTitleLine1Input", hero.titleLine1 || "Piyasaları okuyan,");
  setVal("heroTitlePrefixInput", hero.titlePrefix || "teknolojiyle");
  setVal("heroTitleHighlightInput", hero.titleHighlight || "değer üreten");
  setVal("heroTitleLine3Input", hero.titleLine3 || "bir bakış açısı.");
  setVal(
    "heroSubtitleInput",
    hero.subtitle ||
      "Yazılım ve ürün geliştirme çalışmalarımı sermaye piyasaları, yatırım ve hazine perspektifimle birleştiriyor; katıldığım kurumları, zirveleri ve fikirlerimi burada şeffafça paylaşıyorum."
  );
  setVal(
    "heroPillarsInput",
    (Array.isArray(hero.pillars) && hero.pillars.length
      ? hero.pillars
      : ["Sermaye Piyasaları & Yatırım", "Hazine & Bankacılık", "Yazılım & Dijital Ürün"]
    ).join("\n")
  );
  setVal("heroPrimaryCtaInput", hero.primaryCtaText || "Benimle Tanışın");
  setVal("heroSecondaryCtaInput", hero.secondaryCtaText || "Projeler & Zirveler");

  setVal("topbarCtaInput", site.topCtaText || "Tanışalım ↗");
  setVal(
    "tabRolesInput",
    (Array.isArray(site.tabRoles) && site.tabRoles.length
      ? site.tabRoles
      : ["Sermaye Piyasaları", "Finans", "Hazine & Yatırım", "Teknoloji", "Fintech & Analiz"]
    ).join(", ")
  );
  setVal(
    "topTickerItemsInput",
    (Array.isArray(site.tickerItems) && site.tickerItems.length
      ? site.tickerItems
      : ["SERMAYE PİYASALARI", "YATIRIM & HAZİNE", "YAZILIM & FİNTECH", "ZİRVELER & KURUMLAR", "AÇIK KAYNAK PROJELER"]
    ).join(", ")
  );
  setVal("secAboutPrefix", site.aboutTitlePrefix || "Disiplinler Arası");
  setVal("secAboutHighlight", site.aboutTitleHighlight || "Profil");
  setVal("secProjectsPrefix", site.projectsTitlePrefix || "Ürettiğim");
  setVal("secProjectsHighlight", site.projectsTitleHighlight || "Sistemler");
  setVal("secEventsPrefix", site.eventsTitlePrefix || "Katıldığım");
  setVal("secEventsHighlight", site.eventsTitleHighlight || "Ekosistemler");
  setVal("secIdeasPrefix", site.ideasTitlePrefix || "Notlar &");
  setVal("secIdeasHighlight", site.ideasTitleHighlight || "Bakış Açıları");
  setVal("secSocialPrefix", site.socialTitlePrefix || "Instagram, LinkedIn, GitHub &");
  setVal("secSocialHighlight", site.socialTitleHighlight || "YouTube");
  const pulseCheck = document.getElementById("showMarketPulseCheck");
  if (pulseCheck) pulseCheck.checked = site.showMarketPulse !== false;

  // Profil, Kurumlar & Tanışalım
  setVal("profBrand", profile.brandName || "");
  setVal("profName", profile.name || "");
  setVal("profRole", profile.role || "");
  setVal("profStatus", profile.status || "");
  setVal("profBio", profile.bio || "");
  setVal("profEmail", profile.email || "");
  setVal("profAvatar", profile.avatar || "");
  syncImagePreview("profAvatar", "profPreview", "profRemoveImgBtn");
  const cvTr = (profile.cvUrlTr || profile.cvUrl || "").trim();
  const cvEn = (profile.cvUrlEn || "").trim();
  setVal("cvTrUrlInput", cvTr);
  setVal("cvEnUrlInput", cvEn);
  setVal("profCvTrInput", cvTr);
  setVal("profCvEnInput", cvEn);
  syncCvPreview();
  setVal("profInterests", (profile.interests || []).join(", "));
  setVal("profNow", (profile.now || []).join("\n"));
  setVal("profInstitutions", institutions.join(", "));

  setVal("profPhone", contact.phoneDisplay || "0537 775 12 24");
  setVal("profContactPrefix", contact.titlePrefix || "Sermaye piyasaları, hazine ve teknolojinin kesişiminde");
  setVal("profContactHighlight", contact.titleHighlight || "değer üretmeye hazırım.");
  setVal(
    "profContactDesc",
    contact.description ||
      "Üniversite eğitimimi yazılım projeleri ve zirvelerle beslerken sermaye piyasaları, yatırım ve hazine süreçlerinde de kendimi aktif olarak geliştiriyorum. Büyük ölçekli bankaların ve kurumsal şirketlerin hazine, yatırım veya teknoloji ekiplerinde sorumluluk alarak öğrenmeye ve somut katkı sunmaya açığım."
  );
  setVal("profFooterNote", contact.footerNote || "Tüm hakları saklıdır.");

  const links = profile.socialLinks || [];
  const findLink = (label) => (links.find((l) => (l.label || "").toLowerCase() === label.toLowerCase()) || {}).url || "";
  setVal("profSocInstagram", findLink("Instagram"));
  setVal("profSocLinkedIn", findLink("LinkedIn"));
  setVal("profSocGitHub", findLink("GitHub"));
  setVal("profSocYouTube", findLink("YouTube"));
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
      linkedinUrl: val("evLinkedinUrl") || null,
      instagramUrl: val("evInstagramUrl") || null,
      otherUrl: val("evOtherUrl") || null,
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
      image: val("projImageUrl") || null,
    };
    await publishItem("projects", item, e.target, "projPreview", "projRemoveImgBtn");
  });

  // Eğitim, Sertifika & Yetkinlikler
  const credLabels = {
    egitim: "Eğitim",
    sertifika: "Sertifika",
    yetkinlik: "Yetkinlik",
  };
  document.getElementById("formCredential")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const kind = val("credKind") || "egitim";
    const item = {
      kind,
      kindLabel: credLabels[kind] || kind,
      date: val("credDate"),
      title: val("credTitle"),
      org: val("credOrg"),
      detail: val("credDetail"),
    };
    await publishItem("credentials", item, e.target);
  });

  // Giriş (Hero) & Vitrin Ayarları
  document.getElementById("formHero")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const hero = {
      portraitImage: val("heroImageUrl") || null,
      kicker: val("heroKickerInput"),
      titleLine1: val("heroTitleLine1Input"),
      titlePrefix: val("heroTitlePrefixInput"),
      titleHighlight: val("heroTitleHighlightInput"),
      titleLine3: val("heroTitleLine3Input"),
      subtitle: val("heroSubtitleInput"),
      pillars: val("heroPillarsInput")
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean),
      primaryCtaText: val("heroPrimaryCtaInput"),
      secondaryCtaText: val("heroSecondaryCtaInput"),
    };
    const site = {
      topCtaText: val("topbarCtaInput"),
      tabRoles: val("tabRolesInput")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      tickerItems: val("topTickerItemsInput")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      aboutTitlePrefix: val("secAboutPrefix"),
      aboutTitleHighlight: val("secAboutHighlight"),
      projectsTitlePrefix: val("secProjectsPrefix"),
      projectsTitleHighlight: val("secProjectsHighlight"),
      eventsTitlePrefix: val("secEventsPrefix"),
      eventsTitleHighlight: val("secEventsHighlight"),
      ideasTitlePrefix: val("secIdeasPrefix"),
      ideasTitleHighlight: val("secIdeasHighlight"),
      socialTitlePrefix: val("secSocialPrefix"),
      socialTitleHighlight: val("secSocialHighlight"),
      showMarketPulse: document.getElementById("showMarketPulseCheck")?.checked !== false,
    };

    const res = await fetch("/api/admin/site", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hero, site }),
    });
    if (res.ok) {
      showToast("Giriş ekranı ve vitrin ayarları güncellendi!");
      await loadAdminContent();
    } else {
      showToast("Güncelleme başarısız.", true);
    }
  });

  // Profile, Institutions, Contact & Social Links
  document.getElementById("formProfile")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const socialLinks = [
      { label: "Instagram", url: val("profSocInstagram") || "https://instagram.com" },
      { label: "LinkedIn", url: val("profSocLinkedIn") || "https://linkedin.com" },
      { label: "GitHub", url: val("profSocGitHub") || "https://github.com" },
      { label: "YouTube", url: val("profSocYouTube") || "https://youtube.com" },
    ];
    const profile = {
      brandName: val("profBrand"),
      name: val("profName"),
      role: val("profRole"),
      status: val("profStatus"),
      bio: val("profBio"),
      email: val("profEmail"),
      avatar: val("profAvatar"),
      cvUrlTr: val("profCvTrInput") || null,
      cvUrlEn: val("profCvEnInput") || null,
      cvUrl: val("profCvTrInput") || val("profCvEnInput") || null,
      interests: val("profInterests")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      now: val("profNow")
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean),
      socialLinks,
    };
    const institutions = val("profInstitutions")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const contact = {
      phoneDisplay: val("profPhone"),
      titlePrefix: val("profContactPrefix"),
      titleHighlight: val("profContactHighlight"),
      description: val("profContactDesc"),
      footerNote: val("profFooterNote"),
    };

    const res = await fetch("/api/admin/profile", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile, institutions, contact }),
    });
    if (res.ok) {
      showToast("Profil, kurumlar ve iletişim bilgileri güncellendi!");
      await loadAdminContent();
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

/* ==========================================================================
   TÜRKÇE & İNGİLİZCE PDF CV YÜKLEME, LİNK YÖNETİMİ VE ÖNİZLEME
   ========================================================================== */
function syncSingleCvCard(langKey) {
  const isTr = langKey === "tr";
  const prefix = isTr ? "cvTr" : "cvEn";
  const url = val(`${prefix}UrlInput`);
  const removeBtn = document.getElementById(`${prefix}RemoveBtn`);
  const actionsRow = document.getElementById(`${prefix}ActionsRow`);
  const openLink = document.getElementById(`${prefix}OpenLink`);
  const dlLink = document.getElementById(`${prefix}DownloadLink`);
  const statusLbl = document.getElementById(`${prefix}StatusLabel`);
  const previewState = document.getElementById(`${prefix}PreviewState`);
  const previewFrame = document.getElementById(`${prefix}PreviewFrame`);

  removeBtn?.classList.toggle("hidden", !url);
  actionsRow?.classList.toggle("hidden", !url);
  if (statusLbl) {
    statusLbl.textContent = url
      ? `Aktif ${isTr ? "Türkçe" : "İngilizce"} CV Yayında`
      : `Henüz ${isTr ? "Türkçe" : "İngilizce"} CV yüklenmedi.`;
  }
  if (previewState) previewState.textContent = url ? "Yayında ✓" : "Dosya bekleniyor";

  if (url) {
    const isLocalPdf = url.startsWith("/") && url.toLowerCase().includes(".pdf");
    const dlUrl = isLocalPdf
      ? `${url}${url.includes("?") ? "&" : "?"}download=1&lang=${langKey}`
      : url;
    if (openLink) openLink.href = url;
    if (dlLink) dlLink.href = dlUrl;
    if (previewFrame) {
      if (isLocalPdf || url.toLowerCase().endsWith(".pdf")) {
        if (previewFrame.getAttribute("src") !== url) previewFrame.src = url;
        previewFrame.classList.remove("hidden");
      } else {
        previewFrame.classList.add("hidden");
      }
    }
  } else if (previewFrame) {
    previewFrame.removeAttribute("src");
    previewFrame.classList.add("hidden");
  }
}

function syncCvPreview() {
  syncSingleCvCard("tr");
  syncSingleCvCard("en");
}

async function persistCvUrls(trUrl, enUrl) {
  const cleanTr = (trUrl || "").trim() || null;
  const cleanEn = (enUrl || "").trim() || null;
  const res = await fetch("/api/admin/profile", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      profile: {
        cvUrlTr: cleanTr,
        cvUrlEn: cleanEn,
        cvUrl: cleanTr || cleanEn,
      },
    }),
  });
  if (!res.ok) {
    showToast("CV bağlantısı kaydedilemedi.", true);
    return false;
  }
  setVal("cvTrUrlInput", cleanTr || "");
  setVal("cvEnUrlInput", cleanEn || "");
  setVal("profCvTrInput", cleanTr || "");
  setVal("profCvEnInput", cleanEn || "");
  if (ADMIN_CONTENT.profile) {
    ADMIN_CONTENT.profile.cvUrlTr = cleanTr;
    ADMIN_CONTENT.profile.cvUrlEn = cleanEn;
    ADMIN_CONTENT.profile.cvUrl = cleanTr || cleanEn;
  }
  updateOverviewCounts(ADMIN_CONTENT);
  syncCvPreview();
  return true;
}

function initCvUpload() {
  function bindCvSlot(langKey) {
    const isTr = langKey === "tr";
    const prefix = isTr ? "cvTr" : "cvEn";
    const label = isTr ? "Türkçe CV" : "İngilizce CV";

    const fileInput = document.getElementById(`${prefix}File`);
    const uploadBtn = document.getElementById(`${prefix}UploadBtn`);
    const removeBtn = document.getElementById(`${prefix}RemoveBtn`);
    const saveUrlBtn = document.getElementById(`${prefix}SaveUrlBtn`);
    const dropZone = document.getElementById(`${prefix}DropZone`);

    async function handlePdf(file) {
      if (!file) return;
      if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
        showToast("Lütfen geçerli bir PDF dosyası seç.", true);
        return;
      }
      const reader = new FileReader();
      reader.onload = async () => {
        try {
          const res = await fetch("/api/admin/upload", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ filename: file.name, dataUrl: reader.result }),
          });
          const data = await res.json();
          if (!res.ok) {
            showToast(data.error || "PDF yüklenemedi.", true);
            return;
          }
          const nextTr = isTr ? data.url : val("cvTrUrlInput");
          const nextEn = isTr ? val("cvEnUrlInput") : data.url;
          const saved = await persistCvUrls(nextTr, nextEn);
          if (saved) showToast(`${label} yüklendi ve sitede yayınlandı!`);
        } catch {
          showToast("CV yüklenirken hata oluştu.", true);
        }
      };
      reader.readAsDataURL(file);
    }

    uploadBtn?.addEventListener("click", () => fileInput?.click());
    fileInput?.addEventListener("change", () => handlePdf(fileInput.files?.[0]));

    removeBtn?.addEventListener("click", async () => {
      if (!confirm(`${label} dosyasını yayından kaldırmak istediğine emin misin?`)) return;
      if (fileInput) fileInput.value = "";
      const nextTr = isTr ? "" : val("cvTrUrlInput");
      const nextEn = isTr ? val("cvEnUrlInput") : "";
      const saved = await persistCvUrls(nextTr, nextEn);
      if (saved) showToast(`${label} yayından kaldırıldı.`);
    });

    saveUrlBtn?.addEventListener("click", async () => {
      const nextTr = val("cvTrUrlInput");
      const nextEn = val("cvEnUrlInput");
      const saved = await persistCvUrls(nextTr, nextEn);
      if (saved) showToast(`${label} bağlantısı kaydedildi!`);
    });

    if (dropZone) {
      dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.style.borderColor = "var(--brand)";
      });
      dropZone.addEventListener("dragleave", () => {
        dropZone.style.borderColor = "var(--border-hover)";
      });
      dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.style.borderColor = "var(--border-hover)";
        const f = e.dataTransfer?.files?.[0];
        if (f) handlePdf(f);
      });
    }
  }

  bindCvSlot("tr");
  bindCvSlot("en");
}

/* ==========================================================================
   GELEN MESAJLAR & GEMINI CHATBOT SORU ANALİZİ
   ========================================================================== */
async function loadInboxAndAnalytics() {
  try {
    const [msgRes, anaRes] = await Promise.all([
      fetch("/api/admin/messages", { cache: "no-store" }),
      fetch("/api/admin/analytics", { cache: "no-store" }),
    ]);

    if (msgRes.ok) {
      const msgData = await msgRes.json();
      const unread = msgData.unreadCount || 0;
      setText("countUnreadMessages", unread);
      setText("inboxUnreadBadge", `${unread} okunmamış`);
      const sideBadge = document.getElementById("sidebarUnreadBadge");
      if (sideBadge) {
        sideBadge.textContent = String(unread);
        sideBadge.classList.toggle("hidden", unread === 0);
      }
      renderInboxMessages(msgData.messages || []);
    }

    if (anaRes.ok) {
      const ana = await anaRes.json();
      setText("analyticsTotalChats", ana.totalChats || 0);
      setText("analyticsSuccessChats", ana.successChats || 0);
      renderAnalyticsLists(ana.topQuestions || [], ana.recentLogs || []);
    }
  } catch {
    // Sessiz geç
  }
}

function renderInboxMessages(messages) {
  const wrap = document.getElementById("inboxMessagesList");
  if (!wrap) return;
  if (!messages.length) {
    wrap.innerHTML = `<p class="mono-sub">Henüz ziyaretçi mesajı yok.</p>`;
    return;
  }

  wrap.innerHTML = messages
    .map(
      (m) => `
      <div class="admin-item-row" style="align-items:flex-start; ${m.read ? "opacity:0.78;" : "border-color: var(--brand);"}">
        <div class="admin-item-info">
          <div class="admin-item-title">
            ${!m.read ? `<span class="tag-chip" style="margin-right:6px;">YENİ</span>` : ""}
            ${escapeHtml(m.name)} ${m.organization ? `· <span style="color:var(--emerald);">${escapeHtml(m.organization)}</span>` : ""}
          </div>
          <div class="admin-item-meta">${escapeHtml(m.topic || "Genel")} · ${escapeHtml(m.contactInfo || "")} · ${escapeHtml(m.createdAt || "")}</div>
          <p style="margin-top:6px; font-size:0.86rem; line-height:1.5; white-space:pre-wrap;">${escapeHtml(m.message)}</p>
        </div>
        <div class="item-actions">
          <button type="button" class="edit-btn" data-toggle-read="${escapeHtml(m.id)}" data-next-read="${m.read ? "0" : "1"}">${m.read ? "Okunmadı" : "Okundu"}</button>
          <button type="button" class="delete-btn" data-del-msg="${escapeHtml(m.id)}">Sil</button>
        </div>
      </div>
    `
    )
    .join("");

  wrap.querySelectorAll("[data-toggle-read]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const res = await fetch("/api/admin/messages", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: btn.dataset.toggleRead, read: btn.dataset.nextRead === "1" }),
      });
      if (res.ok) await loadInboxAndAnalytics();
    });
  });

  wrap.querySelectorAll("[data-del-msg]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("Bu mesajı kalıcı olarak silmek istediğine emin misin?")) return;
      const res = await fetch("/api/admin/messages", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: btn.dataset.delMsg }),
      });
      if (res.ok) {
        showToast("Mesaj silindi.");
        await loadInboxAndAnalytics();
      }
    });
  });
}

function renderAnalyticsLists(topQuestions, recentLogs) {
  const topWrap = document.getElementById("topQuestionsList");
  if (topWrap) {
    if (!topQuestions.length) {
      topWrap.innerHTML = `<p class="mono-sub">Henüz soru kaydı yok.</p>`;
    } else {
      topWrap.innerHTML = topQuestions
        .map(
          (q) => `
          <div class="admin-item-row chat-log-row">
            <div class="admin-item-info">
              <div class="chat-log-head">
                <div class="admin-item-title">${escapeHtml(q.question)}</div>
                <span class="tag-chip">${q.count}×</span>
              </div>
              ${
                q.latestAnswer
                  ? `<details class="chat-log-details">
                      <summary>Son Cevabı Gör</summary>
                      <div class="chat-log-answer">${escapeHtml(q.latestAnswer)}</div>
                    </details>`
                  : ""
              }
            </div>
          </div>
        `
        )
        .join("");
    }
  }

  const recentWrap = document.getElementById("recentChatLogsList");
  if (recentWrap) {
    if (!recentLogs.length) {
      recentWrap.innerHTML = `<p class="mono-sub">Henüz sohbet kaydı yok.</p>`;
    } else {
      recentWrap.innerHTML = recentLogs
        .map((r) => {
          const hasAnswer = Boolean(r.answer && String(r.answer).trim());
          const summaryLabel = r.ok ? "Emir AI Cevabını Gör" : "Hata Detayını Gör";
          return `
          <div class="admin-item-row chat-log-row ${r.ok ? "" : "is-error"}">
            <div class="admin-item-info">
              <div class="admin-item-title">${escapeHtml(r.question)}</div>
              <div class="admin-item-meta">${escapeHtml(r.createdAt || "")} · ${escapeHtml(r.model || "-")} · ${r.ok ? "Yanıtlandı" : "Hata"}</div>
              ${
                hasAnswer
                  ? `<details class="chat-log-details">
                      <summary>${summaryLabel}</summary>
                      <div class="chat-log-answer ${r.ok ? "" : "is-error"}">${escapeHtml(r.answer)}</div>
                    </details>`
                  : `<div class="chat-log-missing">Önceki kayıt — cevap saklanmamış.</div>`
              }
            </div>
          </div>
        `;
        })
        .join("");
    }
  }
}

function initInboxAndAnalyticsControls() {
  document.getElementById("markAllReadBtn")?.addEventListener("click", async () => {
    const res = await fetch("/api/admin/messages", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ markAllRead: true }),
    });
    if (res.ok) {
      showToast("Tüm mesajlar okundu olarak işaretlendi.");
      await loadInboxAndAnalytics();
    }
  });

  document.getElementById("clearAnalyticsBtn")?.addEventListener("click", async () => {
    if (!confirm("Chatbot soru analiz geçmişini temizlemek istediğine emin misin?")) return;
    const res = await fetch("/api/admin/analytics", { method: "DELETE" });
    if (res.ok) {
      showToast("Sohbet analizi temizlendi.");
      await loadInboxAndAnalytics();
    }
  });
}
