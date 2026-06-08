  const studentDashboardConfig = window.StudentDashboardConfig || {};
  const studentContentProgressUrlTemplate = studentDashboardConfig.contentProgressUrlTemplate || '';
  const studentMessageReadUrlTemplate = studentDashboardConfig.messageReadUrlTemplate || '';
  const studentMessageUnreadUrlTemplate = studentDashboardConfig.messageUnreadUrlTemplate || '';
  const studentMessagesReadAllUrl = studentDashboardConfig.messagesReadAllUrl || '';

  function getCsrfToken() {
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  async function updateStudentContentProgress(contentId, payload) {
    const progressUrl = studentContentProgressUrlTemplate.replace("/0/", `/${contentId}/`);
    const response = await fetch(progressUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error("progress-update-failed");
    }

    return response.json();
  }

  function initStudentContentTracking(root = document) {
    root.querySelectorAll("[data-track-content]").forEach((node) => {
      if (node.dataset.boundTrack === "1") return;
      node.dataset.boundTrack = "1";

      const sendProgress = () => {
        updateStudentContentProgress(node.dataset.trackContent, {
          progress_percent: Number(node.dataset.trackProgress || 10),
        }).catch(() => {});
      };

      if (node.tagName === "IFRAME" || node.tagName === "IMG") {
        node.addEventListener("load", sendProgress, { once: true });
      } else if (node.tagName === "A") {
        node.addEventListener("click", sendProgress);
      } else if (node.tagName === "BUTTON") {
        node.addEventListener("click", sendProgress);
      } else {
        sendProgress();
      }
    });

    root.querySelectorAll("[data-complete-content]").forEach((node) => {
      if (node.dataset.boundTrack === "1") return;
      node.dataset.boundTrack = "1";
      node.addEventListener("click", () => {
        updateStudentContentProgress(node.dataset.completeContent, {
          progress_percent: 100,
          is_completed: true,
        }).then(() => {
          const body = document.getElementById("studentCourseDetailBody");
          if (body && body.dataset.detailUrl && window.htmx) {
            window.htmx.ajax("GET", body.dataset.detailUrl, "#studentCourseDetailBody");
          } else if (!body) {
            window.location.reload();
          }
        }).catch(() => {});
      });
    });

    root.querySelectorAll("[data-media-progress-content]").forEach((node) => {
      if (node.dataset.boundTrack === "1") return;
      node.dataset.boundTrack = "1";
      node.addEventListener("timeupdate", () => {
        if (!node.duration || !Number.isFinite(node.duration) || node.duration <= 0) return;
        const progressPercent = Math.min(100, Math.round((node.currentTime / node.duration) * 100));
        const lastSent = Number(node.dataset.lastSentProgress || 0);
        if (progressPercent < 100 && progressPercent - lastSent < 10) return;
        node.dataset.lastSentProgress = String(progressPercent);
        updateStudentContentProgress(node.dataset.mediaProgressContent, {
          progress_percent: progressPercent,
          last_position: Math.round(node.currentTime),
          is_completed: progressPercent >= 100,
        }).catch(() => {});
      });
      node.addEventListener("ended", () => {
        updateStudentContentProgress(node.dataset.mediaProgressContent, {
          progress_percent: 100,
          is_completed: true,
          last_position: Math.round(node.duration || 0),
        })
          .then(() => {
            const body = document.getElementById("studentCourseDetailBody");
            if (body && body.dataset.detailUrl && window.htmx) {
              window.htmx.ajax("GET", body.dataset.detailUrl, "#studentCourseDetailBody");
            } else if (!body) {
              window.location.reload();
            }
          })
          .catch(() => {});
      });
    });
  }

  function parseDashboardData(id, fallback) {
    const node = document.getElementById(id);
    if (!node) return fallback;
    try {
      return JSON.parse(node.textContent);
    } catch (error) {
      return fallback;
    }
  }

  function studentDashboard() {
    return {
      darkMode: false,
      sidebarCollapsed: false,
      mobileMenu: false,
      search: "",
      searchOpen: false,
      searchResults: [],
      unreadMessages: 0,
      activeNav: "Tableau de bord",
      activeSection: "overview",
      courseDetailUrl: "",
      courseDetailTitle: "",
      courseDetailMode: "reader",
      activeMeta: {
        kicker: "Dashboard",
        title: "Tableau de bord etudiant",
        description: "Accueil rapide avec les actions essentielles.",
        badge: "Accueil"
      },
      navItems: [
        { label: "Tableau de bord", icon: "layout-dashboard", target: "overview" },
        { label: "Mes cours", icon: "book-open-check", target: "courses" },
        { label: "Calendrier", icon: "calendar-days", target: "schedule" },
        { label: "Academique", icon: "graduation-cap", target: "academics" },
        { label: "Notifications", icon: "bell", target: "messages" },
        { label: "Encadrement", icon: "users-round", target: "teachers" },
        { label: "Parametres", icon: "settings-2", target: "settings" },
        { label: "Boutique", icon: "shopping-bag", target: "shop" }
      ],
      sectionMeta: [
        {
          key: "overview",
          kicker: "Dashboard",
          title: "Tableau de bord etudiant",
          description: "Accueil rapide avec les actions essentielles.",
          badge: "Accueil"
        },
        {
          key: "courses",
          kicker: "Cours",
          title: "Mes cours et ressources",
          description: "Consultez vos matieres, ouvrez les contenus et suivez votre progression sans quitter le dashboard.",
          badge: "Section cours"
        },
        {
          key: "schedule",
          kicker: "Planning",
          title: "Emploi du temps hebdomadaire",
          description: "Affichage metier de la semaine, avec vos cours, vos disponibilites et les statuts utiles.",
          badge: "Vue planning"
        },
        {
          key: "messages",
          kicker: "Centre systeme",
          title: "Notifications et activites",
          description: "Suivez les alertes academiques, administratives, financieres et les evenements importants.",
          badge: "Centre notifications"
        },
        {
          key: "academics",
          kicker: "Academique",
          title: "Situation academique",
          description: "Retrouvez votre affectation, vos credits, vos semestres et votre etat academique dans un espace dedie.",
          badge: "Section academique"
        },
        {
          key: "teachers",
          kicker: "Encadrement",
          title: "Equipe enseignante",
          description: "Consultez les enseignants rattaches a vos EC, leurs matieres et les prochains cours publies.",
          badge: "Suivi pedagogique"
        },
        {
          key: "settings",
          kicker: "Compte etudiant",
          title: "Gestion du compte",
          description: "Modifiez votre profil systeme, vos documents, vos preferences et vos acces sans quitter le dashboard.",
          badge: "Centre compte"
        },
        {
          key: "shop",
          kicker: "Boutique",
          title: "Mes commandes boutique",
          description: "Consultez vos commandes, suivez leur statut et effectuez les paiements.",
          badge: "Section boutique"
        }
      ],
      courses: [],
      teachers: [],
      timetable: [],
      upcoming: [],
      messages: [],
      greetingLabel: "Bonjour",
      greetingTone: "Bonne continuation",
      currentTimeLabel: "",
      miniMonthCursor: null,
      miniMonthLabel: "",
      miniWeekLabels: ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"],
      miniMonthCells: [],
      miniStats: [],
      progressBars: [],
      init() {
        this.darkMode = localStorage.getItem("esfe_student_dark") === "1";
        this.sidebarCollapsed = localStorage.getItem("esfe_student_sidebar_collapsed") === "1";
        this.courses = parseDashboardData("student-courses-data", []);
        this.upcoming = parseDashboardData("student-events-data", []);
        this.messages = parseDashboardData("student-messages-data", []);
        this.unreadMessages = Number(parseDashboardData("student-unread-count-data", 0) || 0);
        this.setGreetingByTime();
        this.updateCurrentTime();
        window.setInterval(() => this.updateCurrentTime(), 30000);
        this.miniMonthCursor = new Date();
        this.miniMonthCursor.setDate(1);
        this.buildMiniMonth();
        this.miniStats = parseDashboardData("student-mini-stats-data", []);
        this.progressBars = parseDashboardData("student-progress-bars-data", []);
        this.$watch("darkMode", value => {
          localStorage.setItem("esfe_student_dark", value ? "1" : "0");
          setTimeout(() => window.lucide && lucide.createIcons(), 50);
        });
        this.$watch("sidebarCollapsed", value => {
          localStorage.setItem("esfe_student_sidebar_collapsed", value ? "1" : "0");
          setTimeout(() => window.lucide && lucide.createIcons(), 50);
        });
        window.addEventListener("resize", () => {
          if (window.innerWidth >= 992) {
            this.mobileMenu = false;
          }
        });
        this.$nextTick(() => {
          this.setActiveSection(this.activeSection, this.activeNav);
          this.ensureSectionLoaded(this.activeSection);
          if (window.AOS) {
            AOS.refreshHard();
          }
          if (window.lucide) {
            lucide.createIcons();
          }
        });
        document.addEventListener("click", (event) => {
          const topbar = event.target.closest(".student-topbar");
          if (!topbar) {
            this.searchOpen = false;
          }
        });
      },
      toggleSidebar() {
        if (window.innerWidth < 992) {
          this.mobileMenu = !this.mobileMenu;
          return;
        }
        this.sidebarCollapsed = !this.sidebarCollapsed;
      },
      toggleDarkMode() {
        this.darkMode = !this.darkMode;
      },
      setActive(label) {
        this.activeNav = label;
        this.mobileMenu = false;
      },
      setActiveSection(target, label) {
        const meta = this.sectionMeta.find((item) => item.key === target);
        this.activeSection = target;
        this.activeNav = label || this.activeNav;
        if (meta) {
          this.activeMeta = {
            kicker: meta.kicker,
            title: meta.title,
            description: meta.description,
            badge: meta.badge
          };
        }
        this.mobileMenu = false;
        this.ensureSectionLoaded(target);
      },
      goToSection(target, label) {
        this.setActiveSection(target, label);
      },
      goToMessages() {
        this.goToSection("messages", "Notifications");
      },
      buildSearchSnippet(text) {
        if (!text) return "";
        const compact = text.replace(/\s+/g, " ").trim();
        return compact.length > 92 ? `${compact.slice(0, 92)}...` : compact;
      },
      sectionLabelByKey(sectionKey) {
        const hit = this.navItems.find((item) => item.target === sectionKey);
        return hit ? hit.label : "Section";
      },
      normalizeSearch(text) {
        return (text || "").toString().toLowerCase();
      },
      performGlobalSearch() {
        const query = this.normalizeSearch(this.search).trim();
        if (query.length < 2) {
          this.searchResults = [];
          this.searchOpen = false;
          return;
        }
        this.searchOpen = true;

        // Charge les sections paresseuses pour que la recherche couvre tout le dashboard.
        ["courses", "schedule", "messages", "academics", "settings"].forEach((key) => this.ensureSectionLoaded(key));

        const results = [];
        const pushResult = (scope, title, snippet, sectionKey, uniqueKey) => {
          if (results.some((r) => r.id === uniqueKey)) return;
          results.push({
            id: uniqueKey,
            scope,
            title,
            snippet: this.buildSearchSnippet(snippet),
            sectionKey,
          });
        };

        this.sectionMeta.forEach((meta) => {
          const hay = this.normalizeSearch(`${meta.title} ${meta.description} ${meta.kicker}`);
          if (hay.includes(query)) {
            pushResult("Section", meta.title, meta.description, meta.key, `meta-${meta.key}`);
          }
        });

        this.courses.forEach((course) => {
          const hay = this.normalizeSearch(`${course.title} ${course.code} ${course.ue} ${course.teacher}`);
          if (hay.includes(query)) {
            pushResult("Cours", course.title, `Semestre ${course.semester} Â· ${course.code}`, "courses", `course-${course.id}`);
          }
        });

        this.upcoming.forEach((event, idx) => {
          const hay = this.normalizeSearch(`${event.title} ${event.desc} ${event.branch}`);
          if (hay.includes(query)) {
            pushResult("Calendrier", event.title, event.desc || "Evenement", "schedule", `event-${idx}-${event.title}`);
          }
        });

        this.messages.forEach((msg) => {
          const hay = this.normalizeSearch(`${msg.name} ${msg.text}`);
          if (hay.includes(query)) {
            pushResult("Messages", msg.name, msg.text, "messages", `message-${msg.id || msg.name}`);
          }
        });

        [
          { id: "overview", section: "overview" },
          { id: "courses", section: "courses" },
          { id: "schedule", section: "schedule" },
          { id: "messages", section: "messages" },
          { id: "academics", section: "academics" },
          { id: "settings", section: "settings" },
        ].forEach((entry) => {
          const node = document.getElementById(entry.id);
          if (!node) return;
          const text = (node.innerText || "").replace(/\s+/g, " ").trim();
          if (!text) return;
          if (this.normalizeSearch(text).includes(query)) {
            pushResult(
              "Contenu",
              this.sectionLabelByKey(entry.section),
              text,
              entry.section,
              `content-${entry.id}`
            );
          }
        });

        this.searchResults = results.slice(0, 12);
      },
      openSearchResult(result) {
        this.searchOpen = false;
        this.goToSection(result.sectionKey, this.sectionLabelByKey(result.sectionKey));
      },
      openFirstSearchResult() {
        if (!this.searchResults.length) return;
        this.openSearchResult(this.searchResults[0]);
      },
      async markMessageRead(messageId) {
        const readUrl = studentMessageReadUrlTemplate.replace("/0/", `/${messageId}/`);
        const response = await fetch(readUrl, {
          method: "POST",
          headers: {
            "X-CSRFToken": getCsrfToken(),
          },
        });
        if (!response.ok) return;
        const payload = await response.json();
        this.unreadMessages = Number(payload.unread_count || 0);
        this.refreshSection("messages");
      },
      async markAllMessagesRead() {
        const response = await fetch(studentMessagesReadAllUrl, {
          method: "POST",
          headers: {
            "X-CSRFToken": getCsrfToken(),
          },
        });
        if (!response.ok) return;
        const payload = await response.json();
        this.unreadMessages = Number(payload.unread_count || 0);
        this.refreshSection("messages");
      },
      async markMessageUnread(messageId) {
        const unreadUrl = studentMessageUnreadUrlTemplate.replace("/0/", `/${messageId}/`);
        const response = await fetch(unreadUrl, {
          method: "POST",
          headers: {
            "X-CSRFToken": getCsrfToken(),
          },
        });
        if (!response.ok) return;
        const payload = await response.json();
        this.unreadMessages = Number(payload.unread_count || 0);
        this.refreshSection("messages");
      },
      refreshSection(elementId) {
        const el = document.getElementById(elementId);
        if (!el || !window.htmx) return;
        const url = el.dataset.sectionUrl;
        if (!url) return;
        el.dataset.sectionLoaded = "loading";
        window.htmx.ajax("GET", url, `#${elementId}`);
      },
      setGreetingByTime() {
        const hour = new Date().getHours();
        if (hour >= 5 && hour < 12) {
          this.greetingLabel = "Bonjour";
          this.greetingTone = "Belle matinee a vous";
        } else if (hour >= 12 && hour < 18) {
          this.greetingLabel = "Bon apres-midi";
          this.greetingTone = "Continuez sur votre lancee";
        } else if (hour >= 18 && hour < 22) {
          this.greetingLabel = "Bonsoir";
          this.greetingTone = "Bonne soiree d'etude";
        } else {
          this.greetingLabel = "Bonne nuit";
          this.greetingTone = "Prenez un rythme serein";
        }
      },
      updateCurrentTime() {
        this.currentTimeLabel = new Intl.DateTimeFormat("fr-FR", {
          weekday: "long",
          hour: "2-digit",
          minute: "2-digit",
        }).format(new Date());
      },
      buildMiniMonth() {
        if (!this.miniMonthCursor) return;
        const monthNames = ["Janvier", "Fevrier", "Mars", "Avril", "Mai", "Juin", "Juillet", "Aout", "Septembre", "Octobre", "Novembre", "Decembre"];
        const year = this.miniMonthCursor.getFullYear();
        const month = this.miniMonthCursor.getMonth();

        const firstDay = new Date(year, month, 1);
        let startDate = new Date(firstDay);
        startDate.setDate(startDate.getDate() - (firstDay.getDay() === 0 ? 6 : firstDay.getDay() - 1));

        const today = new Date();
        today.setHours(0, 0, 0, 0);

        this.miniMonthLabel = `${monthNames[month]} ${year}`;
        this.miniMonthCells = Array.from({ length: 42 }).map((_, index) => {
          const cellDate = new Date(startDate);
          cellDate.setDate(startDate.getDate() + index);
          const isCurrent = cellDate.getMonth() === month;
          const isToday = cellDate.getTime() === today.getTime();
          return {
            day: cellDate.getDate(),
            isCurrentMonth: isCurrent,
            isToday: isToday,
          };
        });
      },
      prevMiniMonth() {
        if (!this.miniMonthCursor) return;
        this.miniMonthCursor = new Date(this.miniMonthCursor.getFullYear(), this.miniMonthCursor.getMonth() - 1, 1);
        this.buildMiniMonth();
      },
      nextMiniMonth() {
        if (!this.miniMonthCursor) return;
        this.miniMonthCursor = new Date(this.miniMonthCursor.getFullYear(), this.miniMonthCursor.getMonth() + 1, 1);
        this.buildMiniMonth();
      },
      ensureSectionLoaded(sectionKey) {
        if (!window.htmx) {
          setTimeout(() => this.ensureSectionLoaded(sectionKey), 80);
          return;
        }
        const idsToLoad = [];
        if (sectionKey === "courses") idsToLoad.push("courses");
        if (sectionKey === "schedule") idsToLoad.push("schedule");
        if (sectionKey === "messages") idsToLoad.push("messages");
        if (sectionKey === "academics") idsToLoad.push("academics");
        if (sectionKey === "settings") idsToLoad.push("settings");
        if (sectionKey === "shop") idsToLoad.push("shop");

        idsToLoad.forEach((elementId) => {
          const el = document.getElementById(elementId);
          if (!el) return;
          if (el.dataset.sectionLoaded === "1") return;
          if (el.dataset.sectionLoaded === "loading") return;
          const url = el.dataset.sectionUrl;
          if (!url || !window.htmx) return;
          el.dataset.sectionLoaded = "loading";
          const request = window.htmx.ajax("GET", url, `#${elementId}`);
          if (request && typeof request.then === "function") {
            request.catch(() => {
              el.dataset.sectionLoaded = "0";
            });
          }
          setTimeout(() => {
            if (el.dataset.sectionLoaded === "loading") {
              el.dataset.sectionLoaded = "0";
            }
          }, 8000);
        });
      },
      openCourseDetail(url, title) {
        this.courseDetailUrl = `${url}?partial=1`;
        this.courseDetailTitle = title || "Detail du cours";
        this.courseDetailMode = "reader";
        this.mobileMenu = false;
        document.body.style.overflow = "hidden";
        this.$nextTick(() => {
          const body = document.getElementById("studentCourseDetailBody");
          if (body) {
            body.dataset.detailUrl = this.courseDetailUrl;
            body.innerHTML = `
              <div class="grid min-h-full place-items-center p-8 text-sm font-bold text-[color:var(--muted)]">
                Chargement du lecteur...
              </div>
            `;
          }
          if (window.htmx) {
            window.htmx.ajax("GET", this.courseDetailUrl, "#studentCourseDetailBody");
          }
        });
      },
      openCoursePreview(url, title) {
        this.courseDetailUrl = url;
        this.courseDetailTitle = title || "Apercu du cours";
        this.courseDetailMode = "preview";
        this.mobileMenu = false;
        document.body.style.overflow = "hidden";
        this.$nextTick(() => {
          const body = document.getElementById("studentCourseDetailBody");
          if (body) {
            body.dataset.detailUrl = this.courseDetailUrl;
            body.innerHTML = `
              <div class="grid min-h-full place-items-center p-8 text-sm font-bold text-[color:var(--muted)]">
                Chargement de l'apercu...
              </div>
            `;
          }
          if (window.htmx) {
            window.htmx.ajax("GET", this.courseDetailUrl, "#studentCourseDetailBody");
          }
        });
      },
      closeCourseDetail() {
        this.courseDetailUrl = "";
        this.courseDetailTitle = "";
        this.courseDetailMode = "reader";
        document.body.style.overflow = "";
        const body = document.getElementById("studentCourseDetailBody");
        if (body) {
          delete body.dataset.detailUrl;
          body.innerHTML = "";
        }
      },
      scrollCourses(direction) {
        const rail = document.getElementById("courseRail");
        if (rail) {
          rail.scrollBy({ left: direction * 260, behavior: "smooth" });
        }
      }
    }
  }

  function initializeStudentDynamicContent(root) {
    if (!root) return;
    window.setTimeout(() => {
      if (typeof Alpine !== "undefined") {
        const alpineRoots = [];
        if (root.matches && root.matches("[x-data]")) {
          alpineRoots.push(root);
        }
        root.querySelectorAll("[x-data]").forEach((node) => alpineRoots.push(node));
        const needsManualInit = alpineRoots.some((node) => !node._x_dataStack);
        if (needsManualInit) {
          Alpine.initTree(root);
        }
      }
      if (window.lucide) {
        lucide.createIcons();
      }
      if (window.AOS) {
        AOS.refreshHard();
      }
      initStudentContentTracking(root);
    }, 0);
  }

  document.body.addEventListener("htmx:afterSwap", (evt) => {
    const target = evt.detail && evt.detail.target;
    if (target && target.dataset && target.dataset.sectionUrl) {
      target.dataset.sectionLoaded = "1";
    }
    initializeStudentDynamicContent(target);
  });

  document.body.addEventListener("htmx:responseError", (evt) => {
    const target = evt.detail && evt.detail.target;
    if (!target || !target.dataset.sectionUrl) return;
    target.dataset.sectionLoaded = "0";
    target.innerHTML = `
      <div class="rounded-xl border border-rose-200 bg-rose-50 p-5 text-sm font-semibold text-rose-700">
        Impossible de charger cette section. Reessayez dans un instant.
      </div>
    `;
  });

  document.addEventListener("DOMContentLoaded", () => {
    initStudentContentTracking(document);
  });
