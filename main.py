import sys
from pathlib import Path
from dotenv import load_dotenv
from PyQt5.QtWidgets import QApplication

load_dotenv(Path(__file__).parent / ".env")

from app.utils.logger import setup_logging, get_logger
from app.api.github_client import GitHubClient
from app.llm.analyzer import RepoAnalyzer
from app.ui.main_window import MainWindow

setup_logging()
log = get_logger("main")


def main() -> None:
    log.info("Starting GitHub Repo Scout")
    app = QApplication(sys.argv)
    app.setApplicationName("GitHub Repo Scout")

    with GitHubClient() as github:
        analyzer = RepoAnalyzer()
        log.info("GitHubClient and RepoAnalyzer initialized")
        window = MainWindow(github, analyzer)
        window.show()
        log.info("Main window shown — entering event loop")
        sys.exit(app.exec_())


if __name__ == "__main__":
    main()
