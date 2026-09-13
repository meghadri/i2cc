from functools import partial

from PySide6.QtWidgets import QMenu, QMenuBar, QMessageBox, QWidget
from pytide6 import Menu

from i2cc import __version__
from i2cc.app import App
from i2cc.dongles.dongle_selector_dialog import select_dongle
from i2cc.find_actions_dialog import FindActionDialog
from i2cc.project.projects_gui import (
    DeleteProjectDialog,
    DownloadProjectDialog,
    NewProjectDialog,
    OpenProjectDialog,
    RenameProjectDialog,
    SaveAsProjectDialog,
)


class FileMenu(QMenu):
    def __init__(self, parent: QMenuBar, app: App):
        super().__init__("&File", parent)

        def show_settings_window():
            pass

        def delete_project():
            if app.project.name == "default":
                app.show_error(f"Project [{app.project.name}] cannot be deleted.")
                app.update_project_selector_current_project(app.project.name)
            else:
                DeleteProjectDialog(app, app.project.name).exec()

        self.addAction("&New Project", lambda: NewProjectDialog(app).exec())
        self.addAction("&Save Project As", lambda: SaveAsProjectDialog(app).exec())
        self.addAction("&Rename Project", lambda: RenameProjectDialog(app).exec())
        self.addAction("&Open Project", lambda: OpenProjectDialog(app).exec())
        self.addAction("&Delete Project", delete_project)
        self.addSeparator()
        self.addAction("E&xport Project to File", app.export_project)
        self.addAction("&Import Project from File", app.import_project)
        self.addSeparator()
        self.addAction("Do&wnload Official Project", lambda: DownloadProjectDialog(app).exec())
        self.addAction("Download Project from &URL", None)
        self.addSeparator()
        self.addAction("S&ettings", show_settings_window)
        self.addSeparator()
        self.addAction("&Quit", lambda: app.exit_application[0]())


class DongleMenu(QMenu):
    def __init__(self, parent: QMenuBar, app: App):
        super().__init__("&Dongle", parent)
        self.addAction("&Connect", partial(select_dongle, app))
        self.addAction("&Reset Dongle")


class MainMenuBar(QMenuBar):
    def __init__(self, app: App, dialogs_parent: QWidget) -> None:
        super().__init__(dialogs_parent)
        self.addMenu(FileMenu(self, app))
        self.addMenu(DongleMenu(self, app))
        self.addMenu(
            Menu(
                "&Help",
                parent=self,
                actions=[
                    (
                        "Find Action... Ctrl+Shift+A",
                        lambda: FindActionDialog(app).exec(),
                    ),
                    (
                        "&About",
                        lambda: QMessageBox.about(
                            self,
                            "About",
                            f"<html><H2>I2C Commander</H2><H4>Version: {__version__}</H4>"
                            '<p style="font-size:14px;">"While there is life there is hope. I beg to assert...that '
                            "as long as a man's heart beats, as long as a man's flesh quivers, I do not allow that "
                            'a being gifted with thought and will can allow himself to despair."</br>'
                            "&nbsp;&nbsp;&nbsp;&nbsp;- <em>Jules Verne, Journey to the Center of the Earth</em></html>",
                        ),
                    ),
                ],
            )
        )
