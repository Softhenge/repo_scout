from __future__ import annotations
import re

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QTextEdit, QLabel, QStatusBar, QSplitter, QHeaderView,
    QComboBox, QGroupBox, QScrollArea, QCheckBox,
    QFrame, QApplication, QStyle, QTabWidget,
    QStyledItemDelegate,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt5.QtGui import QFont, QTextDocument, QColor, QDesktopServices

from app.api.github_client import GitHubClient
from app.llm.analyzer import RepoAnalyzer
from app.models.github_models import GitHubRepo
from app.models.search_filters import (
    SearchFilters, PREDEFINED_DOMAINS, ACTIVITY_OPTIONS, LANGUAGES,
    STAR_OPTIONS, FORK_OPTIONS,
)
from app.utils.readme_parser import parse_readme
from app.utils.logger import get_logger
from app.llm.providers import PROVIDERS, PROVIDER_BY_LABEL

log = get_logger("main_window")


# ──────────────────────────────────────────────────────────────────────────────
# Background workers
# ──────────────────────────────────────────────────────────────────────────────

class SearchWorker(QThread):
    results_ready = pyqtSignal(object)
    error_occurred = pyqtSignal(str)

    def __init__(self, filters: SearchFilters, client: GitHubClient, page: int = 1):
        super().__init__()
        self._filters = filters
        self._client = client
        self._page = page

    def run(self) -> None:
        log.info("SearchWorker started  query=%r  page=%d", self._filters.build_query(), self._page)
        try:
            result = self._client.search_repos(self._filters, page=self._page)
            log.info("SearchWorker done  total=%d  returned=%d  page=%d",
                     result.total_count, len(result.items), self._page)
            self.results_ready.emit(result)
        except Exception as exc:
            log.error("SearchWorker error  %s", exc)
            self.error_occurred.emit(str(exc))


class ReadmeWorker(QThread):
    readme_ready = pyqtSignal(str)

    def __init__(self, repo: GitHubRepo, client: GitHubClient):
        super().__init__()
        self._full_name = repo.full_name
        self._owner, self._repo_name = repo.full_name.split("/", 1)
        self._client = client

    def run(self) -> None:
        log.debug("ReadmeWorker started  repo=%s", self._full_name)
        try:
            b64 = self._client.get_readme_b64(self._owner, self._repo_name)
            parsed = parse_readme(b64)
            log.debug("ReadmeWorker done  repo=%s  content_chars=%d", self._full_name, len(parsed))
            self.readme_ready.emit(parsed)
        except Exception as exc:
            log.warning("ReadmeWorker error  repo=%s  %s", self._full_name, exc)
            self.readme_ready.emit("")


class AnalyzeWorker(QThread):
    analysis_ready = pyqtSignal(object)  # RepoAnalysis
    error_occurred = pyqtSignal(str)

    def __init__(self, repo: GitHubRepo, analyzer: RepoAnalyzer, readme: str = ""):
        super().__init__()
        self._repo = repo
        self._analyzer = analyzer
        self._readme = readme

    def run(self) -> None:
        log.info("AnalyzeWorker started  repo=%s  readme_chars=%d",
                 self._repo.full_name, len(self._readme))
        try:
            result = self._analyzer.analyze_repo(self._repo, self._readme)
            log.info("AnalyzeWorker done  repo=%s", self._repo.full_name)
            self.analysis_ready.emit(result)
        except Exception as exc:
            log.error("AnalyzeWorker error  repo=%s  %s", self._repo.full_name, exc)
            self.error_occurred.emit(str(exc))


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    return line


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont("Sans", 9, QFont.Bold))
    return lbl


# ──────────────────────────────────────────────────────────────────────────────
# Keyword highlight delegate
# ──────────────────────────────────────────────────────────────────────────────

