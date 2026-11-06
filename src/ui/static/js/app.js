/**
 * RO-INTEL OSINT Platform - Application Core
 * Single Page Application router, UI view controllers, and theme management.
 * Designed in the minimalist, calm spirit of Linear, Stripe, and Vercel.
 */

const App = {
  currentRoute: 'overview',
  theme: localStorage.getItem('rointel_theme') || 'light', // Light theme default
  systemStatus: (() => {
    try {
      return JSON.parse(localStorage.getItem('rointel_cached_status')) || null;
    } catch { return null; }
  })(),
  availableReports: (() => {
    try {
      return JSON.parse(localStorage.getItem('rointel_cached_reports')) || [];
    } catch { return []; }
  })(),
  selectedReportFilename: null,
  activeRunId: null,
  isExecuting: false,
  streamSubscription: null,
  autoFollowStream: true,

  // Realtime Agents Store for Live View
  agentsState: {
    selector: { name: 'Selector Dosar Presă', status: 'idle', thinking: '', output: '', duration: null },
    extractor: { name: 'Agent 1: Extractor Entit??i', status: 'idle', thinking: '', output: '', duration: null },
    archivist: { name: 'Agent 2: Arhivist & Anomalii', status: 'idle', thinking: '', output: '', duration: null },
    red_team: { name: 'Agent 3: Red Team Strategist', status: 'idle', thinking: '', output: '', duration: null },
    director: { name: 'Agent 4: Director Sinteză', status: 'idle', thinking: '', output: '', duration: null },
    copyeditor: { name: 'Agent 5: Redactor Diacritice', status: 'idle', thinking: '', output: '', duration: null }
  },

  graphState: {
    mode: 'similarity',
    minSimilarity: 0.60,
    searchQuery: '',
    rawGraphData: null,
    simulation: null,
    selectedNode: null,
    svg: null,
    g: null
  },
  dbState: {
    activeTable: 'raw_articles',
    tables: [],
    rows: [],
    columns: [],
    totalRows: 0,
    page: 1,
    pageSize: 25,
    searchQuery: '',
    dateFrom: '',
    dateTo: '',
    selectedRow: null
  },

  // Initialize Application
  async init() {
    this.initTheme();
    this.initClock();
    this.initGlobalEvents();
    this.initRouter();

    if (API.isMockMode) {
      const mockBanner = document.getElementById('mock-warning-banner');
      if (mockBanner) mockBanner.classList.remove('hidden');
    }

    // Initial Telemetry Load
    await this.refreshStatus();
    await this.refreshReports();

    // Periodic telemetry refresh
    setInterval(() => this.refreshStatus(), 12000);
  },

  // ----------------------------------------------------
  // THEME MANAGEMENT (Light Theme Default)
  // ----------------------------------------------------
  initTheme() {
    const urlTheme = new URLSearchParams(window.location.search).get('theme');
    if (urlTheme === 'light' || urlTheme === 'dark' || urlTheme === 'system') {
      this.theme = urlTheme;
    }

    const applyTheme = (theme) => {
      const isDark = theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
      document.documentElement.classList.toggle('dark', isDark);
      
      const themeLabel = document.getElementById('current-theme-label');
      if (themeLabel) {
        themeLabel.textContent = theme === 'dark' ? 'Dark' : (theme === 'light' ? 'Light' : 'Auto');
      }
    };

    applyTheme(this.theme);

    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
      if (this.theme === 'system') applyTheme('system');
    });

    const toggleBtn = document.getElementById('btn-toggle-theme');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', () => {
        const next = this.theme === 'light' ? 'dark' : (this.theme === 'dark' ? 'system' : 'light');
        this.theme = next;
        localStorage.setItem('rointel_theme', next);
        applyTheme(next);
      });
    }
  },

  // ----------------------------------------------------
  // CLOCK IN EUROPE/BUCHAREST TIMEZONE
  // ----------------------------------------------------
  initClock() {
    const clockEl = document.getElementById('top-bar-clock');
    const update = () => {
      if (!clockEl) return;
      const now = new Date();
      const formatter = new Intl.DateTimeFormat('ro-RO', {
        timeZone: 'Europe/Bucharest',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
      });
      clockEl.textContent = `${formatter.format(now)} EET`;
    };
    update();
    setInterval(update, 1000);
  },

  // ----------------------------------------------------
  // HASH ROUTER
  // ----------------------------------------------------
  initRouter() {
    const handleRoute = () => {
      const hash = window.location.hash.replace(/^#\/?/, '').toLowerCase() || 'overview';
      this.navigateTo(hash, false);
    };

    window.addEventListener('hashchange', handleRoute);
    handleRoute();
  },

  navigateTo(route, updateHash = true) {
    const validRoutes = ['overview', 'live', 'briefings', 'database', 'graph', 'insights', 'runs'];
    const targetRoute = validRoutes.includes(route) ? route : 'overview';
    this.currentRoute = targetRoute;

    if (updateHash && window.location.hash !== `#/${targetRoute}`) {
      window.location.hash = `#/${targetRoute}`;
    }

    // Update active nav button
    document.querySelectorAll('.sidebar-nav-item').forEach(btn => {
      const isActive = btn.dataset.route === targetRoute;
      btn.classList.toggle('active', isActive);
      if (isActive) {
        btn.classList.add('bg-slate-200', 'dark:bg-slate-800', 'text-slate-900', 'dark:text-slate-100', 'font-medium');
        btn.classList.remove('text-slate-600', 'dark:text-slate-400');
      } else {
        btn.classList.remove('bg-slate-200', 'dark:bg-slate-800', 'text-slate-900', 'dark:text-slate-100', 'font-medium');
        btn.classList.add('text-slate-600', 'dark:text-slate-400');
      }
    });

    // Update View Containers
    document.querySelectorAll('.view-section').forEach(view => {
      view.classList.toggle('hidden', view.id !== `view-${targetRoute}`);
    });

    // Update Top Bar Title
    const titleMap = {
      overview: 'Prezentare Generală',
      live: 'Execuție în Timp Real',
      briefings: 'Sinteze Politice',
      database: 'Explorator Bază de Date',
      graph: 'Hartă Relațională & Similaritate Semantică',
      insights: 'Amenințări & Anomalii',
      runs: 'Jurnal Execuții Pipeline'
    };
    const titleEl = document.getElementById('view-title');
    if (titleEl) titleEl.textContent = titleMap[targetRoute] || 'Platformă';

    // Start SSE stream when on live view
    if (targetRoute === 'live' || this.isExecuting) {
      this.ensureStreamConnected();
    }

    // Refresh view specific data
    this.onViewActivated(targetRoute);
    lucide.createIcons();
  },

  onViewActivated(route) {
    if (route === 'graph') {
      this.renderGraphView();
    } else if (route === 'overview') {
      this.renderOverview();
    } else if (route === 'briefings') {
      this.renderBriefingsView();
    } else if (route === 'database') {
      this.renderDatabaseView();
    } else if (route === 'insights') {
      this.renderInsightsView();
    } else if (route === 'runs') {
      this.renderRunsView();
    }
  },

  // ----------------------------------------------------
  // GLOBAL ACTIONS & EVENT HANDLERS
  // ----------------------------------------------------
  initGlobalEvents() {
    // Nav button clicks
    document.querySelectorAll('.sidebar-nav-item').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const route = btn.dataset.route;
        this.navigateTo(route);
      });
    });

    // Date input formatting and quick today preset
    const dateInput = document.getElementById('run-date-input');
    const datePreviewText = document.getElementById('run-date-preview-text');
    const quickTodayBtn = document.getElementById('btn-quick-date-today');

    const updateDatePreview = (val) => {
      if (!datePreviewText) return;
      if (!val) {
        datePreviewText.textContent = 'Dată selectată: Automat (Azi)';
        return;
      }
      try {
        const parts = val.split('-');
        if (parts.length === 3) {
          const d = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
          const roStr = new Intl.DateTimeFormat('ro-RO', { day: 'numeric', month: 'long', year: 'numeric' }).format(d);
          datePreviewText.textContent = `Dată selectată: ${roStr} (${val})`;
        } else {
          datePreviewText.textContent = `Dată selectată: ${val}`;
        }
      } catch {
        datePreviewText.textContent = `Dată selectată: ${val}`;
      }
    };

    if (dateInput) {
      dateInput.addEventListener('input', (e) => updateDatePreview(e.target.value));
      dateInput.addEventListener('change', (e) => updateDatePreview(e.target.value));
    }

    if (quickTodayBtn && dateInput) {
      quickTodayBtn.addEventListener('click', () => {
        const now = new Date();
        const y = now.getFullYear();
        const m = String(now.getMonth() + 1).padStart(2, '0');
        const d = String(now.getDate()).padStart(2, '0');
        const iso = `${y}-${m}-${d}`;
        dateInput.value = iso;
        updateDatePreview(iso);
      });
    }

    // Graph View Controls
    const graphSimSlider = document.getElementById('graph-sim-threshold');
    const graphSimVal = document.getElementById('graph-sim-threshold-val');
    if (graphSimSlider) {
      graphSimSlider.addEventListener('input', (e) => {
        const val = parseFloat(e.target.value);
        if (graphSimVal) graphSimVal.textContent = `${Math.round(val * 100)}%`;
        this.graphState.minSimilarity = val;
        this.filterGraphEdgesByThreshold(val);
      });
    }

    const graphSearchInput = document.getElementById('graph-search-input');
    if (graphSearchInput) {
      graphSearchInput.addEventListener('input', (e) => {
        this.graphState.searchQuery = e.target.value.trim().toLowerCase();
        this.filterGraphNodesBySearch(this.graphState.searchQuery);
      });
    }

    const btnSimMode = document.getElementById('graph-btn-mode-similarity');
    const btnActMode = document.getElementById('graph-btn-mode-actors');
    const btnArtMode = document.getElementById('graph-btn-mode-articles');

    const updateGraphModeButtons = (activeMode) => {
      [
        { btn: btnSimMode, mode: 'similarity' },
        { btn: btnActMode, mode: 'actors' },
        { btn: btnArtMode, mode: 'articles' }
      ].forEach(({ btn, mode }) => {
        if (!btn) return;
        const isActive = mode === activeMode;
        btn.classList.toggle('bg-white', isActive);
        btn.classList.toggle('dark:bg-slate-900', isActive);
        btn.classList.toggle('text-blue-600', isActive);
        btn.classList.toggle('dark:text-blue-400', isActive);
        btn.classList.toggle('shadow-xs', isActive);
        btn.classList.toggle('text-slate-600', !isActive);
        btn.classList.toggle('dark:text-slate-400', !isActive);
      });
      const badge = document.getElementById('graph-mode-badge');
      if (badge) {
        badge.textContent = activeMode === 'similarity' ? 'Embeddings' : (activeMode === 'actors' ? 'Actori & Putere' : 'Articole');
      }
    };

    if (btnSimMode) {
      btnSimMode.addEventListener('click', () => {
        this.graphState.mode = 'similarity';
        updateGraphModeButtons('similarity');
        this.loadGraphData();
      });
    }
    if (btnActMode) {
      btnActMode.addEventListener('click', () => {
        this.graphState.mode = 'actors';
        updateGraphModeButtons('actors');
        this.loadGraphData();
      });
    }
    if (btnArtMode) {
      btnArtMode.addEventListener('click', () => {
        this.graphState.mode = 'articles';
        updateGraphModeButtons('articles');
        this.loadGraphData();
      });
    }

    const btnResetZoom = document.getElementById('graph-btn-reset-zoom');
    if (btnResetZoom) {
      btnResetZoom.addEventListener('click', () => {
        this.resetGraphZoom();
      });
    }

    const btnCloseGraphDrawer = document.getElementById('btn-close-graph-inspector');
    if (btnCloseGraphDrawer) {
      btnCloseGraphDrawer.addEventListener('click', () => {
        const drawer = document.getElementById('graph-inspector-drawer');
        if (drawer) drawer.classList.add('translate-x-full');
        this.clearGraphHighlight();
      });
    }

    // Overview Run Form submission
    const runForm = document.getElementById('overview-run-form');
    if (runForm) {
      runForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        await this.handleStartRun();
      });
    }

    // Cancel Run button
    const cancelBtn = document.getElementById('btn-cancel-run');
    if (cancelBtn) {
      cancelBtn.addEventListener('click', async () => {
        await this.handleCancelRun();
      });
    }

    // Close slide-over drawer
    const closeDrawerBtn = document.getElementById('btn-close-drawer');
    if (closeDrawerBtn) {
      closeDrawerBtn.addEventListener('click', () => {
        document.getElementById('row-detail-drawer').classList.add('translate-x-full');
      });
    }

    // Close Schema modal
    const closeSchemaBtn = document.getElementById('btn-close-schema');
    if (closeSchemaBtn) {
      closeSchemaBtn.addEventListener('click', () => {
        document.getElementById('schema-modal').classList.add('hidden');
      });
    }

    // Open Schema modal
    const openSchemaBtn = document.getElementById('btn-view-schema');
    if (openSchemaBtn) {
      openSchemaBtn.addEventListener('click', () => {
        this.openSchemaModal();
      });
    }

    // Export CSV button
    const exportCsvBtn = document.getElementById('btn-export-csv');
    if (exportCsvBtn) {
      exportCsvBtn.addEventListener('click', () => {
        this.exportTableCsv();
      });
    }

    // Auto-follow toggle button in Live View
    const autoFollowBtn = document.getElementById('btn-toggle-autofollow');
    if (autoFollowBtn) {
      autoFollowBtn.addEventListener('click', () => {
        this.autoFollowStream = !this.autoFollowStream;
        autoFollowBtn.textContent = `Auto-follow: ${this.autoFollowStream ? 'Activ' : 'Oprit'}`;
        autoFollowBtn.classList.toggle('text-blue-600', this.autoFollowStream);
      });
    }
  },

  // ----------------------------------------------------
  // SYSTEM STATUS & HEALTH TELEMETRY
  // ----------------------------------------------------
  async refreshStatus() {
    try {
      const data = await API.getStatus();
      this.systemStatus = data;
      try { localStorage.setItem('rointel_cached_status', JSON.stringify(data)); } catch {}

      // Update Header Badges
      const ollamaDot = document.getElementById('header-ollama-dot');
      const ollamaText = document.getElementById('header-ollama-text');
      const sidebarOllama = document.getElementById('sidebar-ollama-model');
      if (sidebarOllama) {
        sidebarOllama.textContent = data.ollama?.active_model || 'Ollama Conectat';
      }
      if (ollamaDot && ollamaText) {
        const isHealthy = data.ollama?.healthy;
        ollamaDot.className = `w-2 h-2 rounded-full ${isHealthy ? 'bg-emerald-500' : 'bg-rose-500'}`;
        ollamaText.textContent = `Ollama: ${data.ollama?.active_model || 'deconectat'}`;
      }

      const walBadge = document.getElementById('header-wal-badge');
      if (walBadge) {
        walBadge.textContent = 'SQLite WAL';
      }

      const vectorBadge = document.getElementById('header-vector-badge');
      if (vectorBadge) {
        const count = data.vector_store?.count || 0;
        vectorBadge.textContent = `ChromaDB (${count})`;
      }

      // Update Pipeline Run Indicator
      const pipe = data.pipeline || {};
      const statusPill = document.getElementById('header-pipeline-status');
      if (statusPill) {
        if (pipe.is_running) {
          statusPill.textContent = 'Execuție în curs';
          statusPill.className = 'px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300';
          this.isExecuting = true;
          this.ensureStreamConnected();
        } else {
          statusPill.textContent = 'Inactiv';
          statusPill.className = 'px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300';
          this.isExecuting = false;
        }
      }

      // If on overview, update stats cards
      if (this.currentRoute === 'overview') {
        this.renderOverviewStats();
      }

    } catch (err) {
      console.warn('[App] Status refresh error:', err.message);
    }
  },

  async refreshReports() {
    try {
      const reports = await API.getReports();
      this.availableReports = reports;
      try { localStorage.setItem('rointel_cached_reports', JSON.stringify(reports)); } catch {}
      if (!this.selectedReportFilename && reports.length > 0) {
        this.selectedReportFilename = reports[0].filename;
      }
      if (this.currentRoute === 'briefings') {
        this.renderBriefingsList();
      }
      if (this.currentRoute === 'overview') {
        this.renderLatestBriefingCard();
      }
    } catch (err) {
      console.warn('[App] Reports refresh error:', err.message);
    }
  },

  // ----------------------------------------------------
  // VIEW 1: OVERVIEW CONTROLLER
  // ----------------------------------------------------
  renderOverview() {
    this.renderOverviewStats();
    this.renderLatestBriefingCard();
  },

  renderOverviewStats() {
    const db = this.systemStatus?.database || {};
    const setStat = (id, val) => {
      const el = document.getElementById(id);
      if (el) {
        if (val !== undefined && val !== null) {
          el.innerHTML = Number(val).toLocaleString();
        } else {
          el.innerHTML = '<span class="inline-block skeleton h-7 w-16"></span>';
        }
      }
    };

    setStat('stat-articles-total', db.total_articles);
    setStat('stat-events-total', db.total_events);
    setStat('stat-anomalies-total', db.total_anomalies);
    setStat('stat-threats-total', db.total_threats);

    // Health card values
    const ollama = this.systemStatus?.ollama || {};
    const setVal = (id, val) => {
      const el = document.getElementById(id);
      if (el) {
        if (val) el.textContent = val;
        else el.innerHTML = '<span class="inline-block skeleton h-4 w-28"></span>';
      }
    };
    setVal('health-llm-model', ollama.active_model);
    setVal('health-llm-ctx', ollama.num_ctx ? `${Number(ollama.num_ctx).toLocaleString()} tokens` : null);
    setVal('health-embed-model', ollama.embedding_model);
    setVal('health-db-status', 'SQLite WAL (Normal Synchronous)');
  },

  async renderLatestBriefingCard() {
    const cardEl = document.getElementById('overview-latest-briefing');
    if (!cardEl) return;

    if (!this.availableReports || this.availableReports.length === 0) {
      cardEl.innerHTML = `
        <div class="text-xs text-slate-500 py-3">Nu există sinteze generate încă. Lansați o execuție pentru a genera primul raport.</div>
      `;
      return;
    }

    const latest = this.availableReports[0];
    const formattedDate = this.formatDateDisplay(latest.date);

    cardEl.innerHTML = `
      <div class="flex items-center justify-between pb-3 border-b border-slate-200 dark:border-slate-800">
        <div>
          <div class="text-sm font-semibold text-slate-900 dark:text-slate-100">${escapeHtml(latest.filename)}</div>
          <div class="text-xs text-slate-500 mt-0.5">Data: ${formattedDate} • Mărime: ${(latest.size_bytes / 1024).toFixed(1)} KB</div>
        </div>
        <button onclick="App.openBriefing('${latest.filename}')" class="px-3 py-1.5 text-xs font-medium rounded-md bg-blue-600 hover:bg-blue-700 text-white shadow-sm transition">
          Deschide Raportul
        </button>
      </div>
      <div class="pt-3 text-xs text-slate-600 dark:text-slate-400 line-clamp-2 leading-relaxed">
        Sinteză structurată a dinamicii politice, contradicțiilor de poziționare și vulnerabilităților instituționale analizate de pipeline-ul de agenți.
      </div>
    `;
  },

  openBriefing(filename) {
    this.selectedReportFilename = filename;
    this.navigateTo('briefings');
  },

  async handleStartRun() {
    const stageSelect = document.getElementById('run-stage-select');
    const dateInput = document.getElementById('run-date-input');
    const errorEl = document.getElementById('run-form-error');

    if (errorEl) errorEl.classList.add('hidden');

    const stage = stageSelect ? stageSelect.value : 'all';
    let dateVal = dateInput ? dateInput.value.trim() : '';

    // Validate ISO date format if provided
    if (dateVal && !/^\d{4}-\d{2}-\d{2}$/.test(dateVal)) {
      if (errorEl) {
        errorEl.textContent = 'Formatul datei trebuie să fie valid (AAAA-LL-ZZ).';
        errorEl.classList.remove('hidden');
      }
      return;
    }

    const submitBtn = document.getElementById('btn-submit-run');
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = 'Se inițiază...';
    }

    try {
      const res = await API.runPipeline({ stage, date: dateVal || null });
      this.activeRunId = res.run_id;
      this.isExecuting = true;
      
      // Navigate straight to Live Run view to observe stream
      this.navigateTo('live');
    } catch (err) {
      if (errorEl) {
        errorEl.textContent = `Eroare lansare: ${err.message}`;
        errorEl.classList.remove('hidden');
      }
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Lansează Execuție';
      }
    }
  },

  async handleCancelRun() {
    const cancelBtn = document.getElementById('btn-cancel-run');
    if (cancelBtn) {
      cancelBtn.disabled = true;
      cancelBtn.textContent = 'Se oprește...';
    }
    try {
      await API.cancelPipeline();
      this.isExecuting = false;
      this.appendLiveLog('WARN', 'Execuția a fost întreruptă de utilizator.');
    } catch (err) {
      console.warn('Eroare anulare:', err.message);
    } finally {
      if (cancelBtn) {
        cancelBtn.disabled = false;
        cancelBtn.textContent = 'Oprește Execuția';
      }
    }
  },

  // ----------------------------------------------------
  // VIEW 2: LIVE RUN & AGENT STREAMING
  // ----------------------------------------------------
  ensureStreamConnected() {
    if (this.streamSubscription) return;

    this.streamSubscription = API.connectSSE({
      onOpen: () => {
        const streamStatus = document.getElementById('stream-connection-badge');
        if (streamStatus) {
          streamStatus.textContent = 'SSE Conectat';
          streamStatus.className = 'px-2 py-0.5 rounded text-xs font-mono font-medium bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-400';
        }
      },
      onEvent: (data) => {
        this.handleStreamMessage(data);
      },
      onError: () => {
        const streamStatus = document.getElementById('stream-connection-badge');
        if (streamStatus) {
          streamStatus.textContent = 'SSE Reconectare...';
          streamStatus.className = 'px-2 py-0.5 rounded text-xs font-mono font-medium bg-amber-100 text-amber-800 dark:bg-amber-950/40 dark:text-amber-400';
        }
      }
    });
  },

  handleStreamMessage(data) {
    if (!data) return;

    // 1. Stage updates
    if (data.type === 'stage' || (data.message && data.message.includes('[STAGE:'))) {
      const inner = data.data || {};
      const stageName = inner.stage || data.stage || this.extractStageFromMessage(data.text || data.message || '');
      const stageStatus = inner.status || data.status || 'running';
      if (stageName) {
        this.updateStageStep(stageName, stageStatus);
      }
    }

    // 2. Agent start / end
    if (data.type === 'agent_start' && data.agent) {
      this.setAgentActive(data.agent, data.name);
    } else if (data.type === 'agent_end' && data.agent) {
      this.setAgentComplete(data.agent, data.duration_s);
    }

    // 3. Agent thinking (reasoning) stream
    if (data.type === 'thinking' && data.agent) {
      this.appendAgentThinking(data.agent, data.text);
    }

    // 4. Agent output stream
    if (data.type === 'token' && data.agent) {
      this.appendAgentOutput(data.agent, data.text);
    }

    // 5. Standard log entry
    if (data.type === 'log' || data.message) {
      const level = data.level || 'INFO';
      const text = data.text || data.message || '';
      const time = data.ts || data.timestamp || new Date().toLocaleTimeString('ro-RO', { hour12: false });
      this.appendLiveLog(level, text, time);
    }
  },

  extractStageFromMessage(msg) {
    if (!msg) return null;
    const m = msg.toUpperCase();
    if (m.includes('INGEST')) return 'ingest';
    if (m.includes('SELECT')) return 'select';
    if (m.includes('AGENTS')) return 'agents';
    if (m.includes('SYNTHESIZE')) return 'synthesize';
    return null;
  },

  updateStageStep(stage, status) {
    if (!stage) return;
    const stageKey = stage.toLowerCase().trim();
    const stepEl = document.getElementById(`step-${stageKey}`) || 
                   (stageKey === 'agents' ? document.getElementById('step-agents') : null);
    if (!stepEl) return;

    const badge = stepEl.querySelector('.step-status-badge');
    if (!badge) return;

    const s = (status || '').toLowerCase().trim();
    if (s === 'running' || s === 'started') {
      badge.textContent = '?n desf??urare';
      badge.className = 'step-status-badge px-2 py-0.5 rounded text-[10px] font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300';
    } else if (s === 'completed' || s === 'success' || s === 'done') {
      badge.textContent = 'Finalizat';
      badge.className = 'step-status-badge px-2 py-0.5 rounded text-[10px] font-medium bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300';
    } else if (s === 'failed' || s === 'error') {
      badge.textContent = 'E?uat';
      badge.className = 'step-status-badge px-2 py-0.5 rounded text-[10px] font-medium bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300';
    }
  },

  setAgentActive(agentKey, name) {
    const card = document.getElementById(`agent-card-${agentKey}`);
    if (!card) return;
    const badge = card.querySelector('.agent-status-badge');
    if (badge) {
      badge.textContent = 'Activ';
      badge.className = 'agent-status-badge px-2 py-0.5 rounded text-[10px] font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300';
    }
    const timer = card.querySelector('.agent-timing');
    if (timer) timer.textContent = 'se procesează...';
  },

  setAgentComplete(agentKey, duration) {
    const card = document.getElementById(`agent-card-${agentKey}`);
    if (!card) return;
    const badge = card.querySelector('.agent-status-badge');
    if (badge) {
      badge.textContent = 'Finalizat';
      badge.className = 'agent-status-badge px-2 py-0.5 rounded text-[10px] font-medium bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300';
    }
    const timer = card.querySelector('.agent-timing');
    if (timer && duration) timer.textContent = `${duration.toFixed(1)}s`;
  },

  appendAgentThinking(agentKey, text) {
    const card = document.getElementById(`agent-card-${agentKey}`);
    if (!card) return;
    const thinkingContainer = card.querySelector('.agent-thinking-stream');
    if (thinkingContainer) {
      thinkingContainer.classList.remove('hidden');
      const textEl = thinkingContainer.querySelector('.thinking-text');
      if (textEl) {
        textEl.textContent += text;
        if (this.autoFollowStream) {
          thinkingContainer.scrollTop = thinkingContainer.scrollHeight;
        }
      }
    }
  },

  appendAgentOutput(agentKey, text) {
    const card = document.getElementById(`agent-card-${agentKey}`);
    if (!card) return;
    const outputContainer = card.querySelector('.agent-output-stream');
    if (outputContainer) {
      const idleMsg = outputContainer.querySelector('.agent-idle-msg');
      if (idleMsg) outputContainer.innerHTML = '';
      outputContainer.textContent += text;
      if (this.autoFollowStream) {
        outputContainer.scrollTop = outputContainer.scrollHeight;
      }
    }
  },

  copyAgentOutput(agentKey) {
    const card = document.getElementById(`agent-card-${agentKey}`);
    if (!card) return;
    const outputContainer = card.querySelector('.agent-output-stream');
    if (outputContainer) {
      navigator.clipboard.writeText(outputContainer.textContent || '');
    }
  },

  appendLiveLog(level, text, timeStr) {
    const logBox = document.getElementById('live-log-container');
    if (!logBox) return;

    const emptyMsg = logBox.querySelector('.empty-log-msg');
    if (emptyMsg) emptyMsg.remove();

    const time = timeStr || new Date().toLocaleTimeString('ro-RO', { hour12: false });
    const row = document.createElement('div');
    row.className = 'flex items-start gap-2 py-0.5 leading-relaxed font-mono text-xs border-b border-slate-100 dark:border-slate-800/40';

    let levelBadgeClass = 'text-slate-500';
    if (level === 'ERROR') levelBadgeClass = 'text-rose-600 font-semibold';
    else if (level === 'WARN') levelBadgeClass = 'text-amber-600 font-semibold';
    else if (level === 'INFO') levelBadgeClass = 'text-blue-600 dark:text-blue-400';

    row.innerHTML = `
      <span class="text-slate-400 select-none flex-none">[${time}]</span>
      <span class="${levelBadgeClass} uppercase flex-none w-12 text-center text-[10px]">${level}</span>
      <span class="text-slate-700 dark:text-slate-300 flex-1 break-all">${escapeHtml(text)}</span>
    `;

    logBox.appendChild(row);
    if (this.autoFollowStream) {
      logBox.scrollTop = logBox.scrollHeight;
    }
  },

  // ----------------------------------------------------
  // VIEW 3: BRIEFINGS READER
  // ----------------------------------------------------
  async renderBriefingsView() {
    if (!this.availableReports || this.availableReports.length === 0) {
      await this.refreshReports();
    }
    if (!this.selectedReportFilename && this.availableReports.length > 0) {
      this.selectedReportFilename = this.availableReports[0].filename;
    }
    this.renderBriefingsList();
    if (this.selectedReportFilename) {
      await this.loadBriefingContent(this.selectedReportFilename);
    }
  },

  renderBriefingsList() {
    const listEl = document.getElementById('briefings-list');
    if (!listEl) return;

    listEl.innerHTML = '';
    if (!this.availableReports || this.availableReports.length === 0) {
      listEl.innerHTML = '<div class="text-xs text-slate-500 p-4">Nicio sinteză disponibilă.</div>';
      return;
    }

    this.availableReports.forEach(rep => {
      const isSelected = rep.filename === this.selectedReportFilename;
      const formattedDate = this.formatDateDisplay(rep.date);
      const btn = document.createElement('button');
      btn.className = `w-full text-left p-3 rounded-lg border transition mb-1.5 ${
        isSelected
          ? 'bg-blue-50 dark:bg-blue-950/40 border-blue-300 dark:border-blue-800 text-blue-900 dark:text-blue-200'
          : 'bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 text-slate-800 dark:text-slate-200 hover:border-slate-300'
      }`;

      btn.innerHTML = `
        <div class="text-xs font-semibold truncate">${escapeHtml(rep.filename)}</div>
        <div class="text-[11px] text-slate-500 mt-1 flex justify-between">
          <span>${formattedDate}</span>
          <span>${(rep.size_bytes / 1024).toFixed(1)} KB</span>
        </div>
      `;

      btn.addEventListener('click', () => {
        this.selectedReportFilename = rep.filename;
        this.renderBriefingsList();
        this.loadBriefingContent(rep.filename);
      });

      listEl.appendChild(btn);
    });
  },

  async loadBriefingContent(filename) {
    const readerEl = document.getElementById('briefing-markdown-content');
    const headerTitle = document.getElementById('briefing-header-filename');
    const headerDate = document.getElementById('briefing-header-date');

    if (headerTitle) headerTitle.textContent = filename;
    if (readerEl) {
      readerEl.innerHTML = `
        <div class="space-y-3 py-6">
          <div class="skeleton h-6 w-1/3"></div>
          <div class="skeleton h-4 w-full"></div>
          <div class="skeleton h-4 w-5/6"></div>
          <div class="skeleton h-4 w-4/6"></div>
        </div>
      `;
    }

    try {
      const data = await API.getReportContent(filename);
      const rawMarkdown = data.content || '';
      
      const dateMatch = filename.match(/\d{4}-\d{2}-\d{2}/);
      if (headerDate && dateMatch) {
        headerDate.textContent = `Publicat: ${this.formatDateDisplay(dateMatch[0])}`;
      }

      const parsedHtml = marked.parse(rawMarkdown);
      const cleanHtml = DOMPurify.sanitize(parsedHtml);

      if (readerEl) {
        readerEl.innerHTML = cleanHtml;
      }
    } catch (err) {
      if (readerEl) {
        readerEl.innerHTML = `<div class="text-sm text-rose-600 p-4">Eroare la încărcarea raportului: ${err.message}</div>`;
      }
    }
  },

  // ----------------------------------------------------
  // VIEW 4: DATABASE BROWSER
  // ----------------------------------------------------
  async renderDatabaseView() {
    const tables = await API.getDbTables();
    this.dbState.tables = tables;
    this.renderDbTableList();
    await this.loadDbRows();
  },

  renderDbTableList() {
    const container = document.getElementById('db-tables-list');
    if (!container) return;
    container.innerHTML = '';

    this.dbState.tables.forEach(t => {
      const isSelected = t.name === this.dbState.activeTable;
      const btn = document.createElement('button');
      btn.className = `w-full text-left px-3 py-2.5 rounded-md text-xs transition flex items-center justify-between ${
        isSelected
          ? 'bg-slate-200 dark:bg-slate-800 font-semibold text-slate-900 dark:text-slate-100'
          : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800/60'
      }`;

      btn.innerHTML = `
        <span class="font-mono">${t.name}</span>
        <span class="px-1.5 py-0.2 rounded text-[11px] bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 font-mono">
          ${Number(t.row_count || 0).toLocaleString()}
        </span>
      `;

      btn.addEventListener('click', async () => {
        this.dbState.activeTable = t.name;
        this.dbState.page = 1;
        this.renderDbTableList();
        await this.loadDbRows();
      });

      container.appendChild(btn);
    });
  },

  async loadDbRows() {
    const tableEl = document.getElementById('db-grid-container');
    const tableTitle = document.getElementById('db-active-table-name');
    if (tableTitle) tableTitle.textContent = this.dbState.activeTable;

    if (tableEl) {
      tableEl.innerHTML = `
        <div class="p-6 space-y-2">
          <div class="skeleton h-8 w-full"></div>
          <div class="skeleton h-8 w-full"></div>
          <div class="skeleton h-8 w-full"></div>
        </div>
      `;
    }

    try {
      const data = await API.getDbRows(this.dbState.activeTable, {
        limit: this.dbState.pageSize,
        offset: (this.dbState.page - 1) * this.dbState.pageSize,
        q: this.dbState.searchQuery,
        date_from: this.dbState.dateFrom,
        date_to: this.dbState.dateTo
      });

      this.dbState.columns = data.columns || [];
      this.dbState.rows = data.rows || [];
      this.dbState.totalRows = data.total || data.rows.length;

      this.renderDbGrid();
      this.renderDbPagination();
    } catch (err) {
      if (tableEl) {
        tableEl.innerHTML = `<div class="p-4 text-xs text-rose-600">Eroare la încărcarea rândurilor: ${err.message}</div>`;
      }
    }
  },

  renderDbGrid() {
    const container = document.getElementById('db-grid-container');
    if (!container) return;

    if (!this.dbState.rows || this.dbState.rows.length === 0) {
      container.innerHTML = '<div class="p-8 text-center text-xs text-slate-500 font-sans">Niciun rând găsit pentru criteriile selectate.</div>';
      return;
    }

    let html = `
      <div class="overflow-x-auto">
        <table class="w-full text-left text-xs border-collapse">
          <thead>
            <tr class="border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50">
    `;

    this.dbState.columns.forEach(col => {
      html += `<th class="p-2.5 font-medium text-slate-700 dark:text-slate-300 font-sans tracking-tight">${escapeHtml(col)}</th>`;
    });

    html += `</tr></thead><tbody class="divide-y divide-slate-200 dark:divide-slate-800">`;

    this.dbState.rows.forEach((row, idx) => {
      html += `<tr class="hover:bg-slate-50 dark:hover:bg-slate-800/50 cursor-pointer transition" onclick="App.openRowDrawer(${idx})">`;
      this.dbState.columns.forEach(col => {
        const val = row[col];
        let displayVal = '';
        if (val === null || val === undefined || val === '') {
          displayVal = '<span class="text-slate-400 dark:text-slate-600 font-sans select-none">—</span>';
        } else if (col === 'link' || (typeof val === 'string' && (val.startsWith('http://') || val.startsWith('https://')))) {
          displayVal = `<a href="${escapeHtml(String(val))}" target="_blank" rel="noopener noreferrer" class="text-blue-600 dark:text-blue-400 hover:underline inline-flex items-center gap-1 font-sans truncate max-w-[240px]" onclick="event.stopPropagation()"><span class="truncate">${escapeHtml(String(val))}</span><i data-lucide="external-link" class="w-3 h-3 flex-none"></i></a>`;
        } else if (col === 'id' || col === 'run_id' || col === 'article_id' || col === 'event_hash') {
          displayVal = `<span class="font-mono text-slate-500">${escapeHtml(String(val))}</span>`;
        } else {
          displayVal = `<span class="font-sans block truncate max-w-[280px] cursor-pointer hover:text-blue-600 dark:hover:text-blue-400" title="${escapeHtml(String(val))}">${escapeHtml(String(val))}</span>`;
        }
        html += `<td class="p-2.5 text-slate-600 dark:text-slate-400" title="Apasă pentru detalii">${displayVal}</td>`;
      });
      html += `</tr>`;
    });

    html += `</tbody></table></div>`;
    container.innerHTML = html;
    if (window.lucide) lucide.createIcons();
  },

  renderDbPagination() {
    const pageIndicator = document.getElementById('db-page-indicator');
    const totalPages = Math.max(1, Math.ceil(this.dbState.totalRows / this.dbState.pageSize));
    if (pageIndicator) {
      pageIndicator.textContent = `Pagina ${this.dbState.page} din ${totalPages} (${this.dbState.totalRows} rânduri)`;
    }

    const prevBtn = document.getElementById('db-btn-prev');
    const nextBtn = document.getElementById('db-btn-next');
    if (prevBtn) {
      prevBtn.disabled = this.dbState.page <= 1;
      prevBtn.onclick = () => {
        if (this.dbState.page > 1) {
          this.dbState.page--;
          this.loadDbRows();
        }
      };
    }
    if (nextBtn) {
      nextBtn.disabled = this.dbState.page >= totalPages;
      nextBtn.onclick = () => {
        if (this.dbState.page < totalPages) {
          this.dbState.page++;
          this.loadDbRows();
        }
      };
    }
  },

  openRowDrawer(rowIndex) {
    const row = this.dbState.rows[rowIndex];
    if (!row) return;

    this.dbState.selectedRow = row;
    const drawer = document.getElementById('row-detail-drawer');
    const content = document.getElementById('row-detail-content');

    if (content) {
      let fieldsHtml = '<div class="space-y-3 font-mono text-xs">';
      Object.entries(row).forEach(([key, val]) => {
        fieldsHtml += `
          <div class="border-b border-slate-200 dark:border-slate-800 pb-2">
            <div class="text-slate-400 text-[11px] font-sans font-medium uppercase">${escapeHtml(key)}</div>
            <div class="text-slate-900 dark:text-slate-100 mt-0.5 break-all">${escapeHtml(String(val ?? 'null'))}</div>
          </div>
        `;
      });
      fieldsHtml += '</div>';

      fieldsHtml += `
        <div class="mt-4 pt-3 border-t border-slate-200 dark:border-slate-800 flex justify-end">
          <button onclick="navigator.clipboard.writeText(JSON.stringify(App.dbState.selectedRow, null, 2))" class="px-3 py-1.5 rounded text-xs bg-slate-200 dark:bg-slate-800 text-slate-800 dark:text-slate-200 hover:bg-slate-300 transition">
            Copiază JSON
          </button>
        </div>
      `;

      content.innerHTML = fieldsHtml;
    }

    if (drawer) {
      drawer.classList.remove('translate-x-full');
    }
  },

  openSchemaModal() {
    const modal = document.getElementById('schema-modal');
    const content = document.getElementById('schema-modal-content');
    const tableName = document.getElementById('schema-modal-table-name');

    if (tableName) tableName.textContent = this.dbState.activeTable;

    if (content) {
      let schemaHtml = `
        <div class="space-y-2 font-mono text-xs">
          <div class="text-slate-500 mb-2">Coloane identificate în ${this.dbState.activeTable}:</div>
          <table class="w-full text-left border-collapse">
            <thead>
              <tr class="border-b border-slate-200 dark:border-slate-800 text-slate-400 font-sans">
                <th class="py-1">Nume Coloană</th>
                <th class="py-1">Tip Date</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
      `;

      this.dbState.columns.forEach(col => {
        schemaHtml += `
          <tr>
            <td class="py-1.5 font-semibold text-slate-800 dark:text-slate-200">${escapeHtml(col)}</td>
            <td class="py-1.5 text-slate-500">TEXT / INTEGER</td>
          </tr>
        `;
      });

      schemaHtml += `</tbody></table></div>`;
      content.innerHTML = schemaHtml;
    }

    if (modal) modal.classList.remove('hidden');
  },

  exportTableCsv() {
    if (!this.dbState.rows || this.dbState.rows.length === 0) return;

    const cols = this.dbState.columns;
    let csv = cols.join(',') + '\n';
    this.dbState.rows.forEach(row => {
      const line = cols.map(c => `"${String(row[c] ?? '').replace(/"/g, '""')}"`).join(',');
      csv += line + '\n';
    });

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${this.dbState.activeTable}_export.csv`;
    a.click();
    URL.revokeObjectURL(url);
  },

  // ----------------------------------------------------
  // SYSTEM PURGE (SQLITE, CHROMADB, REPORTS)
  // ----------------------------------------------------
  confirmPurgeSystem() {
    const modal = document.getElementById('purge-modal');
    if (modal) modal.classList.remove('hidden');
    if (window.lucide) window.lucide.createIcons();
  },

  closePurgeModal() {
    const modal = document.getElementById('purge-modal');
    if (modal) modal.classList.add('hidden');
  },

  async executePurgeSystem() {
    const btn = document.getElementById('btn-confirm-purge');
    const btnText = document.getElementById('btn-confirm-purge-text');
    if (btn) btn.disabled = true;
    if (btnText) btnText.textContent = 'Se purjeaza...';

    try {
      const res = await API.purgeSystem();
      this.closePurgeModal();
      this.showToast('Ambele baze de date si toate rapoartele au fost sterse cu succes.', 'success');

      // Refresh all UI components and views
      await Promise.allSettled([
        this.loadStats(),
        this.loadDbTables(),
        this.loadDbRows(),
        this.loadBriefingsList(),
        this.loadRunsHistory()
      ]);

      // If in graph view, reload graph
      if (this.currentRoute === 'graph') {
        await this.loadGraphData();
      }

      // If in insights view, reload insights
      if (this.currentRoute === 'insights') {
        await this.renderInsightsView();
      }

      // Clear markdown viewer if currently open
      const preview = document.getElementById('briefing-markdown-preview');
      if (preview) {
        preview.innerHTML = '<div class="text-sm text-slate-400 italic p-6">Niciun raport disponibil. Baza de date si rapoartele au fost purjate.</div>';
      }
    } catch (err) {
      console.error('System purge failed:', err);
      this.showToast(`Eroare la purjare: ${err.message}`, 'error');
    } finally {
      if (btn) btn.disabled = false;
      if (btnText) btnText.textContent = 'Confirma Purjarea';
    }
  },

  showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `pointer-events-auto flex items-center gap-2 px-4 py-3 rounded-lg shadow-xl text-xs font-medium transition-all transform duration-300 opacity-0 translate-y-2 border ${
      type === 'success'
        ? 'bg-emerald-900/90 text-emerald-100 border-emerald-700'
        : type === 'error'
        ? 'bg-rose-900/90 text-rose-100 border-rose-700'
        : 'bg-slate-900/90 text-slate-100 border-slate-700'
    }`;

    const iconName = type === 'success' ? 'check-circle' : type === 'error' ? 'alert-circle' : 'info';
    toast.innerHTML = `
      <i data-lucide="${iconName}" class="w-4 h-4 flex-none"></i>
      <span class="flex-1">${escapeHtml(message)}</span>
    `;

    container.appendChild(toast);
    if (window.lucide) window.lucide.createIcons();

    // Trigger enter animation
    requestAnimationFrame(() => {
      toast.classList.remove('opacity-0', 'translate-y-2');
      toast.classList.add('opacity-100', 'translate-y-0');
    });

    // Auto remove after 4.5 seconds
    setTimeout(() => {
      toast.classList.remove('opacity-100', 'translate-y-0');
      toast.classList.add('opacity-0', 'translate-y-2');
      setTimeout(() => toast.remove(), 350);
    }, 4500);
  },

  // ----------------------------------------------------
  // VIEW 5: INSIGHTS (THREAT VECTORS & CONTRADICTIONS)
  // ----------------------------------------------------
  async renderInsightsView() {
    await this.renderThreatsTable();
    await this.renderAnomaliesTable();
  },

  async renderThreatsTable() {
    const container = document.getElementById('insights-threats-container');
    if (!container) return;

    container.innerHTML = '<div class="skeleton h-24 w-full"></div>';
    try {
      const threats = await API.getThreats(50);
      if (!threats || threats.length === 0) {
        container.innerHTML = '<div class="text-xs text-slate-500 p-4">Niciun vector de amenințare înregistrat.</div>';
        return;
      }

      let html = '<div class="space-y-3">';
      threats.forEach(t => {
        html += `
          <div class="p-4 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm space-y-2">
            <div class="flex items-center justify-between text-xs">
              <span class="font-medium text-slate-900 dark:text-slate-100 font-mono">${escapeHtml(t.threat_type || 'Vulnerabilitate')}</span>
              <span class="text-slate-500 font-mono text-[11px]">${escapeHtml(t.detected_at || '')}</span>
            </div>
            <div class="text-xs text-slate-600 dark:text-slate-400 grid grid-cols-1 md:grid-cols-2 gap-2 pt-1 border-t border-slate-100 dark:border-slate-800">
              <div><strong class="text-slate-700 dark:text-slate-300">Țintă:</strong> ${escapeHtml(t.vulnerable_actor || 'N/A')}</div>
              <div><strong class="text-slate-700 dark:text-slate-300">Exploatat de:</strong> ${escapeHtml(t.exploiting_actor || 'N/A')}</div>
            </div>
            <p class="text-xs text-slate-700 dark:text-slate-300 bg-slate-50 dark:bg-slate-950 p-2.5 rounded border border-slate-200 dark:border-slate-800 leading-relaxed">
              ${escapeHtml(t.description || 'Fără descriere.')}
            </p>
          </div>
        `;
      });
      html += '</div>';
      container.innerHTML = html;
    } catch (err) {
      container.innerHTML = `<div class="text-xs text-rose-600 p-4">Eroare: ${err.message}</div>`;
    }
  },

  async renderAnomaliesTable() {
    const container = document.getElementById('insights-anomalies-container');
    if (!container) return;

    container.innerHTML = '<div class="skeleton h-24 w-full"></div>';
    try {
      const anomalies = await API.getAnomalies(50);
      if (!anomalies || anomalies.length === 0) {
        container.innerHTML = '<div class="text-xs text-slate-500 p-4">Nicio contradicție identificată.</div>';
        return;
      }

      let html = '<div class="space-y-3">';
      anomalies.forEach(a => {
        const score = typeof a.contradiction_score === 'number' ? a.contradiction_score.toFixed(2) : 'N/A';
        html += `
          <div class="p-4 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm space-y-2">
            <div class="flex items-center justify-between text-xs">
              <span class="font-semibold text-slate-900 dark:text-slate-100">${escapeHtml(a.target || 'Actor')}</span>
              <span class="px-2 py-0.5 rounded text-[11px] font-mono bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                Scor contradicție: ${score}
              </span>
            </div>
            <div class="space-y-1.5 text-xs font-mono pt-1">
              <div class="p-2 rounded bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400">
                <span class="text-[10px] font-sans font-semibold text-slate-400 uppercase block">Poziție Anterioară:</span>
                "${escapeHtml(a.past_statement || 'N/A')}"
              </div>
              <div class="p-2 rounded bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-800 dark:text-slate-200">
                <span class="text-[10px] font-sans font-semibold text-slate-400 uppercase block">Declarație Curentă:</span>
                "${escapeHtml(a.current_statement || 'N/A')}"
              </div>
            </div>
            ${a.analyst_note ? `
              <div class="text-xs text-slate-600 dark:text-slate-400 italic pt-1">
                <strong>Notă Analist:</strong> ${escapeHtml(a.analyst_note)}
              </div>
            ` : ''}
          </div>
        `;
      });
      html += '</div>';
      container.innerHTML = html;
    } catch (err) {
      container.innerHTML = `<div class="text-xs text-rose-600 p-4">Eroare: ${err.message}</div>`;
    }
  },

  // ----------------------------------------------------
  // VIEW 6: RUNS AUDIT LOG
  // ----------------------------------------------------
  async renderRunsView() {
    const container = document.getElementById('runs-table-container');
    if (!container) return;

    container.innerHTML = '<div class="p-4"><div class="skeleton h-20 w-full"></div></div>';
    try {
      const execs = await API.getExecutions(30);
      if (!execs || execs.length === 0) {
        container.innerHTML = '<div class="text-xs text-slate-500 p-8 text-center">Nicio execuție înregistrată.</div>';
        return;
      }

      let html = `
        <table class="w-full text-left text-xs border-collapse">
          <thead>
            <tr class="border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50">
              <th class="p-3 font-semibold text-slate-700 dark:text-slate-300 font-mono">Run ID</th>
              <th class="p-3 font-semibold text-slate-700 dark:text-slate-300">Etapă</th>
              <th class="p-3 font-semibold text-slate-700 dark:text-slate-300">Stare</th>
              <th class="p-3 font-semibold text-slate-700 dark:text-slate-300">Detalii</th>
              <th class="p-3 font-semibold text-slate-700 dark:text-slate-300">Dată / Oră</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-200 dark:divide-slate-800">
      `;

      execs.forEach(ex => {
        const isSuccess = ex.status === 'COMPLETED';
        const isFailed = ex.status === 'FAILED';
        const badgeClass = isSuccess
          ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300'
          : (isFailed ? 'bg-rose-100 text-rose-800 dark:bg-rose-950/40 dark:text-rose-300' : 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300');

        html += `
          <tr class="hover:bg-slate-50 dark:hover:bg-slate-800/40">
            <td class="p-3 font-mono font-medium text-slate-900 dark:text-slate-100">${escapeHtml(ex.run_id)}</td>
            <td class="p-3 text-slate-700 dark:text-slate-300 font-mono">${escapeHtml(ex.stage)}</td>
            <td class="p-3"><span class="px-2 py-0.5 rounded text-[11px] font-medium ${badgeClass}">${escapeHtml(ex.status)}</span></td>
            <td class="p-3 text-slate-600 dark:text-slate-400 truncate max-w-[300px]">${escapeHtml(ex.details || '')}</td>
            <td class="p-3 text-slate-500 font-mono text-[11px]">${escapeHtml(ex.created_at || ex.updated_at || '')}</td>
          </tr>
        `;
      });

      html += `</tbody></table>`;
      container.innerHTML = html;
    } catch (err) {
      container.innerHTML = `<div class="p-4 text-xs text-rose-600">Eroare la încărcarea execuțiilor: ${err.message}</div>`;
    }
  },

  // ----------------------------------------------------
  // UTILITIES
  // ----------------------------------------------------
  formatDateDisplay(dateStr) {
    if (!dateStr) return 'N/A';
    try {
      const parsed = new Date(dateStr);
      if (isNaN(parsed.getTime())) return dateStr;
      return new Intl.DateTimeFormat('ro-RO', {
        timeZone: 'Europe/Bucharest',
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      }).format(parsed);
    } catch {
      return dateStr;
    }
  },

  // ====================================================
  // CONNECTED PAPERS RELATIONAL & SEMANTIC GRAPH VIEW
  // ====================================================

  async renderGraphView() {
    if (!this.graphState.rawGraphData) {
      await this.loadGraphData();
    } else {
      this.drawGraph(this.graphState.rawGraphData);
    }
  },

  async loadGraphData() {
    const loadingOverlay = document.getElementById('graph-loading-overlay');
    if (loadingOverlay) loadingOverlay.classList.remove('hidden');

    try {
      const data = await API.getDbGraph({
        mode: this.graphState.mode,
        minSimilarity: this.graphState.minSimilarity,
        limit: 150
      });
      this.graphState.rawGraphData = data;
      this.drawGraph(data);
    } catch (err) {
      console.error('[Graph] Failed loading graph data:', err);
    } finally {
      if (loadingOverlay) loadingOverlay.classList.add('hidden');
    }
  },

  drawGraph(data) {
    if (typeof d3 === 'undefined') {
      console.warn('[Graph] D3.js is not loaded.');
      return;
    }

    const container = document.getElementById('graph-canvas-container');
    const svgEl = document.getElementById('graph-svg');
    if (!container || !svgEl) return;

    const width = container.clientWidth || 900;
    const height = container.clientHeight || 560;

    const svg = d3.select(svgEl)
      .attr('width', width)
      .attr('height', height)
      .attr('viewBox', `0 0 ${width} ${height}`);

    svg.selectAll('*').remove();

    // Defs for arrowhead markers
    const defs = svg.append('defs');
    defs.append('marker')
      .attr('id', 'arrow-threat')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 22)
      .attr('refY', 0)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-5L10,0L0,5')
      .attr('fill', '#f59e0b');

    const g = svg.append('g').attr('class', 'graph-main-group');
    this.graphState.svg = svg;
    this.graphState.g = g;

    // Zoom and pan
    const zoom = d3.zoom()
      .scaleExtent([0.15, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform);
      });
    svg.call(zoom);
    this.graphState.zoom = zoom;

    // Update node/edge counts badges
    const nodesBadge = document.getElementById('graph-stats-nodes');
    const edgesBadge = document.getElementById('graph-stats-edges');
    if (nodesBadge) nodesBadge.textContent = `${data.nodes.length} noduri`;
    if (edgesBadge) edgesBadge.textContent = `${data.edges.length} conexiuni`;

    // Clone data for D3 force simulation
    const nodes = data.nodes.map(d => ({ ...d }));
    const nodeById = new Map(nodes.map(d => [d.id, d]));
    const edges = data.edges
      .filter(e => nodeById.has(e.source) && nodeById.has(e.target))
      .map(e => ({ ...e, source: e.source, target: e.target }));

    // Force simulation
    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(edges).id(d => d.id).distance(d => {
        const w = d.weight || 0.6;
        return Math.max(50, 160 - w * 90);
      }))
      .force('charge', d3.forceManyBody().strength(-220))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(d => (d.radius || 12) + 14));

    this.graphState.simulation = simulation;

    // Draw Links
    const link = g.append('g')
      .attr('class', 'links')
      .selectAll('line')
      .data(edges)
      .enter().append('line')
      .attr('class', 'graph-link')
      .attr('stroke', d => {
        if (d.kind === 'threat') return '#f59e0b';
        if (d.kind === 'topic_affinity') return '#94a3b8';
        return '#cbd5e1';
      })
      .attr('stroke-width', d => Math.max(1.2, (d.weight || 0.5) * 2.8))
      .attr('stroke-opacity', d => d.kind === 'threat' ? 0.85 : 0.45)
      .attr('stroke-dasharray', d => d.kind === 'threat' ? '4 3' : null)
      .attr('marker-end', d => d.kind === 'threat' ? 'url(#arrow-threat)' : null);

    // Node radius and color helpers
    const getNodeRadius = (d) => {
      const base = d.kind === 'topic' ? 14 : (d.kind === 'actor' ? 16 : 10);
      return Math.min(26, base + (d.weight || 0) * 1.5);
    };

    const getNodeColor = (d) => {
      if (d.contradiction_score && d.contradiction_score > 0.5) return '#ef4444'; // Red
      if (d.threat_count && d.threat_count > 0) return '#f59e0b'; // Amber
      if (d.kind === 'actor') return '#2563eb'; // Blue
      if (d.kind === 'topic') return '#0284c7'; // Sky
      if (d.kind === 'article') return '#64748b'; // Slate
      return '#3b82f6'; // Event node
    };

    nodes.forEach(d => { d.radius = getNodeRadius(d); });

    // Draw Nodes Group
    const node = g.append('g')
      .attr('class', 'nodes')
      .selectAll('g')
      .data(nodes)
      .enter().append('g')
      .attr('class', 'graph-node')
      .call(d3.drag()
        .on('start', (event, d) => {
          if (!event.active) simulation.alphaTarget(0.3).restart();
          d.fx = d.x;
          d.fy = d.y;
        })
        .on('drag', (event, d) => {
          d.fx = event.x;
          d.fy = event.y;
        })
        .on('end', (event, d) => {
          if (!event.active) simulation.alphaTarget(0);
          d.fx = null;
          d.fy = null;
        })
      );

    // Contradiction / Threat outer ring
    node.filter(d => (d.contradiction_score > 0.5 || d.threat_count > 0))
      .append('circle')
      .attr('r', d => d.radius + 5)
      .attr('fill', 'none')
      .attr('stroke', d => d.contradiction_score > 0.5 ? '#f87171' : '#fbbf24')
      .attr('stroke-width', 1.5)
      .attr('stroke-dasharray', '3 2')
      .attr('opacity', 0.8);

    // Main Circle
    node.append('circle')
      .attr('r', d => d.radius)
      .attr('fill', d => getNodeColor(d))
      .attr('stroke', '#ffffff')
      .attr('stroke-width', 1.5);

    // Text Label
    node.append('text')
      .text(d => {
        const text = d.actor || d.label || '';
        return text.length > 20 ? text.slice(0, 18) + '...' : text;
      })
      .attr('x', d => d.radius + 4)
      .attr('y', 4)
      .attr('font-size', '10px')
      .attr('font-weight', '500')
      .attr('fill', 'currentColor')
      .attr('class', 'fill-slate-700 dark:fill-slate-300 pointer-events-none select-none');

    // Tooltip Hover and Click Interactions
    node.on('mouseenter', (event, d) => {
      this.highlightGraphNeighborhood(d, node, link, edges);
    })
    .on('mouseleave', () => {
      if (!this.graphState.selectedNode) {
        this.clearGraphHighlight(node, link);
      }
    })
    .on('click', (event, d) => {
      event.stopPropagation();
      this.selectGraphNode(d, edges);
    });

    svg.on('click', () => {
      this.graphState.selectedNode = null;
      const drawer = document.getElementById('graph-inspector-drawer');
      if (drawer) drawer.classList.add('translate-x-full');
      this.clearGraphHighlight(node, link);
    });

    // Simulation Tick
    simulation.on('tick', () => {
      link
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y);

      node.attr('transform', d => `translate(${d.x},${d.y})`);
    });
  },

  highlightGraphNeighborhood(targetNode, nodeSelection, linkSelection, edges) {
    const connectedIds = new Set([targetNode.id]);
    edges.forEach(e => {
      const sId = typeof e.source === 'object' ? e.source.id : e.source;
      const tId = typeof e.target === 'object' ? e.target.id : e.target;
      if (sId === targetNode.id) connectedIds.add(tId);
      if (tId === targetNode.id) connectedIds.add(sId);
    });

    const ns = nodeSelection || d3.selectAll('.graph-node');
    const ls = linkSelection || d3.selectAll('.graph-link');

    ns.classed('dimmed', d => !connectedIds.has(d.id));
    ls.classed('dimmed', e => {
      const sId = typeof e.source === 'object' ? e.source.id : e.source;
      const tId = typeof e.target === 'object' ? e.target.id : e.target;
      return !(sId === targetNode.id || tId === targetNode.id);
    });
    ls.classed('highlighted', e => {
      const sId = typeof e.source === 'object' ? e.source.id : e.source;
      const tId = typeof e.target === 'object' ? e.target.id : e.target;
      return (sId === targetNode.id || tId === targetNode.id);
    });
  },

  clearGraphHighlight(nodeSelection, linkSelection) {
    const ns = nodeSelection || d3.selectAll('.graph-node');
    const ls = linkSelection || d3.selectAll('.graph-link');
    ns.classed('dimmed', false);
    ls.classed('dimmed', false);
    ls.classed('highlighted', false);
  },

  selectGraphNode(nodeData, edges) {
    this.graphState.selectedNode = nodeData;
    this.highlightGraphNeighborhood(nodeData, null, null, edges);

    const drawer = document.getElementById('graph-inspector-drawer');
    const kindBadge = document.getElementById('graph-inspector-kind');
    const dateLabel = document.getElementById('graph-inspector-date');
    const body = document.getElementById('graph-inspector-body');

    if (!drawer || !body) return;

    if (kindBadge) kindBadge.textContent = nodeData.kind === 'actor' ? 'Actor Politic' : (nodeData.kind === 'topic' ? 'Domeniu' : 'Eveniment');
    if (dateLabel) dateLabel.textContent = nodeData.date || '';

    // Find neighbors with weights
    const neighbors = [];
    edges.forEach(e => {
      const sId = typeof e.source === 'object' ? e.source.id : e.source;
      const tId = typeof e.target === 'object' ? e.target.id : e.target;
      if (sId === nodeData.id) {
        neighbors.push({ node: e.target, edge: e });
      } else if (tId === nodeData.id) {
        neighbors.push({ node: e.source, edge: e });
      }
    });

    let threatsHtml = '';
    if (nodeData.threat_count > 0 || (nodeData.contradiction_score && nodeData.contradiction_score > 0)) {
      threatsHtml = `
        <div class="p-3 rounded bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50 text-xs space-y-1">
          <div class="font-semibold text-amber-800 dark:text-amber-300 flex items-center gap-1.5">
            <i data-lucide="alert-triangle" class="w-3.5 h-3.5"></i>
            <span>Indicatori de Risc & Contradicție</span>
          </div>
          ${nodeData.threat_count > 0 ? `<div>Vulnerabilități Red Team asociate: <strong>${nodeData.threat_count}</strong></div>` : ''}
          ${nodeData.contradiction_score > 0 ? `<div>Scor contradicție istorică: <strong>${Math.round(nodeData.contradiction_score * 100)}%</strong></div>` : ''}
        </div>
      `;
    }

    let neighborsHtml = '';
    if (neighbors.length > 0) {
      neighborsHtml = `
        <div>
          <div class="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-2">Conexiuni Semantice (${neighbors.length})</div>
          <div class="space-y-1.5">
            ${neighbors.map(({ node, edge }) => `
              <div class="p-2 rounded border border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 flex items-center justify-between text-xs">
                <span class="font-medium text-slate-800 dark:text-slate-200 truncate pr-2">${node.actor || node.label || 'Nod conex'}</span>
                <span class="font-mono text-[10px] px-1.5 py-0.5 rounded bg-blue-50 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800">
                  ${edge.label || `${Math.round((edge.weight || 0.6) * 100)}%`}
                </span>
              </div>
            `).join('')}
          </div>
        </div>
      `;
    }

    body.innerHTML = `
      <div>
        <h4 class="text-base font-bold text-slate-900 dark:text-slate-100 leading-snug">${nodeData.actor || nodeData.label || 'Detalii Nod'}</h4>
        ${nodeData.topic ? `<div class="text-xs text-blue-600 dark:text-blue-400 font-medium mt-0.5">${nodeData.topic}</div>` : ''}
      </div>

      ${threatsHtml}

      ${nodeData.action ? `
        <div>
          <div class="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-1">Acțiune / Poziție</div>
          <p class="text-xs text-slate-700 dark:text-slate-300 leading-relaxed">${nodeData.action}</p>
        </div>
      ` : ''}

      ${nodeData.quote ? `
        <div>
          <div class="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-1">Citat Verbatim (Dovadă)</div>
          <blockquote class="text-xs italic p-2.5 rounded bg-slate-50 dark:bg-slate-950 border-l-2 border-blue-500 text-slate-600 dark:text-slate-400">
            „${nodeData.quote}”
          </blockquote>
        </div>
      ` : ''}

      ${nodeData.link ? `
        <div>
          <a href="${nodeData.link}" target="_blank" rel="noopener noreferrer" class="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1 font-medium">
            <span>Deschide articolul sursă</span>
            <i data-lucide="external-link" class="w-3.5 h-3.5"></i>
          </a>
        </div>
      ` : ''}

      ${neighborsHtml}
    `;

    drawer.classList.remove('translate-x-full');
    lucide.createIcons();
  },

  filterGraphEdgesByThreshold(threshold) {
    if (typeof d3 === 'undefined') return;
    d3.selectAll('.graph-link').each(function(d) {
      if (d.kind === 'similarity') {
        const visible = (d.weight || 0) >= threshold;
        d3.select(this).style('display', visible ? null : 'none');
      }
    });
  },

  filterGraphNodesBySearch(query) {
    if (typeof d3 === 'undefined') return;
    if (!query) {
      d3.selectAll('.graph-node').classed('dimmed', false);
      return;
    }
    d3.selectAll('.graph-node').each(function(d) {
      const match = (d.actor && d.actor.toLowerCase().includes(query)) ||
                    (d.topic && d.topic.toLowerCase().includes(query)) ||
                    (d.action && d.action.toLowerCase().includes(query)) ||
                    (d.label && d.label.toLowerCase().includes(query));
      d3.select(this).classed('dimmed', !match);
    });
  },

  resetGraphZoom() {
    if (this.graphState.svg && this.graphState.zoom) {
      this.graphState.svg.transition().duration(500).call(this.graphState.zoom.transform, d3.zoomIdentity);
    }
  }
};

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

window.App = App;
document.addEventListener('DOMContentLoaded', () => App.init());
