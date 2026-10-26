from typing import Union, Optional
from pathlib import Path
import markdown

from PyQt6.QtCore import Qt, QUrl

from PyQt6.QtWidgets import QVBoxLayout, QDialog
from PyQt6.QtWebEngineWidgets import QWebEngineView


class HelpDialog(QDialog):
    """Dialog for displaying help information."""

    def __init__(
        self,
        markdown_file: Union[str, Path],
        base_url: Union[Path, str, None] = None,
        parent: Optional[object] = None
    ):
        super(HelpDialog, self).__init__(parent)

        self.setWindowTitle("Help")
        self.setMinimumSize(800, 600)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint |
            Qt.WindowType.MSWindowsFixedSizeDialogHint)

        markdown_file = Path(markdown_file)

        with open(markdown_file, "r", encoding="utf-8") as f:
            markdown_text = f.read()

        # Markdown to HTML
        html_body = markdown.markdown(
            markdown_text,
            extensions=["extra", "toc", "tables", "fenced_code"]
        )

        # Wrap into an HTML page
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 20px;
                    background-color: #ffffff;
                }}
                img {{
                    max-width: 90%;
                    height: auto;
                    display: block;
                    margin-left: auto;
                    margin-right: auto;
                }}
                code {{
                    background: #f0f0f0;
                    padding: 2px 4px;
                    border-radius: 4px;
                }}
                pre {{
                    background: #f0f0f0;
                    padding: 10px;
                    overflow-x: auto;
                }}
            </style>
        </head>
        <body>
            {html_body}
        </body>
        </html>
        """

        self.web_view = QWebEngineView()
        self.web_view.setContextMenuPolicy(
            Qt.ContextMenuPolicy.NoContextMenu)  # Disable right-click
        if not base_url:
            base_url = QUrl.fromLocalFile(str(markdown_file.parent))
        else:
            base_url = QUrl.fromLocalFile(str(base_url))
        self.web_view.setHtml(
            html, baseUrl=base_url)

        layout = QVBoxLayout()
        layout.addWidget(self.web_view)
        self.setLayout(layout)