class KeywordHighlightDelegate(QStyledItemDelegate):
    """Renders the Repository column with matched keywords in bold blue."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._keywords: list[str] = []

    def set_keywords(self, keywords: list[str]) -> None:
        self._keywords = [k for k in keywords if k]

    def _to_html(self, text: str) -> str:
        if not self._keywords:
            return text
        result = re.escape(text)  # start from plain text
        result = text
        for kw in self._keywords:
            result = re.sub(
                f"({re.escape(kw)})",
                r"<b style='color:#0969da'>\1</b>",
                result,
                flags=re.IGNORECASE,
            )
        return result

    def paint(self, painter, option, index):
        self.initStyleOption(option, index)
        text = index.data(Qt.DisplayRole) or ""

        # Elide to fit available width (keeps single-line, adds … if too long)
        available_width = option.rect.width() - 8
        elided = painter.fontMetrics().elidedText(text, Qt.ElideRight, available_width)

        if not self._keywords:
            # No highlights — let the standard delegate draw the elided text
            option.text = elided
            QApplication.style().drawControl(QStyle.CE_ItemViewItem, option, painter)
            return

        html = self._to_html(elided)
        doc = QTextDocument()
        doc.setDefaultFont(option.font)
        doc.setHtml(html)
        # Single line — no wrapping
        doc.setTextWidth(-1)

        painter.save()
        option.text = ""
        QApplication.style().drawControl(QStyle.CE_ItemViewItem, option, painter)
        painter.translate(
            option.rect.left() + 4,
            option.rect.top() + max(0, (option.rect.height() - doc.size().height()) / 2),
        )
        # Clip to cell so even rich-text can't overflow
        painter.setClipRect(QApplication.style().subElementRect(
            QStyle.SE_ItemViewItemText, option
        ).translated(-option.rect.left() - 4, -option.rect.top()))
        doc.drawContents(painter)
        painter.restore()


# ──────────────────────────────────────────────────────────────────────────────
# Main window
# ──────────────────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self, github_client: GitHubClient, analyzer: RepoAnalyzer):
        super().__init__()
        self._github = github_client
        self._analyzer = analyzer
        self._repos: list[GitHubRepo] = []
        self._worker: QThread | None = None
        self._readme_worker: ReadmeWorker | None = None
        self._current_readme: str = ""
        self._current_filters: SearchFilters | None = None
        self._current_page: int = 1
        self._total_count: int = 0
        self._domain_checks: dict[str, QCheckBox] = {}

        self.setWindowTitle("GitHub Repo Scout")
        self.resize(1280, 780)
        self._build_ui()
        self._update_provider_status(PROVIDERS[0])

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        # Top-level horizontal split: sidebar | content
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar(), stretch=0)
        root.addWidget(self._build_content(), stretch=1)

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Ready — configure filters and press Search")

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setFixedWidth(260)
        sidebar.setObjectName("sidebar")
        sidebar.setStyleSheet(
            "#sidebar { background: #f5f5f5; border-right: 1px solid #ddd; }"
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # ── Domains ──────────────────────────────────────────────────────────
        layout.addWidget(_section_label("Technical Domains"))
        domains_box = QGroupBox()
        domains_box.setFlat(True)
        domains_layout = QVBoxLayout(domains_box)
        domains_layout.setSpacing(4)
        domains_layout.setContentsMargins(0, 0, 0, 0)
        for domain in PREDEFINED_DOMAINS:
            cb = QCheckBox(domain)
            self._domain_checks[domain] = cb
            domains_layout.addWidget(cb)
        layout.addWidget(domains_box)

        layout.addWidget(_separator())

        # ── Keywords ─────────────────────────────────────────────────────────
        layout.addWidget(_section_label("Keywords"))
        self._keywords_input = QLineEdit()
        self._keywords_input.setPlaceholderText("e.g. asyncio, rest api, graph ql")
        self._keywords_input.setToolTip(
            "Comma-separated search terms.\n"
            "Each term can be a single word or a phrase.\n"
            "Example: 'rest api, graph ql' searches for repos\n"
            "matching 'rest api' OR 'graph ql'."
        )
        layout.addWidget(self._keywords_input)

        layout.addWidget(_separator())

        # ── Filters ───────────────────────────────────────────────────────────
        layout.addWidget(_section_label("Filters"))

        # Min stars
        layout.addWidget(QLabel("Min stars:"))
        self._min_stars_combo = QComboBox()
        self._min_stars_combo.addItems(list(STAR_OPTIONS.keys()))
        self._min_stars_combo.setCurrentText("100+")
        layout.addWidget(self._min_stars_combo)

        # Min forks
        layout.addWidget(QLabel("Min forks:"))
        self._min_forks_combo = QComboBox()
        self._min_forks_combo.addItems(list(FORK_OPTIONS.keys()))
        layout.addWidget(self._min_forks_combo)

        # Language
        layout.addWidget(QLabel("Language:"))
        self._language_combo = QComboBox()
        self._language_combo.addItems(LANGUAGES)
        layout.addWidget(self._language_combo)

        # Activity
        layout.addWidget(QLabel("Last activity:"))
        self._activity_combo = QComboBox()
        self._activity_combo.addItems(list(ACTIVITY_OPTIONS.keys()))
        self._activity_combo.setCurrentText("Any time")
        layout.addWidget(self._activity_combo)

        # Required GitHub topics
        layout.addWidget(QLabel("Required GitHub topic:"))
        self._topics_input = QLineEdit()
        self._topics_input.setPlaceholderText("e.g. hacktoberfest, awesome")
        self._topics_input.setToolTip(
            "Comma-separated topic slugs (e.g. 'cli, awesome').\n"
            "Each term matches repos that have it as a GitHub topic tag\n"
            "OR have it in their repository name.\n"
            "Multiple terms are AND-ed — repo must satisfy all of them."
        )
        layout.addWidget(self._topics_input)

        layout.addWidget(_separator())

        # ── AI Provider ───────────────────────────────────────────────────────
        layout.addWidget(_section_label("AI Provider"))
        self._provider_combo = QComboBox()
        for p in PROVIDERS:
            self._provider_combo.addItem(p.label)
        self._provider_combo.currentTextChanged.connect(self._on_provider_changed)
        layout.addWidget(self._provider_combo)

        self._provider_status = QLabel()
        self._provider_status.setWordWrap(True)
        self._provider_status.setStyleSheet("font-size: 10px; color: #666;")
        layout.addWidget(self._provider_status)

        layout.addWidget(_separator())

        # ── Sort ─────────────────────────────────────────────────────────────
        layout.addWidget(_section_label("Sort by"))
        self._sort_combo = QComboBox()
        self._sort_combo.addItems(["Relevance", "Stars", "Forks", "Recently updated"])
        layout.addWidget(self._sort_combo)

        layout.addStretch()

        # ── Search button ─────────────────────────────────────────────────────
        self._search_btn = QPushButton("Search Repositories")
        self._search_btn.setFixedHeight(36)
        self._search_btn.setStyleSheet(
            "QPushButton { background: #238636; color: white; border-radius: 4px; font-weight: bold; }"
            "QPushButton:disabled { background: #94d3a2; }"
            "QPushButton:hover { background: #2ea043; }"
        )
        self._search_btn.clicked.connect(self._on_search)
        layout.addWidget(self._search_btn)

        scroll.setWidget(inner)

        outer = QVBoxLayout(sidebar)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        return sidebar

    # ── Content area ──────────────────────────────────────────────────────────

    def _build_content(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Active query display
        self._query_label = QLabel("No search yet")
        self._query_label.setStyleSheet("color: #666; font-style: italic;")
        self._query_label.setWordWrap(True)
        layout.addWidget(self._query_label)

        # Vertical splitter: table (top) + detail (bottom)
        splitter = QSplitter(Qt.Vertical)

        # Results table
        self._table = QTableWidget(0, 9)
        self._table.setHorizontalHeaderLabels([
            "Repository", "Owner", "Language", "Stars", "Forks",
            "Open Issues", "Last Push", "License", "Owner Type",
        ])
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)       # Repository — takes all spare space
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Owner
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Language
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Stars
        hh.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Forks
        hh.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Open Issues
        hh.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Last Push
        hh.setSectionResizeMode(7, QHeaderView.Fixed)             # License — fixed narrow
        hh.setSectionResizeMode(8, QHeaderView.ResizeToContents)  # Owner Type
        self._table.setColumnWidth(7, 90)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.selectionModel().selectionChanged.connect(self._on_row_selected)
        self._table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self._kw_delegate = KeywordHighlightDelegate(self._table)
        self._table.setItemDelegateForColumn(0, self._kw_delegate)

        # Wrap table + Load More in a container so they sit together above the splitter
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(4)
        table_layout.addWidget(self._table)

        load_more_row = QHBoxLayout()
        self._load_more_btn = QPushButton("Load more results")
        self._load_more_btn.setEnabled(False)
        self._load_more_btn.setStyleSheet(
            "QPushButton { border: 1px solid #ccc; border-radius: 4px; padding: 4px 16px; }"
            "QPushButton:disabled { color: #aaa; }"
            "QPushButton:hover { background: #f0f0f0; }"
        )
        self._load_more_btn.clicked.connect(self._on_load_more)
        self._results_label = QLabel("")
        self._results_label.setStyleSheet("color: #666; font-size: 11px;")
        load_more_row.addWidget(self._results_label)
        load_more_row.addStretch()
        load_more_row.addWidget(self._load_more_btn)
        table_layout.addLayout(load_more_row)

        splitter.addWidget(table_container)

        # Detail panel with tabs
        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(0, 4, 0, 0)
        detail_layout.setSpacing(4)

        # Analyze button sits above the tabs
        detail_header = QHBoxLayout()
        detail_header.addWidget(_section_label("Repository Detail"))
        detail_header.addStretch()
        self._analyze_btn = QPushButton("Analyze with AI")
        self._analyze_btn.setEnabled(False)
        self._analyze_btn.setStyleSheet(
            "QPushButton { background: #0969da; color: white; border-radius: 4px; padding: 4px 12px; }"
            "QPushButton:disabled { background: #a8c7f0; }"
            "QPushButton:hover { background: #0860ca; }"
        )
        self._analyze_btn.clicked.connect(self._on_analyze)
        detail_header.addWidget(self._analyze_btn)
        detail_layout.addLayout(detail_header)

        self._detail_tabs = QTabWidget()
        mono = QFont("Monospace", 10)

        # Tab 1 — Overview (repo info + README)
        self._detail_view = QTextEdit()
        self._detail_view.setReadOnly(True)
        self._detail_view.setFont(mono)
        self._detail_tabs.addTab(self._detail_view, "Overview")

        detail_layout.addWidget(self._detail_tabs)

        splitter.addWidget(detail_widget)
        splitter.setSizes([420, 300])
        layout.addWidget(splitter)

        return content

    # ── Analysis tab helpers ──────────────────────────────────────────────────

    def _clear_analysis_tabs(self) -> None:
        """Remove all tabs except the Overview tab (index 0)."""
        while self._detail_tabs.count() > 1:
            self._detail_tabs.removeTab(1)

    def _add_analysis_tab(self, title: str, text: str) -> None:
        """Add a new read-only tab with the given title and content, then switch to it."""
        view = QTextEdit()
        view.setReadOnly(True)
        view.setFont(QFont("Monospace", 10))
        view.setPlainText(text)
        idx = self._detail_tabs.addTab(view, title)
        self._detail_tabs.setCurrentIndex(idx)

    # ── Filter collection ─────────────────────────────────────────────────────

    def _collect_filters(self) -> SearchFilters:
        domains = [d for d, cb in self._domain_checks.items() if cb.isChecked()]

        # Comma = term separator; spaces within a term = multi-word phrase
        keywords = [k.strip() for k in self._keywords_input.text().split(",") if k.strip()]

        # Topics are single-word GitHub topic slugs, comma or space separated
        raw_topics = self._topics_input.text().replace(",", " ").split()
        topics = [t.strip().lower() for t in raw_topics if t.strip()]

        lang_text = self._language_combo.currentText()
        language = None if lang_text == "Any" else lang_text

        activity_label = self._activity_combo.currentText()
        pushed_after = ACTIVITY_OPTIONS.get(activity_label)

        sort_label = self._sort_combo.currentText()
        sort_map = {
            "Relevance": "best-match",
            "Stars": "stars",
            "Forks": "forks",
            "Recently updated": "updated",
        }
        sort = sort_map.get(sort_label, "stars")

        return SearchFilters(
            keywords=keywords,
            domains=domains,
            min_stars=STAR_OPTIONS.get(self._min_stars_combo.currentText(), 0),
            min_forks=FORK_OPTIONS.get(self._min_forks_combo.currentText(), 0),
            language=language,
            topics=topics,
            pushed_after=pushed_after,
            sort=sort,
        )

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_provider_changed(self, label: str) -> None:
        provider = PROVIDER_BY_LABEL.get(label)
        if not provider:
            return
        self._analyzer.set_provider(provider)
        self._update_provider_status(provider)
        log.info("AI provider changed  provider=%s", label)

    def _update_provider_status(self, provider) -> None:
        from app.models.settings import settings
        if not provider.env_key:
            self._provider_status.setText("Local — no key required")
            self._provider_status.setStyleSheet("font-size: 10px; color: #238636;")
        elif settings.get_key_for_env_var(provider.env_key):
            self._provider_status.setText(f"Key set ({provider.env_key})")
            self._provider_status.setStyleSheet("font-size: 10px; color: #238636;")
        else:
            self._provider_status.setText(f"No key — add {provider.env_key} to .env")
            self._provider_status.setStyleSheet("font-size: 10px; color: #cf222e;")

    def _on_search(self) -> None:
        filters = self._collect_filters()
        query = filters.build_query()

        if not query.strip():
            self._status.showMessage("Please select at least one domain or enter a keyword.")
            return

        log.info("Search triggered  query=%r", query)
        self._query_label.setText(f"Query: {query}")
        self._search_btn.setEnabled(False)
        self._load_more_btn.setEnabled(False)
        self._detail_view.clear()
        self._clear_analysis_tabs()
        self._analyze_btn.setEnabled(False)
        self._table.setRowCount(0)
        self._repos = []
        self._current_filters = filters
        self._current_page = 1
        self._total_count = 0
        self._detail_tabs.setCurrentIndex(0)
        self._status.showMessage("Searching GitHub…")
        self._kw_delegate.set_keywords(filters.keywords + filters.topics)

        self._worker = SearchWorker(filters, self._github, page=1)
        self._worker.results_ready.connect(self._on_results)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.start()

    def _on_results(self, result) -> None:
        self._total_count = result.total_count
        new_repos = result.items
        start_row = len(self._repos)
        self._repos.extend(new_repos)

        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(self._repos))

        for offset, repo in enumerate(new_repos):
            row = start_row + offset
            pushed = repo.pushed_at.strftime("%Y-%m-%d") if repo.pushed_at else ""
            license_name = repo.license.name if repo.license else ""
            cols = [
                repo.full_name,
                repo.owner.login,
                repo.language or "",
                f"{repo.stargazers_count:,}",
                f"{repo.forks_count:,}",
                str(repo.open_issues_count),
                pushed,
                license_name,
                repo.owner.type or "",
            ]
            for col, text in enumerate(cols):
                item = QTableWidgetItem(text)
                if col in (3, 4, 5):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if col == 0:
                    item.setForeground(QColor("#0969da"))
                    item.setToolTip(f"Double-click to open {repo.html_url}")
                    item.setData(Qt.UserRole, repo.html_url)
                self._table.setItem(row, col, item)

        self._table.setSortingEnabled(True)

        shown = len(self._repos)
        total = self._total_count
        # GitHub caps search results at 1000
        can_load_more = shown < total and shown < 1000 and len(new_repos) > 0
        self._load_more_btn.setEnabled(can_load_more)
        self._results_label.setText(
            f"Showing {shown:,} of {total:,}"
            + (" (GitHub cap: 1,000)" if total > 1000 else "")
        )
        self._status.showMessage(
            f"{total:,} repositories found — showing {shown:,}"
            + (" — Load more available" if can_load_more else "")
        )
        self._search_btn.setEnabled(True)

    def _on_load_more(self) -> None:
        if not self._current_filters:
            return
        self._current_page += 1
        self._load_more_btn.setEnabled(False)
        self._status.showMessage(f"Loading page {self._current_page}…")
        log.info("Load more triggered  page=%d", self._current_page)
        self._worker = SearchWorker(self._current_filters, self._github, page=self._current_page)
        self._worker.results_ready.connect(self._on_results)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.start()

    def _on_cell_double_clicked(self, row: int, col: int) -> None:
        if col != 0:
            return
        item = self._table.item(row, col)
        url = item.data(Qt.UserRole) if item else None
        if url:
            log.info("Opening browser  url=%s", url)
            QDesktopServices.openUrl(QUrl(url))

    def _on_row_selected(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            self._analyze_btn.setEnabled(False)
            return
        repo = self._repos[rows[0].row()]
        log.info("Row selected  repo=%s", repo.full_name)
        self._analyze_btn.setEnabled(True)
        self._clear_analysis_tabs()
        self._current_readme = ""
        self._detail_tabs.setCurrentIndex(0)
        self._show_repo_detail(repo)

        # Cancel any in-flight README fetch and start a new one
        if self._readme_worker and self._readme_worker.isRunning():
            self._readme_worker.terminate()
        self._readme_worker = ReadmeWorker(repo, self._github)
        self._readme_worker.readme_ready.connect(self._on_readme_ready)
        self._readme_worker.start()

    def _show_repo_detail(self, repo: GitHubRepo) -> None:
        topics = ", ".join(repo.topics) if repo.topics else "none"
        license_name = repo.license.name if repo.license else "unknown"
        pushed = repo.pushed_at.strftime("%Y-%m-%d %H:%M UTC") if repo.pushed_at else "unknown"
        created = repo.created_at.strftime("%Y-%m-%d") if repo.created_at else "unknown"

        text = (
            f"  {repo.full_name}\n"
            f"{'─' * 64}\n"
            f"Description : {repo.description or '—'}\n"
            f"Language    : {repo.language or 'unknown'}\n"
            f"Stars       : {repo.stargazers_count:,}\n"
            f"Forks       : {repo.forks_count:,}\n"
            f"Open issues : {repo.open_issues_count:,}\n"
            f"Topics      : {topics}\n"
            f"License     : {license_name}\n"
            f"Branch      : {repo.default_branch}\n"
            f"Created     : {created}\n"
            f"Last push   : {pushed}\n"
            f"URL         : {repo.html_url}\n"
            f"\n  Fetching README…\n"
        )
        self._detail_view.setPlainText(text)

    def _on_readme_ready(self, readme_text: str) -> None:
        self._current_readme = readme_text
        current = self._detail_view.toPlainText()
        current = current.replace("\n  Fetching README…\n", "")
        if readme_text:
            current += f"\n{'─' * 64}\nREADME — Overview\n{'─' * 64}\n{readme_text}\n"
        self._detail_view.setPlainText(current)

    def _on_analyze(self) -> None:
        if not self._analyzer.has_key():
            provider = self._analyzer.provider
            env_key = provider.env_key
            self._add_analysis_tab(
                provider.label,
                f"No API key configured for {provider.label}.\n\n"
                f"Add it to your .env file:\n"
                f"  {env_key}=your_key_here\n\n"
                f"Then restart the application.",
            )
            self._status.showMessage(f"Missing {env_key} — see AI Analysis tab")
            log.warning("Analyze requested but key not set  provider=%s", provider.label)
            return

        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return
        repo = self._repos[rows[0].row()]
        self._analyze_btn.setEnabled(False)
        self._status.showMessage("Asking Claude for analysis…")
        self._worker = AnalyzeWorker(repo, self._analyzer, self._current_readme)
        self._worker.analysis_ready.connect(self._on_analysis_done)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.start()

    def _on_analysis_done(self, analysis) -> None:
        def score_bar(score: float) -> str:
            filled = round(score)
            return "█" * filled + "░" * (10 - filled) + f"  {score:.1f}/10"

        def reasons(detail) -> str:
            return "\n".join(f"    • {r}" for r in detail.reasons) or "    —"

        text = (
            f"  {analysis.repo_full_name}\n"
            f"{'─' * 64}\n\n"
            f"Summary\n{'─' * 32}\n  {analysis.summary}\n\n"
            f"Target audience\n{'─' * 32}\n  {analysis.target_audience}\n\n"
            f"{'─' * 64}\n"
            f"SCORES\n"
            f"{'─' * 64}\n\n"
            f"Relevance    {score_bar(analysis.relevance_score.score)}\n"
            f"{reasons(analysis.relevance_score)}\n\n"
            f"Health       {score_bar(analysis.health_score.score)}\n"
            f"{reasons(analysis.health_score)}\n\n"
            f"Contribution {score_bar(analysis.contribution_score.score)}\n"
            f"{reasons(analysis.contribution_score)}\n\n"
            f"{'─' * 64}\n"
            f"FINAL SCORE  {score_bar(analysis.final_score)}\n\n"
            f"Verdict\n{'─' * 32}\n  {analysis.verdict or '—'}\n"
        )
        self._add_analysis_tab(self._analyzer.provider.label, text)
        self._analyze_btn.setEnabled(True)
        self._status.showMessage(f"Analysis complete — final score {analysis.final_score:.1f}/10")

    def _on_error(self, msg: str) -> None:
        self._status.showMessage(f"Error: {msg}")
        self._search_btn.setEnabled(True)
        self._analyze_btn.setEnabled(True)
        self._detail_view.setPlainText(f"Error:\n{msg}")
