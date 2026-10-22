// Alpine.js root component

function app() {
  return {
    // ── state ────────────────────────────────────────────────────────────────
    activeTab: 'dashboard',
    tabs: [
      { id: 'dashboard', label: 'Dashboard' },
      { id: 'scanner',   label: 'Scanner' },
      { id: 'positions', label: 'Positions' },
      { id: 'backtest',  label: 'Backtest' },
      { id: 'settings',  label: 'Settings' },
    ],
    status: { running: false, kill_switch: false, mode: 'PAPER', last_message: '', account: {}, setup: {} },
    scanner: [],
    positions: [],
    trades: [],
    signals: [],
    strategies: [],
    analytics: {},

    btForm: { strategy_name: 'orb_v1', start_date: '', end_date: '', universe_name: 'NIFTY_500' },
    btRunning: false,
    btResult: null,
    btPollTimer: null,

    settingsForm: {},
    settingsFields: [
      { key: 'virtual_capital',            label: 'Virtual Capital (₹)',              hint: 'Starting paper cash' },
      { key: 'max_open_positions',         label: 'Max Open Positions',               type: 'number', step: '1', hint: 'Concurrent trades allowed' },
      { key: 'max_position_notional',      label: 'Max Position Notional (₹)',        hint: 'Max value per trade' },
      { key: 'max_total_exposure',         label: 'Max Total Exposure (₹)',           hint: 'Sum of all open notionals' },
      { key: 'risk_per_trade_pct',         label: 'Risk Per Trade (%)',               step: '0.001', hint: 'e.g. 0.005 = 0.5% of capital' },
      { key: 'max_entries_per_day',        label: 'Max Entries Per Day',              type: 'number', step: '1', hint: '' },
      { key: 'max_daily_loss',             label: 'Max Daily Loss (₹)',               hint: 'Stop trading if loss exceeds this' },
      { key: 'minimum_relative_volume',    label: 'Min Relative Volume (RVOL)',       hint: 'Minimum RVOL for entry, e.g. 1.5' },
      { key: 'minimum_median_traded_value',label: 'Min Median Traded Value (₹)',      hint: '0 = disabled' },
      { key: 'maximum_spread_bps',         label: 'Max Spread (bps)',                 hint: '0 = disabled; 20 = 0.2%' },
    ],
    settingsSaved: false,

    // ── computed ─────────────────────────────────────────────────────────────
    get unrealizedPnl() {
      return this.positions.reduce((s, p) => s + (p.unrealized_pnl || 0), 0)
    },
    get setupSteps() {
      const s = this.status.setup || {}
      return [
        { label: '1. Kite Login',   done: s.kite_connected,  hint: 'Click Login to authorize Zerodha', action: 'login' },
        { label: '2. Load Universe',done: s.universe_loaded,  hint: 'Pull Nifty 500 constituents', action: 'refresh_universe' },
        { label: '3. History Warmup',done: s.history_loaded, hint: 'Fetch 45-day candle history',  action: 'warmup' },
        { label: '4. Live Feed',    done: s.feed_live,        hint: 'Auto-starts with engine',       action: null },
      ]
    },

    // ── lifecycle ─────────────────────────────────────────────────────────────
    async init() {
      await this.loadAll()
      setInterval(() => this.loadStatus(), 5000)
      setInterval(() => this.loadPositions(), 5000)
      setInterval(() => {
        if (this.activeTab === 'scanner') this.loadScanner()
        if (this.activeTab === 'positions') { this.loadPositions(); this.loadTrades() }
        if (this.activeTab === 'dashboard') this.loadSignals()
      }, 10000)

      // Pre-fill today's dates for backtest
      const today = new Date().toISOString().slice(0, 10)
      const sixMonthsAgo = new Date(Date.now() - 180 * 864e5).toISOString().slice(0, 10)
      this.btForm.end_date = today
      this.btForm.start_date = sixMonthsAgo
    },

    async loadAll() {
      await Promise.all([
        this.loadStatus(),
        this.loadScanner(),
        this.loadPositions(),
        this.loadTrades(),
        this.loadSignals(),
        this.loadStrategies(),
        this.loadSettings(),
      ])
    },

    // ── API calls ─────────────────────────────────────────────────────────────
    async loadStatus() {
      const data = await this.get('/api/status')
      if (data) this.status = data
    },
    async loadScanner() {
      const data = await this.get('/api/scanner')
      if (data) this.scanner = data
    },
    async loadPositions() {
      const data = await this.get('/api/positions')
      if (data) this.positions = data
    },
    async loadTrades() {
      const data = await this.get('/api/trades')
      if (data) this.trades = data
    },
    async loadSignals() {
      const data = await this.get('/api/signals')
      if (data) this.signals = data
    },
    async loadStrategies() {
      const data = await this.get('/api/strategies')
      if (data) { this.strategies = data; if (data.length) this.btForm.strategy_name = data[0].name }
    },
    async loadSettings() {
      const data = await this.get('/api/settings')
      if (data) this.settingsForm = { ...data }
    },

    async startEngine()  { await this.post('/api/engine/start');       await this.loadStatus() },
    async stopEngine()   { await this.post('/api/engine/stop');        await this.loadStatus() },
    async killSwitch()   { await this.post('/api/engine/kill-switch'); await this.loadStatus() },

    async runAction(action) {
      if (action === 'login') { window.location.href = '/login'; return }
      if (action === 'refresh_universe') await this.post('/api/universe/refresh')
      if (action === 'warmup') await this.post('/api/history/warmup')
      await this.loadStatus()
    },

    async runBacktest() {
      this.btRunning = true
      this.btResult = null
      const params = new URLSearchParams({
        strategy_name: this.btForm.strategy_name,
        start_date:    this.btForm.start_date,
        end_date:      this.btForm.end_date,
        universe_name: this.btForm.universe_name,
      })
      const data = await this.post(`/api/backtests?${params}`)
      if (!data?.run_id) { this.btRunning = false; return }
      this._pollBacktest(data.run_id)
    },

    _pollBacktest(runId) {
      clearInterval(this.btPollTimer)
      this.btPollTimer = setInterval(async () => {
        const data = await this.get(`/api/backtests/${runId}`)
        if (data?.status === 'DONE' || data?.status === 'FAILED') {
          clearInterval(this.btPollTimer)
          this.btRunning = false
          this.btResult = data
        }
      }, 2000)
    },

    async saveSettings() {
      const payload = {}
      for (const f of this.settingsFields) payload[f.key] = this.settingsForm[f.key]
      await this.patch('/api/settings', payload)
      this.settingsSaved = true
      setTimeout(() => this.settingsSaved = false, 3000)
    },

    // ── helpers ───────────────────────────────────────────────────────────────
    async get(url) {
      try { return await (await fetch(url)).json() } catch { return null }
    },
    async post(url, body) {
      try { return await (await fetch(url, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined,
      })).json() } catch { return null }
    },
    async patch(url, body) {
      try { return await (await fetch(url, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })).json() } catch { return null }
    },

    fmt(n) {
      if (n == null) return '—'
      return new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n)
    },
    timeAgo(iso) {
      if (!iso) return '—'
      const diff = (Date.now() - new Date(iso)) / 1000
      if (diff < 60) return `${Math.floor(diff)}s ago`
      if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
      return new Date(iso).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })
    },
    statusBadgeText() {
      if (this.status.kill_switch) return 'KILL SWITCH'
      return this.status.running ? 'LIVE' : 'STOPPED'
    },
    statusBadgeClass() {
      if (this.status.kill_switch) return 'bg-red-900 text-red-300'
      return this.status.running ? 'bg-emerald-900 text-emerald-300' : 'bg-gray-800 text-gray-400'
    },
    statusClass(s) {
      if (s === 'FILLED') return 'badge-green'
      if (s === 'REJECTED') return 'badge-gray'
      if (s === 'CANDIDATE') return 'badge-blue'
      return 'badge-yellow'
    },
    scanStatusClass(s) {
      if (s === 'SIGNAL') return 'badge-green'
      if (s === 'REJECTED') return 'badge-gray'
      if (s === 'PENDING_FILL') return 'badge-yellow'
      if (s === 'PAPER_OPEN') return 'badge-blue'
      return 'badge-gray'
    },
    dirClass(d) {
      if (d === 'UP') return 'badge-green'
      if (d === 'DOWN') return 'badge-red'
      return 'badge-gray'
    },
  }
}
